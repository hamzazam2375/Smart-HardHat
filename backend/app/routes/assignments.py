"""Worker-to-device assignment (F26-113 §4.8.4, Table 5.2; UC-03; FR-28, FR-29, FR-38).

GET  /api/assignments           devices with eligibility, open intervals, recent history
POST /api/assignments           create an interval starting now; closes ONLY the open
                                intervals the supervisor explicitly selected, in the same
                                transaction (reassignment). Any other conflict -> 409.
POST /api/assignments/{id}/end  close an open interval (idempotent)
assignment.reason holds the END reason ("reassigned" or the supervisor's text).

Intervals are never edited or deleted here, so delayed events keep the context of the
shift they belong to. The DB also enforces one open interval per worker/device and no
overlaps (exclusion constraints), which covers races between supervisors.
"""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.db import get_conn
from app.deps import require_supervisor
from app.services.overview import iso

router = APIRouter(prefix="/api/assignments", tags=["assignments"], dependencies=[Depends(require_supervisor)])

ASSIGNMENT_COLS = """
a.assignment_id, a.start_at, a.end_at, a.reason,
w.worker_id, w.worker_code, w.display_name AS worker_name,
d.device_id, d.label AS device_label,
cb.display_name AS created_by_name, eb.display_name AS ended_by_name
FROM assignment a
JOIN worker w ON w.worker_id = a.worker_id
JOIN device d ON d.device_id = a.device_id
JOIN account cb ON cb.account_id = a.created_by
LEFT JOIN account eb ON eb.account_id = a.ended_by
"""

OPEN_SQL = text(f"SELECT {ASSIGNMENT_COLS} WHERE a.end_at IS NULL ORDER BY d.label")
# Ended intervals inside the 30-day retention window, newest first.
HISTORY_SQL = text(f"""SELECT {ASSIGNMENT_COLS}
WHERE a.end_at IS NOT NULL AND a.end_at > now() - interval '30 days'
ORDER BY a.end_at DESC LIMIT :limit""")
ONE_SQL = text(f"SELECT {ASSIGNMENT_COLS} WHERE a.assignment_id = :id")

DEVICES_SQL = text("""
SELECT d.device_id, d.label, d.state, d.last_seen_at FROM device d
WHERE d.state <> 'retired' ORDER BY d.label
""")


def assignment_json(r) -> dict:
    return {
        "id": str(r["assignment_id"]),
        "worker": {"id": str(r["worker_id"]), "code": r["worker_code"], "name": r["worker_name"]},
        "device": {"id": str(r["device_id"]), "label": r["device_label"]},
        "startAt": iso(r["start_at"]), "endAt": iso(r["end_at"]), "reason": r["reason"],
        "createdBy": r["created_by_name"], "endedBy": r["ended_by_name"],
    }


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found") from None


def _audit(conn: Connection, actor, resource_id, action: str, **meta):
    conn.execute(
        text("INSERT INTO audit_log (actor_id, resource_type, resource_id, action, safe_metadata)"
             " VALUES (:a, 'assignment', :r, :act, CAST(:m AS jsonb))"),
        {"a": actor, "r": resource_id, "act": action, "m": json.dumps(meta)},
    )


@router.get("")
def list_assignments(limit: int = Query(50, ge=1, le=200), conn: Connection = Depends(get_conn)):
    active = [assignment_json(r) for r in conn.execute(OPEN_SQL).mappings()]
    by_device = {a["device"]["id"]: a["id"] for a in active}
    devices = [{"id": str(d["device_id"]), "label": d["label"], "state": d["state"],
                "lastSeenAt": iso(d["last_seen_at"]),
                "eligible": d["state"] == "registered",
                "activeAssignmentId": by_device.get(str(d["device_id"]))}
               for d in conn.execute(DEVICES_SQL).mappings()]
    history = [assignment_json(r) for r in conn.execute(HISTORY_SQL, {"limit": limit}).mappings()]
    return {"devices": devices, "active": active, "history": history}


class AssignmentIn(BaseModel):
    workerId: str
    deviceId: str
    # Open intervals the supervisor saw and chose to close (reassignment).
    closeAssignmentIds: list[str] = Field(default_factory=list, max_length=2)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_assignment(body: AssignmentIn, conn: Connection = Depends(get_conn),
                      account: dict = Depends(require_supervisor)):
    wid, did = _uuid(body.workerId, "Worker"), _uuid(body.deviceId, "Device")
    close_ids = {_uuid(x, "Assignment") for x in body.closeAssignmentIds}

    # Lock worker and device so two supervisors cannot assign them at the same time.
    worker = conn.execute(text("SELECT worker_code, active FROM worker WHERE worker_id = :id FOR UPDATE"),
                          {"id": wid}).mappings().first()
    device = conn.execute(text("SELECT label, state FROM device WHERE device_id = :id FOR UPDATE"),
                          {"id": did}).mappings().first()
    if worker is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Worker not found")
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    if not worker["active"]:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Worker {worker['worker_code']} is inactive.")
    if device["state"] != "registered":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Hardhat {device['label']} is {device['state']} and cannot be assigned.")

    open_rows = list(conn.execute(
        text("SELECT assignment_id FROM assignment"
             " WHERE end_at IS NULL AND (worker_id = :w OR device_id = :d) FOR UPDATE"),
        {"w": wid, "d": did}).scalars())
    open_ids = set(open_rows)
    if open_ids != close_ids:
        # Either an interval opened since the form loaded, or a selected one was already closed.
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "The active assignments changed since this form was opened. Review them and try again.")

    try:
        with conn.begin_nested():
            for aid in close_ids:   # close the selected previous interval(s) first ...
                conn.execute(
                    text("UPDATE assignment SET end_at = clock_timestamp(), ended_by = :a,"
                         " reason = 'reassigned' WHERE assignment_id = :id"),
                    {"a": account["account_id"], "id": aid})
            new_id = conn.execute(   # ... then create the new one, in one transaction
                text("INSERT INTO assignment (worker_id, device_id, start_at, created_by)"
                     " VALUES (:w, :d, clock_timestamp(), :a) RETURNING assignment_id"),
                {"w": wid, "d": did, "a": account["account_id"]}).scalar_one()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This assignment conflicts with another interval. Refresh and try again.") from None

    for aid in close_ids:
        _audit(conn, account["account_id"], aid, "assignment.end", replaced_by=str(new_id))
    _audit(conn, account["account_id"], new_id, "assignment.create", closed=[str(x) for x in close_ids])
    return {"assignment": assignment_json(conn.execute(ONE_SQL, {"id": new_id}).mappings().one())}


class EndIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


@router.post("/{assignment_id}/end")
def end_assignment(assignment_id: str, body: EndIn | None = None, conn: Connection = Depends(get_conn),
                   account: dict = Depends(require_supervisor)):
    aid = _uuid(assignment_id, "Assignment")
    reason = ((body.reason if body else None) or "").strip() or None
    row = conn.execute(text("SELECT end_at, start_at >= clock_timestamp() AS future FROM assignment"
                            " WHERE assignment_id = :id FOR UPDATE"), {"id": aid}).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")
    if row["end_at"] is not None:   # idempotent: already closed, return it unchanged
        return {"assignment": assignment_json(conn.execute(ONE_SQL, {"id": aid}).mappings().one()),
                "alreadyEnded": True}
    if row["future"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "This assignment has not started yet.")
    conn.execute(text("UPDATE assignment SET end_at = clock_timestamp(), ended_by = :a, reason = :r"
                      " WHERE assignment_id = :id"), {"a": account["account_id"], "r": reason, "id": aid})
    _audit(conn, account["account_id"], aid, "assignment.end")
    return {"assignment": assignment_json(conn.execute(ONE_SQL, {"id": aid}).mappings().one()),
            "alreadyEnded": False}
