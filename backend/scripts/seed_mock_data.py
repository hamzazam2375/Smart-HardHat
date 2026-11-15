"""Seed the dev PostgreSQL database with interconnected MOCK data.

Never changes the schema. Every row is clearly mock:
  accounts  *@mock.smarthardhat.test, "(mock)" names     workers   MOCK-W-###
  devices   MOCK-HAT-##, radio_id 71001+                 gateways  MOCK-GW-##
  configs   mock-cfg-*        calibrations MOCK-*        models    ml/artifacts/mock/*
  recs      version mock-r*   events  source_event_key mock:*, evidence.mock = true
  notes/reasons start with "[MOCK]"; audit_log.safe_metadata.mock = true

Safe to rerun:
  * Every primary key is a deterministic UUIDv5 and every INSERT is ON CONFLICT DO NOTHING.
  * The time anchor of the first run is stored in a marker audit_log row and reused, so a
    rerun regenerates byte-identical rows and inserts nothing new.
  * --reset deletes all mock rows and reseeds relative to "now" (fresh timestamps for demos).
  * --delete removes all mock rows only.

Run from backend/ with the DB up and migrated:
  .venv\\Scripts\\python -m scripts.seed_mock_data [--reset | --delete]

Scenarios (relative to the anchor T, "now" at first seed):
  Volume is kept small (~1.3k telemetry rows): the current shift has full 60 s data,
  past shifts keep only short excerpts around each scenario.

  Current shift (T-2h .. T)
    MOCK-HAT-01 / W-001  normal; fall pre-alert cancelled by worker (resolved)
    MOCK-HAT-02 / W-002  CO warning -> CO urgent 236 ppm (resolved); new CO warning OPEN
    MOCK-HAT-03 / W-003  possible fall 12 min ago, ACKNOWLEDGED, physically acknowledged
    MOCK-HAT-04 / W-004  reboot (estimated time), low battery OPEN, STALE (last data T-6 min)
    MOCK-HAT-05 / W-005  SOS (resolved), IMU fault OPEN, OFFLINE since T-1h30m
    MOCK-HAT-06          spare on charger, reporting with no assignment
    MOCK-HAT-07          disabled (CO cell failed bump test)    MOCK-HAT-08 retired (dropped)
    MOCK-HAT-09          registered yesterday, never seen (last_seen_at NULL)
  Past 5 day shifts: heat warning, accidental SOS, slip/possible fall, brief CO urgent,
  gateway outage backlog, critical battery, brownout reboot with unknown time quality,
  invalid temperature/humidity channel, model outage / no active model, early-ended shift.
  Workers W-009 and W-010 are inactive; W-006..W-008 are active but off shift.

Flag bits below are a MOCK convention: F26-113 Table 5.1 requires "defined bits only" but
does not number them. Align with the firmware when the packet format is frozen.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.types.json import Jsonb

from app.db_url import database_url

SEED_VERSION = 1
NS = uuid.UUID("6f1c2a8e-5b3d-4c7a-9e21-0d4b8f6a3c11")       # fixed namespace for mock ids
EMAIL_DOMAIN = "mock.smarthardhat.test"
MARKER_ID = uuid.uuid5(NS, "seed-marker")
SITE = (31.469700, 74.272800)                                # mock site, Lahore
UTC = timezone.utc
PKT = 5                                                      # site local offset, hours


# validity_flags (per-channel quality)
V_CO_INVALID, V_CO_PARTIAL, V_ENV_INVALID, V_HEAT_UNSUPPORTED = 1, 2, 4, 8
V_IMU_INVALID, V_BATTERY_UNAVAILABLE, V_GPS_NO_FIX = 16, 32, 64
# motion_flags (event-state bits)
M_IMPACT, M_PREALERT, M_CANCELLED, M_POSSIBLE_FALL, M_SOS = 1, 2, 4, 8, 16

LEVELS = ["low", "moderate", "high", "critical"]


# ---------------------------------------------------------------- helpers ---
def mid(*parts) -> uuid.UUID:
    return uuid.uuid5(NS, "/".join(map(str, parts)))


def n(*parts) -> float:
    """Deterministic pseudo-random number in [0, 1) from any key."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def u(lo: float, hi: float, *parts) -> float:
    return lo + (hi - lo) * n(*parts)


def sec(s: float) -> timedelta:
    return timedelta(seconds=s)


def mins(m: float) -> timedelta:
    return timedelta(minutes=m)


def hrs(h: float) -> timedelta:
    return timedelta(hours=h)


def overlap(a0, a1, b0, b1) -> bool:
    return a0 < b1 and b0 < a1


def interp(points, x):
    """Piecewise-linear value of [(x, y), ...] at x; None outside the range."""
    if x < points[0][0] or x > points[-1][0]:
        return None
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def crossing(points, level, rising=True):
    """Seconds offset where the piecewise curve first crosses `level`."""
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if (rising and y0 < level <= y1) or (not rising and y0 > level >= y1):
            return x0 + (x1 - x0) * (level - y0) / (y1 - y0)
    raise ValueError(f"curve never crosses {level}")


def heat_index_c(t_c, rh):
    """NWS heat index (Rothfusz + adjustments). Mock supported domain 20-50 C."""
    if t_c is None or rh is None or not 20 <= t_c <= 50:
        return None
    t = t_c * 9 / 5 + 32
    hi = 0.5 * (t + 61 + (t - 68) * 1.2 + rh * 0.094)
    if (hi + t) / 2 >= 80:
        hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh
              - 0.00683783 * t * t - 0.05481717 * rh * rh + 0.00122874 * t * t * rh
              + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
        if rh < 13 and 80 <= t <= 112:
            hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t - 95)) / 17)
        elif rh > 85 and 80 <= t <= 87:
            hi += ((rh - 85) / 10) * ((87 - t) / 5)
    return round((hi - 32) * 5 / 9, 2)


# ----------------------------------------------------------- static data ---
ACCOUNTS = {  # key: (local part, display name, role, enabled, session_version)
    "usman": ("usman.tariq", "Usman Tariq (mock)", "admin", True, 0),
    "sana": ("sana.iqbal", "Sana Iqbal (mock)", "supervisor", True, 1),
    "kamran": ("kamran.akhtar", "Kamran Akhtar (mock)", "admin_supervisor", True, 0),
    "fatima": ("fatima.noor", "Fatima Noor (mock)", "supervisor", False, 3),
}
WORKERS = {  # no: (name, active)
    1: ("Ali Raza", True), 2: ("Bilal Hussain", True), 3: ("Imran Khan", True),
    4: ("Nadeem Abbas", True), 5: ("Shahid Mehmood", True), 6: ("Asif Javed", True),
    7: ("Tariq Mahmood", True), 8: ("Zubair Ahmed", True), 9: ("Rashid Ali", False),
    10: ("Waqas Anjum", False),
}


@dataclass(frozen=True)
class Dev:
    idx: int
    hw: str
    fw: str
    state: str
    co_base: float      # ambient CO ppm
    temp_off: float     # local microclimate offset, C
    hum_off: float
    indoor: float       # share of 10-min blocks without a GPS fix
    zone: tuple         # work-zone offset from SITE (deg)
    drain: float        # battery %/h

    @property
    def id(self):
        return mid("device", self.idx)

    @property
    def label(self):
        return f"MOCK-HAT-{self.idx:02d}"

    @property
    def battery_estimate(self):  # HH-A2 has no fuel gauge -> voltage-curve estimate
        return self.hw == "HH-A2"


DEVS = {d.idx: d for d in [
    Dev(1, "HH-B1", "0.4.1", "registered", 2.5, 0.0, 0, 0.10, (0.0004, -0.0003), 6.2),
    Dev(2, "HH-B1", "0.4.1", "registered", 4.0, 1.0, 10, 0.75, (-0.0002, 0.0005), 6.6),
    Dev(3, "HH-B1", "0.4.1", "registered", 2.0, 0.5, 0, 0.05, (0.0006, 0.0002), 6.4),
    Dev(4, "HH-B1", "0.4.0", "registered", 3.0, 0.0, 0, 0.35, (-0.0005, -0.0004), 7.1),
    Dev(5, "HH-A2", "0.4.0", "registered", 2.8, 0.0, 0, 0.15, (0.0001, 0.0007), 6.9),
    Dev(6, "HH-A2", "0.4.1", "registered", 1.5, -1.0, 5, 0.60, (0.0, 0.0), 6.5),
    Dev(7, "HH-A2", "0.3.7", "disabled", 3.5, 0.0, 0, 0.30, (0.0003, -0.0006), 7.4),
    Dev(8, "HH-A2", "0.3.7", "retired", 2.2, 0.0, 0, 0.20, (-0.0007, 0.0001), 7.0),
    Dev(9, "HH-B1", "0.4.1", "registered", 2.0, 0.0, 0, 0.20, (0.0, 0.0), 6.5),
]}

GW1, GW2 = mid("gateway", 1), mid("gateway", 2)
CFG = {v: mid("configuration", v) for v in ("mock-cfg-0.9", "mock-cfg-1.0", "mock-cfg-1.1")}
MODEL = {v: mid("model", v) for v in ("v0", "v1", "v2")}
REC_VERSION = "mock-r1"

THRESHOLDS = {
    "co_warning_ppm": 35, "co_urgent_ppm": 200, "co_reset_ppm": 180,
    "heat_index_warning_c": 32, "battery_low_pct": 20, "battery_critical_pct": 10,
    "fall_impact_g": 3.0, "fall_orientation_change_deg": 45, "fall_inactivity_ms": 10000,
}
TIMINGS = {
    "summary_period_s": 60, "stale_after_s": 180, "co_reset_hold_s": 30,
    "fall_prealert_s": 15, "fall_rearm_stable_s": 10, "sos_hold_ms": 2000,
    "motion_hz": 50, "co_hz": 1, "temp_humidity_s": 5, "battery_s": 30,
}


def acc(key):
    return mid("account", key)


def wkr(no):
    return mid("worker", no)


# ---------------------------------------------------------- the dataset ----
@dataclass
class Sess:
    dev: int
    boot_time: datetime
    first_ws: datetime
    last_we: datetime
    assignment: uuid.UUID | None
    gateway: uuid.UUID
    bat0: float
    bat_t0: datetime
    bat_rate: float                      # %/h, negative while charging
    brk: tuple | None = None             # (start, end) rest break: indoor, still
    tq_unknown: int = 0                  # first N packets: RTC lost, no window
    tq_estimated: int = 0                # next N packets: time estimated
    backlog: tuple | None = None         # (from, to, delivered_at) gateway uplink outage
    charging: bool = False
    excerpt: bool = False                # past shift: keep only short excerpts (see telemetry())
    boot: int = 0


class Seed:
    def __init__(self, T: datetime, cfg_active: bool, model_active: bool):
        self.T = T
        self.cfg_active, self.model_active = cfg_active, model_active
        self.t: dict[str, list[dict]] = {k: [] for k in (
            "account", "worker", "device", "gateway", "configuration", "calibration",
            "model_version", "recommendation", "assignment", "telemetry",
            "device_status_snapshot", "event", "alert_action", "risk_assessment", "audit_log")}
        self.sessions: list[Sess] = []
        self.assignments: list[tuple] = []          # (device, start, end, id)
        self.co_eps = {i: [] for i in DEVS}         # (t0, points)
        self.heat_eps = {i: [] for i in DEVS}       # (t0, t1, +C)
        self.env_bad = {i: [] for i in DEVS}        # (t0, t1)
        self.imu_bad = {i: [] for i in DEVS}
        self.co_bad = {i: [] for i in DEVS}
        self.indoor_force = {i: [] for i in DEVS}
        self.motion = {i: [] for i in DEVS}
        self.event_specs: list[dict] = []
        self.model_down: list[tuple] = []           # (t0, t1, reason)

    # --- time helpers
    def day(self, d):           # 00:00 UTC, d days before the anchor date
        return datetime(self.T.year, self.T.month, self.T.day, tzinfo=UTC) - timedelta(days=d)

    def shift(self, d):         # 08:00 PKT = 03:00 UTC
        return self.day(d) + hrs(3)

    def audit(self, key, action, at, actor=None, rtype=None, rid=None, **meta):
        self.t["audit_log"].append(dict(
            audit_id=mid("audit", key), actor_id=acc(actor) if actor else None,
            resource_type=rtype, resource_id=rid, action=action, occurred_at=at,
            safe_metadata={"mock": True, **meta}))

    # ------------------------------------------------------------ build ---
    def build(self):
        self.reference_data()
        self.roster()
        self.scenarios()
        self.telemetry()
        self.events()
        self.snapshots_and_last_seen()
        self.risk()
        return self.t

    def reference_data(self):
        T = self.T
        for key, (local, name, role, enabled, sv) in ACCOUNTS.items():
            self.t["account"].append(dict(
                account_id=acc(key), email=f"{local}@{EMAIL_DOMAIN}", display_name=name,
                password_hash=password_hash(), role=role, enabled=enabled, session_version=sv,
                created_at=self.day(29) + hrs(5), updated_at=self.day(2 if not enabled else 29) + hrs(6)))
            self.audit(f"account-create-{key}", "account.create", self.day(29) + hrs(5), "usman",
                       "account", acc(key), role=role)
        self.audit("account-disable-fatima", "account.disable", self.day(2) + hrs(6), "usman",
                   "account", acc("fatima"), reason="left project (mock)")

        for no, (name, active) in WORKERS.items():
            created = self.day(28 if no != 10 else 20) + hrs(4)
            self.t["worker"].append(dict(
                worker_id=wkr(no), worker_code=f"MOCK-W-{no:03d}", display_name=f"{name} (mock)",
                active=active, created_by=acc("kamran"), created_at=created))
            self.audit(f"worker-create-{no}", "worker.create", created, "kamran", "worker", wkr(no))
        self.audit("worker-deactivate-9", "worker.deactivate", self.day(3) + hrs(12), "kamran",
                   "worker", wkr(9), reason="contract ended (mock)")
        self.audit("worker-deactivate-10", "worker.deactivate", self.day(15) + hrs(5), "kamran",
                   "worker", wkr(10), reason="did not join site (mock)")

        for d in DEVS.values():
            created = self.day({6: 6, 9: 1}.get(d.idx, 25)) + hrs(5)
            self.t["device"].append(dict(
                device_id=d.id, radio_id=71000 + d.idx, label=d.label, hardware_revision=d.hw,
                firmware_version=d.fw, key_slot_reference=f"mock-keyslot-{d.idx:02d}",
                state=d.state, last_seen_at=None, created_at=created))
            self.audit(f"device-register-{d.idx}", "device.register", created, "usman", "device", d.id,
                       radio_id=71000 + d.idx)
        self.audit("device-disable-7", "device.disable", self.shift(3) + hrs(9), "usman", "device",
                   DEVS[7].id, reason="CO cell failed bump test (mock)")
        self.audit("device-retire-8", "device.retire", self.shift(5) + hrs(7), "usman", "device",
                   DEVS[8].id, reason="shell cracked after drop (mock)")

        self.t["gateway"] += [
            dict(gateway_id=GW1, gateway_code="MOCK-GW-01", credential_reference="mock-cred-gw-01",
                 enabled=True, last_seen_at=T - sec(20), firmware_version="0.2.3", queue_depth=2,
                 loss_count=4, created_at=self.day(26) + hrs(5)),
            dict(gateway_id=GW2, gateway_code="MOCK-GW-02", credential_reference="mock-cred-gw-02",
                 enabled=False, last_seen_at=self.shift(3) + hrs(8) + mins(3), firmware_version="0.2.1",
                 queue_depth=0, loss_count=17, created_at=self.day(26) + hrs(5)),
        ]
        for g, gid in ((1, GW1), (2, GW2)):
            self.audit(f"gateway-register-{g}", "gateway.register", self.day(26) + hrs(5), "usman",
                       "gateway", gid)
        self.audit("gateway-disable-2", "gateway.disable", self.day(2) + hrs(4), "usman", "gateway", GW2,
                   reason="backup unit returned to store (mock)")

        def cfg(version, state, created, activated, reviewer, reason, thresholds, timings):
            body = json.dumps({"thresholds": thresholds, "timings": timings}, sort_keys=True)
            self.t["configuration"].append(dict(
                config_id=CFG[version], config_version=version,
                checksum="sha256:" + hashlib.sha256(body.encode()).hexdigest(),
                thresholds=thresholds, timings=timings, state=state, review_reason=reason,
                reviewer=acc(reviewer) if reviewer else None, activated_at=activated,
                created_at=created))
        old_t = dict(THRESHOLDS, fall_impact_g=3.5)
        cfg("mock-cfg-0.9", "retired", self.day(29), self.day(27) + hrs(6), "kamran",
            "[MOCK] Bench review of initial thresholds", old_t, TIMINGS)
        cfg("mock-cfg-1.0", "active" if self.cfg_active else "retired", self.day(12), self.day(10) + hrs(5),
            "kamran", "[MOCK] Lower impact threshold after drop-rig trials", THRESHOLDS, TIMINGS)
        cfg("mock-cfg-1.1", "draft", self.day(1) + hrs(9), None, None, None,
            dict(THRESHOLDS, co_warning_ppm=30), TIMINGS)
        self.audit("cfg-activate-0.9", "configuration.activate", self.day(27) + hrs(6), "kamran",
                   "configuration", CFG["mock-cfg-0.9"])
        self.audit("cfg-activate-1.0", "configuration.activate", self.day(10) + hrs(5), "kamran",
                   "configuration", CFG["mock-cfg-1.0"], replaces="mock-cfg-0.9")
        self.audit("cfg-draft-1.1", "configuration.create", self.day(1) + hrs(9), "kamran",
                   "configuration", CFG["mock-cfg-1.1"])

        # Calibration: CO bump test per device; HAT-06 / HAT-09 not yet checked.
        self.calib = {}
        for d in DEVS.values():
            if d.idx in (6, 9):
                continue
            cid = mid("calibration", d.idx, "initial")
            checked = self.day(14) + hrs(6) + mins(10 * d.idx)
            result = "limited" if d.idx == 5 else "pass"
            self.t["calibration"].append(dict(
                calibration_id=cid, sensor_serial=f"MOCK-CO-SN-{2600 + d.idx}",
                procedure="[MOCK] Bump test, 100 ppm CO span gas, 2 min exposure",
                checked_at=checked, due_at=checked + timedelta(days=90), result=result,
                reference_id="MOCK-REF-SPANGAS-LOT-2611", created_at=checked + mins(5)))
            self.calib[d.idx] = [(checked, cid)]
        fail_at = self.shift(3) + hrs(8) + mins(30)
        fail_id = mid("calibration", 7, "recheck")
        self.t["calibration"].append(dict(
            calibration_id=fail_id, sensor_serial="MOCK-CO-SN-2607",
            procedure="[MOCK] Re-check after self-test fault, 100 ppm span gas",
            checked_at=fail_at, due_at=None, result="fail",
            reference_id="MOCK-REF-SPANGAS-LOT-2611", created_at=fail_at + mins(5)))
        self.calib[7].append((fail_at, fail_id))

        env = {"co_ppm": [0, 150], "temperature_c": [0, 50], "humidity_pct": [5, 95],
               "accel_peak_g": [0, 16], "required_valid": ["co", "temperature", "imu"],
               "min_leaf_support": 12}
        for v, state, created, sessions in (("v0", "retired", self.day(28), 31),
                                            ("v1", "active", self.day(12), 48),
                                            ("v2", "candidate", self.day(1), 63)):
            if state == "active" and not self.model_active:
                state = "retired"
            self.t["model_version"].append(dict(
                model_id=MODEL[v], artifact_reference=f"ml/artifacts/mock/risk_tree_{v}.joblib",
                checksum="sha256:" + hashlib.sha256(f"mock-model-{v}".encode()).hexdigest(),
                feature_schema_version="mock-fs-1", validation_envelope=env,
                training_provenance={"mock": True, "sessions": sessions, "simulated_fraction": 0.35,
                                     "sources": {"bench_rig": sessions // 3, "wear_trials": sessions - sessions // 3},
                                     "split": "grouped by session"},
                evaluation_reference=f"evaluation/mock/model_{v}_holdout.json", state=state,
                created_at=created))
        self.model_v1_active_at = self.shift(5) + mins(20)
        self.audit("model-retire-v0", "model.retire", self.shift(5), "kamran", "model_version",
                   MODEL["v0"], reason="drift review (mock)")
        self.audit("model-activate-v1", "model.activate", self.model_v1_active_at, "kamran",
                   "model_version", MODEL["v1"])

        recs = [
            ("co_warning", "co", "Move away from the area when able and follow the site CO procedure. A later low reading does not authorize re-entry."),
            ("co_urgent", "co", "CO emergency. Start the site CO response procedure and move the worker to fresh air. Do not re-enter until the area is cleared."),
            ("sos_active", "sos", "Help requested. Start the assigned site response procedure and contact the worker."),
            ("possible_fall", "possible_fall", "Possible fall. Check on the worker promptly. The sensors cannot confirm injury."),
            ("heat_index_high", "heat", "Follow the site heat procedure: rest break and a cooler area. This is an environmental estimate."),
            ("battery_low", "battery", "Charge or replace the hardhat battery."),
            ("sensor_fault", "fault", "Inspect the hardhat sensor. A missing value is not a zero reading."),
            ("stale_status", "status", "Status is stale. Check the worker and the radio path; readings shown are old."),
            ("model_input_unsupported", "assessment", "Review available measurements and fixed alerts; model input is outside its supported range."),
            ("unrecognized", "any", "Review this alert against the site procedure."),
        ]
        for code, etype, msg in recs:
            self.t["recommendation"].append(dict(
                recommendation_id=mid("rec", code), version=REC_VERSION, factor_code=code,
                event_type=etype, message=f"[MOCK] {msg}", review_status="approved",
                created_at=self.day(12)))
        self.t["recommendation"] += [
            dict(recommendation_id=mid("rec", "co_warning"), version="mock-r0", factor_code="co_warning",
                 event_type="co", message="[MOCK] CO detected. Leave the area.", review_status="retired",
                 created_at=self.day(28)),
            dict(recommendation_id=mid("rec", "heat_index_high"), version="mock-r2",
                 factor_code="heat_index_high", event_type="heat",
                 message="[MOCK] Heat index high. Take a rest break in shade and drink water per site procedure.",
                 review_status="draft", created_at=self.day(1) + hrs(10)),
        ]

    # --- assignments + sessions
    def assign(self, key, w, d, start, end, created_by="sana", ended_by="sana", reason=None):
        aid = mid("assignment", key)
        self.t["assignment"].append(dict(
            assignment_id=aid, worker_id=wkr(w), device_id=DEVS[d].id, start_at=start, end_at=end,
            created_by=acc(created_by), ended_by=acc(ended_by) if end else None, reason=reason,
            created_at=start))
        self.assignments.append((d, start, end, aid))
        self.audit(f"assign-create-{key}", "assignment.create", start, created_by, "assignment", aid)
        if end:
            self.audit(f"assign-end-{key}", "assignment.end", end, ended_by, "assignment", aid)
        return aid

    def roster(self):
        T = self.T
        roster = {
            5: [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (7, 6), (9, 7), (8, 8)],
            4: [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (7, 6), (9, 7)],
            3: [(1, 1), (2, 3), (3, 2), (4, 4), (5, 5), (6, 6), (8, 7)],
            2: [(1, 1), (2, 2), (3, 3), (4, 4), (6, 6), (7, 5)],
            1: [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6)],
        }
        for d, pairs in roster.items():
            S = self.shift(d)
            sup = "fatima" if d >= 4 else ("sana" if d % 2 else "kamran")
            gw = GW2 if d == 3 else GW1
            backlog = (S + hrs(2), S + hrs(2) + mins(20), S + hrs(2) + mins(21)) if d == 2 else None
            for w, dv in pairs:
                end, reason, last = S + hrs(8), None, S + hrs(8) - mins(2)
                if (d, dv) == (2, 5):
                    end, last = S + hrs(4) + mins(30), S + hrs(4) + mins(28)
                    reason = "[MOCK] Hardhat battery critical; worker moved to site office duties"
                if (d, dv) == (5, 8):
                    end, last = S + hrs(5) + mins(45), S + hrs(5) + mins(40)
                    reason = "[MOCK] Hardhat damaged after drop; withdrawn from service"
                aid = self.assign(f"d{d}-w{w}-hat{dv}", w, dv, S, end, sup, sup, reason)
                dev = DEVS[dv]
                bat0 = u(91, 100, "bat0", d, dv)
                rate = dev.drain
                if (d, dv) == (2, 5):
                    bat0, rate = 36.0, 6.0          # not charged overnight
                boot = S + mins(3)
                brk = (S + hrs(4), S + hrs(4) + mins(30))
                if (d, dv) == (4, 7):               # brownout reboot at S+3h
                    self.sessions.append(Sess(dv, boot, boot, S + hrs(3), aid, gw, bat0, boot, rate, brk,
                                              backlog=backlog, excerpt=True))
                    b2 = S + hrs(3) + sec(30)
                    self.sessions.append(Sess(dv, b2, b2, last, aid, gw, bat0, boot, rate, brk,
                                              tq_unknown=4, tq_estimated=3, backlog=backlog, excerpt=True))
                else:
                    self.sessions.append(Sess(dv, boot, boot, last, aid, gw, bat0, boot, rate, brk,
                                              backlog=backlog, excerpt=True))

        # Current shift (last 2 h, full 60 s telemetry)
        C0, A0 = T - hrs(2), T - hrs(2) - mins(5)
        brk = None
        cur = {}
        for w, dv in ((1, 1), (2, 2), (3, 3), (4, 4), (5, 5)):
            cur[dv] = self.assign(f"current-w{w}-hat{dv}", w, dv, A0, None, "kamran")
        for dv in (1, 2, 3):
            self.sessions.append(Sess(dv, C0, C0, T, cur[dv], GW1, u(93, 100, "bat0c", dv), C0,
                                      DEVS[dv].drain, brk))
        # HAT-04: not charged overnight, rebooted at C0+1h (time estimated after), stale at T-6m
        self.sessions.append(Sess(4, C0, C0, C0 + hrs(1) - mins(1), cur[4], GW1, 34.0, C0, 8.2, brk))
        r = C0 + hrs(1) + mins(1)
        self.sessions.append(Sess(4, r, r, T - mins(6), cur[4], GW1, 34.0, C0, 8.2, brk, tq_estimated=6))
        # HAT-05: offline since C0+30m (T-1h30m)
        self.sessions.append(Sess(5, C0, C0, C0 + mins(30), cur[5], GW1, 97.0, C0, 6.9, brk))
        # HAT-06: spare on the charging rack, reporting without an assignment
        self.sessions.append(Sess(6, T - mins(45), T - mins(45), T, None, GW1, 38.0, T - mins(45),
                                  -42.0, None, charging=True))
        self.indoor_force[6].append((T - mins(45), T + mins(1)))

        # boot_epoch: per-device monotonic counter in boot order
        for dv in DEVS:
            ss = sorted((s for s in self.sessions if s.dev == dv), key=lambda s: s.boot_time)
            for i, s in enumerate(ss):
                s.boot = 101 + i

    def assignment_at(self, dv, t):
        for d, s, e, aid in self.assignments:
            if d == dv and s <= t and (e is None or t < e):
                return aid
        return None

    # --- scenario episodes and events
    def ev(self, key, dv, etype, at, local, actions=(), tq="trusted", recv_delay=None, **evidence):
        self.event_specs.append(dict(key=key, dev=dv, type=etype, at=at, local=local, tq=tq,
                                     actions=list(actions), recv_delay=recv_delay, extra=evidence))

    def fall(self, dv, tf, alarm, local_ack, move, accel, orient):
        self.motion[dv].append(("fall", tf, alarm, local_ack, move, accel, orient))

    def scenarios(self):
        T, C0 = self.T, self.T - hrs(2)

        # HAT-01 current: fall pre-alert cancelled by the worker (normal operation)
        tc = C0 + mins(37) + sec(12)
        self.motion[1].append(("cancel", tc))
        self.ev("cur-hat1-cancel", 1, "cancellation", tc + sec(15), "cleared",
                [("acknowledge", 50, "kamran", None),
                 ("resolve", 360, "kamran", "[MOCK] Worker cancelled the pre-alert; tripped on rebar and carried on working.")],
                cancelled="fall_prealert", impact_g=3.9, prealert_elapsed_s=11)

        # HAT-02 current: CO warning -> urgent -> cleared, then a new warning still open
        t0 = T - mins(100)
        pts = [(0, 9), (120, 28), (200, 41), (300, 95), (400, 210), (470, 236), (560, 190),
               (620, 150), (700, 60), (900, 12)]
        self.co_eps[2].append((t0, pts))
        self.indoor_force[2].append((t0 - mins(20), t0 + mins(30)))
        w_at = t0 + sec(math.ceil(crossing(pts, 35)))
        u_at = t0 + sec(math.ceil(crossing(pts, 200)))
        self.ev("cur-hat2-co-warning", 2, "co", w_at, "cleared",
                [("acknowledge", 55, "sana", None),
                 ("resolve", 2400, "sana", "[MOCK] Superseded by the CO urgent event at the same location; handled there.")],
                level="warning", threshold_ppm=35)
        self.ev("cur-hat2-co-urgent", 2, "co", u_at, "cleared",
                [("acknowledge", 40, "kamran", None),
                 ("note", 240, "sana", "[MOCK] Worker evacuated basement level B2. Portable generator exhaust suspected."),
                 ("resolve", 2280, "kamran", "[MOCK] Generator moved outside; area ventilated and re-checked with a handheld meter before re-entry.")],
                level="urgent", threshold_ppm=200, peak_ppm=236, reset_after_s=30, reset_below_ppm=180)
        t1 = T - mins(22)
        pts2 = [(0, 8), (240, 31), (360, 38), (600, 41), (900, 37), (1500, 38)]
        self.co_eps[2].append((t1, pts2))
        self.indoor_force[2].append((t1, T + mins(1)))
        self.ev("cur-hat2-co-warning-2", 2, "co", t1 + sec(math.ceil(crossing(pts2, 35))), "active",
                level="warning", threshold_ppm=35)

        # HAT-03 current: possible fall, acknowledged, not yet resolved
        tf = T - mins(12) + sec(5)
        self.fall(3, tf, tf + sec(20), T - mins(7), T - mins(5), 6.8, 82)
        self.ev("cur-hat3-fall", 3, "possible_fall", tf + sec(20), "physically_acknowledged",
                [("acknowledge", 75, "kamran", None),
                 ("note", 330, "sana", "[MOCK] Reached worker at scaffold bay C; worker responsive. Supervisor staying with the worker.")],
                impact_g=6.8, orientation_change_deg=82, inactivity_ms=15000, prealert_s=15, cancelled=False)

        # HAT-04 current: low battery (open) shortly before it went stale
        low_at = C0 + hrs((34.0 - 20) / 8.2)
        self.ev("cur-hat4-battery-low", 4, "battery", low_at, "active", level="low", threshold_pct=20)

        # HAT-05 current: SOS (resolved), then IMU fault (open), then offline
        ts = C0 + mins(10) + sec(14)
        self.motion[5].append(("sos", ts, ts + mins(8)))
        self.ev("cur-hat5-sos", 5, "sos", ts + sec(2), "cleared",
                [("acknowledge", 35, "sana", None),
                 ("note", 180, "kamran", "[MOCK] Worker's sleeve caught on a rebar cage; crew on the way."),
                 ("resolve", 1320, "sana", "[MOCK] Worker freed by crew; no further assistance needed. Resumed work.")],
                hold_ms=2350)
        fault_t = C0 + mins(27)
        self.imu_bad[5].append((fault_t, T))
        self.ev("cur-hat5-imu-fault", 5, "fault", fault_t + sec(30), "active",
                fault_code="imu_i2c_timeout", channel="imu")

        # d1: heat warning on HAT-01 (bitumen kettle area); accidental SOS on HAT-03
        S = self.shift(1)
        self.heat_eps[1].append((S + hrs(5), S + hrs(6) + mins(30), 9.0))
        self.heat_spec = ("d1-hat1-heat", 1, S + hrs(5), S + hrs(6) + mins(30))
        ts = S + hrs(2) + mins(14) + sec(40)
        self.motion[3].append(("sos", ts, ts + sec(40)))
        self.ev("d1-hat3-sos", 3, "sos", ts + sec(2), "cleared",
                [("acknowledge", 20, "kamran", None),
                 ("resolve", 240, "kamran", "[MOCK] Accidental activation while adjusting the chin strap; confirmed by radio call.")],
                hold_ms=2100)

        # d2: slip on HAT-02, battery critical on HAT-05 (W-007), uplink outage backlog
        S = self.shift(2)
        tf = S + hrs(3) + mins(5) + sec(10)
        self.fall(2, tf, tf + sec(20), tf + mins(3), tf + mins(4), 4.6, 71)
        self.ev("d2-hat2-fall", 2, "possible_fall", tf + sec(20), "cleared",
                [("acknowledge", 50, "kamran", None),
                 ("note", 300, "kamran", "[MOCK] Worker slipped on the wet ramp and sat down; checked per site procedure."),
                 ("resolve", 900, "kamran", "[MOCK] Worker returned to work. Ramp cordoned off and sanded.")],
                impact_g=4.6, orientation_change_deg=71, inactivity_ms=12000, prealert_s=15, cancelled=False)
        b_low = S + mins(3) + hrs((36 - 20) / 6.0)
        b_crit = S + mins(3) + hrs((36 - 10) / 6.0)
        self.ev("d2-hat5-battery-low", 5, "battery", b_low, "cleared",
                [("acknowledge", 120, "kamran", None),
                 ("resolve", int((b_crit - b_low).total_seconds()) + 300, "kamran",
                  "[MOCK] Superseded by the critical battery event.")],
                level="low", threshold_pct=20)
        self.ev("d2-hat5-battery-critical", 5, "battery", b_crit, "cleared",
                [("acknowledge", 60, "kamran", None),
                 ("resolve", 300, "kamran", "[MOCK] Hardhat returned for charging; worker reassigned to the site office.")],
                level="critical", threshold_pct=10)

        # d3: CO self-test fault on HAT-07 -> CO invalid, failed bump test, disabled.
        #     DHT22 read failures on HAT-04. Model service error for 15 min.
        S = self.shift(3)
        self.co_bad[7].append((S + hrs(6), S + hrs(9)))
        self.ev("d3-hat7-co-fault", 7, "fault", S + hrs(6) + sec(4), "active",
                [("acknowledge", 90, "sana", None),
                 ("note", 900, "sana", "[MOCK] CO channel reporting invalid; worker told to use a handheld meter."),
                 ("resolve", 9600, "usman", "[MOCK] CO cell failed the bump test; hardhat withdrawn and disabled pending a replacement cell.")],
                fault_code="co_self_test_fail", channel="co")
        self.env_bad[4].append((S + hrs(2) + mins(10), S + hrs(2) + mins(22)))
        self.ev("d3-hat4-env-fault", 4, "fault", S + hrs(2) + mins(10) + sec(6), "cleared",
                [("acknowledge", 140, "sana", None),
                 ("resolve", 1500, "sana", "[MOCK] Temperature/humidity sensor recovered after reseating the cable.")],
                fault_code="dht_read_timeout", channel="temperature_humidity")
        self.model_down.append((S + hrs(1), S + hrs(1) + mins(8), "model_error"))

        # d4: brief CO urgent on HAT-04 (cutting saw in stairwell); brownout on HAT-07
        S = self.shift(4)
        t0 = S + hrs(6) + mins(10)
        pts = [(0, 5), (60, 60), (120, 212), (170, 205), (220, 120), (300, 15)]
        self.co_eps[4].append((t0, pts))
        self.indoor_force[4].append((t0 - mins(10), t0 + mins(10)))
        self.ev("d4-hat4-co-warning", 4, "co", t0 + sec(math.ceil(crossing(pts, 35))), "cleared",
                [("acknowledge", 70, "fatima", None),
                 ("resolve", 1500, "fatima", "[MOCK] Superseded by the CO urgent event.")],
                level="warning", threshold_ppm=35)
        self.ev("d4-hat4-co-urgent", 4, "co", t0 + sec(math.ceil(crossing(pts, 200))), "cleared",
                [("acknowledge", 30, "fatima", None),
                 ("resolve", 1440, "fatima", "[MOCK] Petrol cut-off saw used in the stairwell. Moved outdoors; stairwell ventilated.")],
                level="urgent", threshold_ppm=200, peak_ppm=212, reset_after_s=30, reset_below_ppm=180)
        self.ev("d4-hat7-brownout", 7, "fault", None, "cleared",
                [("acknowledge", 300, "fatima", None),
                 ("resolve", 1200, "fatima", "[MOCK] Loose battery connector reseated; time sync restored.")],
                tq="unknown", recv_delay=S + hrs(3) + mins(2) + sec(7), fault_code="power_brownout_reset",
                channel="power")

        # d5: HAT-08 dropped from scaffold (not worn) -> retired; no active model for 20 min
        S = self.shift(5)
        tf = S + hrs(5) + mins(20) + sec(33)
        self.fall(8, tf, tf + sec(20), tf + mins(2), S + hrs(6), 9.6, 140)
        self.ev("d5-hat8-drop", 8, "possible_fall", tf + sec(20), "physically_acknowledged",
                [("acknowledge", 45, "fatima", None),
                 ("resolve", 1100, "fatima", "[MOCK] Hardhat dropped from scaffold level 3 while not worn; worker unhurt. Shell cracked, device withdrawn.")],
                impact_g=9.6, orientation_change_deg=140, inactivity_ms=60000, prealert_s=15, cancelled=False)

    # --------------------------------------------------------- telemetry ---
    def co_value(self, dv, ts):
        d = DEVS[dv]
        e = ts.timestamp()
        base = d.co_base + 1.2 * math.sin(e / 1700 + dv) + 1.0 * (n("co", dv, int(e // 10)) - 0.5)
        v = max(base, 0.0)
        for t0, pts in self.co_eps[dv]:
            ep = interp(pts, (ts - t0).total_seconds())
            if ep is not None:
                v = max(v, ep + 0.8 * (n("coe", dv, int(e)) - 0.5))
        return round(max(v, 0.0), 1)

    def in_any(self, ranges, a, b=None):
        b = b or a + sec(0.001)
        return any(overlap(a, b, r0, r1) for r0, r1 in ranges)

    def make_row(self, s: Sess, k: int):
        d = DEVS[s.dev]
        ws = s.first_ws + mins(k)
        we = ws + mins(1)
        seq = k + 1
        key = (d.idx, s.boot, seq)
        vflags = mflags = 0

        # CO (1 Hz, valid samples only, 2 min warm-up after boot)
        vals = []
        for i in range(60):
            ts = ws + sec(i + 1)
            if ts - s.boot_time < sec(120) or self.in_any(self.co_bad[d.idx], ts):
                continue
            vals.append(self.co_value(d.idx, ts))
        if not vals:
            vflags |= V_CO_INVALID
            co = (None, None, None)
        else:
            if len(vals) < 60:
                vflags |= V_CO_PARTIAL
            co = (vals[-1], round(sum(vals) / len(vals), 2), max(vals))

        # Temperature / humidity / heat index
        temp = hum = hi = None
        if self.in_any(self.env_bad[d.idx], ws, we):
            vflags |= V_ENV_INVALID | V_HEAT_UNSUPPORTED
        else:
            h = (we.hour + we.minute / 60 + PKT) % 24
            temp = 14 + 12 * max(0.0, math.sin(math.pi * (h - 7) / 12)) + d.temp_off
            temp += sum(add for a, b, add in self.heat_eps[d.idx] if a <= we < b)
            if s.charging:
                temp += 2.0
            temp = round(temp + u(-0.3, 0.3, "t", *key), 1)
            hum = round(min(95.0, max(15.0, 70 - 1.4 * (temp - 14) + d.hum_off + u(-2, 2, "h", *key))), 1)
            hi = heat_index_c(temp, hum)
            if hi is None:
                vflags |= V_HEAT_UNSUPPORTED

        # Motion
        in_break = s.brk and s.brk[0] <= ws < s.brk[1]
        if s.charging:
            accel, orient, inact = 1.0, 0.0, 60000
        elif in_break:
            accel, orient, inact = u(1.0, 1.08, "a", *key), u(0.5, 5, "o", *key), int(u(38000, 60000, "i", *key))
        else:
            accel = u(2.1, 3.2, "a2", *key) if n("bump", *key) < 0.03 else u(1.12, 1.95, "a", *key)
            orient, inact = u(6, 48, "o", *key), int(u(1500, 24000, "i", *key))
        for ep in self.motion[d.idx]:
            if ep[0] == "cancel" and ws <= ep[1] < we:
                accel, orient, inact = 3.9, 38.0, 7000
                mflags |= M_IMPACT | M_PREALERT | M_CANCELLED
            elif ep[0] == "sos" and overlap(ws, we, ep[1], ep[2]):
                mflags |= M_SOS
            elif ep[0] == "fall":
                _, tf, alarm, lack, move, a_g, o_d = ep
                if ws <= tf < we:
                    accel, orient = a_g, float(o_d)
                    inact = int(max(0, min(60000, (we - tf).total_seconds() * 1000 - 3000)))
                    mflags |= M_IMPACT | M_PREALERT
                elif tf < ws < move:
                    accel, orient = u(1.0, 1.04, "fa", *key), u(0.3, 3, "fo", *key)
                    inact = 60000 if we <= move else int((move - ws).total_seconds() * 1000)
                if overlap(ws, we, alarm, lack):
                    mflags |= M_POSSIBLE_FALL
        if self.in_any(self.imu_bad[d.idx], ws, we):
            accel = orient = inact = None
            vflags |= V_IMU_INVALID

        # Battery (HH-A2 needs one window of voltage settling after boot)
        bat = s.bat0 - s.bat_rate * (we - s.bat_t0).total_seconds() / 3600
        bat = int(round(min(100.0, max(0.0, bat))))
        if d.battery_estimate and seq == 1:
            bat = None
            vflags |= V_BATTERY_UNAVAILABLE

        # GPS: outdoor fix only
        block = int(ws.timestamp() // 600)
        indoor = (in_break or self.in_any(self.indoor_force[d.idx], ws, we)
                  or n("indoor", d.idx, block) < d.indoor)
        lat = lon = age = None
        if indoor:
            vflags |= V_GPS_NO_FIX
        else:
            lat = round(SITE[0] + d.zone[0] + u(-0.00025, 0.00025, "lat", *key), 6)
            lon = round(SITE[1] + d.zone[1] + u(-0.00025, 0.00025, "lon", *key), 6)
            age = int(u(1, 12, "age", *key))

        # Time quality and arrival
        tq = "trusted"
        win = (ws, we)
        if k < s.tq_unknown:
            tq, win = "unknown", (None, None)
        elif k < s.tq_unknown + s.tq_estimated:
            tq = "estimated"
        recv = we + sec(u(0.6, 2.8, "rx", *key))
        if s.backlog and s.backlog[0] <= we < s.backlog[1]:
            recv = s.backlog[2] + sec(0.35 * k % 30)

        cal = None
        for at, cid in self.calib.get(d.idx, []):
            if at <= ws:
                cal = cid
        return dict(
            telemetry_id=mid("telemetry", *key), device_id=d.id, gateway_id=s.gateway,
            boot_epoch=s.boot, packet_seq=seq, window_start=win[0], window_end=win[1],
            # unknown source time -> uncertain worker context, so no assignment link
            received_at=recv, time_quality=tq, assignment_id=None if tq == "unknown" else s.assignment,
            config_id=CFG["mock-cfg-1.0"], calibration_id=cal,
            co_latest=co[0], co_mean=co[1], co_max=co[2], co_valid_count=len(vals), expected_count=60,
            temperature_c=temp, humidity_pct=hum, heat_index_c=hi,
            accel_peak_g=None if accel is None else round(accel, 3),
            orientation_change_deg=None if orient is None else round(orient, 2),
            inactivity_ms=inact, motion_flags=mflags,
            battery_pct=bat, battery_is_estimate=None if bat is None else d.battery_estimate,
            latitude=lat, longitude=lon, gps_fix_age_s=age, validity_flags=vflags,
            _ws=ws, _we=we, _dev=d.idx)

    def keep_windows(self):
        """Past shifts keep only short excerpts to stay small: the first 10 min of each
        session, +-10 min around every scenario, and day-wide windows (uplink backlog,
        model outage, no-active-model period). Gaps between excerpts are seeding gaps,
        not modelled radio loss."""
        per_dev = {i: [] for i in DEVS}
        pad = mins(10)
        for e in self.event_specs:
            t = e["at"] or e["recv_delay"]
            per_dev[e["dev"]].append((t - pad, t + pad))
        for dv in DEVS:
            per_dev[dv] += [(t0 - pad, t0 + pad) for t0, _ in self.co_eps[dv]]
            per_dev[dv] += [(a - pad, a + pad) for a, _, _ in self.heat_eps[dv]]
            per_dev[dv] += [(a - pad, b) for a, b in self.env_bad[dv]]
        everyone = [(self.shift(2) + hrs(2) + mins(8), self.shift(2) + hrs(2) + mins(20)),   # backlog tail
                    (self.shift(3) + hrs(1) - mins(2), self.shift(3) + hrs(1) + mins(10)),   # model error
                    (self.shift(5), self.model_v1_active_at + mins(3))]                      # no model
        return per_dev, everyone

    def telemetry(self):
        self.rows_by_dev = {i: [] for i in DEVS}
        per_dev, everyone = self.keep_windows()
        for s in self.sessions:
            k = 0
            while s.first_ws + mins(k + 1) <= s.last_we:
                row = self.make_row(s, k)
                k += 1
                if s.excerpt and k > 10 and not (self.in_any(per_dev[s.dev], row["_ws"], row["_we"])
                                                 or self.in_any(everyone, row["_ws"], row["_we"])):
                    continue
                # ~0.8 % radio loss, never on minutes that carry an alarm or CO excursion
                if (row["motion_flags"] == 0 and (row["co_max"] or 0) < 35
                        and n("loss", row["device_id"], row["boot_epoch"], row["packet_seq"]) < 0.008):
                    continue
                if row["received_at"] > self.T:
                    continue
                self.t["telemetry"].append(row)
                self.rows_by_dev[s.dev].append(row)
        for rows in self.rows_by_dev.values():
            rows.sort(key=lambda r: r["_ws"])

        # Heat warning: first d1 HAT-01 minute with heat index >= threshold
        key, dv, a, b = self.heat_spec
        hot = [r for r in self.rows_by_dev[dv] if a <= r["_ws"] < b and (r["heat_index_c"] or 0) >= 32]
        if hot:
            r = hot[0]
            self.ev(key, dv, "heat", r["_we"] - sec(10), "cleared",
                    [("acknowledge", 120, "sana", None),
                     ("resolve", 1500, "sana", "[MOCK] Crew rotated off the bitumen kettle; rest break in the shaded zone.")],
                    level="warning", threshold_c=32, heat_index_c=r["heat_index_c"])

    def row_at(self, dv, t):
        rows = self.rows_by_dev[dv]
        i = bisect.bisect_right([r["_ws"] for r in rows], t) - 1
        if i >= 0 and rows[i]["_ws"] <= t < rows[i]["_we"]:
            return rows[i]
        return None

    def session_at(self, dv, t):
        cands = [s for s in self.sessions if s.dev == dv and s.boot_time <= t <= s.last_we + mins(1)]
        return max(cands, key=lambda s: s.boot)

    # ------------------------------------------------------------ events ---
    def events(self):
        counters: dict[tuple, int] = {}
        # order: real detection time, unknown-time events by arrival
        def when(e):
            return e["at"] or e["recv_delay"]
        for e in sorted(self.event_specs, key=when):
            dv = e["dev"]
            t = when(e)
            s = self.session_at(dv, t)
            counters[(dv, s.boot)] = counters.get((dv, s.boot), 0) + 1
            row = self.row_at(dv, t)
            snap = None
            if row:
                snap = {"co_ppm": self.co_value(dv, t) if not row["validity_flags"] & V_CO_INVALID else None,
                        "temperature_c": row["temperature_c"], "humidity_pct": row["humidity_pct"],
                        "heat_index_c": row["heat_index_c"], "accel_peak_g": row["accel_peak_g"],
                        "battery_pct": row["battery_pct"]}
            gps = None
            if row and row["latitude"] is not None:
                gps = {"lat": float(row["latitude"]), "lon": float(row["longitude"]),
                       "fix_age_s": row["gps_fix_age_s"]}
            recv = e["recv_delay"] or e["at"] + sec(u(0.8, 3.5, "erx", e["key"]))
            evidence = {"mock": True, "source_counter": counters[(dv, s.boot)],
                        "monotonic_age_ms": int((recv - t).total_seconds() * 1000) if e["at"] else None,
                        "source_time_quality": e["tq"], "snapshot": snap,
                        "validity_flags": row["validity_flags"] if row else None, "gps": gps, **e["extra"]}
            eid = mid("event", e["key"])
            acts = e["actions"]
            state = "resolved" if any(a[0] == "resolve" for a in acts) else (
                "acknowledged" if any(a[0] == "acknowledge" for a in acts) else "open")
            self.t["event"].append(dict(
                event_id=eid, source_event_key=f"mock:{DEVS[dv].label}:{s.boot}:{counters[(dv, s.boot)]}",
                device_id=DEVS[dv].id,
                assignment_id=None if e["tq"] == "unknown" else self.assignment_at(dv, t),
                event_type=e["type"], detected_at=e["at"], received_at=recv, time_quality=e["tq"],
                evidence=evidence, workflow_state=state, local_state=e["local"],
                row_version=sum(a[0] in ("acknowledge", "resolve") for a in acts)))
            for i, (atype, off, actor, note) in enumerate(acts):
                at = recv + sec(off)
                assert at <= self.T, f"{e['key']} action {atype} is in the future"
                self.t["alert_action"].append(dict(
                    action_id=mid("action", e["key"], i), event_id=eid, actor_id=acc(actor),
                    action_type=atype, note=note, created_at=at))

        # sign-ins and daily retention runs (system actor)
        for d in range(0, 6):
            for who in ("sana", "kamran") if d < 4 else ("fatima", "kamran"):
                at = (self.shift(d) if d else self.T - hrs(4)) - mins(15) + mins(5 * (who == "kamran"))
                self.audit(f"signin-{who}-d{d}", "auth.sign_in", at, who, "account", acc(who))
            self.audit(f"retention-d{d}", "retention.run", self.day(d) + hrs(21) if d else min(self.T, self.day(0) + mins(30)),
                       None, None, None, cutoff_days=30, deleted_rows=0)

    # ------------------------------------------------- snapshot/last seen ---
    def snapshots_and_last_seen(self):
        last = {}
        for r in self.t["telemetry"]:
            last[r["_dev"]] = max(last.get(r["_dev"], r["received_at"]), r["received_at"])
        for e in self.t["event"]:
            dv = next(i for i, d in DEVS.items() if d.id == e["device_id"])
            last[dv] = max(last.get(dv, e["received_at"]), e["received_at"])
        for dev in self.t["device"]:
            idx = int(dev["label"][-2:])
            dev["last_seen_at"] = last.get(idx)
        for dv, rows in self.rows_by_dev.items():
            ok = [r for r in rows if r["time_quality"] in ("trusted", "estimated")]
            if not ok:
                continue
            r = max(ok, key=lambda r: (r["boot_epoch"], r["packet_seq"]))
            self.t["device_status_snapshot"].append(dict(
                device_id=r["device_id"], telemetry_id=r["telemetry_id"], boot_epoch=r["boot_epoch"],
                packet_seq=r["packet_seq"], time_quality=r["time_quality"], received_at=r["received_at"],
                updated_at=r["received_at"]))

    # -------------------------------------------------------------- risk ---
    def risk(self):
        for r in self.t["telemetry"]:
            f = r["motion_flags"]
            co_max = r["co_max"]
            emergency = None
            if f & M_SOS:
                emergency = "sos_active"
            elif co_max is not None and co_max >= 200:
                emergency = "co_urgent"
            elif f & M_POSSIBLE_FALL:
                emergency = "possible_fall"
            created = r["received_at"] + sec(u(0.3, 1.6, "ra", r["telemetry_id"]))
            status, reason, model, pred = "available", None, MODEL["v1"], None
            down = next((x for x in self.model_down if x[0] <= r["received_at"] < x[1]), None)
            if r["received_at"] < self.model_v1_active_at or not self.model_active:
                status, reason, model = "unavailable", "no_active_model", None
            elif down:
                status, reason = "failed", down[2]
            elif r["co_valid_count"] == 0 or r["temperature_c"] is None or r["accel_peak_g"] is None:
                status, reason = "unavailable", "missing_input"
            elif co_max > 150 or r["accel_peak_g"] > 16:
                status, reason = "unavailable", "unsupported_range"
            factors = []
            if status == "available":
                hi = r["heat_index_c"]
                if co_max >= 35:
                    pred = "high"
                elif hi is not None and hi >= 39:
                    pred = "high"
                elif f & M_POSSIBLE_FALL or (r["accel_peak_g"] >= 4 and r["orientation_change_deg"] >= 60):
                    pred = "high"
                elif (hi is not None and hi >= 32) or f & M_IMPACT or co_max >= 20:
                    pred = "moderate"
                else:
                    pred = "low"
                x = n("model-noise", r["telemetry_id"])
                if x < 0.02:
                    pred = LEVELS[max(0, LEVELS.index(pred) - 1)]
                elif x < 0.05:
                    pred = LEVELS[min(3, LEVELS.index(pred) + 1)]
                factors = [
                    {"feature": "co_max_ppm", "value": co_max, "split": 35.0, "side": ">=" if co_max >= 35 else "<"},
                    {"feature": "heat_index_c", "value": hi, "split": 32.0,
                     "side": None if hi is None else (">=" if hi >= 32 else "<")},
                    {"feature": "accel_peak_g", "value": r["accel_peak_g"], "split": 3.0,
                     "side": ">=" if r["accel_peak_g"] >= 3 else "<"},
                ]
            else:
                missing = [k for k in ("co_mean", "temperature_c", "accel_peak_g") if r[k] is None]
                factors = [{"feature": k, "value": None, "issue": "missing"} for k in missing]
                if reason == "unsupported_range":
                    factors.append({"feature": "co_max_ppm", "value": co_max, "issue": "outside_envelope", "max": 150})
            if emergency:
                factors.append({"rule": emergency, "priority": 1, "overrides_model": True})
            effective = "critical" if emergency else pred
            self.t["risk_assessment"].append(dict(
                assessment_id=mid("risk", r["telemetry_id"]), telemetry_id=r["telemetry_id"],
                model_id=model, status=status, predicted_level=pred, effective_level=effective,
                factors=factors, reason_code=reason,
                recommendation_version=REC_VERSION if effective in ("moderate", "high", "critical") else None,
                created_at=created))


def password_hash() -> str:
    """Accounts get a hash that can never verify, unless MOCK_ACCOUNT_PASSWORD is set
    (then a real Argon2id hash; needs `pip install argon2-cffi`). The password itself is
    never stored or logged."""
    pw = os.getenv("MOCK_ACCOUNT_PASSWORD")
    if not pw:
        return "$argon2id$v=19$m=65536,t=3,p=4$TU9DSy1OTy1MT0dJTg$TU9DSy1OTy1MT0dJTi1QTEFDRUhPTERFUg"
    from argon2 import PasswordHasher
    return PasswordHasher().hash(pw)


# -------------------------------------------------------------- database ---
TABLE_ORDER = ["account", "worker", "device", "gateway", "configuration", "calibration",
               "model_version", "recommendation", "assignment", "telemetry",
               "device_status_snapshot", "event", "alert_action", "risk_assessment", "audit_log"]

DELETE_SQL = [  # children first; telemetry delete cascades to risk_assessment
    "DELETE FROM device_status_snapshot WHERE device_id IN (SELECT device_id FROM device WHERE label LIKE 'MOCK-%')",
    "DELETE FROM event WHERE source_event_key LIKE 'mock:%' OR device_id IN (SELECT device_id FROM device WHERE label LIKE 'MOCK-%')",
    "DELETE FROM risk_assessment WHERE model_id IN (SELECT model_id FROM model_version WHERE artifact_reference LIKE 'ml/artifacts/mock/%')",
    "DELETE FROM telemetry WHERE device_id IN (SELECT device_id FROM device WHERE label LIKE 'MOCK-%')",
    "DELETE FROM assignment WHERE device_id IN (SELECT device_id FROM device WHERE label LIKE 'MOCK-%')"
    " OR worker_id IN (SELECT worker_id FROM worker WHERE worker_code LIKE 'MOCK-%')",
    "DELETE FROM audit_log WHERE safe_metadata @> '{\"mock\": true}'",
    "DELETE FROM calibration WHERE sensor_serial LIKE 'MOCK-%'",
    "DELETE FROM configuration WHERE config_version LIKE 'mock-%'",
    "DELETE FROM model_version WHERE artifact_reference LIKE 'ml/artifacts/mock/%'",
    "DELETE FROM recommendation WHERE version LIKE 'mock-%'",
    "DELETE FROM gateway WHERE gateway_code LIKE 'MOCK-%'",
    "DELETE FROM device WHERE label LIKE 'MOCK-%'",
    "DELETE FROM worker WHERE worker_code LIKE 'MOCK-%'",
    f"DELETE FROM account WHERE email LIKE '%@{EMAIL_DOMAIN}'",
]


def conninfo() -> str:
    url = database_url()
    return psycopg.conninfo.make_conninfo(
        host=url.host, port=url.port, user=url.username, password=url.password,
        dbname=url.database, connect_timeout=5)


def insert_rows(conn, table, rows):
    if not rows:
        return
    cols = [c for c in rows[0] if not c.startswith("_")]
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
           " ON CONFLICT DO NOTHING")
    params = [[Jsonb(r[c]) if isinstance(r[c], (dict, list)) else r[c] for c in cols] for r in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, params)


def counts(conn):
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLE_ORDER}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = p.add_mutually_exclusive_group()
    g.add_argument("--reset", action="store_true", help="delete mock rows, then reseed with fresh timestamps")
    g.add_argument("--delete", action="store_true", help="delete mock rows only")
    p.add_argument("--allow-remote", action="store_true", help="allow a non-local database host")
    args = p.parse_args(argv)

    url = database_url()
    if url.host not in ("127.0.0.1", "localhost", "::1") and not args.allow_remote:
        sys.exit(f"Refusing to seed non-local host {url.host!r} (use --allow-remote).")

    with psycopg.connect(conninfo()) as conn:
        before = counts(conn)
        if args.reset or args.delete:
            for sql in DELETE_SQL:
                conn.execute(sql)
            print("Deleted all mock rows.")
            if args.delete:
                conn.commit()
                return

        marker = conn.execute("SELECT safe_metadata FROM audit_log WHERE audit_id=%s", [MARKER_ID]).fetchone()
        if marker:
            meta = marker[0]
            if meta.get("seed_version") != SEED_VERSION:
                sys.exit(f"Mock data is seed_version {meta.get('seed_version')}; this script is "
                         f"{SEED_VERSION}. Run with --reset.")
            T = datetime.fromisoformat(meta["anchor"])
            print(f"Mock data already present (anchor {T.isoformat()}); topping up missing rows only.")
        else:
            T = datetime.now(UTC).replace(second=0, microsecond=0)
            print(f"Seeding mock data with anchor {T.isoformat()}.")

        # Do not displace a real active configuration / model (one-active unique indexes)
        real_cfg = conn.execute("SELECT 1 FROM configuration WHERE state='active'"
                                " AND config_version NOT LIKE 'mock-%'").fetchone()
        real_model = conn.execute("SELECT 1 FROM model_version WHERE state='active'"
                                  " AND artifact_reference NOT LIKE 'ml/artifacts/mock/%'").fetchone()
        if real_cfg or real_model:
            print("Note: a non-mock active configuration/model exists; mock ones are seeded as retired.")

        data = Seed(T, cfg_active=not real_cfg, model_active=not real_model).build()
        data["audit_log"].append(dict(
            audit_id=MARKER_ID, actor_id=None, resource_type=None, resource_id=None,
            action="mock_seed.applied", occurred_at=T,
            safe_metadata={"mock": True, "seed_version": SEED_VERSION, "anchor": T.isoformat()}))
        for table in TABLE_ORDER:
            insert_rows(conn, table, data[table])
        conn.commit()
        after = counts(conn)

    width = max(map(len, TABLE_ORDER))
    print(f"\n{'table'.ljust(width)}  generated  net_added  total")
    for t in TABLE_ORDER:
        print(f"{t.ljust(width)}  {len(data[t]):9d}  {after[t] - before[t]:9d}  {after[t]:5d}")


if __name__ == "__main__":
    main()
