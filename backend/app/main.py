"""FastAPI app. Run from backend/:  .venv\\Scripts\\uvicorn app.main:app --reload --port 8000

API for all dashboard pages (Sign-in, Overview, Alerts, Alert detail, Workers/assignments,
History, Device health, Configuration review, Accounts).
Ingestion, SSE and the risk service come later.
"""
from fastapi import Depends, FastAPI
from sqlalchemy import Connection, text

from app.db import get_conn
from app.routes import accounts, assignments, auth, configuration, devices, events, history, overview, workers

app = FastAPI(title="Smart Hardhat API", version="0.1.0")
app.include_router(auth.router)
app.include_router(overview.router)
app.include_router(events.router)
app.include_router(workers.router)
app.include_router(assignments.router)
app.include_router(history.router)
app.include_router(devices.router)
app.include_router(configuration.router)
app.include_router(accounts.router)


@app.get("/api/health", tags=["health"])
def health(conn: Connection = Depends(get_conn)):
    conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
