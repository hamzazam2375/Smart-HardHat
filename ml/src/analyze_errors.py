
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from .validation import FEATURES, CONTRACT

DATA_PATH = Path("data/synthetic_experiment.csv")
MODEL_PATH = Path("artifacts/risk_tree_v1.joblib")
OUTPUT_PATH = Path("reports/error_analysis_v1.csv")


def main():
    # 1. Load dataset and trained model
    df = pd.read_csv(DATA_PATH)
    bundle = joblib.load(MODEL_PATH)

    # 2. Reproduce the session-grouped test split
    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=0.25,
        random_state=42
    )

    _, test_idx = next(
        splitter.split(
            df[FEATURES],
            df["label"],
            df["session_id"]
        )
    )

    test = df.iloc[test_idx].copy()

    # 3. Predict on held-out sessions
    test["prediction"] = bundle["model"].predict(
        test[FEATURES]
    )

    # 4. Convert risk levels to numerical severity
    levels = {
        label: i
        for i, label in enumerate(CONTRACT["labels"])
    }

    test["actual_rank"] = test["label"].map(levels)
    test["predicted_rank"] = test["prediction"].map(levels)

    # 5. Detect underestimation
    test["underestimated"] = (
        test["predicted_rank"] < test["actual_rank"]
    )

    test["underestimation_steps"] = (
        test["actual_rank"] - test["predicted_rank"]
    ).clip(lower=0)

    # 6. Save individual predictions for inspection
    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )
    test.to_csv(OUTPUT_PATH, index=False)

    # 7. Calculate safety-oriented metrics
    critical_mask = test["label"] == "critical"
    elevated_mask = test["label"].isin(
        ["moderate", "high", "critical"]
    )

    summary = {
        "test_rows": int(len(test)),
        "underestimated_rows": int(
            test["underestimated"].sum()
        ),
        "underestimation_rate": round(
            float(test["underestimated"].mean()), 4
        ),
        "critical_underestimated": int(
            (critical_mask & test["underestimated"]).sum()
        ),
        "critical_total": int(critical_mask.sum()),
        "elevated_risk_predicted_low": int(
            (
                elevated_mask
                & (test["prediction"] == "low")
            ).sum()
        ),
        "high_or_critical_predicted_low": int(
            (
                test["label"].isin(["high", "critical"])
                & (test["prediction"] == "low")
            ).sum()
        ),
        "underestimation_by_class": {
            label: {
                "total": int((test["label"] == label).sum()),
                "underestimated": int(
                    (
                        (test["label"] == label)
                        & test["underestimated"]
                    ).sum()
                )
            }
            for label in CONTRACT["labels"]
        }
    }

    # 8. Save the summary
    summary_path = Path(
        "reports/error_summary_v1.json"
    )
    summary_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8"
    )

    print(json.dumps(summary, indent=2))
    print(f"\nDetailed report: {OUTPUT_PATH}")
    print(f"Summary report: {summary_path}")


if __name__ == "__main__":
    main()
