"""FastAPI app. Run from backend/:  .venv\\Scripts\\uvicorn app.main:app --reload --port 8000

Thin read-only API for the built pages (Sign-in, Overview). Ingestion, alert actions,
SSE and the risk service come later.
"""
from fastapi import Depends, FastAPI
from sqlalchemy import Connection, text

from app.db import get_conn
from app.routes import auth, overview

app = FastAPI(title="Smart Hardhat API", version="0.1.0")
app.include_router(auth.router)
app.include_router(overview.router)


@app.get("/api/health", tags=["health"])
def health(conn: Connection = Depends(get_conn)):
    conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
