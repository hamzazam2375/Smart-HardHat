"""Create an explicitly SYNTHETIC scenario dataset. Labels are scenario assumptions, not clinical/safety ground truth."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from .validation import FEATURES

def build(n_sessions=120, windows_per_session=12, seed=42):
    rng = np.random.default_rng(seed)
    rows=[]
    for session in range(n_sessions):
        # Session-level latent hazard; prevents random-row leakage in evaluation.
        kind = rng.choice(["normal", "co_rise", "heat", "motion", "combined"], p=[.35,.18,.18,.18,.11])
        severity = rng.uniform(.25,1)
        for minute in range(windows_per_session):
            co = max(0, rng.normal(4, 2)); temp = rng.normal(25, 3); rh = rng.uniform(35,75)
            accel = rng.uniform(1.05,2.0); orient = rng.uniform(3,40); inactive = rng.uniform(1000,24000)
            if kind in ("co_rise","combined"):
                co += severity * rng.uniform(22,85) * (0.55 + 0.45 * minute/max(1,windows_per_session-1))
            if kind in ("heat","combined"):
                temp += severity * rng.uniform(8,16); rh += severity * rng.uniform(0,8)
            if kind in ("motion","combined"):
                accel += severity * rng.uniform(1.5,5.5)
                orient += severity * rng.uniform(25,85)
                inactive += severity * rng.uniform(12000,35000)
            rh = float(np.clip(rh,5,95)); accel=float(np.clip(accel,0,16)); orient=float(np.clip(orient,0,180))
            inactive=float(np.clip(inactive,0,60000)); temp=float(np.clip(temp,0,50))
            # Deliberately simplified apparent-heat proxy, not the firmware's NWS heat-index algorithm.
            heat=float(np.clip(temp + max(0,temp-26)*rh/110,0,75))
            co_latest=float(np.clip(co+rng.normal(0,1.5),0,150)); co_mean=float(np.clip(co+rng.normal(0,1),0,150))
            co_max=float(np.clip(max(co_latest,co_mean)+abs(rng.normal(1.5,1.2)),0,150))
            score=max(co_max/35, max(0,heat-27)/9, max(0,accel-1.8)/3 + max(0,orient-40)/120)
            label="low" if score<.55 else "moderate" if score<1.05 else "high" if score<1.9 else "critical"
            # Labels intentionally derived from synthetic scenario severity: do not claim independent validation.
            rows.append(dict(session_id=f"sim-{session:04d}",source_type="synthetic",scenario=kind,
                             label=label,co_latest=round(co_latest,2),co_mean=round(co_mean,2),co_max=round(co_max,2),
                             temperature_c=round(temp,2),humidity_pct=round(rh,2),heat_index_c=round(heat,2),
                             accel_peak_g=round(accel,3),orientation_change_deg=round(orient,2),inactivity_ms=round(inactive)))
    return pd.DataFrame(rows)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--output",default="data/synthetic_experiment.csv")
    args=parser.parse_args(); path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    df=build(); df.to_csv(path,index=False); print(f"Created {len(df)} synthetic rows across {df.session_id.nunique()} sessions: {path}")
if __name__=="__main__": main()
