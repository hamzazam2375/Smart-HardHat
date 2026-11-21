"""Read-only overview data: GET /api/status and GET /api/events (UC-04, UC-05; FR-31..FR-34).
Supervisor roles only (Table 4.34)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Connection, text

from app.config import SITE_NAME
from app.db import get_conn
from app.deps import require_supervisor
from app.services import overview as ov

router = APIRouter(prefix="/api", tags=["overview"], dependencies=[Depends(require_supervisor)])

DEVICES_SQL = text("""
SELECT d.device_id, d.label,
       w.worker_code, w.display_name AS worker_name,
       s.received_at AS snap_received_at, s.time_quality AS snap_time_quality,
       t.telemetry_id, t.received_at, t.window_end, t.validity_flags, t.motion_flags,
       t.co_latest, t.temperature_c, t.humidity_pct, t.heat_index_c, t.accel_peak_g,
       t.battery_pct, t.battery_is_estimate, t.latitude, t.longitude, t.gps_fix_age_s,
       r.status AS risk_status, r.predicted_level, r.effective_level, r.factors AS risk_factors,
       r.reason_code, r.created_at AS risk_created_at, m.artifact_reference AS model_artifact,
       g.received_at AS last_fix_received_at, g.window_end AS last_fix_window_end,
       g.gps_fix_age_s AS last_fix_age_s
FROM device d
LEFT JOIN assignment a ON a.device_id = d.device_id AND a.end_at IS NULL AND a.start_at <= now()
LEFT JOIN worker w ON w.worker_id = a.worker_id
LEFT JOIN device_status_snapshot s ON s.device_id = d.device_id
LEFT JOIN telemetry t ON t.telemetry_id = s.telemetry_id
LEFT JOIN LATERAL (
    SELECT * FROM risk_assessment ra WHERE ra.telemetry_id = t.telemetry_id
    ORDER BY ra.created_at DESC LIMIT 1) r ON true
LEFT JOIN model_version m ON m.model_id = r.model_id
LEFT JOIN LATERAL (
    SELECT received_at, window_end, gps_fix_age_s FROM telemetry tg
    WHERE tg.device_id = d.device_id AND tg.latitude IS NOT NULL
    ORDER BY tg.received_at DESC LIMIT 1) g ON true
WHERE d.state = 'registered'
ORDER BY d.label
""")

GATEWAYS_SQL = text("""
SELECT gateway_code, enabled, last_seen_at, firmware_version, queue_depth, loss_count
FROM gateway ORDER BY gateway_code
""")

MODEL_SQL = text("""
SELECT m.artifact_reference,
       COALESCE((SELECT max(occurred_at) FROM audit_log
                 WHERE action = 'model.activate' AND resource_id = m.model_id), m.created_at) AS activated_at
FROM model_version m WHERE m.state = 'active'
""")

EVENTS_SQL = text("""
SELECT e.event_id, e.event_type, e.detected_at, e.received_at, e.time_quality, e.evidence,
       e.workflow_state, e.local_state, d.label,
       w.worker_code, w.display_name AS worker_name,
       ack.created_at AS ack_at, ackby.display_name AS ack_by
FROM event e
JOIN device d ON d.device_id = e.device_id
LEFT JOIN assignment a ON a.assignment_id = e.assignment_id
LEFT JOIN worker w ON w.worker_id = a.worker_id
LEFT JOIN LATERAL (
    SELECT aa.created_at, aa.actor_id FROM alert_action aa
    WHERE aa.event_id = e.event_id AND aa.action_type = 'acknowledge'
    ORDER BY aa.created_at LIMIT 1) ack ON true
LEFT JOIN account ackby ON ackby.account_id = ack.actor_id
WHERE e.workflow_state IN ('open', 'acknowledged')
ORDER BY e.received_at DESC
LIMIT :limit
""")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/status")
def get_status(conn: Connection = Depends(get_conn)):
    devices = [ov.device_status(r) for r in conn.execute(DEVICES_SQL).mappings()]
    gateways = [
        {"code": g["gateway_code"], "enabled": g["enabled"], "lastSeenAt": ov.iso(g["last_seen_at"]),
         "firmware": g["firmware_version"], "queueDepth": g["queue_depth"], "lossCount": g["loss_count"]}
        for g in conn.execute(GATEWAYS_SQL).mappings()
    ]
    m = conn.execute(MODEL_SQL).mappings().first()
    model = ({"state": "active", "version": ov.model_name(m["artifact_reference"]),
              "activatedAt": ov.iso(m["activated_at"])} if m
             else {"state": "unavailable", "reason": "No active model"})
    return {"generatedAt": _now(), "site": SITE_NAME, "devices": devices, "gateways": gateways, "model": model}


@router.get("/events")
def get_events(limit: int = Query(200, ge=1, le=500), conn: Connection = Depends(get_conn)):
    """Unresolved (open or acknowledged) events. History filters come with the History page."""
    rows = conn.execute(EVENTS_SQL, {"limit": limit}).mappings()
    return {"generatedAt": _now(), "alerts": [ov.active_alert(r) for r in rows]}
