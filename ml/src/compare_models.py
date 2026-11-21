
import json
from pathlib import Path

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    f1_score,
    recall_score,
    accuracy_score
)

from .validation import FEATURES, CONTRACT

DATA_PATH = Path("data/synthetic_experiment.csv")
OUTPUT_PATH = Path("reports/model_comparison_v2.json")


def evaluate(y_true, y_pred):
    levels = CONTRACT["labels"]
    ranks = {name: i for i, name in enumerate(levels)}

    actual = pd.Series(y_true).map(ranks).to_numpy()
    predicted = pd.Series(y_pred).map(ranks).to_numpy()

    return {
        "macro_f1": float(
            f1_score(
                y_true, y_pred,
                labels=levels,
                average="macro",
                zero_division=0
            )
        ),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "high_recall": float(
            recall_score(
                y_true, y_pred,
                labels=["high"],
                average="macro",
                zero_division=0
            )
        ),
        "critical_recall": float(
            recall_score(
                y_true, y_pred,
                labels=["critical"],
                average="macro",
                zero_division=0
            )
        ),
        "underestimation_rate": float(
            (predicted < actual).mean()
        )
    }


def main():
    df = pd.read_csv(DATA_PATH)

    # Reproduce the original session-level holdout
    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=0.25,
        random_state=42
    )

    train_idx, _ = next(
        splitter.split(
            df[FEATURES],
            df["label"],
            df["session_id"]
        )
    )

    train = df.iloc[train_idx].copy()

    X = train[FEATURES]
    y = train["label"]
    groups = train["session_id"]

    models = {
        "tree_v1_reference": DecisionTreeClassifier(
            max_depth=5,
            min_samples_leaf=15,
            class_weight="balanced",
            random_state=42
        ),
        "tree_depth8": DecisionTreeClassifier(
            max_depth=8,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=42
        ),
        "tree_depth12": DecisionTreeClassifier(
            max_depth=12,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=42
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=150,
            max_depth=10,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1
        )
    }

    cv = GroupKFold(n_splits=5)
    results = {}

    for name, model in models.items():
        fold_results = []

        for train_fold, val_fold in cv.split(X, y, groups):
            X_train = X.iloc[train_fold]
            X_val = X.iloc[val_fold]
            y_train = y.iloc[train_fold]
            y_val = y.iloc[val_fold]

            model.fit(X_train, y_train)
            predictions = model.predict(X_val)

            fold_results.append(
                evaluate(y_val, predictions)
            )

        metrics = pd.DataFrame(fold_results)

        results[name] = {
            "mean": metrics.mean().round(4).to_dict(),
            "std": metrics.std().round(4).to_dict()
        }

        print(f"\n{name}")
        print(metrics.mean().round(4).to_string())

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )
    OUTPUT_PATH.write_text(
        json.dumps(results, indent=2),
        encoding="utf-8"
    )

    print(f"\nSaved comparison to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
