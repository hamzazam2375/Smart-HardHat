"""Password checks (Argon2id) and signed session tokens.

Token = base64url(json{a: account_id, v: session_version, e: expiry epoch s}) + "." + HMAC-SHA256.
No session table: revocation works by bumping account.session_version (DB decision).
"""
import base64
import hashlib
import hmac
import json
import time

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

from app.config import SESSION_MAX_AGE_S, SESSION_SECRET

_hasher = PasswordHasher()
_dummy_hash: str | None = None


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-ish time: an unknown account still runs one Argon2 verify (UC-01, no enumeration)."""
    global _dummy_hash
    if password_hash is None:
        _dummy_hash = _dummy_hash or _hasher.hash("not-a-real-password")
    try:
        _hasher.verify(password_hash or _dummy_hash, password)
    except Argon2Error:
        return False
    return password_hash is not None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(data: str) -> str:
    return _b64(hmac.new(SESSION_SECRET, data.encode(), hashlib.sha256).digest())


def issue_token(account_id: str, session_version: int) -> tuple[str, int]:
    expires = int(time.time()) + SESSION_MAX_AGE_S
    data = _b64(json.dumps({"a": account_id, "v": session_version, "e": expires}).encode())
    return f"{data}.{_sign(data)}", expires


def read_token(token: str) -> dict | None:
    """Payload if the signature is valid and the token has not expired, else None."""
    data, _, sig = token.partition(".")
    if not data or not sig or not hmac.compare_digest(sig, _sign(data)):
        return None
    try:
        payload = json.loads(_unb64(data))
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("e", 0) <= time.time():
        return None
    return payload
