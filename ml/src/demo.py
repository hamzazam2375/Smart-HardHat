from datetime import datetime, timedelta, timezone
from uuid import uuid4
from .generate_experiment import build
from .inference import assess, load_bundle

def main():
    data=build(n_sessions=1,windows_per_session=1)
    row=data.iloc[0].to_dict(); now=datetime.now(timezone.utc)
    row.update(window_start=now-timedelta(seconds=60),window_end=now,time_quality="trusted",co_valid_count=60,expected_count=60,validity_flags=0)
    bundle=load_bundle("artifacts/risk_tree_v1.joblib")
    model_id=str(uuid4()) # DEMO placeholder, not a registered database model ID
    print("Normal:",assess(row,model_bundle=bundle,model_id=model_id))
    print("Missing CO:",assess({**row,"co_mean":None},model_bundle=bundle,model_id=model_id))
    events=[{"event_type":"sos","local_state":"active","workflow_state":"acknowledged","source_event_key":"demo:sos:1"}]
    print("SOS override:",assess({**row,"co_mean":None},events,model_bundle=bundle,model_id=model_id))
if __name__=="__main__": main()
