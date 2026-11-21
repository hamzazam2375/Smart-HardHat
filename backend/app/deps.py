"""Auth dependencies: current account from the session token, role checks (Table 4.34)."""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import Connection, text

from app.db import get_conn
from app.security import read_token

SESSION_COOKIE = "hh_session"
SUPERVISOR_ROLES = ("supervisor", "admin_supervisor")
ADMIN_ROLES = ("admin", "admin_supervisor")


def _token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def current_account(request: Request, conn: Connection = Depends(get_conn)) -> dict:
    """Valid session or 401. Disabled accounts and bumped session versions are rejected."""
    token = _token(request)
    payload = read_token(token) if token else None
    if payload:
        row = conn.execute(
            text("SELECT account_id, email, display_name, role, enabled, session_version"
                 " FROM account WHERE account_id = CAST(:id AS uuid)"),
            {"id": payload.get("a")},
        ).mappings().first()
        if row and row["enabled"] and row["session_version"] == payload.get("v"):
            return dict(row)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")


def require_supervisor(account: dict = Depends(current_account)) -> dict:
    """Worker names, readings and locations are for supervisor roles only (Table 4.34)."""
    if account["role"] not in SUPERVISOR_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Supervisor role required")
    return account


def account_json(row: dict) -> dict:
    return {"id": str(row["account_id"]), "email": row["email"], "displayName": row["display_name"],
            "role": row["role"]}


def require_admin(account: dict = Depends(current_account)) -> dict:
    """Device registration/retirement and account administration (Table 4.34, FR-28, FR-29)."""
    if account["role"] not in ADMIN_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required")
    return account
