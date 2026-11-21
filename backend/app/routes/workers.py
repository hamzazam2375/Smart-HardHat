"""Minimal worker records (F26-113 §4.8.4; UC-02; FR-27, FR-38).

Only the internal worker ID and display name are stored: no medical, home-address or
employment-profile fields. Creation is attributed (worker.created_by + audit_log).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.db import get_conn
from app.deps import require_supervisor
from app.services.overview import iso

router = APIRouter(prefix="/api/workers", tags=["workers"], dependencies=[Depends(require_supervisor)])

WORKERS_SQL = text("""
SELECT w.worker_id, w.worker_code, w.display_name, w.active, w.created_at,
       cb.display_name AS created_by_name,
       a.assignment_id, a.start_at, d.device_id, d.label AS device_label
FROM worker w
JOIN account cb ON cb.account_id = w.created_by
LEFT JOIN assignment a ON a.worker_id = w.worker_id AND a.end_at IS NULL
LEFT JOIN device d ON d.device_id = a.device_id
ORDER BY w.worker_code
""")


def worker_json(r) -> dict:
    current = ({"assignmentId": str(r["assignment_id"]), "deviceId": str(r["device_id"]),
                "deviceLabel": r["device_label"], "startAt": iso(r["start_at"])}
               if r["assignment_id"] else None)
    return {"id": str(r["worker_id"]), "code": r["worker_code"], "name": r["display_name"],
            "active": r["active"], "createdAt": iso(r["created_at"]), "createdBy": r["created_by_name"],
            "currentAssignment": current}


@router.get("")
def list_workers(conn: Connection = Depends(get_conn)):
    return {"workers": [worker_json(r) for r in conn.execute(WORKERS_SQL).mappings()]}


class WorkerIn(BaseModel):
    code: str = Field(max_length=32)
    name: str = Field(max_length=100)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_worker(body: WorkerIn, conn: Connection = Depends(get_conn),
                  account: dict = Depends(require_supervisor)):
    code, name = body.code.strip().upper(), " ".join(body.name.split())
    if not code or not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Worker ID and display name are required.")
    try:
        with conn.begin_nested():   # savepoint: a duplicate leaves no partial record
            wid = conn.execute(
                text("INSERT INTO worker (worker_code, display_name, created_by)"
                     " VALUES (:c, :n, :a) RETURNING worker_id"),
                {"c": code, "n": name, "a": account["account_id"]},
            ).scalar_one()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Worker ID {code} already exists.") from None
    conn.execute(
        text("INSERT INTO audit_log (actor_id, resource_type, resource_id, action)"
             " VALUES (:a, 'worker', :w, 'worker.create')"),
        {"a": account["account_id"], "w": wid},
    )
    row = conn.execute(text(WORKERS_SQL.text.replace("ORDER BY w.worker_code", "WHERE w.worker_id = :id")),
                       {"id": wid}).mappings().one()
    return {"worker": worker_json(row)}
