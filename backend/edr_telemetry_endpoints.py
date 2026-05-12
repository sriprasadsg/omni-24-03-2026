"""
EDR Telemetry API Endpoints
Receives real-time process/network/alert events from EDR agents.
Stores in MongoDB and surfaces them to the frontend EDR Dashboard.
Automatically routes each incoming alert through the response orchestrator
so that enabled policies can trigger kill/quarantine/isolate actions.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from response_orchestrator import ResponseOrchestrator
from enhanced_playbook_engine import PlaybookExecutionEngine
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/edr", tags=["EDR - Real-Time Telemetry"])

# Shared orchestrator instance (same as response_endpoints.py)
_orchestrator = ResponseOrchestrator()


_RANSOMWARE_ALERT_TYPES = {"RANSOMWARE_DETECTED", "ransomware_detected", "file_encryption", "mass_file_rename", "shadow_copy_deletion"}


async def _run_orchestrator(alert: Dict[str, Any], agent_id: str) -> None:
    """Background coroutine: evaluate one EDR alert against all enabled policies."""
    try:
        dispatched = await _orchestrator.evaluate_alert(alert, agent_id)
        if dispatched:
            logger.info(
                "EDR auto-response: %d task(s) dispatched for alert %s on agent %s",
                len(dispatched), alert.get("alert_id"), agent_id,
            )
    except Exception as exc:
        logger.error("Orchestrator evaluation failed for alert %s: %s",
                     alert.get("alert_id"), exc)


async def _run_ransomware_playbooks(alert: Dict[str, Any], agent_id: str) -> None:
    """
    Immediately fire any enabled playbooks with trigger_type='alert' and
    category='ransomware_recovery' when a ransomware alert is ingested.
    This fires without waiting for the 5-minute XDR correlation scan.
    """
    try:
        from database import get_database
        db = get_database()
        playbooks = await db._db.playbooks.find(
            {"trigger_type": "alert", "trigger_conditions.alert_types": alert.get("type"), "enabled": True},
            {"_id": 0}
        ).to_list(length=10)
        if not playbooks:
            # Fall back: find the ransomware XDR seed playbook by id
            playbooks = await db._db.playbooks.find(
                {"id": "xdr-ransomware-recovery", "enabled": True},
                {"_id": 0}
            ).to_list(length=1)
        for pb in playbooks:
            engine = PlaybookExecutionEngine()
            trigger_data = {**alert, "agent_id": agent_id}
            asyncio.create_task(engine.execute_playbook(pb, trigger_data))
            logger.warning(
                "Ransomware alert %s — firing playbook '%s' immediately",
                alert.get("alert_id"), pb.get("name"),
            )
    except Exception as exc:
        logger.error("Ransomware playbook trigger failed for alert %s: %s",
                     alert.get("alert_id"), exc)


# ------------------------------------------------------------------
# Pydantic Models
# ------------------------------------------------------------------

class EDREventBatch(BaseModel):
    agent_id: str
    hostname: str
    timestamp: str
    process_tree: List[Dict[str, Any]] = []
    network_connections: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    alert_count: int = 0
    process_count: int = 0
    etw_events_captured: int = 0


class IOCEntry(BaseModel):
    sha256: Optional[str] = None
    process_name: Optional[str] = None
    ip_address: Optional[str] = None
    description: str
    severity: str = "high"


# ------------------------------------------------------------------
# Ingest endpoint (called by agent)
# ------------------------------------------------------------------

async def _verify_edr_agent(
    batch: EDREventBatch,
    x_tenant_key: Optional[str] = Header(None, alias="X-Tenant-Key"),
    authorization: Optional[str] = Header(None),
    db=Depends(get_database),
) -> EDREventBatch:
    """
    Verify the inbound EDR batch comes from a registered agent.
    Accepts the same credentials as other agent endpoints:
      • X-Tenant-Key header (legacy)
      • Authorization: Bearer <agent-jwt>
    Also cross-checks that batch.agent_id is registered in the tenant.
    """
    from agent_endpoints import verify_agent_key
    # Reuse the existing agent-key / JWT verifier — raises HTTP 401/403 on failure
    tenant = await verify_agent_key(x_tenant_key=x_tenant_key, authorization=authorization, db=db)

    # Ensure the reported agent_id actually belongs to the authenticated tenant
    tenant_id = tenant.get("id") or tenant.get("tenantId")
    agent = await db.agents.find_one({"id": batch.agent_id, "tenantId": tenant_id}, {"_id": 1})
    if not agent:
        # Allow newly-registered agents a grace period (registration may still be in-flight)
        agent = await db.agents.find_one({"id": batch.agent_id}, {"_id": 1, "tenantId": 1})
        if not agent:
            raise HTTPException(status_code=403, detail=f"Agent '{batch.agent_id}' is not registered")
        if agent.get("tenantId") != tenant_id:
            raise HTTPException(status_code=403, detail=f"Agent '{batch.agent_id}' does not belong to this tenant")
    return batch


@router.post("/events")
async def ingest_edr_events(batch: EDREventBatch = Depends(_verify_edr_agent)):
    """
    Receive real-time EDR telemetry from an authenticated agent.
    Stores events and alerts in MongoDB and routes alerts through the response orchestrator.
    """
    db = get_database()
    now = datetime.now(timezone.utc)

    # Store alert documents and route each through the response orchestrator
    if batch.alerts:
        alert_docs = []
        for alert in batch.alerts:
            enriched = {
                **alert,
                "agent_id": batch.agent_id,
                "hostname": batch.hostname,
                "ingested_at": now.isoformat(),
                "acknowledged": False,
            }
            alert_docs.append(enriched)
            # Fire-and-forget: evaluate policy match in background so ingest
            # response is not delayed by policy evaluation I/O.
            asyncio.create_task(_run_orchestrator(enriched, batch.agent_id))
            # Ransomware alerts bypass the 5-min XDR scan and trigger playbooks immediately.
            if alert.get("type") in _RANSOMWARE_ALERT_TYPES:
                asyncio.create_task(_run_ransomware_playbooks(enriched, batch.agent_id))
        await db.edr_alerts.insert_many(alert_docs)

    # Store a telemetry snapshot (capped at last 500 per agent)
    await db.edr_telemetry.insert_one({
        "agent_id": batch.agent_id,
        "hostname": batch.hostname,
        "timestamp": batch.timestamp,
        "process_count": batch.process_count,
        "alert_count": batch.alert_count,
        "etw_events_captured": batch.etw_events_captured,
        "network_connection_count": len(batch.network_connections),
        "ingested_at": now.isoformat(),
        # Store top 20 processes only for the snapshot
        "processes_sample": batch.process_tree[:20],
        "connections_sample": batch.network_connections[:30],
    })

    # Trim old snapshots (keep last 500 per agent)
    count = await db.edr_telemetry.count_documents({"agent_id": batch.agent_id})
    if count > 500:
        oldest = await db.edr_telemetry.find(
            {"agent_id": batch.agent_id}, {"_id": 1}
        ).sort("ingested_at", 1).limit(count - 500).to_list(length=500)
        ids = [d["_id"] for d in oldest]
        if ids:
            await db.edr_telemetry.delete_many({"_id": {"$in": ids}})

    return {
        "status": "ok",
        "alerts_stored": len(batch.alerts),
        "agent_id": batch.agent_id
    }


# ------------------------------------------------------------------
# Alerts
# ------------------------------------------------------------------

@router.get("/alerts")
async def get_edr_alerts(
    agent_id: Optional[str] = None,
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    current_user: TokenData = Depends(get_current_user)
):
    """Get EDR alerts with optional filters."""
    db = get_database()
    query: Dict[str, Any] = {}
    if agent_id:
        query["agent_id"] = agent_id
    if severity:
        query["severity"] = severity
    if acknowledged is not None:
        query["acknowledged"] = acknowledged

    alerts = await db.edr_alerts.find(
        query, {"_id": 0}
    ).sort("ingested_at", -1).limit(limit).to_list(length=limit)
    return alerts


@router.patch("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Mark an EDR alert as acknowledged."""
    db = get_database()
    result = await db.edr_alerts.update_one(
        {"alert_id": alert_id},
        {"$set": {"acknowledged": True, "acknowledged_by": current_user.username,
                  "acknowledged_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "acknowledged", "alert_id": alert_id}


# ------------------------------------------------------------------
# Process Tree / Live Telemetry
# ------------------------------------------------------------------

@router.get("/process-tree/{agent_id}")
async def get_process_tree(
    agent_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Get the most recent process snapshot for an agent."""
    db = get_database()
    snapshot = await db.edr_telemetry.find_one(
        {"agent_id": agent_id}, {"_id": 0},
        sort=[("ingested_at", -1)]
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="No telemetry found for this agent")
    return snapshot


@router.get("/telemetry/summary")
async def get_telemetry_summary(
    current_user: TokenData = Depends(get_current_user)
):
    """Get aggregated EDR health summary across all agents."""
    db = get_database()
    # Last 24h alerts by severity
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    pipeline = [
        {"$match": {"ingested_at": {"$gte": since}}},
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]
    severity_counts = await db.edr_alerts.aggregate(pipeline).to_list(length=20)
    total_alerts = await db.edr_alerts.count_documents({"ingested_at": {"$gte": since}})
    unack = await db.edr_alerts.count_documents({"acknowledged": False})
    critical = await db.edr_alerts.count_documents({
        "severity": "critical", "acknowledged": False
    })

    return {
        "total_alerts_24h": total_alerts,
        "unacknowledged": unack,
        "critical_unacknowledged": critical,
        "by_severity": {s["_id"]: s["count"] for s in severity_counts},
    }


# ------------------------------------------------------------------
# IOC Management
# ------------------------------------------------------------------

@router.post("/ioc")
async def add_ioc(
    ioc: IOCEntry,
    current_user: TokenData = Depends(get_current_user)
):
    """Add a new Indicator of Compromise to the blocklist."""
    db = get_database()
    doc = {**ioc.dict(), "added_by": current_user.username,
           "added_at": datetime.now(timezone.utc).isoformat()}
    await db.edr_ioc.insert_one(doc)
    return {"status": "IOC added", "ioc": ioc.dict()}


@router.get("/ioc")
async def list_ioc(current_user: TokenData = Depends(get_current_user)):
    """List all IOCs in the blocklist."""
    db = get_database()
    iocs = await db.edr_ioc.find({}, {"_id": 0}).to_list(length=1000)
    return iocs
