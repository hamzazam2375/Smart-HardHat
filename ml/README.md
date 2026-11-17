# Smart Hard Hat ML starter (backend migration 0001 compatible)

## Scope
This is a standalone ML proof-of-concept that respects the existing PostgreSQL field names, risk-assessment statuses and reason codes. It does **not** write to the database or claim actual safety performance. The dataset is **synthetic** and labels are generated from synthetic scenario assumptions. Do not train using the teammate's seeded `risk_assessment.predicted_level` as ground truth.

## Windows PowerShell
From the `ml` folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m src.generate_experiment
python -m src.train
python -m pytest -q
python -m src.demo
```

If PowerShell refuses activation, use `.\.venv\Scripts\python.exe` instead of `python` and skip activation.

## Interface
`src.inference.assess(row, events, model_bundle, model_id, recommendation_version)` returns fields matching the `risk_assessment` migration. `model_id` must be the UUID of a **real registered** `model_version` row when persisting. `telemetry_id` is added by the backend caller. Never persist the random demo UUID. The backend should validate model artifact checksums, invoke after accepted telemetry commit, and use the authoritative current event state. Historical events alone are insufficient to establish whether an emergency is active.

## Fixed backend conventions
- CO ppm: `co_latest`, `co_mean`, `co_max`; temperature C; humidity percent; heat index C; acceleration g; orientation degrees; inactivity milliseconds.
- 60-second summaries; `time_quality` values `trusted`, `estimated`, `unknown`.
- Risk statuses `available`, `unavailable`, `failed`; reason codes `missing_input`, `unsupported_range`, `model_error`, `no_active_model`.
- The `model_version` registry needs artifact path, checksum, schema version, training provenance, validation envelope, evaluation reference and state.

## Provisional choices to review before real hardware
- Require all nine features, CO valid sample fraction >= 0.8, time quality trusted or estimated, exactly ~60-second window.
- Heat index unsupported -> unavailable. This is conservative, but will exclude many cool normal windows in the teammate's mock data. A later model version could handle heat-index absence with a separately evaluated strategy.
- Validity/motion bit assignments are **mock conventions**, not final firmware protocol.
- Envelope ranges are demonstration bounds, not validated hardware operating limits.
- A database `event` is not automatically an active urgent condition; only locally active urgent events (or unresolved unknown states) override.

## Next integration step
Have the backend team implement an adapter that fetches a telemetry row, determines active urgent events, retrieves an active verified model artifact, calls `assess`, and inserts into `risk_assessment`. Avoid loading untrusted joblib files. Keep urgent-event delivery independent of inference. Add DB integration tests before production use.
