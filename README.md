# Smart Hardhat

An IoT-based construction site safety monitoring system (FYP F26-113, FAST-NU Lahore).

A removable hardhat module monitors **CO, temperature, humidity, motion (fall detection), battery and GPS**. It has a guarded **SOS** button and local light, vibration and sound alerts that work without a network. Data travels over **LoRa** to an ESP32 gateway, then to a local **FastAPI + PostgreSQL** backend and a **Next.js** supervisor dashboard. A decision-tree model provides advisory risk assessments.

## Architecture

```
Hardhat (ESP32 + sensors) --LoRa--> Gateway (ESP32) --HTTPS--> FastAPI --> PostgreSQL
                                                                  |
                                                     Next.js dashboard (SSE)
```

## Stack

- **Firmware:** ESP-IDF (ESP32-S3 + SX1262), AES-GCM radio framing
- **Backend:** Python, FastAPI, PostgreSQL, scikit-learn
- **Frontend:** Next.js
- **Deployment:** local network behind a TLS reverse proxy (no cloud)

## Running locally (Windows / PowerShell)

**One-time setup**

1. Copy `.env.example` to `.env` (repo root) and fill in the DB values, `SESSION_SECRET` and `MOCK_ACCOUNT_PASSWORD`.
2. Backend packages: `cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt`
3. Frontend packages: `cd frontend; npm install` (optional `frontend/.env.local` with `BACKEND_URL`, default `http://127.0.0.1:8000`)
4. Create the tables: `cd backend; .venv\Scripts\alembic upgrade head`

**Each session** (separate terminals)

```powershell
docker compose up -d                                          # 1. DB (repo root), Postgres on 127.0.0.1:5433
cd backend; .venv\Scripts\python -m scripts.seed_mock_data --reset   # 2. optional: fresh mock data
cd backend; .venv\Scripts\uvicorn app.main:app --reload --port 8000  # 3. API (docs at /docs)
cd frontend; npm run dev                                      # 4. Dashboard at http://localhost:3000
```

Sign in as `sana.iqbal@mock.smarthardhat.test` (supervisor) with your `MOCK_ACCOUNT_PASSWORD`.
Mock data goes stale about 3 min after seeding; rerun step 2 for fresh timestamps.
Tests: `cd backend; .venv\Scripts\python -m pytest -q`. More detail is in `backend/README.md`.

## Docs

- `F26-113.pdf`: full requirements and design (Deliverable II)
- `PROJECT_OVERVIEW.txt`: condensed design and current implementation status

## Team

Hamza Azam, Muzzammil Shahid and Roshni Waheed. Supervisor: Mr. Saifullah Tanvir.

> Prototype for controlled evaluation only. It makes no claim of certified protective performance.
