"""
EDR Telemetry API Endpoints
Receives real-time process/network/alert events from EDR agents.
Stores in MongoDB and surfaces them to the frontend EDR Dashboard.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
import asyncio

router = APIRouter(prefix="/api/edr", tags=["EDR - Real-Time Telemetry"])


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

@router.post("/events")
async def ingest_edr_events(batch: EDREventBatch):
    """
    Receive real-time EDR telemetry from an agent.
    Stores events and alerts in MongoDB.
    Called by the agent every ~30 seconds.
    """
    db = get_database()
    now = datetime.utcnow()

    # Store alert documents
    if batch.alerts:
        alert_docs = []
        for alert in batch.alerts:
            alert_docs.append({
                **alert,
                "agent_id": batch.agent_id,
                "hostname": batch.hostname,
                "ingested_at": now.isoformat(),
                "acknowledged": False,
            })
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
                  "acknowledged_at": datetime.utcnow().isoformat()}}
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
    since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
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
           "added_at": datetime.utcnow().isoformat()}
    await db.edr_ioc.insert_one(doc)
    return {"status": "IOC added", "ioc": ioc.dict()}


@router.get("/ioc")
async def list_ioc(current_user: TokenData = Depends(get_current_user)):
    """List all IOCs in the blocklist."""
    db = get_database()
    iocs = await db.edr_ioc.find({}, {"_id": 0}).to_list(length=1000)
    return iocs
