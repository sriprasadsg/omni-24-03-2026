"""Real-time ETW telemetry ingestion for the agent-rust ETW engine.

Receives batched host events (process/network/registry/DNS) and behavioural detections
from the Windows agent's ETW engine, stores them tenant-scoped, and raises security
alerts for high/critical detections. See agent-rust/docs/etw-telemetry-design.md.
"""
from fastapi import APIRouter, Depends, Query, Body
from typing import Dict, Any, List
from database import get_database
from authentication_service import get_current_user
from datetime import datetime, timezone
import uuid
from agent_auth import verify_agent_key

router = APIRouter(prefix="/api/agents", tags=["Agents"])

_MAX_TELEMETRY_EVENTS = 1000  # hard cap per batch; agent batches up to 512
_MAX_RAW_LOG_LINES = 1000  # log_shipper.py sends up to 50 lines per tick + any buffered backlog


@router.post("/{agent_id}/telemetry")
async def ingest_telemetry(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    _auth=Depends(verify_agent_key),
):
    """Ingest a batch of real-time ETW telemetry events from the agent.

    Body: {batch_id, collected_at, dropped_events, events: [{kind, pid, ppid,
    image, cmdline, ts_unix}, ...]}. Events are stored tenant-scoped; a per-batch
    summary (with the agent-reported drop count) is recorded for pipeline health.
    """
    tenant_id = _auth.get("id") or _auth.get("tenant_id") or ""
    # BSON Date (not ISO string) so the received_at TTL index actually expires old rows;
    # FastAPI still serializes it to an ISO string on the GET response.
    received_at = datetime.now(timezone.utc)

    raw_events = payload.get("events")
    events: List[Dict[str, Any]] = raw_events[:_MAX_TELEMETRY_EVENTS] if isinstance(raw_events, list) else []
    batch_id = str(payload.get("batch_id") or uuid.uuid4())

    docs: List[Dict[str, Any]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        docs.append({
            "id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "tenantId": tenant_id,
            "batch_id": batch_id,
            "kind": ev.get("kind", "unknown"),
            "pid": ev.get("pid"),
            "ppid": ev.get("ppid"),
            "image": ev.get("image"),
            "cmdline": ev.get("cmdline"),
            "ts_unix": ev.get("ts_unix"),
            "received_at": received_at,
        })

    if docs:
        await db.agent_telemetry.insert_many(docs)

    # Behavioural detections from the agent's rule engine. Store them and raise a
    # security alert for high/critical severities so they surface in the SOC queue.
    raw_dets = payload.get("detections")
    detections: List[Dict[str, Any]] = raw_dets[:_MAX_TELEMETRY_EVENTS] if isinstance(raw_dets, list) else []
    alert_count = 0
    for det in detections:
        if not isinstance(det, dict):
            continue
        det_id = str(uuid.uuid4())
        severity = str(det.get("severity", "medium")).lower()
        await db.agent_detections.insert_one({
            "id": det_id,
            "agent_id": agent_id,
            "tenantId": tenant_id,
            "batch_id": batch_id,
            "rule": det.get("rule"),
            "severity": severity,
            "mitre": det.get("mitre"),
            "pid": det.get("pid"),
            "evidence": det.get("evidence"),
            "status": "open",
            "received_at": received_at,
        })
        if severity in ("high", "critical"):
            alert_count += 1
            await db.security_alerts.insert_one({
                "id": str(uuid.uuid4()),
                "tenantId": tenant_id,
                "agent_id": agent_id,
                "type": "etw_behavioral_detection",
                "severity": severity,
                "title": f"ETW rule '{det.get('rule')}' on agent {agent_id}",
                "description": det.get("evidence", ""),
                "rule": det.get("rule"),
                "mitre": det.get("mitre"),
                "detection_id": det_id,
                "created_at": received_at,
                "status": "open",
            })

    # Per-batch summary — lets the platform observe drop rate / event volume per agent.
    await db.agent_telemetry_batches.insert_one({
        "id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "batch_id": batch_id,
        "event_count": len(docs),
        "detection_count": len(detections),
        "dropped_events": int(payload.get("dropped_events") or 0),
        "collected_at": payload.get("collected_at"),
        "received_at": received_at,
    })

    return {"ok": True, "stored": len(docs), "detections": len(detections),
            "alerts": alert_count, "batch_id": batch_id}


@router.post("/{agent_id}/logs/raw")
async def ingest_raw_logs(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    _auth=Depends(verify_agent_key),
):
    """Ingest a batch of raw OS logs (syslog / Windows Event Log lines) from
    the legacy Python agent's log_shipper capability.

    Body: {agent_id, logs: [{source, raw_message, collected_at}, ...]}. This
    route did not exist before — log_shipper.py has always POSTed here, and
    every attempt 404'd, silently buffering every log line to local disk
    forever instead of shipping it. Stored into the same db.logs collection
    log_endpoints.py's GET /api/logs already reads, so shipped lines appear
    in the existing Logs UI with no new frontend surface needed.
    """
    tenant_id = _auth.get("id") or _auth.get("tenant_id") or ""
    received_at = datetime.now(timezone.utc)

    raw_logs = payload.get("logs")
    logs: List[Dict[str, Any]] = raw_logs[:_MAX_RAW_LOG_LINES] if isinstance(raw_logs, list) else []

    docs: List[Dict[str, Any]] = []
    for entry in logs:
        if not isinstance(entry, dict):
            continue
        docs.append({
            "id": str(uuid.uuid4()),
            "timestamp": entry.get("collected_at") or received_at.isoformat(),
            "severity": "INFO",
            "service": entry.get("source", "log_shipper"),
            "hostname": agent_id,
            "agentId": agent_id,
            "message": entry.get("raw_message", ""),
            "tenantId": tenant_id,
            "metadata": {},
        })

    if docs:
        await db.logs.insert_many(docs)

    return {"ok": True, "stored": len(docs)}


@router.get("/{agent_id}/telemetry")
async def get_telemetry(
    agent_id: str,
    kind: str = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    current_user=Depends(get_current_user),
):
    """Retrieve recent ETW telemetry events for an agent, newest first."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    if kind:
        query["kind"] = kind
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
    events = await db.agent_telemetry.find(query, {"_id": 0}).sort("received_at", -1).to_list(length=limit)
    return events


@router.get("/{agent_id}/detections")
async def get_detections(
    agent_id: str,
    severity: str = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    current_user=Depends(get_current_user),
):
    """Retrieve recent ETW behavioural detections for an agent, newest first."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    if severity:
        query["severity"] = severity.lower()
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
    dets = await db.agent_detections.find(query, {"_id": 0}).sort("received_at", -1).to_list(length=limit)
    return dets
