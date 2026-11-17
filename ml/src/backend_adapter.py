
import hashlib
import json
from pathlib import Path

from .inference import assess, load_bundle
from .validation import CONTRACT


ROOT = Path(__file__).resolve().parents[1]


class ModelIntegrityError(RuntimeError):
    pass


def verify_checksum(path, expected):
    digest = hashlib.sha256()

    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    if digest.hexdigest() != expected:
        raise ModelIntegrityError(
            "Model artifact checksum mismatch"
        )


class RiskModelAdapter:
    def __init__(self, manifest_path=None):
        if manifest_path is None:
            manifest_path = (
                ROOT / "reports" / "model_manifest_v2.json"
            )

        manifest_path = Path(manifest_path).resolve()

        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

        artifact_reference = manifest["artifact_reference"]
        artifact_path = (ROOT / artifact_reference).resolve()

        # Prevent manifest paths from escaping the ML directory.
        if not artifact_path.is_relative_to(ROOT.resolve()):
            raise ModelIntegrityError(
                "Artifact path outside ML directory"
            )

        verify_checksum(
            artifact_path,
            manifest["checksum"]
        )

        self.bundle = load_bundle(artifact_path)

        if (
            self.bundle.get("schema_version")
            != CONTRACT["schema_version"]
        ):
            raise ModelIntegrityError(
                "Model feature schema mismatch"
            )

        if self.bundle.get("features") != CONTRACT["features"]:
            raise ModelIntegrityError(
                "Model feature order mismatch"
            )

        self.manifest = manifest

    def predict(
        self,
        telemetry,
        events=(),
        model_id=None,
        recommendation_version=None,
    ):
        result = assess(
            row=telemetry,
            events=events,
            model_bundle=self.bundle,
            model_id=model_id,
            recommendation_version=recommendation_version,
        )

        return {
            "model_id": result["model_id"],
            "status": result["status"],
            "predicted_level": result["predicted_level"],
            "effective_level": result["effective_level"],
            "factors": result["factors"],
            "reason_code": result["reason_code"],
            "recommendation_version":
                result["recommendation_version"],
        }
