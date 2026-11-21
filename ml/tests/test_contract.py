from datetime import datetime, timedelta, timezone
from src.validation import validate, InvalidInput, CONTRACT
from src.inference import assess
from src.safety import resolve
from src.generate_experiment import build
import pytest

def row():
    r=build(n_sessions=1,windows_per_session=1).iloc[0].to_dict()
    now=datetime.now(timezone.utc)
    r.update(window_start=now-timedelta(seconds=60),window_end=now,time_quality="trusted",co_valid_count=60,expected_count=60,validity_flags=0)
    return r

def test_valid(): assert len(validate(row()))==9

def test_missing():
    r=row();r["co_latest"]=None
    with pytest.raises(InvalidInput): validate(r)

def test_coverage():
    r=row();r["co_valid_count"]=12
    with pytest.raises(InvalidInput): validate(r)

def test_unsupported():
    r=row();r["co_max"]=210
    with pytest.raises(InvalidInput) as exc:validate(r)
    assert exc.value.code=="unsupported_range"

def test_active_sos():
    event={"event_type":"sos","local_state":"active","workflow_state":"acknowledged"}
    assert resolve(None,[event])[0]=="critical"

def test_cleared_sos():
    event={"event_type":"sos","local_state":"cleared","workflow_state":"open"}
    assert resolve("low",[event])[0]=="low"

def test_warning_co_not_emergency():
    event={"event_type":"co","evidence":{"level":"warning"},"local_state":"active"}
    assert resolve("low",[event])[0]=="low"

def test_unavailable_with_sos():
    event={"event_type":"sos","local_state":"active","workflow_state":"open"}
    out=assess(row(),[event],model_bundle=None)
    assert out["status"]=="unavailable" and out["predicted_level"] is None and out["effective_level"]=="critical"

def test_schema_mismatch():
    out=assess(row(),model_bundle={"schema_version":"other","features":[],"model":None},model_id="demo")
    assert out["status"]=="unavailable" and out["reason_code"]=="missing_input"
