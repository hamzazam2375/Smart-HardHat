import json
import math
from pathlib import Path
from datetime import datetime

CONTRACT = json.loads((Path(__file__).resolve().parents[1] / "contract.json").read_text())
FEATURES = CONTRACT["features"]

class InvalidInput(Exception):
    def __init__(self, code, detail):
        self.code, self.detail = code, detail
        super().__init__(detail)

def validate(row):
    """Validate accepted telemetry; never replace missing readings with zero."""
    if row.get("time_quality") not in CONTRACT["require_time_quality"]:
        raise InvalidInput("missing_input", "time_quality_not_usable")
    start, end = row.get("window_start"), row.get("window_end")
    if start is None or end is None:
        raise InvalidInput("missing_input", "window_missing")
    if isinstance(start, str): start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if isinstance(end, str): end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    try: duration = (end - start).total_seconds()
    except (TypeError, ValueError): raise InvalidInput("missing_input", "invalid_window_timestamps")
    if abs(duration - CONTRACT["expected_window_seconds"]) > 1:
        raise InvalidInput("missing_input", "window_duration_not_60_seconds")
    count, expected = row.get("co_valid_count"), row.get("expected_count")
    if count is None or expected is None or expected <= 0 or not 0 <= count <= expected:
        raise InvalidInput("missing_input", "invalid_co_counts")
    if count / expected < CONTRACT["min_co_valid_fraction"]:
        raise InvalidInput("missing_input", "insufficient_co_coverage")
    flags = int(row.get("validity_flags") or 0)
    if flags & (1 | 4 | 8 | 16):
        raise InvalidInput("missing_input", "required_sensor_invalid_or_heat_unsupported")
    values = []
    for name in FEATURES:
        value = row.get(name)
        if value is None:
            raise InvalidInput("missing_input", f"missing_{name}")
        try: value = float(value)
        except (ValueError, TypeError): raise InvalidInput("missing_input", f"invalid_{name}")
        if not math.isfinite(value):
            raise InvalidInput("missing_input", f"nonfinite_{name}")
        lo, hi = CONTRACT["supported_ranges"][name]
        if not lo <= value <= hi:
            raise InvalidInput("unsupported_range", f"outside_envelope_{name}")
        values.append(value)
    validated = dict(zip(FEATURES, values))

    if (
        validated["co_mean"] > validated["co_max"]
        or validated["co_latest"] > validated["co_max"]
    ):
        raise InvalidInput(
            "missing_input",
            "inconsistent_co_statistics"
        )

    return values