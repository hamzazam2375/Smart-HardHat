
from pathlib import Path

from src.inference import assess, load_bundle
from src.validation import CONTRACT, FEATURES


MODEL_PATH = Path("artifacts/risk_forest_v2.joblib")

SAMPLE = {
    "time_quality": "trusted",
    "window_start": "2026-11-17T10:00:00+00:00",
    "window_end": "2026-11-17T10:01:00+00:00",
    "co_valid_count": 60,
    "expected_count": 60,
    "validity_flags": 0,
    "co_latest": 5.0,
    "co_mean": 5.0,
    "co_max": 7.0,
    "temperature_c": 27.0,
    "humidity_pct": 45.0,
    "heat_index_c": 28.0,
    "accel_peak_g": 1.2,
    "orientation_change_deg": 5.0,
    "inactivity_ms": 2000.0,
}

MODEL_ID = "00000000-0000-4000-8000-000000000001"


def test_v2_bundle_contract():
    bundle = load_bundle(MODEL_PATH)

    assert bundle["schema_version"] == CONTRACT["schema_version"]
    assert bundle["features"] == FEATURES


def test_v2_normal_inference():
    bundle = load_bundle(MODEL_PATH)

    result = assess(
        SAMPLE,
        model_bundle=bundle,
        model_id=MODEL_ID
    )

    assert result["status"] == "available"
    assert result["predicted_level"] in CONTRACT["labels"]
    assert result["effective_level"] == result["predicted_level"]
    assert result["reason_code"] is None


def test_v2_missing_input():
    bundle = load_bundle(MODEL_PATH)

    invalid = SAMPLE.copy()
    invalid["co_mean"] = None

    result = assess(
        invalid,
        model_bundle=bundle,
        model_id=MODEL_ID
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "missing_input"
    assert result["predicted_level"] is None


def test_v2_sos_override():
    bundle = load_bundle(MODEL_PATH)

    invalid = SAMPLE.copy()
    invalid["co_mean"] = None

    events = [{
        "event_type": "sos",
        "local_state": "active",
        "workflow_state": "acknowledged",
        "source_event_key": "test-sos-001"
    }]

    result = assess(
        invalid,
        events=events,
        model_bundle=bundle,
        model_id=MODEL_ID
    )

    assert result["status"] == "unavailable"
    assert result["predicted_level"] is None
    assert result["effective_level"] == "critical"