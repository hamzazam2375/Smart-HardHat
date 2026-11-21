"""API tests for the alert-detail, workers/assignments, history, device-health, configuration
and accounts routes. Same rolled-back-transaction fixtures as test_api.py; needs the DB at head."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app import flags
from app.services import configuration as cfg_svc
from tests.test_api import account, auth, client, conn, graph, ins, sign_in  # noqa: F401  (fixtures)


def event(conn, g, etype="co", state="open", tq="trusted", assignment=True, detected=True, **ev):
    return ins(conn, "event", source_event_key=f"t:{uuid.uuid4()}", device_id=g["dev"],
               assignment_id=g["asg"] if assignment else None, event_type=etype, time_quality=tq,
               detected_at=datetime.now(timezone.utc) - timedelta(minutes=5) if detected else None,
               evidence=json.dumps(ev), workflow_state=state, local_state="active")


def telemetry(conn, g, device=None, seq=1, snapshot=True, **cols):
    base = dict(device_id=device or g["dev"], gateway_id=g["gw"], boot_epoch=1, packet_seq=seq,
                time_quality="trusted", config_id=g["cfg"], co_valid_count=60, expected_count=60,
                motion_flags=0, validity_flags=0)
    base.update(cols)
    tid = ins(conn, "telemetry", **base)
    if snapshot:
        conn.execute(text("INSERT INTO device_status_snapshot (device_id, telemetry_id, boot_epoch, packet_seq,"
                          " time_quality, received_at) VALUES (:d, :t, 1, :s, 'trusted', now())"
                          " ON CONFLICT (device_id) DO UPDATE SET telemetry_id = EXCLUDED.telemetry_id"),
                     {"d": base["device_id"], "t": tid, "s": seq})
    return tid


def audits(conn, resource_id, action):
    return conn.execute(text("SELECT count(*) FROM audit_log WHERE resource_id = :r AND action = :a"),
                        {"r": resource_id, "a": action}).scalar()


# --------------------------------------------------------- alert detail ---
def test_event_detail_labels_missing_context(client, conn, graph):
    telemetry(conn, graph, latitude=31.5, longitude=74.3, gps_fix_age_s=4, snapshot=False)
    eid = event(conn, graph, "co", tq="unknown", assignment=False, detected=False, level="urgent",
                snapshot={"co_ppm": None, "temperature_c": 30.0}, validity_flags=flags.CO_INVALID)
    h = auth(client, conn)
    assert client.get(f"/api/events/{uuid.uuid4()}", headers=h).status_code == 404
    assert client.get("/api/events/not-a-uuid", headers=h).status_code == 404

    r = client.get(f"/api/events/{eid}", headers=h)
    assert r.status_code == 200
    a = r.json()["alert"]
    assert a["detectedAt"] is None and a["assignment"]["state"] == "unresolved"
    assert "unknown" in a["assignment"]["reason"].lower()
    assert a["readings"]["co"] == {"value": None, "quality": "invalid"}
    assert a["readings"]["temperature"] == {"value": 30.0, "quality": "valid"}
    assert a["readings"]["battery"]["quality"] == "missing"
    assert a["location"]["state"] == "no_fix" and a["location"]["lastKnown"]["lat"] == 31.5
    assert a["rowVersion"] == 0 and r.json()["actions"] == []


def test_event_detail_requires_supervisor(client, conn, graph):
    eid = event(conn, graph)
    assert client.get(f"/api/events/{eid}").status_code == 401
    assert client.get(f"/api/events/{eid}", headers=auth(client, conn, "admin")).status_code == 403


def test_alert_actions_workflow_and_conflicts(client, conn, graph):
    eid = event(conn, graph, "sos", hold_ms=2100)
    original = conn.execute(text("SELECT evidence, detected_at FROM event WHERE event_id = :e"), {"e": eid}).one()
    h = auth(client, conn)
    url = f"/api/events/{eid}/actions"

    assert client.post(url, json={"action": "resolve", "note": "x", "expectedRowVersion": 0}, headers=h).status_code == 409
    assert client.post(url, json={"action": "note", "note": "  ", "expectedRowVersion": 0}, headers=h).status_code == 422

    r = client.post(url, json={"action": "acknowledge", "expectedRowVersion": 0}, headers=h)
    assert r.status_code == 200
    assert r.json()["alert"]["state"] == "acknowledged" and r.json()["alert"]["rowVersion"] == 1

    stale = client.post(url, json={"action": "acknowledge", "expectedRowVersion": 0}, headers=h)
    assert stale.status_code == 409
    assert stale.json()["detail"]["latest"]["alert"]["state"] == "acknowledged"

    r = client.post(url, json={"action": "note", "note": "Reached worker", "expectedRowVersion": 1}, headers=h)
    assert r.json()["alert"]["state"] == "acknowledged" and r.json()["alert"]["rowVersion"] == 1

    assert client.post(url, json={"action": "resolve", "expectedRowVersion": 1}, headers=h).status_code == 422
    r = client.post(url, json={"action": "resolve", "note": "Worker safe", "expectedRowVersion": 1}, headers=h)
    assert r.json()["alert"]["state"] == "resolved"
    assert [a["type"] for a in r.json()["actions"]] == ["acknowledge", "note", "resolve"]
    assert all(a["by"] == "Test User" for a in r.json()["actions"])

    after = conn.execute(text("SELECT evidence, detected_at, local_state FROM event WHERE event_id = :e"),
                         {"e": eid}).one()
    assert (after.evidence, after.detected_at) == (original.evidence, original.detected_at)
    assert after.local_state == "active"   # dashboard actions never change the hardhat state
    assert audits(conn, eid, "event.resolve") == 1


# ------------------------------------------------- workers + assignments ---
def test_create_worker_validates_and_rejects_duplicates(client, conn):
    h = auth(client, conn)
    code = f"t-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/workers", json={"code": code, "name": "  New   Worker "}, headers=h)
    assert r.status_code == 201
    w = r.json()["worker"]
    assert w["code"] == code.upper() and w["name"] == "New Worker" and w["currentAssignment"] is None
    assert client.post("/api/workers", json={"code": code, "name": "Other"}, headers=h).status_code == 409
    assert client.post("/api/workers", json={"code": " ", "name": "x"}, headers=h).status_code == 422
    assert client.post("/api/workers", json={"code": "Z1", "name": "x"},
                       headers=auth(client, conn, "admin")).status_code == 403
    assert audits(conn, uuid.UUID(w["id"]), "worker.create") == 1


def test_assignment_conflicts_reassignment_and_end(client, conn, graph):
    h = auth(client, conn)
    other = ins(conn, "worker", worker_code=f"T-{uuid.uuid4().hex[:6]}", display_name="Worker Two",
                created_by=graph["acc"])
    body = {"workerId": str(other), "deviceId": str(graph["dev"])}

    # Device is held by graph's worker: conflict unless that interval is explicitly selected.
    assert client.post("/api/assignments", json=body, headers=h).status_code == 409
    r = client.post("/api/assignments", json={**body, "closeAssignmentIds": [str(graph["asg"])]}, headers=h)
    assert r.status_code == 201
    new = r.json()["assignment"]
    assert new["worker"]["name"] == "Worker Two" and new["endAt"] is None

    old = conn.execute(text("SELECT end_at, reason FROM assignment WHERE assignment_id = :a"), {"a": graph["asg"]}).one()
    assert old.end_at is not None and old.reason == "reassigned"

    listing = client.get("/api/assignments", headers=h).json()
    dev = next(d for d in listing["devices"] if d["id"] == str(graph["dev"]))
    assert dev["activeAssignmentId"] == new["id"]
    assert any(a["id"] == str(graph["asg"]) for a in listing["history"])

    end = client.post(f"/api/assignments/{new['id']}/end", json={"reason": "end of shift"}, headers=h)
    assert end.status_code == 200 and end.json()["assignment"]["reason"] == "end of shift"
    again = client.post(f"/api/assignments/{new['id']}/end", json={}, headers=h)
    assert again.status_code == 200 and again.json()["alreadyEnded"] is True


def test_disabled_device_cannot_be_assigned(client, conn, graph):
    conn.execute(text("UPDATE device SET state = 'disabled' WHERE device_id = :d"), {"d": graph["never"]})
    other = ins(conn, "worker", worker_code=f"T-{uuid.uuid4().hex[:6]}", display_name="W", created_by=graph["acc"])
    r = client.post("/api/assignments", json={"workerId": str(other), "deviceId": str(graph["never"])},
                    headers=auth(client, conn))
    assert r.status_code == 409 and "disabled" in r.json()["detail"]


# ----------------------------------------------------------------- history ---
def test_history_filters_and_pagination(client, conn, graph):
    h = auth(client, conn)
    for _ in range(3):
        event(conn, graph, "cancellation", state="resolved")
    event(conn, graph, "possible_fall")
    base = {"deviceId": str(graph["dev"])}

    r = client.get("/api/history", params={**base, "type": "cancellation", "limit": 2}, headers=h)
    assert r.status_code == 200
    page1 = r.json()
    assert len(page1["items"]) == 2 and page1["nextCursor"]
    assert {i["type"] for i in page1["items"]} == {"cancellation"}
    page2 = client.get("/api/history", params={**base, "type": "cancellation", "limit": 2,
                                               "cursor": page1["nextCursor"]}, headers=h).json()
    assert len(page2["items"]) == 1 and page2["nextCursor"] is None
    ids = {i["eventId"] for i in page1["items"] + page2["items"]}
    assert len(ids) == 3

    falls = client.get("/api/history", params={**base, "type": "possible_fall", "state": "open"}, headers=h).json()
    assert [i["type"] for i in falls["items"]] == ["possible_fall"]


def test_history_validates_range_and_clamps_retention(client, conn, graph):
    h = auth(client, conn)
    assert client.get("/api/history", params={"from": "2026-01-01T00:00:00"}, headers=h).status_code == 422
    now = datetime.now(timezone.utc)
    bad = {"from": now.isoformat(), "to": (now - timedelta(hours=1)).isoformat()}
    assert client.get("/api/history", params=bad, headers=h).status_code == 422
    assert client.get("/api/history", params={"type": "nope"}, headers=h).status_code == 422
    assert client.get("/api/history", params={"cursor": "!!"}, headers=h).status_code == 422

    old = (now - timedelta(days=60)).isoformat()
    r = client.get("/api/history", params={"from": old, "deviceId": str(graph["never"])}, headers=h).json()
    assert r["range"]["clamped"] is True and r["items"] == []
    assert client.get("/api/history", headers=auth(client, conn, "admin")).status_code == 403


# ---------------------------------------------------------- device health ---
def test_device_health_channels_and_roles(client, conn, graph):
    telemetry(conn, graph, co_latest=12, temperature_c=25, humidity_pct=40, accel_peak_g=None,
              battery_pct=8, validity_flags=flags.IMU_INVALID | flags.GPS_NO_FIX)
    r = client.get("/api/devices", headers=auth(client, conn))
    assert r.status_code == 200
    devs = {d["label"]: d for d in r.json()["devices"]}
    d = devs["T-HAT-1"]
    assert d["status"] == "current" and d["worker"]["name"] == "Worker One"
    ch = d["channels"]
    assert ch["co"]["state"] == "valid" and ch["motion"]["state"] == "invalid"
    assert "fall detection" in ch["motion"]["affects"].lower()
    assert ch["gps"]["state"] == "no_fix" and "other sensors are unaffected" in ch["gps"]["affects"]
    assert ch["battery"]["state"] == "critical"
    assert devs["T-HAT-2"]["status"] == "unknown" and devs["T-HAT-2"]["channels"] is None
    assert "slot" not in json.dumps(r.json())   # key_slot_reference never returned

    admin_view = client.get("/api/devices", headers=auth(client, conn, "admin")).json()
    assert all("worker" not in x for x in admin_view["devices"])
    assert client.get("/api/devices").status_code == 401


def test_admin_device_register_and_state(client, conn, graph):
    adm = auth(client, conn, "admin")
    body = {"radioId": 990077, "label": "t-hat-77", "hardwareRevision": "A", "firmwareVersion": "0.1",
            "keySlotReference": "slot-77"}
    assert client.post("/api/admin/devices", json=body, headers=auth(client, conn)).status_code == 403
    r = client.post("/api/admin/devices", json=body, headers=adm)
    assert r.status_code == 201
    dev = r.json()["device"]
    assert dev["label"] == "T-HAT-77" and "keySlotReference" not in dev
    assert client.post("/api/admin/devices", json=body, headers=adm).status_code == 409

    # Assigned device cannot be retired; unassigned one can, and retirement is final.
    busy = client.post(f"/api/admin/devices/{graph['dev']}/state", json={"state": "retired"}, headers=adm)
    assert busy.status_code == 409
    url = f"/api/admin/devices/{dev['id']}/state"
    assert client.post(url, json={"state": "disabled"}, headers=adm).json()["device"]["state"] == "disabled"
    assert client.post(url, json={"state": "registered"}, headers=adm).json()["device"]["state"] == "registered"
    assert client.post(url, json={"state": "retired"}, headers=adm).json()["device"]["state"] == "retired"
    assert client.post(url, json={"state": "registered"}, headers=adm).status_code == 409
    assert audits(conn, uuid.UUID(dev["id"]), "device.retired") == 1


# ---------------------------------------------------------- configuration ---
def good_config():
    t = {k: (lo + hi) / 2 if not integer else int((lo + hi) // 2) for k, (_, lo, hi, integer, _) in cfg_svc.THRESHOLDS.items()}
    m = {k: (lo + hi) / 2 if not integer else int((lo + hi) // 2) for k, (_, lo, hi, integer, _) in cfg_svc.TIMINGS.items()}
    t.update(co_warning_ppm=35, co_reset_ppm=180, co_urgent_ppm=200, battery_low_pct=20, battery_critical_pct=10)
    m.update(summary_period_s=60, stale_after_s=180, battery_s=30, temp_humidity_s=5)
    return t, m


def test_configuration_validation():
    t, m = good_config()
    assert cfg_svc.validate(t, m)[2] == []
    _, _, errs = cfg_svc.validate({**t, "co_warning_ppm": 250}, m)
    assert errs   # out of range
    _, _, errs = cfg_svc.validate({**t, "co_reset_ppm": 210, "co_urgent_ppm": 200}, m)
    assert any("reset" in e.lower() for e in errs)
    _, _, errs = cfg_svc.validate({**t, "battery_critical_pct": 25}, m)
    assert any("critical" in e.lower() for e in errs)
    _, _, errs = cfg_svc.validate({**t, "extra": 1}, {**m, "stale_after_s": 60})
    assert any("unknown" in e.lower() for e in errs)
    _, _, errs = cfg_svc.validate({k: v for k, v in t.items() if k != "fall_impact_g"}, m)
    assert any("fall_impact_g" in e for e in errs)


def test_configuration_draft_and_approve(client, conn):
    adm = auth(client, conn, "admin")
    t, m = good_config()
    version = f"t-cfg-{uuid.uuid4().hex[:6]}"
    assert client.get("/api/admin/configurations", headers=auth(client, conn)).status_code == 403
    bad = client.post("/api/admin/configurations", json={"version": version, "thresholds": {**t, "co_urgent_ppm": 30},
                                                         "timings": m}, headers=adm)
    assert bad.status_code == 422 and bad.json()["detail"]["errors"]

    r = client.post("/api/admin/configurations", json={"version": version, "thresholds": t, "timings": m}, headers=adm)
    assert r.status_code == 201
    draft = r.json()["configuration"]
    assert draft["state"] == "draft" and draft["checksum"] == cfg_svc.checksum(t, m)
    assert client.post("/api/admin/configurations", json={"version": version, "thresholds": t, "timings": m},
                       headers=adm).status_code == 409

    url = f"/api/admin/configurations/{draft['id']}/approve"
    assert client.post(url, json={"reason": " "}, headers=adm).status_code == 422
    r = client.post(url, json={"reason": "Bench review"}, headers=adm)
    assert r.status_code == 200
    active = r.json()["configuration"]
    assert active["state"] == "active" and active["reviewer"] == "Test User" and active["activatedAt"]
    assert conn.execute(text("SELECT count(*) FROM configuration WHERE state = 'active'")).scalar() == 1
    assert client.post(url, json={"reason": "again"}, headers=adm).status_code == 409

    listing = client.get("/api/admin/configurations", headers=adm).json()
    assert {s["key"] for s in listing["schema"]["thresholds"]} == set(cfg_svc.THRESHOLDS)


# ---------------------------------------------------------------- accounts ---
def test_account_create_reset_and_disable(client, conn):
    adm = auth(client, conn, "admin")
    email = f"{uuid.uuid4().hex[:8]}@test.local"
    assert client.get("/api/admin/accounts", headers=auth(client, conn)).status_code == 403

    r = client.post("/api/admin/accounts", json={"email": email.upper(), "displayName": "New Sup",
                                                 "role": "supervisor"}, headers=adm)
    assert r.status_code == 201
    acc, temp = r.json()["account"], r.json()["temporaryPassword"]
    assert acc["email"] == email and len(temp) >= 12
    assert client.post("/api/admin/accounts", json={"email": email, "displayName": "x", "role": "supervisor"},
                       headers=adm).status_code == 409
    assert client.post("/api/admin/accounts", json={"email": "nope", "displayName": "x", "role": "supervisor"},
                       headers=adm).status_code == 422

    token = sign_in(client, email, temp).json()["token"]
    sess = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/session", headers=sess).status_code == 200

    new_temp = client.post(f"/api/admin/accounts/{acc['id']}/reset-password", headers=adm).json()["temporaryPassword"]
    assert new_temp != temp
    assert client.get("/api/auth/session", headers=sess).status_code == 401          # sessions revoked
    assert sign_in(client, email, temp).status_code == 401
    token = sign_in(client, email, new_temp).json()["token"]

    r = client.post(f"/api/admin/accounts/{acc['id']}/enabled", json={"enabled": False}, headers=adm)
    assert r.status_code == 200 and r.json()["account"]["enabled"] is False
    assert client.get("/api/auth/session", headers={"Authorization": f"Bearer {token}"}).status_code == 401

    r = client.post(f"/api/admin/accounts/{acc['id']}/role", json={"role": "admin_supervisor"}, headers=adm)
    assert r.json()["account"]["role"] == "admin_supervisor"
    listing = client.get("/api/admin/accounts", headers=adm).json()
    assert "password" not in json.dumps(listing).lower()
    assert audits(conn, uuid.UUID(acc["id"]), "account.disable") == 1


def test_admin_cannot_disable_or_demote_self(client, conn):
    aid, email = account(conn, "admin")
    adm = {"Authorization": f"Bearer {sign_in(client, email).json()['token']}"}
    assert client.post(f"/api/admin/accounts/{aid}/enabled", json={"enabled": False}, headers=adm).status_code == 409
    assert client.post(f"/api/admin/accounts/{aid}/role", json={"role": "supervisor"}, headers=adm).status_code == 409


@pytest.mark.parametrize("path", ["/api/admin/accounts", "/api/admin/configurations", "/api/admin/devices"])
def test_admin_routes_reject_anonymous(client, path):
    assert client.get(path).status_code == 401
