
from pathlib import Path

import joblib
import pandas as pd
from sklearn.tree import export_text

from .validation import FEATURES

MODEL_PATH = Path("artifacts/risk_tree_v1.joblib")
OUTPUT_PATH = Path("reports/tree_rules_v1.txt")


def main():
    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]

    # Display importance of every input feature
    importance = pd.DataFrame({
        "feature": FEATURES,
        "importance": model.feature_importances_
    }).sort_values("importance", ascending=False)

    print("\nFEATURE IMPORTANCE")
    print(importance.to_string(index=False))

    # Display learned decision rules
    rules = export_text(
        model,
        feature_names=FEATURES,
        max_depth=5
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )
    OUTPUT_PATH.write_text(rules, encoding="utf-8")

    print("\nDECISION TREE RULES")
    print(rules)

    print(f"\nSaved rules to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
