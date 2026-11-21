"""Retained event history with filters (F26-113 §4.8.5, Table 5.2 "GET /api/events" filters;
UC-13; FR-37, FR-49, FR-50). Supervisor roles only (Table 4.34).

GET /api/history?from=&to=&workerId=&deviceId=&type=&state=&cursor=&limit=

- The time range applies to SERVER RECEIPT time (always present). Detection time can be
  unknown or estimated, so it is shown with each result but not used for the bounds.
- from/to must carry a time zone, so a browser time-zone conversion cannot silently move
  an event outside the chosen range. The lower bound is clamped to the 30-day retention
  window: expired identifiable history is never returned.
- Keyset (cursor) pagination on (received_at, event_id), newest first. Bounded page size.
- An empty page means no retained record matches, not a server failure.
"""
import base64
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Connection, text

from app.db import get_conn
from app.deps import require_supervisor
from app.services.overview import active_alert, iso

router = APIRouter(prefix="/api/history", tags=["history"], dependencies=[Depends(require_supervisor)])

RETENTION = timedelta(days=30)

# Dashboard alert type -> fixed SQL condition (chosen by key, never built from user text).
TYPE_SQL = {
    "sos": "e.event_type = 'sos'",
    "possible_fall": "e.event_type = 'possible_fall'",
    "cancellation": "e.event_type = 'cancellation'",
    "co_urgent": "e.event_type = 'co' AND COALESCE(e.evidence->>'level', '') <> 'warning'",
    "co_warning": "e.event_type = 'co' AND e.evidence->>'level' = 'warning'",
    "heat_warning": "e.event_type = 'heat'",
    "battery_low": "e.event_type = 'battery' AND COALESCE(e.evidence->>'level', '') <> 'critical'",
    "battery_critical": "e.event_type = 'battery' AND e.evidence->>'level' = 'critical'",
    "sensor_fault": "e.event_type = 'fault'",
}
STATES = ("open", "acknowledged", "resolved")

BASE_SQL = """
SELECT e.event_id, e.event_type, e.detected_at, e.received_at, e.time_quality, e.evidence,
       e.workflow_state, e.local_state, d.label,
       w.worker_code, w.display_name AS worker_name,
       ack.created_at AS ack_at, ackby.display_name AS ack_by,
       res.created_at AS resolved_at, resby.display_name AS resolved_by
FROM event e
JOIN device d ON d.device_id = e.device_id
LEFT JOIN assignment a ON a.assignment_id = e.assignment_id
LEFT JOIN worker w ON w.worker_id = a.worker_id
LEFT JOIN LATERAL (
    SELECT aa.created_at, aa.actor_id FROM alert_action aa
    WHERE aa.event_id = e.event_id AND aa.action_type = 'acknowledge'
    ORDER BY aa.created_at LIMIT 1) ack ON true
LEFT JOIN account ackby ON ackby.account_id = ack.actor_id
LEFT JOIN LATERAL (
    SELECT aa.created_at, aa.actor_id FROM alert_action aa
    WHERE aa.event_id = e.event_id AND aa.action_type = 'resolve'
    ORDER BY aa.created_at DESC LIMIT 1) res ON true
LEFT JOIN account resby ON resby.account_id = res.actor_id
"""

OPTIONS_WORKERS = text("SELECT worker_id, worker_code, display_name FROM worker ORDER BY worker_code")
OPTIONS_DEVICES = text("SELECT device_id, label, state FROM device ORDER BY label")


def _encode(received_at: datetime, event_id: uuid.UUID) -> str:
    raw = f"{received_at.isoformat()}|{event_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        at, eid = raw.split("|", 1)
        return datetime.fromisoformat(at), uuid.UUID(eid)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid page cursor.") from None


def _aware(v: datetime | None, name: str) -> datetime | None:
    if v is not None and v.tzinfo is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{name}' must include a time zone offset.")
    return v


def _uuid_or_422(v: str | None, name: str) -> uuid.UUID | None:
    if not v:
        return None
    try:
        return uuid.UUID(v)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid {name}.") from None


@router.get("")
def get_history(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    workerId: str | None = Query(None),
    deviceId: str | None = Query(None),
    type: str | None = Query(None),
    state: str | None = Query(None),
    cursor: str | None = Query(None, max_length=200),
    limit: int = Query(25, ge=1, le=100),
    conn: Connection = Depends(get_conn),
):
    now = datetime.now(timezone.utc)
    retention_start = now - RETENTION
    start, end = _aware(from_, "from"), _aware(to, "to")
    if start and end and start >= end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The start of the range must be before its end.")
    if type and type not in TYPE_SQL:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown event type.")
    if state and state not in STATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown response state.")

    eff_start = max(start, retention_start) if start else retention_start
    eff_end = min(end, now) if end else now
    where = ["e.received_at >= :start", "e.received_at < :end"]
    params: dict = {"start": eff_start, "end": eff_end, "limit": limit + 1}
    if (wid := _uuid_or_422(workerId, "worker")) is not None:
        where.append("a.worker_id = :wid")
        params["wid"] = wid
    if (did := _uuid_or_422(deviceId, "device")) is not None:
        where.append("e.device_id = :did")
        params["did"] = did
    if type:
        where.append(f"({TYPE_SQL[type]})")
    if state:
        where.append("e.workflow_state = :state")
        params["state"] = state
    if cursor:
        params["cat"], params["cid"] = _decode(cursor)
        where.append("(e.received_at, e.event_id) < (:cat, :cid)")

    sql = text(BASE_SQL + " WHERE " + " AND ".join(where)
               + " ORDER BY e.received_at DESC, e.event_id DESC LIMIT :limit")
    rows = list(conn.execute(sql, params).mappings())
    more = len(rows) > limit
    rows = rows[:limit]

    items = []
    for r in rows:
        item = active_alert(r)
        item["state"] = r["workflow_state"]
        if r["resolved_at"] is not None:
            item["resolved"] = {"by": r["resolved_by"], "at": iso(r["resolved_at"])}
        items.append(item)

    return {
        "generatedAt": now.isoformat(),
        "range": {"from": iso(eff_start), "to": iso(eff_end), "retentionStart": iso(retention_start),
                  "clamped": bool(start and start < retention_start)},
        "items": items,
        "nextCursor": _encode(rows[-1]["received_at"], rows[-1]["event_id"]) if more and rows else None,
        "options": {
            "workers": [{"id": str(w["worker_id"]), "code": w["worker_code"], "name": w["display_name"]}
                        for w in conn.execute(OPTIONS_WORKERS).mappings()],
            "devices": [{"id": str(d["device_id"]), "label": d["label"], "state": d["state"]}
                        for d in conn.execute(OPTIONS_DEVICES).mappings()],
        },
    }
