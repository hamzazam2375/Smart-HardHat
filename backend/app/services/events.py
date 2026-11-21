"""Alert detail mapping (F26-113 §4.8.3; UC-06..UC-11; FR-34, FR-35, FR-36, FR-38).

The source event is shown as received and never changed by supervisor actions. Missing
context (detection time, assignment, location, readings) is labelled, never filled in.
"""
from datetime import datetime, timedelta, timezone

from app import flags
from app.services.overview import active_alert, iso, num

# Dashboard alert type -> recommendation.factor_code (reviewed library, no generated advice).
RECOMMENDATION_FACTOR = {
    "co_urgent": "co_urgent",
    "co_warning": "co_warning",
    "sos": "sos_active",
    "possible_fall": "possible_fall",
    "heat_warning": "heat_index_high",
    "battery_low": "battery_low",
    "battery_critical": "battery_low",
    "sensor_fault": "sensor_fault",
}
FALLBACK_FACTOR = "unrecognized"

# Evidence keys shown under "source evidence". Internal/bookkeeping keys are left out.
HIDDEN_EVIDENCE_KEYS = {"mock", "snapshot", "gps", "validity_flags"}


def _reading(snap: dict | None, key: str, vf: int | None, invalid_bit: int, unsupported_bit: int = 0) -> dict:
    if snap is None:
        return {"value": None, "quality": "missing"}
    if vf is not None and vf & invalid_bit:
        return {"value": None, "quality": "invalid"}
    v = snap.get(key)
    if v is None:
        if unsupported_bit and vf is not None and vf & unsupported_bit:
            return {"value": None, "quality": "unsupported"}
        return {"value": None, "quality": "missing"}
    return {"value": num(v), "quality": "valid"}


def readings(ev: dict) -> dict | None:
    """Readings captured with the event (evidence.snapshot). None = not recorded with the event."""
    snap = ev.get("snapshot")
    if not isinstance(snap, dict):
        return None
    vf = ev.get("validity_flags")
    battery = _reading(snap, "battery_pct", vf, flags.BATTERY_UNAVAILABLE)
    return {
        "co": _reading(snap, "co_ppm", vf, flags.CO_INVALID),
        "temperature": _reading(snap, "temperature_c", vf, flags.ENV_INVALID),
        "humidity": _reading(snap, "humidity_pct", vf, flags.ENV_INVALID),
        "heatIndex": _reading(snap, "heat_index_c", vf, flags.ENV_INVALID, flags.HEAT_UNSUPPORTED),
        "accelPeak": _reading(snap, "accel_peak_g", vf, flags.IMU_INVALID),
        "battery": battery,
    }


def location(row, ev: dict) -> dict:
    """Location at detection, or the last known fix before it (labelled with its time)."""
    gps = ev.get("gps")
    if isinstance(gps, dict) and gps.get("lat") is not None:
        base = row["detected_at"]
        fix_at = base - timedelta(seconds=gps.get("fix_age_s") or 0) if base else None
        return {"state": "fix", "lat": num(gps["lat"]), "lon": num(gps["lon"]), "fixAt": iso(fix_at),
                "fixAgeS": gps.get("fix_age_s")}
    last = None
    if row["last_lat"] is not None:
        at = (row["last_window_end"] or row["last_received_at"]) - timedelta(seconds=row["last_fix_age_s"] or 0)
        last = {"lat": num(row["last_lat"]), "lon": num(row["last_lon"]), "fixAt": iso(at)}
    return {"state": "no_fix", "lastKnown": last}


def assignment(row) -> dict:
    if row["assignment_id"] is not None:
        return {"state": "resolved",
                "worker": {"code": row["worker_code"], "name": row["worker_name"]},
                "startAt": iso(row["assign_start"]), "endAt": iso(row["assign_end"])}
    if row["time_quality"] == "unknown" or row["detected_at"] is None:
        reason = "Detection time is unknown, so the wearer cannot be determined."
    elif row["time_quality"] == "estimated":
        reason = "Detection time is estimated and could fall in more than one shift."
    else:
        reason = "No assignment was active for this hardhat at the detection time."
    return {"state": "unresolved", "reason": reason}


def source_evidence(ev: dict) -> list[dict]:
    out = []
    for k, v in ev.items():
        if k in HIDDEN_EVIDENCE_KEYS or v is None or isinstance(v, (dict, list)):
            continue
        out.append({"key": k, "value": num(v) if not isinstance(v, (str, bool)) else v})
    return out


def action_json(a) -> dict:
    return {"id": str(a["action_id"]), "type": a["action_type"], "note": a["note"],
            "by": a["actor_name"], "at": iso(a["created_at"])}


def event_detail(row, actions: list, recommendations: list) -> dict:
    ev = row["evidence"] or {}
    alert = active_alert(row)   # same identity/type/priority/detail as the overview list
    alert.update({
        "state": row["workflow_state"],
        "rowVersion": row["row_version"],
        "deviceId": str(row["device_id"]),
        "sourceEventKey": row["source_event_key"],
        "readings": readings(ev),
        "location": location(row, ev),
        "assignment": assignment(row),
        "evidence": source_evidence(ev),
        "isMock": bool(ev.get("mock")),
    })
    return {"generatedAt": datetime.now(timezone.utc).isoformat(), "alert": alert, "actions": [action_json(a) for a in actions],
            "recommendations": [{"code": r["factor_code"], "message": r["message"], "version": r["version"]}
                                for r in recommendations]}
