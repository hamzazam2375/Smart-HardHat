import joblib
import pandas as pd
from pathlib import Path
from .validation import validate, InvalidInput, CONTRACT
from .safety import resolve

def assess(row, events=(), model_bundle=None, model_id=None, recommendation_version=None):
    """Returns columns compatible with backend.risk_assessment (except telemetry_id).
    Caller supplies model_id from the registered model_version UUID.
    """
    status, reason, predicted, factors = "unavailable", None, None, []
    if model_bundle is None or model_id is None:
        reason = "no_active_model"
        factors = [{"issue": "no_registered_model"}]
    elif model_bundle.get("schema_version") != CONTRACT["schema_version"] or model_bundle.get("features") != CONTRACT["features"]:
        reason = "missing_input"
        factors = [{"issue": "schema_mismatch"}]
    else:
        try:
            x = validate(row)
            predicted = str(model_bundle["model"].predict(pd.DataFrame([x], columns=CONTRACT["features"]))[0])
            if predicted not in CONTRACT["labels"]: raise ValueError("unknown_class")
            status = "available"
            factors = [{"feature": name, "value": value} for name, value in zip(CONTRACT["features"], x)]
        except InvalidInput as ex:
            reason = ex.code
            factors = [{"issue": ex.detail}]
        except Exception as ex:
            status, reason = "failed", "model_error"
            factors = [{"issue": "inference_exception", "type": type(ex).__name__}]
    effective, urgent = resolve(predicted, events)
    factors += urgent
    return {"model_id": model_id if model_bundle is not None else None,
            "status": status, "predicted_level": predicted, "effective_level": effective,
            "factors": factors, "reason_code": reason,
            "recommendation_version": recommendation_version if effective in ("moderate", "high", "critical") else None}

def load_bundle(path):
    """Only load trusted locally produced joblib artifacts; joblib uses pickle."""
    return joblib.load(Path(path))
