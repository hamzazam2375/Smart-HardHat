"""SQLAlchemy engine and the per-request connection dependency."""
from collections.abc import Iterator

from sqlalchemy import Connection, create_engine

from app.db_url import database_url

engine = create_engine(database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 5})


def get_conn() -> Iterator[Connection]:
    """One transaction per request: committed on success, rolled back on error."""
    with engine.begin() as conn:
        yield conn
