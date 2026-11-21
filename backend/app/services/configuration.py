"""Configuration validation (F26-113 §4.8.7; UC-20; FR-47, FR-48, FR-53).

Every threshold/timing has a unit and an allowed range, and contradictory combinations are
rejected before a draft can be saved or approved. Ranges are PROTOTYPE review bounds, not
certified alarm setpoints. Keys match the mock seed and the hardhat config (align with the
firmware's wired-setup format when frozen).
"""
import hashlib
import json

# key: (unit, min, max, integer?, label)
THRESHOLDS = {
    "co_warning_ppm": ("ppm", 10, 100, True, "CO screening warning"),
    "co_urgent_ppm": ("ppm", 50, 500, True, "CO urgent emergency"),
    "co_reset_ppm": ("ppm", 10, 500, True, "CO urgent reset level"),
    "heat_index_warning_c": ("°C", 25, 45, False, "Heat index warning"),
    "battery_low_pct": ("%", 5, 50, True, "Battery low"),
    "battery_critical_pct": ("%", 1, 30, True, "Battery critical"),
    "fall_impact_g": ("g", 1.5, 8, False, "Fall impact"),
    "fall_orientation_change_deg": ("°", 15, 180, True, "Fall orientation change"),
    "fall_inactivity_ms": ("ms", 1000, 60000, True, "Fall inactivity"),
}
TIMINGS = {
    "summary_period_s": ("s", 10, 300, True, "Status summary period"),
    "stale_after_s": ("s", 30, 900, True, "Stale after"),
    "co_reset_hold_s": ("s", 5, 300, True, "CO reset hold"),
    "fall_prealert_s": ("s", 5, 60, True, "Fall pre-alert cancel window"),
    "fall_rearm_stable_s": ("s", 1, 60, True, "Fall re-arm after stable movement"),
    "sos_hold_ms": ("ms", 500, 5000, True, "SOS hold time"),
    "motion_hz": ("Hz", 10, 200, True, "Motion sample rate"),
    "co_hz": ("Hz", 1, 10, True, "CO sample rate"),
    "temp_humidity_s": ("s", 1, 60, True, "Temperature/humidity period"),
    "battery_s": ("s", 5, 300, True, "Battery period"),
}


def schema() -> dict:
    def out(spec):
        return [{"key": k, "unit": u, "min": lo, "max": hi, "integer": i, "label": lbl}
                for k, (u, lo, hi, i, lbl) in spec.items()]
    return {"thresholds": out(THRESHOLDS), "timings": out(TIMINGS)}


def _check_group(values, spec: dict, group: str, errors: list[str]) -> dict:
    if not isinstance(values, dict):
        errors.append(f"{group} must be an object.")
        return {}
    clean = {}
    for k in values:
        if k not in spec:
            errors.append(f"Unknown {group[:-1]} '{k}'.")
    for k, (unit, lo, hi, integer, label) in spec.items():
        v = values.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"{label} ({k}) is required and must be a number.")
            continue
        if integer and float(v) != int(v):
            errors.append(f"{label} must be a whole number of {unit}.")
            continue
        if not lo <= v <= hi:
            errors.append(f"{label} must be between {lo} and {hi} {unit}.")
            continue
        clean[k] = int(v) if integer else float(v)
    return clean


def validate(thresholds, timings) -> tuple[dict, dict, list[str]]:
    """Range + contradiction checks. Returns cleaned values and a list of errors (empty = valid)."""
    errors: list[str] = []
    t = _check_group(thresholds, THRESHOLDS, "thresholds", errors)
    m = _check_group(timings, TIMINGS, "timings", errors)
    if errors:
        return t, m, errors
    if not t["co_warning_ppm"] < t["co_urgent_ppm"]:
        errors.append("CO warning must be below the CO urgent level.")
    if not t["co_reset_ppm"] < t["co_urgent_ppm"]:
        errors.append("CO reset level must be below the CO urgent level (hysteresis).")
    if not t["co_warning_ppm"] <= t["co_reset_ppm"]:
        errors.append("CO reset level must not be below the CO warning level.")
    if not t["battery_critical_pct"] < t["battery_low_pct"]:
        errors.append("Battery critical must be below battery low.")
    if not m["stale_after_s"] >= 2 * m["summary_period_s"]:
        errors.append("Stale-after must be at least two summary periods, or one late packet marks a device stale.")
    if not m["battery_s"] <= m["summary_period_s"]:
        errors.append("Battery period must not exceed the summary period.")
    if not m["temp_humidity_s"] <= m["summary_period_s"]:
        errors.append("Temperature/humidity period must not exceed the summary period.")
    return t, m, errors


def checksum(thresholds: dict, timings: dict) -> str:
    """Same canonical form as the mock seed: sorted JSON of both groups."""
    body = json.dumps({"thresholds": thresholds, "timings": timings}, sort_keys=True)
    return "sha256:" + hashlib.sha256(body.encode()).hexdigest()
