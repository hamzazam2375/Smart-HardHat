"""Read-side mapping from DB rows to the dashboard overview shape (F26-113 §4.8.2).

Rules kept here (CLAUDE.md): missing / invalid / unsupported / never-reported stay
distinct and are never turned into 0 or "safe"; the model is advisory and rule
emergencies override it; supervisor ack and physical (hardhat) ack are separate fields.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import PurePosixPath

from app import flags

TIME_QUALITY = ("trusted", "estimated", "unknown")

RISK_REASON = {
    "missing_input": "Required input missing or invalid",
    "unsupported_range": "Input outside the model's supported range",
    "model_error": "Model error",
    "no_active_model": "No active model",
}


def num(v):
    return float(v) if isinstance(v, Decimal) else v


def iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def reading(value, invalid: bool) -> dict:
    if invalid:
        return {"value": None, "quality": "invalid"}
    if value is None:
        return {"value": None, "quality": "missing"}
    return {"value": num(value), "quality": "valid"}


def model_name(artifact_reference: str | None) -> str | None:
    return PurePosixPath(artifact_reference.replace("\\", "/")).stem if artifact_reference else None


# ------------------------------------------------------------------ devices ---
def motion(row) -> dict:
    vf, mf = row["validity_flags"], row["motion_flags"]
    if vf & flags.IMU_INVALID:
        return {"state": None, "quality": "invalid"}
    if row["accel_peak_g"] is None:
        return {"state": None, "quality": "missing"}
    if mf & flags.POSSIBLE_FALL:
        state = "still_after_impact"
    elif mf & flags.PREALERT and not mf & flags.CANCELLED:
        state = "fall_pre_alert"
    else:
        state = "normal"
    return {"state": state, "quality": "valid"}


def heat_index(row) -> dict:
    vf = row["validity_flags"]
    if vf & flags.ENV_INVALID:
        return {"value": None, "quality": "invalid"}
    if row["heat_index_c"] is None and vf & flags.HEAT_UNSUPPORTED:
        return {"value": None, "quality": "unsupported"}   # outside the NWS formula's range
    return reading(row["heat_index_c"], False)


def gps(row) -> dict:
    if row["latitude"] is not None:
        at = (row["window_end"] or row["received_at"]) - timedelta(seconds=row["gps_fix_age_s"] or 0)
        return {"state": "fix", "fixAt": iso(at), "lat": num(row["latitude"]), "lon": num(row["longitude"])}
    last = None
    if row["last_fix_received_at"] is not None:
        last = ((row["last_fix_window_end"] or row["last_fix_received_at"])
                - timedelta(seconds=row["last_fix_age_s"] or 0))
    return {"state": "no_fix", "fixAt": iso(last)}


def risk(row) -> dict:
    if row["risk_status"] is None:
        return {"state": "unavailable", "reason": "No assessment for the latest status"}
    predicted, effective = row["predicted_level"], row["effective_level"]
    overridden = any(isinstance(f, dict) and f.get("overrides_model") for f in row["risk_factors"] or [])
    if effective and (overridden or predicted is None or effective != predicted):
        return {"state": "available", "level": effective, "source": "rule_override",
                "modelVersion": model_name(row["model_artifact"]), "assessedAt": iso(row["risk_created_at"])}
    if row["risk_status"] == "available":
        return {"state": "available", "level": effective or predicted, "source": "model",
                "modelVersion": model_name(row["model_artifact"]), "assessedAt": iso(row["risk_created_at"])}
    reason = RISK_REASON.get(row["reason_code"], "Unavailable")
    if row["risk_status"] == "failed":
        reason = f"Assessment failed: {reason.lower()}"
    return {"state": "unavailable", "reason": reason}


def device_status(row) -> dict:
    worker = ({"code": row["worker_code"], "name": row["worker_name"]} if row["worker_code"] else None)
    base = {"deviceId": str(row["device_id"]), "label": row["label"], "worker": worker}
    if row["telemetry_id"] is None:   # never reported (or no status with usable time quality)
        missing = {"value": None, "quality": "missing"}
        return {**base, "receivedAt": None, "timeQuality": "unknown",
                "co": missing, "temperature": missing, "humidity": missing, "heatIndex": missing,
                "battery": {**missing, "isEstimate": False}, "motion": {"state": None, "quality": "missing"},
                "gps": gps(row),
                "risk": {"state": "unavailable", "reason": "Device has never reported"}}
    vf = row["validity_flags"]
    env_bad = bool(vf & flags.ENV_INVALID)
    battery = reading(None if vf & flags.BATTERY_UNAVAILABLE else row["battery_pct"], False)
    return {
        **base,
        "receivedAt": iso(row["snap_received_at"]),
        "timeQuality": row["snap_time_quality"],
        "co": reading(row["co_latest"], bool(vf & flags.CO_INVALID)),
        "temperature": reading(row["temperature_c"], env_bad),
        "humidity": reading(row["humidity_pct"], env_bad),
        "heatIndex": heat_index(row),
        "battery": {**battery, "isEstimate": bool(row["battery_is_estimate"])},
        "motion": motion(row),
        "gps": gps(row),
        "risk": risk(row),
    }


# ------------------------------------------------------------------- events ---
def classify(event_type: str, evidence: dict) -> tuple[str, int]:
    """Dashboard type and spec priority (1 CO/SOS/fall, 2 pre-alert, 3 fault, 4 heat/CO warning, 5 battery).
    Unknown CO level is treated as urgent, never as the milder warning."""
    level = evidence.get("level")
    if event_type == "sos":
        return "sos", 1
    if event_type == "possible_fall":
        return "possible_fall", 1
    if event_type == "co":
        return ("co_warning", 4) if level == "warning" else ("co_urgent", 1)
    if event_type == "cancellation":
        return "cancellation", 2
    if event_type == "fault":
        return "sensor_fault", 3
    if event_type == "heat":
        return "heat_warning", 4
    if event_type == "battery":
        return ("battery_critical", 5) if level == "critical" else ("battery_low", 5)
    return "sensor_fault", 3


def _fmt(v, digits=0) -> str:
    return f"{float(v):.{digits}f}"


def event_detail(etype: str, ev: dict) -> str:
    snap = ev.get("snapshot") or {}
    if etype in ("co_urgent", "co_warning"):
        ppm = snap.get("co_ppm") if snap.get("co_ppm") is not None else ev.get("peak_ppm")
        at = f"CO {_fmt(ppm)} ppm at detection" if ppm is not None else "CO value at detection not recorded"
        return f"{at} (screening warning at 35 ppm; urgent at 200 ppm)."
    if etype == "sos":
        hold = ev.get("hold_ms")
        return f"SOS button held {_fmt(hold / 1000, 1)} s." if hold else "SOS button held."
    if etype == "possible_fall":
        parts = []
        if ev.get("impact_g") is not None:
            parts.append(f"impact {_fmt(ev['impact_g'], 1)} g")
        if ev.get("orientation_change_deg") is not None:
            parts.append(f"orientation change {_fmt(ev['orientation_change_deg'])}°")
        what = ", ".join(parts) if parts else "Impact and orientation change"
        return f"{what[0].upper()}{what[1:]}, then inactivity. The 15 s cancel window expired."
    if etype == "cancellation":
        return "The worker cancelled the fall pre-alert on the hardhat."
    if etype == "heat_warning":
        hi = ev.get("heat_index_c", snap.get("heat_index_c"))
        return (f"Heat index {_fmt(hi, 1)} °C (warning at 32 °C)." if hi is not None
                else "Heat index above the warning level (32 °C).")
    if etype in ("battery_low", "battery_critical"):
        pct = snap.get("battery_pct")
        return f"Battery {_fmt(pct)}% at detection." if pct is not None else "Battery below the warning level."
    channel = ev.get("channel")
    code = ev.get("fault_code")
    text = f"Fault on {channel.replace('_', '/')}" if channel else "Sensor fault"
    text += f" ({code})." if code else "."
    if channel == "imu":
        text += " Fall detection is unavailable on this hardhat."
    elif channel == "co":
        text += " CO readings are unavailable on this hardhat."
    return text


def active_alert(row) -> dict:
    ev = row["evidence"] or {}
    etype, priority = classify(row["event_type"], ev)
    worker = ({"code": row["worker_code"], "name": row["worker_name"]} if row["worker_code"] else None)
    alert = {
        "eventId": str(row["event_id"]),
        "code": "E-" + row["event_id"].hex[:8].upper(),
        "type": etype,
        "priority": priority,
        "state": row["workflow_state"],
        "deviceLabel": row["label"],
        "worker": worker,                      # null = assignment uncertain
        "detectedAt": iso(row["detected_at"]),  # null = detection time unknown
        "timeQuality": row["time_quality"],
        "receivedAt": iso(row["received_at"]),
        "detail": event_detail(etype, ev),
        "localState": row["local_state"],       # hardhat state, separate from supervisor workflow
    }
    if row["ack_at"] is not None:
        alert["supervisorAck"] = {"by": row["ack_by"], "at": iso(row["ack_at"])}
    return alert
