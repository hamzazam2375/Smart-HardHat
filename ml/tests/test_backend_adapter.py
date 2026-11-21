
from src.backend_adapter import RiskModelAdapter
from src.validation import CONTRACT


MODEL_ID = "00000000-0000-4000-8000-000000000001"


def sample_telemetry():
    return {
        "time_quality": CONTRACT["require_time_quality"][0],
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


def test_adapter_prediction():
    adapter = RiskModelAdapter()

    result = adapter.predict(
        sample_telemetry(),
        model_id=MODEL_ID,
    )

    assert result["status"] == "available"
    assert result["predicted_level"] in CONTRACT["labels"]
    assert result["effective_level"] == result["predicted_level"]


def test_adapter_urgent_override():
    adapter = RiskModelAdapter()

    telemetry = sample_telemetry()
    telemetry["co_mean"] = None

    events = [{
        "event_type": "sos",
        "local_state": "active",
        "workflow_state": "acknowledged",
        "source_event_key": "test-sos-001",
    }]

    result = adapter.predict(
        telemetry,
        events=events,
        model_id=MODEL_ID,
    )

    assert result["status"] == "unavailable"
    assert result["predicted_level"] is None
    assert result["effective_level"] == "critical"


def test_adapter_rejects_missing_model_id():
    adapter = RiskModelAdapter()

    result = adapter.predict(
        sample_telemetry(),
        model_id=None,
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "no_active_model"
