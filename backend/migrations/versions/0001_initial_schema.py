"""Initial schema: all entities from F26-113 section 4.9 (Table 4.35 data dictionary,
Table 4.36 integrity rules).

Conventions
- UUID keys (gen_random_uuid), UTC timestamptz everywhere.
- Sensor values are NULLABLE with no defaults: missing/invalid data is never stored
  as 0 or "safe" (validity_flags / time_quality carry the state).
- Allowed value sets are text + CHECK (easier to extend than PG enums).
- alert_action and audit_log are append-only (UPDATE blocked by trigger). DELETE is
  allowed only so the 30-day retention job can remove identifiable data.

Revision ID: 0001
Revises:
Create Date: 2026-11-15
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
CREATE EXTENSION IF NOT EXISTS btree_gist;   -- needed for assignment overlap exclusion

-- Shared trigger functions ---------------------------------------------------
CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;

CREATE FUNCTION forbid_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only; updates are not allowed', TG_TABLE_NAME;
END $$;

-- 1. account (FR auth: individual accounts, no self-registration) -----------
CREATE TABLE account (
    account_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email            text NOT NULL UNIQUE
                     CHECK (email = lower(btrim(email)) AND email LIKE '%_@_%'),
    display_name     text NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 100),
    password_hash    text NOT NULL,                        -- Argon2id encoded hash only
    role             text NOT NULL
                     CHECK (role IN ('supervisor', 'admin', 'admin_supervisor')),
    enabled          boolean NOT NULL DEFAULT true,
    session_version  integer NOT NULL DEFAULT 0 CHECK (session_version >= 0),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER account_set_updated_at BEFORE UPDATE ON account
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 2. worker (no medical or home-address fields) -----------------------------
CREATE TABLE worker (
    worker_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_code   text NOT NULL UNIQUE CHECK (length(btrim(worker_code)) BETWEEN 1 AND 32),
    display_name  text NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 100),
    active        boolean NOT NULL DEFAULT true,
    created_by    uuid NOT NULL REFERENCES account(account_id),
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- 3. device (hardhat) -------------------------------------------------------
CREATE TABLE device (
    device_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    radio_id            integer NOT NULL UNIQUE CHECK (radio_id > 0),
    label               text NOT NULL UNIQUE CHECK (length(btrim(label)) BETWEEN 1 AND 32),
    hardware_revision   text NOT NULL,
    firmware_version    text NOT NULL,
    key_slot_reference  text NOT NULL,      -- reference to managed key material, never the key
    state               text NOT NULL DEFAULT 'registered'
                        CHECK (state IN ('registered', 'disabled', 'retired')),
    last_seen_at        timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- 4. gateway ----------------------------------------------------------------
CREATE TABLE gateway (
    gateway_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    gateway_code          text NOT NULL UNIQUE CHECK (length(btrim(gateway_code)) BETWEEN 1 AND 32),
    credential_reference  text NOT NULL,    -- reference to secret/cert, never the secret
    enabled               boolean NOT NULL DEFAULT true,
    last_seen_at          timestamptz,
    firmware_version      text NOT NULL,
    queue_depth           integer NOT NULL DEFAULT 0 CHECK (queue_depth >= 0),
    loss_count            bigint  NOT NULL DEFAULT 0 CHECK (loss_count >= 0),
    created_at            timestamptz NOT NULL DEFAULT now()
);

-- 5. configuration (thresholds/timings; reviewed before activation) ---------
CREATE TABLE configuration (
    config_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    config_version  text NOT NULL UNIQUE,
    checksum        text NOT NULL,
    thresholds      jsonb NOT NULL CHECK (jsonb_typeof(thresholds) = 'object'),
    timings         jsonb NOT NULL CHECK (jsonb_typeof(timings) = 'object'),
    state           text NOT NULL DEFAULT 'draft'
                    CHECK (state IN ('draft', 'active', 'retired')),
    review_reason   text,
    reviewer        uuid REFERENCES account(account_id),
    activated_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT configuration_review_required_for_activation CHECK (
        state = 'draft'
        OR (review_reason IS NOT NULL AND reviewer IS NOT NULL AND activated_at IS NOT NULL)
    )
);
CREATE UNIQUE INDEX configuration_one_active ON configuration ((true)) WHERE state = 'active';

-- 6. calibration ------------------------------------------------------------
CREATE TABLE calibration (
    calibration_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sensor_serial   text NOT NULL,
    procedure       text NOT NULL,
    checked_at      timestamptz NOT NULL,
    due_at          timestamptz CHECK (due_at IS NULL OR due_at > checked_at),
    result          text NOT NULL CHECK (result IN ('pass', 'fail', 'limited')),
    reference_id    text NOT NULL,          -- reference instrument or supplier record
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- 7. model_version ----------------------------------------------------------
CREATE TABLE model_version (
    model_id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_reference      text NOT NULL,
    checksum                text NOT NULL,
    feature_schema_version  text NOT NULL,
    training_provenance     jsonb NOT NULL CHECK (jsonb_typeof(training_provenance) = 'object'),
    validation_envelope     jsonb NOT NULL CHECK (jsonb_typeof(validation_envelope) = 'object'),
    evaluation_reference    text NOT NULL,
    state                   text NOT NULL DEFAULT 'candidate'
                            CHECK (state IN ('candidate', 'active', 'retired')),
    created_at              timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX model_version_one_active ON model_version ((true)) WHERE state = 'active';

-- 8. recommendation (reviewed action library; no free-form generated advice) -
CREATE TABLE recommendation (
    recommendation_id  uuid NOT NULL DEFAULT gen_random_uuid(),
    version            text NOT NULL,
    factor_code        text NOT NULL,
    event_type         text NOT NULL,
    message            text NOT NULL CHECK (length(btrim(message)) BETWEEN 1 AND 300),
    review_status      text NOT NULL DEFAULT 'draft'
                       CHECK (review_status IN ('draft', 'approved', 'retired')),
    created_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (recommendation_id, version)
);
CREATE INDEX recommendation_lookup ON recommendation (factor_code, event_type, review_status);

-- 9. assignment (dated worker/device intervals; end is exclusive) -----------
CREATE TABLE assignment (
    assignment_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_id      uuid NOT NULL REFERENCES worker(worker_id),
    device_id      uuid NOT NULL REFERENCES device(device_id),
    start_at       timestamptz NOT NULL,
    end_at         timestamptz,
    created_by     uuid NOT NULL REFERENCES account(account_id),
    ended_by       uuid REFERENCES account(account_id),
    reason         text CHECK (reason IS NULL OR length(reason) <= 200),
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT assignment_end_after_start CHECK (end_at IS NULL OR end_at > start_at),
    CONSTRAINT assignment_ended_by_matches_end CHECK ((end_at IS NULL) = (ended_by IS NULL)),
    -- No overlapping intervals per device or per worker (also covers concurrent races)
    CONSTRAINT assignment_no_device_overlap EXCLUDE USING gist
        (device_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&),
    CONSTRAINT assignment_no_worker_overlap EXCLUDE USING gist
        (worker_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&)
);
-- At most one open assignment per device and per worker (Table 4.36)
CREATE UNIQUE INDEX assignment_one_open_per_device ON assignment (device_id) WHERE end_at IS NULL;
CREATE UNIQUE INDEX assignment_one_open_per_worker ON assignment (worker_id) WHERE end_at IS NULL;

-- 10. telemetry (one accepted 60 s status packet) ---------------------------
CREATE TABLE telemetry (
    telemetry_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id               uuid NOT NULL REFERENCES device(device_id),
    gateway_id              uuid NOT NULL REFERENCES gateway(gateway_id),
    boot_epoch              bigint NOT NULL CHECK (boot_epoch >= 0),
    packet_seq              bigint NOT NULL CHECK (packet_seq >= 0),
    window_start            timestamptz,
    window_end              timestamptz,
    received_at             timestamptz NOT NULL DEFAULT now(),
    time_quality            text NOT NULL CHECK (time_quality IN ('trusted', 'estimated', 'unknown')),
    assignment_id           uuid REFERENCES assignment(assignment_id),
    config_id               uuid NOT NULL REFERENCES configuration(config_id),
    calibration_id          uuid REFERENCES calibration(calibration_id),
    -- CO (valid samples only, ppm)
    co_latest               numeric(7,2) CHECK (co_latest >= 0),
    co_mean                 numeric(7,2) CHECK (co_mean >= 0),
    co_max                  numeric(7,2) CHECK (co_max >= 0),
    co_valid_count          integer NOT NULL CHECK (co_valid_count >= 0),
    expected_count          integer NOT NULL CHECK (expected_count >= 0),
    -- Environment
    temperature_c           numeric(5,2) CHECK (temperature_c BETWEEN -40 AND 85),
    humidity_pct            numeric(5,2) CHECK (humidity_pct BETWEEN 0 AND 100),
    heat_index_c            numeric(5,2),        -- derived (NWS), never body temperature
    -- Motion
    accel_peak_g            numeric(6,3) CHECK (accel_peak_g >= 0),
    orientation_change_deg  numeric(5,2) CHECK (orientation_change_deg BETWEEN 0 AND 180),
    inactivity_ms           integer CHECK (inactivity_ms BETWEEN 0 AND 60000),
    motion_flags            integer NOT NULL CHECK (motion_flags >= 0),
    -- Battery
    battery_pct             numeric(5,2) CHECK (battery_pct BETWEEN 0 AND 100),
    battery_is_estimate     boolean,
    -- GPS (outdoor fix only)
    latitude                numeric(9,6) CHECK (latitude BETWEEN -90 AND 90),
    longitude               numeric(9,6) CHECK (longitude BETWEEN -180 AND 180),
    gps_fix_age_s           integer CHECK (gps_fix_age_s >= 0),
    validity_flags          integer NOT NULL CHECK (validity_flags >= 0),
    CONSTRAINT telemetry_packet_identity UNIQUE (device_id, boot_epoch, packet_seq),
    CONSTRAINT telemetry_window_pair CHECK (
        (window_start IS NULL AND window_end IS NULL)
        OR (window_start IS NOT NULL AND window_end IS NOT NULL AND window_end > window_start)
    ),
    CONSTRAINT telemetry_location_pair CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CONSTRAINT telemetry_co_counts CHECK (co_valid_count <= expected_count)
);
CREATE INDEX telemetry_device_time     ON telemetry (device_id, received_at DESC);
CREATE INDEX telemetry_assignment_time ON telemetry (assignment_id, received_at DESC);
CREATE INDEX telemetry_received_at     ON telemetry (received_at);   -- retention cutoff

-- 11. device_status_snapshot (current status per device; Table 4.36 rule) ---
-- Updated only when the accepted source ordering is newer and time quality is
-- suitable, so delayed backlog cannot replace current status.
CREATE TABLE device_status_snapshot (
    device_id     uuid PRIMARY KEY REFERENCES device(device_id),
    telemetry_id  uuid NOT NULL REFERENCES telemetry(telemetry_id) ON DELETE CASCADE,
    boot_epoch    bigint NOT NULL,
    packet_seq    bigint NOT NULL,
    time_quality  text NOT NULL CHECK (time_quality IN ('trusted', 'estimated', 'unknown')),
    received_at   timestamptz NOT NULL,
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER device_status_snapshot_set_updated_at BEFORE UPDATE ON device_status_snapshot
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 12. event (urgent events and recorded warning transitions) ----------------
CREATE TABLE event (
    event_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_event_key  text NOT NULL UNIQUE,   -- device + boot + source counter; stable across retries
    device_id         uuid NOT NULL REFERENCES device(device_id),
    assignment_id     uuid REFERENCES assignment(assignment_id),
    event_type        text NOT NULL CHECK (event_type IN
                      ('sos', 'possible_fall', 'co', 'heat', 'battery', 'fault', 'cancellation')),
    detected_at       timestamptz,
    received_at       timestamptz NOT NULL DEFAULT now(),
    time_quality      text NOT NULL CHECK (time_quality IN ('trusted', 'estimated', 'unknown')),
    evidence          jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    -- Supervisor response state is separate from the helmet's local hazard state
    workflow_state    text NOT NULL DEFAULT 'open'
                      CHECK (workflow_state IN ('open', 'acknowledged', 'resolved')),
    local_state       text NOT NULL DEFAULT 'unknown'
                      CHECK (local_state IN ('active', 'physically_acknowledged', 'cleared', 'unknown')),
    row_version       integer NOT NULL DEFAULT 0 CHECK (row_version >= 0)
);
CREATE INDEX event_device_time     ON event (device_id, received_at DESC);
CREATE INDEX event_assignment_time ON event (assignment_id, received_at DESC);
CREATE INDEX event_type_state_time ON event (event_type, workflow_state, received_at DESC);
CREATE INDEX event_received_at     ON event (received_at);           -- retention cutoff

-- 13. alert_action (append-only supervisor responses) -----------------------
CREATE TABLE alert_action (
    action_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id     uuid NOT NULL REFERENCES event(event_id) ON DELETE CASCADE,
    actor_id     uuid NOT NULL REFERENCES account(account_id),
    action_type  text NOT NULL CHECK (action_type IN ('acknowledge', 'note', 'resolve')),
    note         text CHECK (note IS NULL OR length(note) <= 1000),
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT alert_action_note_required CHECK (
        action_type = 'acknowledge' OR (note IS NOT NULL AND length(btrim(note)) > 0)
    )
);
CREATE INDEX alert_action_event_time ON alert_action (event_id, created_at);
CREATE TRIGGER alert_action_append_only BEFORE UPDATE ON alert_action
    FOR EACH ROW EXECUTE FUNCTION forbid_update();

-- 14. risk_assessment (advisory only; never overwritten) --------------------
CREATE TABLE risk_assessment (
    assessment_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    telemetry_id            uuid NOT NULL REFERENCES telemetry(telemetry_id) ON DELETE CASCADE,
    model_id                uuid REFERENCES model_version(model_id),
    status                  text NOT NULL CHECK (status IN ('available', 'unavailable', 'failed')),
    predicted_level         text CHECK (predicted_level IN ('low', 'moderate', 'high', 'critical')),
    effective_level         text CHECK (effective_level IN ('low', 'moderate', 'high', 'critical')),
    factors                 jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(factors) = 'array'),
    reason_code             text CHECK (reason_code IN
                            ('missing_input', 'unsupported_range', 'model_error', 'no_active_model')),
    recommendation_version  text,
    created_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT risk_level_only_when_available
        CHECK ((status = 'available') = (predicted_level IS NOT NULL)),
    CONSTRAINT risk_available_needs_model
        CHECK (status <> 'available' OR model_id IS NOT NULL),
    CONSTRAINT risk_unavailable_needs_reason
        CHECK (status = 'available' OR reason_code IS NOT NULL)
);
CREATE INDEX risk_assessment_telemetry_time ON risk_assessment (telemetry_id, created_at DESC);

-- 15. audit_log (append-only; no secrets in safe_metadata) ------------------
CREATE TABLE audit_log (
    audit_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id       uuid REFERENCES account(account_id),   -- null for scheduled system actions
    resource_type  text,
    resource_id    uuid,                                  -- null for system-wide actions
    action         text NOT NULL,
    occurred_at    timestamptz NOT NULL DEFAULT now(),
    safe_metadata  jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(safe_metadata) = 'object')
);
CREATE INDEX audit_log_occurred_at ON audit_log (occurred_at);
CREATE INDEX audit_log_resource    ON audit_log (resource_type, resource_id);
CREATE TRIGGER audit_log_append_only BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION forbid_update();
"""

DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS audit_log, risk_assessment, alert_action, event,
    device_status_snapshot, telemetry, assignment, recommendation, model_version,
    calibration, configuration, gateway, device, worker, account;
DROP FUNCTION IF EXISTS forbid_update();
DROP FUNCTION IF EXISTS set_updated_at();
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
