"""API tests for the thin read backend (auth + overview). Each test runs in one transaction
that is rolled back, so the dev database is untouched. Needs the DB up at head."""
import json
import uuid

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import flags
from app.db import engine, get_conn
from app.main import app
from app.services.overview import classify

PW = "correct horse battery"


@pytest.fixture
def conn():
    with engine.connect() as c:
        tx = c.begin()
        try:
            yield c
        finally:
            tx.rollback()


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def ins(conn, table, **cols):
    keys = ", ".join(cols)
    vals = ", ".join(f":{k}" for k in cols)
    return conn.execute(text(f"INSERT INTO {table} ({keys}) VALUES ({vals}) RETURNING *"), cols).first()[0]


def account(conn, role="supervisor", enabled=True):
    email = f"{uuid.uuid4().hex[:10]}@test.local"
    aid = ins(conn, "account", email=email, display_name="Test User", role=role, enabled=enabled,
              password_hash=PasswordHasher().hash(PW))
    return aid, email


def sign_in(client, email, password=PW):
    return client.post("/api/auth/session", json={"email": email, "password": password})


def auth(client, conn, role="supervisor"):
    _, email = account(conn, role)
    return {"Authorization": f"Bearer {sign_in(client, email).json()['token']}"}


# ---------------------------------------------------------------- auth -----
def test_sign_in_and_session(client, conn):
    _, email = account(conn)
    r = sign_in(client, email.upper())
    assert r.status_code == 200
    body = r.json()
    assert body["account"]["email"] == email and body["account"]["role"] == "supervisor"
    me = client.get("/api/auth/session", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200 and me.json()["account"]["email"] == email


def test_sign_in_failures_share_one_message(client, conn):
    _, email = account(conn)
    _, disabled = account(conn, enabled=False)
    results = [sign_in(client, email, "wrong"), sign_in(client, disabled), sign_in(client, "nobody@test.local")]
    assert {r.status_code for r in results} == {401}
    assert len({r.json()["detail"] for r in results}) == 1


def test_session_revoked_by_version_bump_and_bad_token(client, conn):
    aid, email = account(conn)
    token = sign_in(client, email).json()["token"]
    conn.execute(text("UPDATE account SET session_version = session_version + 1 WHERE account_id = :a"), {"a": aid})
    assert client.get("/api/auth/session", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/auth/session", headers={"Authorization": "Bearer x.y"}).status_code == 401


def test_overview_requires_supervisor(client, conn):
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers=auth(client, conn, "admin")).status_code == 403
    assert client.get("/api/events", headers=auth(client, conn, "admin_supervisor")).status_code == 200


# ------------------------------------------------------------- overview ----
@pytest.fixture
def graph(conn):
    acc, _ = account(conn, "admin")
    wid = ins(conn, "worker", worker_code=f"T-{uuid.uuid4().hex[:6]}", display_name="Worker One", created_by=acc)
    dev = ins(conn, "device", radio_id=990001, label="T-HAT-1", hardware_revision="A",
              firmware_version="0.1", key_slot_reference="slot")
    never = ins(conn, "device", radio_id=990002, label="T-HAT-2", hardware_revision="A",
                firmware_version="0.1", key_slot_reference="slot")
    gw = ins(conn, "gateway", gateway_code="T-GW-1", credential_reference="c", firmware_version="0.1")
    cfg = ins(conn, "configuration", config_version=f"t-{uuid.uuid4().hex[:6]}", checksum="c",
              thresholds="{}", timings="{}")
    asg = conn.execute(text("INSERT INTO assignment (worker_id, device_id, start_at, created_by)"
                            " VALUES (:w, :d, now() - interval '1 hour', :a) RETURNING assignment_id"),
                       {"w": wid, "d": dev, "a": acc}).scalar()
    return dict(acc=acc, dev=dev, never=never, gw=gw, cfg=cfg, asg=asg)


def test_status_keeps_invalid_missing_and_never_reported_distinct(client, conn, graph):
    tid = ins(conn, "telemetry", device_id=graph["dev"], gateway_id=graph["gw"], boot_epoch=1, packet_seq=1,
              time_quality="estimated", config_id=graph["cfg"], assignment_id=graph["asg"],
              co_valid_count=0, expected_count=60, temperature_c=18.0, humidity_pct=50,
              accel_peak_g=None, motion_flags=0, battery_pct=None,
              validity_flags=flags.CO_INVALID | flags.HEAT_UNSUPPORTED | flags.IMU_INVALID
              | flags.BATTERY_UNAVAILABLE | flags.GPS_NO_FIX)
    conn.execute(text("INSERT INTO device_status_snapshot (device_id, telemetry_id, boot_epoch, packet_seq,"
                      " time_quality, received_at) VALUES (:d, :t, 1, 1, 'estimated', now())"),
                 {"d": graph["dev"], "t": tid})
    ins(conn, "risk_assessment", telemetry_id=tid, status="unavailable", reason_code="missing_input")

    r = client.get("/api/status", headers=auth(client, conn))
    assert r.status_code == 200
    devs = {d["label"]: d for d in r.json()["devices"]}
    d = devs["T-HAT-1"]
    assert d["worker"]["name"] == "Worker One" and d["timeQuality"] == "estimated"
    assert d["co"] == {"value": None, "quality": "invalid"}
    assert d["temperature"] == {"value": 18.0, "quality": "valid"}
    assert d["heatIndex"]["quality"] == "unsupported"
    assert d["motion"] == {"state": None, "quality": "invalid"}
    assert d["battery"]["quality"] == "missing"
    assert d["gps"]["state"] == "no_fix"
    assert d["risk"] == {"state": "unavailable", "reason": "Required input missing or invalid"}
    n = devs["T-HAT-2"]
    assert n["receivedAt"] is None and n["worker"] is None and n["co"]["quality"] == "missing"


def test_events_lists_unresolved_with_separate_acks(client, conn, graph):
    def event(etype, state, local="active", **ev):
        return ins(conn, "event", source_event_key=f"t:{uuid.uuid4()}", device_id=graph["dev"],
                   assignment_id=graph["asg"], event_type=etype, time_quality="trusted",
                   evidence=json.dumps(ev), workflow_state=state, local_state=local)
    acked = event("co", "acknowledged", "physically_acknowledged", level="urgent", snapshot={"co_ppm": 236})
    ins(conn, "alert_action", event_id=acked, actor_id=graph["acc"], action_type="acknowledge")
    event("sos", "resolved", "cleared")

    alerts = client.get("/api/events", headers=auth(client, conn)).json()["alerts"]
    mine = [a for a in alerts if a["deviceLabel"] == "T-HAT-1"]
    assert len(mine) == 1
    a = mine[0]
    assert (a["type"], a["priority"], a["state"]) == ("co_urgent", 1, "acknowledged")
    assert a["localState"] == "physically_acknowledged" and a["supervisorAck"]["by"] == "Test User"
    assert "236 ppm" in a["detail"]


def test_classify_is_conservative():
    assert classify("co", {}) == ("co_urgent", 1)          # unknown CO level -> urgent
    assert classify("co", {"level": "warning"}) == ("co_warning", 4)
    assert classify("battery", {"level": "critical"}) == ("battery_critical", 5)
    assert classify("possible_fall", {}) == ("possible_fall", 1)
