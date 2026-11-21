"""Device health + device administration (F26-113 §4.8.6, Table 5.2; UC-14, UC-15, UC-18;
FR-06, FR-23, FR-26, FR-29, FR-53).

GET  /api/devices                    any signed-in role: health of every device + gateways.
                                     Worker names only for supervisor roles (Table 4.34).
GET  /api/admin/devices              administrator: device identities (no key material)
POST /api/admin/devices              administrator: register a hardhat
POST /api/admin/devices/{id}/state   administrator: registered | disabled | retired

Retired devices stay in the table so retained history remains identifiable. A device
with an active assignment cannot be disabled or retired (end the assignment first).
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.db import get_conn
from app.deps import SUPERVISOR_ROLES, current_account, require_admin
from app.services.devices import device_health
from app.services.overview import iso

router = APIRouter(tags=["devices"])

HEALTH_SQL = text("""
SELECT d.device_id, d.radio_id, d.label, d.state, d.hardware_revision, d.firmware_version,
       d.created_at, d.last_seen_at,
       w.worker_code, w.display_name AS worker_name,
       s.received_at AS snap_received_at, s.time_quality AS snap_time_quality,
       t.telemetry_id, t.validity_flags, t.co_latest, t.co_valid_count, t.expected_count,
       t.temperature_c, t.humidity_pct, t.accel_peak_g, t.battery_pct, t.battery_is_estimate,
       t.latitude, t.gps_fix_age_s,
       c.config_version, c.state AS config_state,
       cal.calibration_id, cal.sensor_serial, cal.result AS cal_result,
       cal.checked_at AS cal_checked_at, cal.due_at AS cal_due_at,
       g.gateway_code, g.last_seen_at AS gateway_last_seen,
       (SELECT count(*) FROM event e WHERE e.device_id = d.device_id AND e.event_type = 'fault'
          AND e.workflow_state <> 'resolved') AS open_faults
FROM device d
LEFT JOIN assignment a ON a.device_id = d.device_id AND a.end_at IS NULL AND a.start_at <= now()
LEFT JOIN worker w ON w.worker_id = a.worker_id
LEFT JOIN device_status_snapshot s ON s.device_id = d.device_id
LEFT JOIN telemetry t ON t.telemetry_id = s.telemetry_id
LEFT JOIN configuration c ON c.config_id = t.config_id
LEFT JOIN calibration cal ON cal.calibration_id = t.calibration_id
LEFT JOIN gateway g ON g.gateway_id = t.gateway_id
ORDER BY (d.state = 'retired'), d.label
""")

GATEWAYS_SQL = text("""
SELECT gateway_code, enabled, last_seen_at, firmware_version, queue_depth, loss_count
FROM gateway ORDER BY gateway_code
""")

ACTIVE_CONFIG_SQL = text("SELECT config_version, activated_at FROM configuration WHERE state = 'active'")


@router.get("/api/devices")
def get_devices(conn: Connection = Depends(get_conn), account: dict = Depends(current_account)):
    now = datetime.now(timezone.utc)
    show_worker = account["role"] in SUPERVISOR_ROLES
    devices = [device_health(r, now, show_worker) for r in conn.execute(HEALTH_SQL).mappings()]
    gateways = [{"code": g["gateway_code"], "enabled": g["enabled"], "lastSeenAt": iso(g["last_seen_at"]),
                 "firmware": g["firmware_version"], "queueDepth": g["queue_depth"], "lossCount": g["loss_count"]}
                for g in conn.execute(GATEWAYS_SQL).mappings()]
    cfg = conn.execute(ACTIVE_CONFIG_SQL).mappings().first()
    return {
        "generatedAt": now.isoformat(),
        "devices": devices,
        "gateways": gateways,
        "activeConfig": {"version": cfg["config_version"], "activatedAt": iso(cfg["activated_at"])} if cfg else None,
    }


# ------------------------------------------------------------------ admin ---
ADMIN_SQL = text("""
SELECT device_id, radio_id, label, hardware_revision, firmware_version, state, last_seen_at, created_at
FROM device ORDER BY label
""")


def admin_json(r) -> dict:   # key_slot_reference deliberately omitted
    return {"id": str(r["device_id"]), "radioId": r["radio_id"], "label": r["label"],
            "hardwareRevision": r["hardware_revision"], "firmwareVersion": r["firmware_version"],
            "state": r["state"], "lastSeenAt": iso(r["last_seen_at"]), "createdAt": iso(r["created_at"])}


def _audit(conn: Connection, actor, device_id, action: str, **meta):
    conn.execute(
        text("INSERT INTO audit_log (actor_id, resource_type, resource_id, action, safe_metadata)"
             " VALUES (:a, 'device', :r, :act, CAST(:m AS jsonb))"),
        {"a": actor, "r": device_id, "act": action, "m": json.dumps(meta)},
    )


@router.get("/api/admin/devices", dependencies=[Depends(require_admin)])
def admin_list(conn: Connection = Depends(get_conn)):
    return {"devices": [admin_json(r) for r in conn.execute(ADMIN_SQL).mappings()]}


class DeviceIn(BaseModel):
    radioId: int = Field(gt=0, lt=2**31)
    label: str = Field(max_length=32)
    hardwareRevision: str = Field(max_length=32)
    firmwareVersion: str = Field(max_length=32)
    # Reference to provisioned key material (slot/name), NEVER the key itself.
    keySlotReference: str = Field(max_length=64)


@router.post("/api/admin/devices", status_code=status.HTTP_201_CREATED)
def admin_register(body: DeviceIn, conn: Connection = Depends(get_conn), account: dict = Depends(require_admin)):
    label = body.label.strip().upper()
    hw, fw, slot = body.hardwareRevision.strip(), body.firmwareVersion.strip(), body.keySlotReference.strip()
    if not (label and hw and fw and slot):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "All fields are required.")
    try:
        with conn.begin_nested():
            did = conn.execute(
                text("INSERT INTO device (radio_id, label, hardware_revision, firmware_version, key_slot_reference)"
                     " VALUES (:r, :l, :h, :f, :k) RETURNING device_id"),
                {"r": body.radioId, "l": label, "h": hw, "f": fw, "k": slot}).scalar_one()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A device with this label or radio ID already exists.") from None
    _audit(conn, account["account_id"], did, "device.register", label=label, radio_id=body.radioId)
    row = conn.execute(text(ADMIN_SQL.text.replace("ORDER BY label", "WHERE device_id = :id")),
                       {"id": did}).mappings().one()
    return {"device": admin_json(row)}


class StateIn(BaseModel):
    state: Literal["registered", "disabled", "retired"]
    reason: str | None = Field(default=None, max_length=200)


@router.post("/api/admin/devices/{device_id}/state")
def admin_set_state(device_id: str, body: StateIn, conn: Connection = Depends(get_conn),
                    account: dict = Depends(require_admin)):
    try:
        did = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found") from None
    cur = conn.execute(text("SELECT state FROM device WHERE device_id = :id FOR UPDATE"), {"id": did}).scalar()
    if cur is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    if cur == body.state:
        pass   # idempotent
    elif cur == "retired":
        raise HTTPException(status.HTTP_409_CONFLICT, "A retired device cannot be returned to service.")
    else:
        if body.state != "registered":
            busy = conn.execute(text("SELECT 1 FROM assignment WHERE device_id = :id AND end_at IS NULL"),
                                {"id": did}).first()
            if busy:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    "This hardhat has an active assignment. End the assignment first.")
        conn.execute(text("UPDATE device SET state = :s WHERE device_id = :id"), {"s": body.state, "id": did})
        _audit(conn, account["account_id"], did, f"device.{body.state}", previous=cur,
               reason=(body.reason or "").strip() or None)
    row = conn.execute(text(ADMIN_SQL.text.replace("ORDER BY label", "WHERE device_id = :id")),
                       {"id": did}).mappings().one()
    return {"device": admin_json(row)}
