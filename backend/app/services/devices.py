"""Device-health mapping (F26-113 §4.8.6; UC-14, UC-15; FR-06, FR-23, FR-26, FR-53).

Each channel is reported separately with the function it affects, so a missing GPS fix
is never read as a CO or motion failure. A device that never reported is "unknown", and
a stale one is "stale"; neither is ever shown as healthy. No key material is returned
(key_slot_reference is not selected).
"""
from datetime import datetime, timedelta

from app import flags
from app.services.overview import iso, num

STALE_AFTER = timedelta(seconds=180)
BATTERY_LOW, BATTERY_CRITICAL = 20, 10


def _ch(state: str, summary: str, affects: str | None = None) -> dict:
    return {"state": state, "summary": summary, "affects": affects}


def channels(r) -> dict:
    vf = r["validity_flags"]
    # CO
    if vf & flags.CO_INVALID:
        co = _ch("invalid", "CO channel fault", "CO measurement and the CO alarm on this hardhat")
    elif vf & flags.CO_PARTIAL:
        co = _ch("partial", f"{r['co_valid_count']} of {r['expected_count']} CO samples valid in the last window",
                 "CO summary uses valid samples only")
    elif r["co_latest"] is None:
        co = _ch("missing", "No CO value in the latest status", "CO measurement")
    else:
        co = _ch("valid", f"{num(r['co_latest']):.0f} ppm latest")
    # Temperature / humidity
    if vf & flags.ENV_INVALID:
        env = _ch("invalid", "Temperature/humidity sensor fault", "Temperature, humidity and heat index")
    elif r["temperature_c"] is None or r["humidity_pct"] is None:
        env = _ch("missing", "No temperature/humidity value in the latest status", "Heat index")
    else:
        env = _ch("valid", f"{num(r['temperature_c']):.1f} °C, {num(r['humidity_pct']):.0f} %RH")
    # Motion (IMU)
    if vf & flags.IMU_INVALID:
        imu = _ch("invalid", "Motion sensor fault", "Fall detection on this hardhat")
    elif r["accel_peak_g"] is None:
        imu = _ch("missing", "No motion summary in the latest status", "Fall detection status")
    else:
        imu = _ch("valid", f"peak {num(r['accel_peak_g']):.2f} g in the last window")
    # Battery
    if vf & flags.BATTERY_UNAVAILABLE or r["battery_pct"] is None:
        bat = _ch("missing", "Battery level unavailable (not zero)", "Battery warnings")
    else:
        pct = num(r["battery_pct"])
        est = " (estimate)" if r["battery_is_estimate"] else ""
        if pct <= BATTERY_CRITICAL:
            bat = _ch("critical", f"{pct:.0f}%{est}, critical", "Hardhat may shut down soon")
        elif pct <= BATTERY_LOW:
            bat = _ch("low", f"{pct:.0f}%{est}, low", "Charge before the next shift")
        else:
            bat = _ch("valid", f"{pct:.0f}%{est}")
    # GPS (outdoor only)
    if r["latitude"] is None:
        gps = _ch("no_fix", "No current outdoor fix",
                  "Current location only. Indoor position is not supported; other sensors are unaffected.")
    else:
        gps = _ch("valid", f"Outdoor fix, {r['gps_fix_age_s'] or 0} s old at send time")
    return {"co": co, "environment": env, "motion": imu, "battery": bat, "gps": gps}


def device_health(r, now: datetime, show_worker: bool) -> dict:
    base = {
        "deviceId": str(r["device_id"]),
        "label": r["label"],
        "radioId": r["radio_id"],
        "state": r["state"],
        "hardwareRevision": r["hardware_revision"],
        "firmwareVersion": r["firmware_version"],
        "registeredAt": iso(r["created_at"]),
        "lastSeenAt": iso(r["last_seen_at"]),   # radio contact (any accepted packet)
        "openFaults": r["open_faults"],
    }
    if show_worker:   # worker identity is for supervisor roles only (Table 4.34)
        base["worker"] = {"code": r["worker_code"], "name": r["worker_name"]} if r["worker_code"] else None
    if r["telemetry_id"] is None:
        return {**base, "status": "unknown", "receivedAt": None, "timeQuality": None, "channels": None,
                "config": None, "calibration": None, "gateway": None}
    stale = now - r["snap_received_at"] > STALE_AFTER
    cal = None
    if r["calibration_id"] is not None:
        cal = {"sensorSerial": r["sensor_serial"], "result": r["cal_result"], "checkedAt": iso(r["cal_checked_at"]),
               "dueAt": iso(r["cal_due_at"]), "overdue": bool(r["cal_due_at"] and r["cal_due_at"] < now)}
    return {
        **base,
        "status": "stale" if stale else "current",
        "receivedAt": iso(r["snap_received_at"]),
        "timeQuality": r["snap_time_quality"],
        "channels": channels(r),
        "config": {"version": r["config_version"], "state": r["config_state"]} if r["config_version"] else None,
        "calibration": cal,
        "gateway": {"code": r["gateway_code"], "lastSeenAt": iso(r["gateway_last_seen"])} if r["gateway_code"] else None,
    }
