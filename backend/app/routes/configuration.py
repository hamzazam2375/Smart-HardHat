"""Configuration review (F26-113 §4.8.7; UC-20; FR-47, FR-48, FR-53). Administrator only.

GET  /api/admin/configurations                list versions, allowed ranges, device versions
POST /api/admin/configurations                save a validated DRAFT (never sent to a hardhat)
POST /api/admin/configurations/{id}/approve   record the review (reason + reviewer) and make it
                                              the active version; the previous active one is retired

Approving does NOT update any hardhat: hardhat settings change only through controlled wired
setup, and the device-health page shows which version each hardhat actually reports.
"""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.db import get_conn
from app.deps import require_admin
from app.services import configuration as cfg
from app.services.overview import iso

router = APIRouter(prefix="/api/admin/configurations", tags=["configuration"],
                   dependencies=[Depends(require_admin)])

LIST_SQL = text("""
SELECT c.config_id, c.config_version, c.checksum, c.thresholds, c.timings, c.state,
       c.review_reason, r.display_name AS reviewer_name, c.activated_at, c.created_at,
       (SELECT count(*) FROM telemetry t WHERE t.config_id = c.config_id) AS telemetry_count
FROM configuration c LEFT JOIN account r ON r.account_id = c.reviewer
ORDER BY c.created_at DESC
""")

DEVICE_VERSIONS_SQL = text("""
SELECT d.label, d.state, c.config_version, s.received_at
FROM device d
LEFT JOIN device_status_snapshot s ON s.device_id = d.device_id
LEFT JOIN telemetry t ON t.telemetry_id = s.telemetry_id
LEFT JOIN configuration c ON c.config_id = t.config_id
WHERE d.state <> 'retired' ORDER BY d.label
""")


def config_json(r) -> dict:
    return {"id": str(r["config_id"]), "version": r["config_version"], "checksum": r["checksum"],
            "thresholds": r["thresholds"], "timings": r["timings"], "state": r["state"],
            "reviewReason": r["review_reason"], "reviewer": r["reviewer_name"],
            "activatedAt": iso(r["activated_at"]), "createdAt": iso(r["created_at"]),
            "telemetryCount": r["telemetry_count"]}


def _audit(conn: Connection, actor, cid, action: str, **meta):
    conn.execute(
        text("INSERT INTO audit_log (actor_id, resource_type, resource_id, action, safe_metadata)"
             " VALUES (:a, 'configuration', :r, :act, CAST(:m AS jsonb))"),
        {"a": actor, "r": cid, "act": action, "m": json.dumps(meta)},
    )


@router.get("")
def list_configurations(conn: Connection = Depends(get_conn)):
    return {
        "schema": cfg.schema(),
        "configurations": [config_json(r) for r in conn.execute(LIST_SQL).mappings()],
        "devices": [{"label": d["label"], "state": d["state"], "reportedVersion": d["config_version"],
                     "receivedAt": iso(d["received_at"])}
                    for d in conn.execute(DEVICE_VERSIONS_SQL).mappings()],
    }


class DraftIn(BaseModel):
    version: str = Field(max_length=40)
    thresholds: dict
    timings: dict


@router.post("", status_code=status.HTTP_201_CREATED)
def create_draft(body: DraftIn, conn: Connection = Depends(get_conn), account: dict = Depends(require_admin)):
    version = body.version.strip()
    if not version:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter a version name.")
    t, m, errors = cfg.validate(body.thresholds, body.timings)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"message": "Fix the values below.", "errors": errors})
    try:
        with conn.begin_nested():
            cid = conn.execute(
                text("INSERT INTO configuration (config_version, checksum, thresholds, timings)"
                     " VALUES (:v, :c, CAST(:t AS jsonb), CAST(:m AS jsonb)) RETURNING config_id"),
                {"v": version, "c": cfg.checksum(t, m), "t": json.dumps(t), "m": json.dumps(m)}).scalar_one()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Version {version} already exists.") from None
    _audit(conn, account["account_id"], cid, "configuration.create", version=version)
    row = conn.execute(text(LIST_SQL.text.replace("ORDER BY c.created_at DESC", "WHERE c.config_id = :id")),
                       {"id": cid}).mappings().one()
    return {"configuration": config_json(row)}


class ApproveIn(BaseModel):
    reason: str = Field(max_length=500)


@router.post("/{config_id}/approve")
def approve(config_id: str, body: ApproveIn, conn: Connection = Depends(get_conn),
            account: dict = Depends(require_admin)):
    try:
        cid = uuid.UUID(config_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Configuration not found") from None
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A review reason is required to approve.")
    row = conn.execute(text("SELECT config_version, state, thresholds, timings FROM configuration"
                            " WHERE config_id = :id FOR UPDATE"), {"id": cid}).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Configuration not found")
    if row["state"] != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Version {row['config_version']} is {row['state']}, not a draft.")
    _, _, errors = cfg.validate(row["thresholds"], row["timings"])   # re-check: ranges may have changed
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"message": "This draft is no longer valid.", "errors": errors})
    prev = conn.execute(text("UPDATE configuration SET state = 'retired' WHERE state = 'active'"
                             " RETURNING config_version")).scalar()
    conn.execute(text("UPDATE configuration SET state = 'active', review_reason = :r, reviewer = :a,"
                      " activated_at = now() WHERE config_id = :id"),
                 {"r": reason, "a": account["account_id"], "id": cid})
    _audit(conn, account["account_id"], cid, "configuration.activate", replaces=prev)
    row = conn.execute(text(LIST_SQL.text.replace("ORDER BY c.created_at DESC", "WHERE c.config_id = :id")),
                       {"id": cid}).mappings().one()
    return {"configuration": config_json(row)}
