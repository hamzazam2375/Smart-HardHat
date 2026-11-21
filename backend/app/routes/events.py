"""Alert detail and response actions (F26-113 §4.8.3, Table 5.2; UC-11; FR-34..FR-36, FR-38).

GET  /api/events/{id}          event evidence + response history + reviewed recommendations
POST /api/events/{id}/actions  acknowledge | note | resolve, with the expected row version

Actions are appended to alert_action (append-only) and audited. They change only the
supervisor workflow state; the source event (type, evidence, detection time) and the
hardhat's local state are never changed, and the hardhat alarm is not silenced.
"""
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app.db import get_conn
from app.deps import require_supervisor
from app.services import events as svc
from app.services.overview import classify

router = APIRouter(prefix="/api/events", tags=["events"])

EVENT_SQL = text("""
SELECT e.event_id, e.source_event_key, e.device_id, e.assignment_id, e.event_type, e.detected_at,
       e.received_at, e.time_quality, e.evidence, e.workflow_state, e.local_state, e.row_version,
       d.label, w.worker_code, w.display_name AS worker_name,
       a.start_at AS assign_start, a.end_at AS assign_end,
       ack.created_at AS ack_at, ackby.display_name AS ack_by,
       lf.latitude AS last_lat, lf.longitude AS last_lon, lf.received_at AS last_received_at,
       lf.window_end AS last_window_end, lf.gps_fix_age_s AS last_fix_age_s
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
    SELECT latitude, longitude, received_at, window_end, gps_fix_age_s FROM telemetry t
    WHERE t.device_id = e.device_id AND t.latitude IS NOT NULL AND t.received_at <= e.received_at
    ORDER BY t.received_at DESC LIMIT 1) lf ON true
WHERE e.event_id = :id
""")

ACTIONS_SQL = text("""
SELECT aa.action_id, aa.action_type, aa.note, aa.created_at, ac.display_name AS actor_name
FROM alert_action aa JOIN account ac ON ac.account_id = aa.actor_id
WHERE aa.event_id = :id ORDER BY aa.created_at, aa.action_id
""")

# Latest approved version per factor code.
RECOMMENDATION_SQL = text("""
SELECT DISTINCT ON (factor_code) factor_code, message, version
FROM recommendation
WHERE factor_code = :code AND review_status = 'approved'
ORDER BY factor_code, created_at DESC
""")


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found") from None


def load_detail(conn: Connection, event_id: uuid.UUID) -> dict:
    row = conn.execute(EVENT_SQL, {"id": event_id}).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    actions = list(conn.execute(ACTIONS_SQL, {"id": event_id}).mappings())
    etype, _ = classify(row["event_type"], row["evidence"] or {})
    code = svc.RECOMMENDATION_FACTOR.get(etype, svc.FALLBACK_FACTOR)
    recs = list(conn.execute(RECOMMENDATION_SQL, {"code": code}).mappings())
    if not recs and code != svc.FALLBACK_FACTOR:
        recs = list(conn.execute(RECOMMENDATION_SQL, {"code": svc.FALLBACK_FACTOR}).mappings())
    return svc.event_detail(row, actions, recs)


@router.get("/{event_id}")
def get_event(event_id: str, conn: Connection = Depends(get_conn), _=Depends(require_supervisor)):
    return load_detail(conn, _uuid(event_id))


class ActionIn(BaseModel):
    action: Literal["acknowledge", "note", "resolve"]
    note: str | None = Field(default=None, max_length=1000)
    expectedRowVersion: int = Field(ge=0)


# Allowed workflow transitions. A note never changes the workflow state.
TRANSITIONS = {"acknowledge": ("open", "acknowledged"), "resolve": ("acknowledged", "resolved")}


@router.post("/{event_id}/actions")
def add_action(event_id: str, body: ActionIn, conn: Connection = Depends(get_conn),
               account: dict = Depends(require_supervisor)):
    eid = _uuid(event_id)
    note = (body.note or "").strip() or None
    if body.action in ("note", "resolve") and not note:
        msg = "Record the outcome before resolving." if body.action == "resolve" else "Enter a note."
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)

    # Lock the event row so concurrent responses are serialised; a stale row version or a
    # state that no longer allows the action returns 409 with the latest state (UC-11 alt flow).
    cur = conn.execute(text("SELECT workflow_state, row_version FROM event WHERE event_id = :id FOR UPDATE"),
                       {"id": eid}).mappings().first()
    if cur is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    def conflict(message: str):
        latest = load_detail(conn, eid)
        raise HTTPException(status.HTTP_409_CONFLICT, {"message": message, "latest": latest})

    if body.action in TRANSITIONS:
        frm, to = TRANSITIONS[body.action]
        if cur["row_version"] != body.expectedRowVersion:
            conflict("Another supervisor updated this alert. The latest state is shown.")
        if cur["workflow_state"] != frm:
            conflict(f"This alert is {cur['workflow_state']}; it cannot be {to} now.")
        conn.execute(text("UPDATE event SET workflow_state = :to, row_version = row_version + 1"
                          " WHERE event_id = :id"), {"to": to, "id": eid})

    action_id = conn.execute(
        text("INSERT INTO alert_action (event_id, actor_id, action_type, note, created_at)"
             " VALUES (:e, :a, :t, :n, clock_timestamp()) RETURNING action_id"),   # actual server time
        {"e": eid, "a": account["account_id"], "t": body.action, "n": note},
    ).scalar_one()
    conn.execute(
        text("INSERT INTO audit_log (actor_id, resource_type, resource_id, action, safe_metadata)"
             " VALUES (:a, 'event', :e, :act, CAST(:meta AS jsonb))"),
        {"a": account["account_id"], "e": eid, "act": f"event.{body.action}",
         "meta": json.dumps({"action_id": str(action_id)})},
    )
    return load_detail(conn, eid)
