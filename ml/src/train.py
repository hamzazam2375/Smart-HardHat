import argparse
import json
from pathlib import Path
import joblib
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from .validation import CONTRACT, FEATURES

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--data",default="data/synthetic_experiment.csv")
    parser.add_argument("--artifact",default="artifacts/risk_tree_v1.joblib")
    parser.add_argument("--report",default="reports/evaluation_v1.json")
    args=parser.parse_args()
    df=pd.read_csv(args.data)
    needed=FEATURES+["label","session_id","source_type"]
    missing=[k for k in needed if k not in df]
    if missing: raise ValueError(f"Missing dataset columns: {missing}")
    if not set(df.source_type).issubset({"synthetic"}):
        raise ValueError("Starter trainer is synthetic-only; physical data requires a separate reviewed evaluation plan")
    if df[needed].isna().any().any(): raise ValueError("Missing features/labels; do not silently impute")
    X=df[FEATURES]; y=df.label; groups=df.session_id
    splitter=GroupShuffleSplit(n_splits=1,test_size=.25,random_state=42)
    tr,te=next(splitter.split(X,y,groups))
    baseline=DummyClassifier(strategy="most_frequent").fit(X.iloc[tr],y.iloc[tr])
    tree=DecisionTreeClassifier(max_depth=5,min_samples_leaf=15,class_weight="balanced",random_state=42).fit(X.iloc[tr],y.iloc[tr])
    labels=CONTRACT["labels"]
    results={"dataset_type":"synthetic_scenario_assumptions_only", "feature_schema_version":CONTRACT["schema_version"],
             "train_rows":len(tr),"test_rows":len(te),"train_sessions":int(groups.iloc[tr].nunique()),
             "test_sessions":int(groups.iloc[te].nunique()),"holdout_group_overlap":len(set(groups.iloc[tr]) & set(groups.iloc[te])),
             "models":{}}
    for name,model in (("dummy",baseline),("decision_tree",tree)):
        pred=model.predict(X.iloc[te]); truth=y.iloc[te]
        results["models"][name]={"macro_f1":float(f1_score(truth,pred,labels=labels,average="macro",zero_division=0)),
                                  "confusion_matrix":confusion_matrix(truth,pred,labels=labels).tolist(),
                                  "classification_report":classification_report(truth,pred,labels=labels,output_dict=True,zero_division=0)}
    artifact=Path(args.artifact); artifact.parent.mkdir(parents=True,exist_ok=True)
    joblib.dump({"model":tree,"features":FEATURES,"schema_version":CONTRACT["schema_version"]},artifact)
    report=Path(args.report); report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(results,indent=2)); print(json.dumps({"artifact":str(artifact),"report":str(report),"macro_f1":{k:v["macro_f1"] for k,v in results["models"].items()}},indent=2))
if __name__=="__main__": main()
