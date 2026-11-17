
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .validation import CONTRACT

ROOT = Path(__file__).resolve().parents[1]

MODEL_PATH = ROOT / "artifacts" / "risk_forest_v2.joblib"
EVALUATION_PATH = ROOT / "reports" / "evaluation_v2.json"
MANIFEST_PATH = ROOT / "reports" / "model_manifest_v2.json"


def sha256_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def main():
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(
            f"Missing model artifact: {MODEL_PATH}"
        )

    if not EVALUATION_PATH.is_file():
        raise FileNotFoundError(
            f"Missing evaluation report: {EVALUATION_PATH}"
        )

    evaluation = json.loads(
        EVALUATION_PATH.read_text(encoding="utf-8")
    )

    manifest = {
        "model_name": "risk_forest_v2",
        "feature_schema_version": CONTRACT["schema_version"],
        "artifact_reference": "artifacts/risk_forest_v2.joblib",
        "checksum_algorithm": "sha256",
        "checksum": sha256_file(MODEL_PATH),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_provenance": {
            "dataset": "synthetic_experiment.csv",
            "dataset_type": "synthetic",
            "sessions": 120,
            "train_sessions": 90,
            "test_sessions": 30,
            "split_strategy": "GroupShuffleSplit",
            "split_random_state": 42,
            "model_type": "RandomForestClassifier",
            "n_estimators": 150,
            "max_depth": 10,
            "min_samples_leaf": 3,
            "class_weight": "balanced",
            "model_random_state": 42,
            "limitations": [
                "Training labels generated from synthetic scenarios",
                "Not validated against real-world safety incidents",
                "Critical-risk recall remains limited",
            ],
        },
        "validation_envelope": {
            "features": CONTRACT["features"],
            "supported_ranges": CONTRACT["supported_ranges"],
            "expected_window_seconds":
                CONTRACT["expected_window_seconds"],
            "min_co_valid_fraction":
                CONTRACT["min_co_valid_fraction"],
        },
        "evaluation_reference": "reports/evaluation_v2.json",
        "evaluation_metrics": {
            "accuracy": evaluation["metrics"]["accuracy"],
            "macro_f1": evaluation["metrics"]["macro_f1"],
            "underestimation_rate":
                evaluation["metrics"]["underestimation_rate"],
            "critical_underestimated":
                evaluation["metrics"]["critical_underestimated"],
        },
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("Model package prepared successfully")
    print(f"Model: {manifest['model_name']}")
    print(f"Schema: {manifest['feature_schema_version']}")
    print(f"SHA-256: {manifest['checksum']}")
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
