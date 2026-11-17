
from pathlib import Path

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

DATA_PATH = Path("data/synthetic_experiment.csv")


def main():
    df = pd.read_csv(DATA_PATH)

    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=0.25,
        random_state=42
    )

    train_idx, test_idx = next(
        splitter.split(
            df,
            df["label"],
            df["session_id"]
        )
    )

    train = df.iloc[train_idx]
    test = df.iloc[test_idx]

    print("\nDATASET OVERVIEW")
    print(f"Total rows: {len(df)}")
    print(f"Total sessions: {df['session_id'].nunique()}")

    print("\nTRAIN LABEL DISTRIBUTION")
    print(train["label"].value_counts().to_string())

    print("\nTEST LABEL DISTRIBUTION")
    print(test["label"].value_counts().to_string())

    print("\nTRAIN SCENARIO DISTRIBUTION")
    print(train["scenario"].value_counts().to_string())

    print("\nTEST SCENARIO DISTRIBUTION")
    print(test["scenario"].value_counts().to_string())

    print("\nSCENARIO x LABEL (TRAIN)")
    print(pd.crosstab(train["scenario"], train["label"]))

    print("\nSCENARIO x LABEL (TEST)")
    print(pd.crosstab(test["scenario"], test["label"]))

    print("\nSESSION OVERLAP")
    overlap = set(train["session_id"]) & set(test["session_id"])
    print(f"Overlapping sessions: {len(overlap)}")


if __name__ == "__main__":
    main()
