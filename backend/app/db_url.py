"""Database URL resolution shared by Alembic migrations and tests.

Reads DATABASE_URL from the repo-root .env (never hard-coded; no secrets in source).
If DATABASE_URL is missing, it is built from POSTGRES_* on 127.0.0.1:5433
(docker-compose.yml). "localhost" is rewritten to 127.0.0.1 because Docker binds IPv4
only and Windows tries IPv6 (::1) first, stalling every connection.
"""
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


def database_url(driver: str = "postgresql+psycopg") -> URL:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url.startswith("postgres"):
        user = os.environ["POSTGRES_USER"]
        pwd = quote_plus(os.environ["POSTGRES_PASSWORD"])
        db = os.environ["POSTGRES_DB"]
        host = os.getenv("POSTGRES_HOST", "127.0.0.1")
        port = os.getenv("POSTGRES_PORT", "5433")
        url = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
    u = make_url(url).set(drivername=driver)
    if u.host in (None, "localhost"):
        u = u.set(host="127.0.0.1")
    return u
