"""App settings from the repo-root .env (loaded by app.db_url). No secrets in source."""
import os
import secrets
import sys

import app.db_url  # noqa: F401  (loads the repo-root .env)

PRODUCTION = os.getenv("APP_ENV", "development") == "production"
SITE_NAME = os.getenv("SITE_NAME", "Prototype trial site")
STALE_AFTER_S = 180          # F26-113: stale after 3 missed 60 s status intervals
SESSION_MAX_AGE_S = 8 * 60 * 60   # one shift


def _session_secret() -> bytes:
    value = os.getenv("SESSION_SECRET", "")
    if len(value) >= 32:
        return value.encode()
    if PRODUCTION:
        raise RuntimeError("SESSION_SECRET (32+ chars) must be set in production")
    # Dev fallback: random per process, so restarting the API signs everyone out.
    print("WARNING: SESSION_SECRET not set; using a random dev key.", file=sys.stderr)
    return secrets.token_bytes(32)


SESSION_SECRET = _session_secret()
