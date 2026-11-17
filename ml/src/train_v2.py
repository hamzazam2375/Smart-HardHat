
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)

from .validation import FEATURES, CONTRACT

DATA_PATH = Path("data/synthetic_experiment.csv")
MODEL_PATH = Path("artifacts/risk_forest_v2.joblib")
REPORT_PATH = Path("reports/evaluation_v2.json")

LABELS = CONTRACT["labels"]


def main():
    df = pd.read_csv(DATA_PATH)

    # Reproduce the original held-out session split
    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=0.25,
        random_state=42,
    )

    train_idx, test_idx = next(
        splitter.split(
            df[FEATURES],
            df["label"],
            df["session_id"],
        )
    )

    train = df.iloc[train_idx]
    test = df.iloc[test_idx]

    model = RandomForestClassifier(
        n_estimators=150,
        max_depth=10,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    model.fit(train[FEATURES], train["label"])

    predictions = model.predict(test[FEATURES])

    ranks = {label: i for i, label in enumerate(LABELS)}
    actual_rank = test["label"].map(ranks).to_numpy()
    predicted_rank = pd.Series(predictions).map(ranks).to_numpy()

    report = {
        "model": "random_forest_v2",
        "dataset_type": "synthetic_scenario_assumptions_only",
        "feature_schema_version": "1.0.0",
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_sessions": int(train["session_id"].nunique()),
        "test_sessions": int(test["session_id"].nunique()),
        "session_overlap": int(
            len(
                set(train["session_id"])
                & set(test["session_id"])
            )
        ),
        "metrics": {
            "accuracy": float(
                accuracy_score(test["label"], predictions)
            ),
            "macro_f1": float(
                f1_score(
                    test["label"],
                    predictions,
                    labels=LABELS,
                    average="macro",
                    zero_division=0,
                )
            ),
            "underestimation_rate": float(
                np.mean(predicted_rank < actual_rank)
            ),
            "critical_underestimated": int(
                np.sum(
                    (test["label"].to_numpy() == "critical")
                    & (predicted_rank < actual_rank)
                )
            ),
            "classification_report": classification_report(
                test["label"],
                predictions,
                labels=LABELS,
                output_dict=True,
                zero_division=0,
            ),
            "confusion_matrix": confusion_matrix(
                test["label"],
                predictions,
                labels=LABELS,
            ).tolist(),
        },
        "feature_importance": dict(
            zip(
                FEATURES,
                map(float, model.feature_importances_),
            )
        ),
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Preserve the same model-bundle structure
    # expected by our existing inference component.
    bundle = {
        "model": model,
        "features": FEATURES,
        "feature_schema_version": "1.0.0",
        "model_name": "risk_forest_v2",
    }

    joblib.dump(bundle, MODEL_PATH)

    REPORT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\nMODEL V2 RESULTS")
    print(f"Accuracy: {report['metrics']['accuracy']:.4f}")
    print(f"Macro-F1: {report['metrics']['macro_f1']:.4f}")
    print(
        "Underestimation rate: "
        f"{report['metrics']['underestimation_rate']:.4f}"
    )
    print(
        "Critical underestimated: "
        f"{report['metrics']['critical_underestimated']}"
    )

    print("\nPER-CLASS PERFORMANCE")
    print(
        classification_report(
            test["label"],
            predictions,
            labels=LABELS,
            zero_division=0,
        )
    )

    print("\nFEATURE IMPORTANCE")
    for feature, importance in sorted(
        report["feature_importance"].items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        print(f"{feature}: {importance:.4f}")

    print(f"\nModel saved: {MODEL_PATH}")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
