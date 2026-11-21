"""/api/auth/session: sign in, current session, sign out (UC-01, UC-02)."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.db import get_conn
from app.deps import account_json, current_account
from app.security import issue_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# One message for unknown account, wrong password and disabled account (UC-01).
GENERAL_ERROR = "Sign-in failed"


class SignIn(BaseModel):
    email: str
    password: str


@router.post("/session")
def sign_in(body: SignIn, conn: Connection = Depends(get_conn)):
    email = body.email.strip().lower()
    row = conn.execute(
        text("SELECT account_id, email, display_name, role, enabled, session_version, password_hash"
             " FROM account WHERE email = :email"),
        {"email": email},
    ).mappings().first()
    ok = verify_password(row["password_hash"] if row else None, body.password)
    if not row or not ok or not row["enabled"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERAL_ERROR)
    token, expires = issue_token(str(row["account_id"]), row["session_version"])
    conn.execute(
        text("INSERT INTO audit_log (actor_id, resource_type, resource_id, action)"
             " VALUES (:id, 'account', :id, 'auth.sign_in')"),
        {"id": row["account_id"]},
    )
    return {"token": token, "expiresAt": expires, "account": account_json(row)}


@router.get("/session")
def get_session(account: dict = Depends(current_account)):
    return {"account": account_json(account)}


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(account: dict = Depends(current_account)) -> Response:
    # Stateless token: the client drops its cookie. Revoking every session of an account
    # (account.session_version bump) is an admin action, not part of sign-out.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
