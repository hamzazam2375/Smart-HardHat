"""Schema tests for migration 0001 (F26-113 Table 4.35 data dictionary, Table 4.36 rules)."""
import uuid

import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from tests.conftest import insert, rejects

EXPECTED_TABLES = {
    "account", "worker", "device", "gateway", "configuration", "calibration",
    "model_version", "recommendation", "assignment", "telemetry",
    "device_status_snapshot", "event", "alert_action", "risk_assessment", "audit_log",
}


def telemetry(db, base, seq=1, **extra):
    cols = dict(device_id=base["d1"], gateway_id=base["gateway"], boot_epoch=7,
                packet_seq=seq, time_quality="trusted", config_id=base["config"],
                co_valid_count=60, expected_count=60, motion_flags=0, validity_flags=0)
    cols.update(extra)
    return insert(db, "telemetry", **cols)


def event(db, base, **extra):
    cols = dict(source_event_key=f"{uuid.uuid4()}", device_id=base["d1"],
                event_type="sos", time_quality="trusted", evidence=Jsonb({"co_ppm": None}))
    cols.update(extra)
    return insert(db, "event", **cols)


# --- migration state --------------------------------------------------------
def test_migration_at_head_and_all_tables_exist(db):
    assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0001"
    rows = db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()
    assert EXPECTED_TABLES <= {r[0] for r in rows}


# --- account ----------------------------------------------------------------
def test_account_email_must_be_normalized_and_unique(db, base):
    rejects(db, errors.CheckViolation, "INSERT INTO account(email,display_name,password_hash,role)"
            " VALUES ('Upper@x.com','A','h','admin')")
    email = db.execute("SELECT email FROM account WHERE account_id=%s", [base["account"]]).fetchone()[0]
    rejects(db, errors.UniqueViolation, "INSERT INTO account(email,display_name,password_hash,role)"
            " VALUES (%s,'A','h','admin')", [email])


def test_account_role_restricted_and_defaults(db, base):
    rejects(db, errors.CheckViolation, "INSERT INTO account(email,display_name,password_hash,role)"
            " VALUES ('r@x.com','A','h','root')")
    enabled, sv = db.execute("SELECT enabled, session_version FROM account WHERE account_id=%s",
                             [base["account"]]).fetchone()
    assert enabled is True and sv == 0


# --- device / gateway -------------------------------------------------------
def test_device_radio_id_positive_and_unique(db, base):
    sql = ("INSERT INTO device(radio_id,label,hardware_revision,firmware_version,key_slot_reference)"
           " VALUES (%s,%s,'A','0.1','k')")
    rejects(db, errors.CheckViolation, sql, [0, "X-1"])
    rejects(db, errors.UniqueViolation, sql, [900001, "X-2"])
    rejects(db, errors.CheckViolation, "UPDATE device SET state='lost' WHERE device_id=%s", [base["d1"]])


def test_gateway_counters_non_negative(db, base):
    rejects(db, errors.CheckViolation, "UPDATE gateway SET loss_count=-1 WHERE gateway_id=%s", [base["gateway"]])


# --- assignment (one active per device and per worker, no overlaps) ---------
def _assign(db, base, worker, device, start, end=None):
    return insert(db, "assignment", worker_id=base[worker], device_id=base[device],
                  start_at=start, end_at=end, created_by=base["account"],
                  ended_by=base["account"] if end else None)


def test_one_open_assignment_per_device_and_worker(db, base):
    _assign(db, base, "w1", "d1", "2026-01-01T08:00Z")
    rejects(db, errors.IntegrityError, "INSERT INTO assignment(worker_id,device_id,start_at,created_by)"
            " VALUES (%s,%s,'2026-01-02T08:00Z',%s)", [base["w2"], base["d1"], base["account"]])
    rejects(db, errors.IntegrityError, "INSERT INTO assignment(worker_id,device_id,start_at,created_by)"
            " VALUES (%s,%s,'2026-01-02T08:00Z',%s)", [base["w1"], base["d2"], base["account"]])


def test_assignment_closed_intervals_cannot_overlap_but_can_touch(db, base):
    _assign(db, base, "w1", "d1", "2026-01-01T08:00Z", "2026-01-01T16:00Z")
    # end is exclusive, so the next shift may start exactly at 16:00
    _assign(db, base, "w2", "d1", "2026-01-01T16:00Z", "2026-01-01T20:00Z")
    rejects(db, errors.ExclusionViolation,
            "INSERT INTO assignment(worker_id,device_id,start_at,end_at,created_by,ended_by)"
            " VALUES (%s,%s,'2026-01-01T15:00Z','2026-01-01T17:00Z',%s,%s)",
            [base["w1"], base["d1"], base["account"], base["account"]])


def test_assignment_end_after_start_and_ended_by_required(db, base):
    rejects(db, errors.CheckViolation,
            "INSERT INTO assignment(worker_id,device_id,start_at,end_at,created_by,ended_by)"
            " VALUES (%s,%s,'2026-01-01T08:00Z','2026-01-01T08:00Z',%s,%s)",
            [base["w1"], base["d1"], base["account"], base["account"]])
    rejects(db, errors.CheckViolation,
            "INSERT INTO assignment(worker_id,device_id,start_at,end_at,created_by)"
            " VALUES (%s,%s,'2026-01-01T08:00Z','2026-01-01T09:00Z',%s)",
            [base["w1"], base["d1"], base["account"]])


# --- telemetry --------------------------------------------------------------
def test_telemetry_duplicate_packet_rejected(db, base):
    telemetry(db, base, seq=1)
    rejects(db, errors.UniqueViolation,
            "INSERT INTO telemetry(device_id,gateway_id,boot_epoch,packet_seq,time_quality,config_id,"
            "co_valid_count,expected_count,motion_flags,validity_flags)"
            " VALUES (%s,%s,7,1,'trusted',%s,60,60,0,0)",
            [base["d1"], base["gateway"], base["config"]])


def test_telemetry_missing_readings_stay_null_not_zero(db, base):
    tid = telemetry(db, base, time_quality="unknown")
    row = db.execute("SELECT co_latest, temperature_c, battery_pct, latitude, window_start"
                     " FROM telemetry WHERE telemetry_id=%s", [tid]).fetchone()
    assert row == (None, None, None, None, None)


@pytest.mark.parametrize("bad", [
    {"humidity_pct": 101},
    {"battery_pct": -1},
    {"inactivity_ms": 60001},
    {"latitude": 31.5},                                  # latitude without longitude
    {"window_start": "2026-01-01T08:00Z"},               # window without end
    {"co_valid_count": 61},                              # more valid than expected
    {"time_quality": "good"},
])
def test_telemetry_invalid_values_rejected(db, base, bad):
    with pytest.raises(errors.CheckViolation):
        with db.transaction():
            telemetry(db, base, seq=99, **bad)


# --- event / alert_action ---------------------------------------------------
def test_event_source_key_unique_and_type_restricted(db, base):
    eid = event(db, base, source_event_key="d1:7:1")
    rejects(db, errors.UniqueViolation,
            "INSERT INTO event(source_event_key,device_id,event_type,time_quality,evidence)"
            " VALUES ('d1:7:1',%s,'sos','trusted','{}')", [base["d1"]])
    rejects(db, errors.CheckViolation,
            "INSERT INTO event(source_event_key,device_id,event_type,time_quality,evidence)"
            " VALUES ('d1:7:2',%s,'earthquake','trusted','{}')", [base["d1"]])
    states = db.execute("SELECT workflow_state, local_state, row_version FROM event WHERE event_id=%s",
                        [eid]).fetchone()
    assert states == ("open", "unknown", 0)


def test_alert_action_append_only_and_resolve_needs_note(db, base):
    eid = event(db, base)
    aid = insert(db, "alert_action", event_id=eid, actor_id=base["account"], action_type="acknowledge")
    rejects(db, errors.RaiseException, "UPDATE alert_action SET note='x' WHERE action_id=%s", [aid])
    rejects(db, errors.CheckViolation, "INSERT INTO alert_action(event_id,actor_id,action_type)"
            " VALUES (%s,%s,'resolve')", [eid, base["account"]])
    insert(db, "alert_action", event_id=eid, actor_id=base["account"],
           action_type="resolve", note="Worker checked, no injury")


def test_retention_delete_cascades_event_actions(db, base):
    eid = event(db, base)
    insert(db, "alert_action", event_id=eid, actor_id=base["account"], action_type="acknowledge")
    db.execute("DELETE FROM event WHERE event_id=%s", [eid])
    assert db.execute("SELECT count(*) FROM alert_action WHERE event_id=%s", [eid]).fetchone()[0] == 0


# --- risk_assessment / model_version ----------------------------------------
def _model(db, state="candidate"):
    return insert(db, "model_version", artifact_reference="ml/artifacts/t.joblib", checksum="c",
                  feature_schema_version="1", training_provenance=Jsonb({}),
                  validation_envelope=Jsonb({}), evaluation_reference="e", state=state)


def test_risk_unavailable_needs_reason_and_no_level(db, base):
    tid = telemetry(db, base)
    insert(db, "risk_assessment", telemetry_id=tid, status="unavailable", reason_code="no_active_model")
    sql = "INSERT INTO risk_assessment(telemetry_id,status,predicted_level,reason_code) VALUES (%s,%s,%s,%s)"
    rejects(db, errors.CheckViolation, sql, [tid, "unavailable", None, None])          # no reason
    rejects(db, errors.CheckViolation, sql, [tid, "unavailable", "low", "model_error"])  # level when unavailable


def test_risk_available_needs_model_and_level(db, base):
    tid = telemetry(db, base)
    mid = _model(db)
    insert(db, "risk_assessment", telemetry_id=tid, model_id=mid, status="available",
           predicted_level="moderate", effective_level="critical")
    rejects(db, errors.CheckViolation, "INSERT INTO risk_assessment(telemetry_id,status,predicted_level)"
            " VALUES (%s,'available','low')", [tid])


def test_only_one_active_model(db, base):
    db.execute("UPDATE model_version SET state='retired' WHERE state='active'")
    _model(db, "active")
    with pytest.raises(errors.UniqueViolation):
        with db.transaction():
            _model(db, "active")


# --- configuration ----------------------------------------------------------
def test_configuration_activation_requires_review(db, base):
    db.execute("UPDATE configuration SET state='retired' WHERE state='active'")
    rejects(db, errors.CheckViolation, "UPDATE configuration SET state='active' WHERE config_id=%s",
            [base["config"]])
    db.execute("UPDATE configuration SET state='active', review_reason='Bench reviewed',"
               " reviewer=%s, activated_at=now() WHERE config_id=%s", [base["account"], base["config"]])


# --- audit_log --------------------------------------------------------------
def test_audit_log_append_only_and_system_actor_allowed(db, base):
    aid = insert(db, "audit_log", action="retention.run")   # scheduled job: no actor, no resource
    rejects(db, errors.RaiseException, "UPDATE audit_log SET action='x' WHERE audit_id=%s", [aid])
