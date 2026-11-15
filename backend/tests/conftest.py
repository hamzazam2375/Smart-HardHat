"""Schema test fixtures.

Each test runs inside one transaction that is always rolled back, so the tests can
run against the dev database without leaving rows behind. Requires the Docker DB
to be up and `alembic upgrade head` to have been applied.
"""
import uuid

import psycopg
import pytest

from app.db_url import database_url


def _conninfo() -> str:
    u = database_url()
    return psycopg.conninfo.make_conninfo(
        host=u.host, port=u.port, user=u.username, password=u.password,
        dbname=u.database, connect_timeout=5,
    )


@pytest.fixture
def db():
    with psycopg.connect(_conninfo()) as conn:
        try:
            yield conn
        finally:
            conn.rollback()


def insert(conn, table: str, **cols):
    """INSERT one row and return its first column (the primary key)."""
    names = ", ".join(cols)
    marks = ", ".join(["%s"] * len(cols))
    return conn.execute(
        f"INSERT INTO {table} ({names}) VALUES ({marks}) RETURNING *",
        list(cols.values()),
    ).fetchone()[0]


def rejects(conn, error, sql, params=None):
    """Assert the statement fails with `error`; a savepoint keeps the outer txn usable."""
    with pytest.raises(error):
        with conn.transaction():
            conn.execute(sql, params)


@pytest.fixture
def base(db):
    """Minimal valid graph: account, 2 workers, 2 devices, gateway, active config."""
    j = psycopg.types.json.Jsonb
    acc = insert(db, "account", email=f"{uuid.uuid4().hex[:8]}@test.local",
                 display_name="Tester", password_hash="$argon2id$x", role="admin")
    w1 = insert(db, "worker", worker_code=f"T-{uuid.uuid4().hex[:6]}", display_name="W1", created_by=acc)
    w2 = insert(db, "worker", worker_code=f"T-{uuid.uuid4().hex[:6]}", display_name="W2", created_by=acc)
    d1 = insert(db, "device", radio_id=900001, label="T-HAT-1", hardware_revision="A",
                firmware_version="0.1", key_slot_reference="slot-1")
    d2 = insert(db, "device", radio_id=900002, label="T-HAT-2", hardware_revision="A",
                firmware_version="0.1", key_slot_reference="slot-2")
    gw = insert(db, "gateway", gateway_code="T-GW-1", credential_reference="cred-1",
                firmware_version="0.1")
    cfg = insert(db, "configuration", config_version=f"t-{uuid.uuid4().hex[:6]}", checksum="c",
                 thresholds=j({"co_urgent_ppm": 200}), timings=j({"summary_s": 60}))
    return dict(account=acc, w1=w1, w2=w2, d1=d1, d2=d2, gateway=gw, config=cfg)
