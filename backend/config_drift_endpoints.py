"""Configuration Drift Detection Endpoints — /api/config-drift/"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from authentication_service import get_current_user, TokenData
from database import get_database
from datetime import datetime, timezone
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api/config-drift", tags=["Config Drift"])


class BaselineCapture(BaseModel):
    agent_id: str
    config_keys: List[str] = []  # empty = capture all monitored keys


class RemediateRequest(BaseModel):
    notes: str = ""


def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


# Default monitored config keys (infrastructure / security settings)
DEFAULT_MONITORED_KEYS = [
    "firewall.enabled", "firewall.default_policy",
    "ssh.permit_root_login", "ssh.password_auth", "ssh.port",
    "selinux.mode", "apparmor.status",
    "auditd.enabled", "auditd.rules_hash",
    "ntp.servers", "ntp.enabled",
    "password.min_length", "password.complexity", "password.max_age",
    "screen_lock.enabled", "screen_lock.timeout",
    "auto_update.enabled", "auto_update.security_only",
    "remote_desktop.enabled", "telnet.enabled",
    "disk_encryption.enabled", "disk_encryption.algorithm",
    "smb_signing.required", "ntlm_auth.restricted",
]


@router.post("/baseline/{agent_id}", status_code=201)
async def capture_baseline(
    agent_id: str,
    body: BaselineCapture,
    current_user: TokenData = Depends(get_current_user),
):
    """Capture a configuration baseline snapshot for an agent."""
    db = get_database()
    agent = await db.agents.find_one(
        {"id": agent_id, "tenantId": current_user.tenant_id}
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    keys = body.config_keys if body.config_keys else DEFAULT_MONITORED_KEYS
    now = datetime.now(timezone.utc).isoformat()
    # Read current config values from stored agent config data
    config_snapshot = await db.agent_config.find_one(
        {"agent_id": agent_id, "tenantId": current_user.tenant_id}
    ) or {}
    values = {k: config_snapshot.get(k, "unknown") for k in keys}
    snapshot = {
        "id": str(uuid.uuid4()),
        "tenantId": current_user.tenant_id,
        "agent_id": agent_id,
        "hostname": agent.get("hostname"),
        "platform": agent.get("platform"),
        "config_values": values,
        "monitored_keys": keys,
        "captured_at": now,
        "captured_by": current_user.email,
        "is_active": True,
    }
    # Deactivate previous baseline
    await db.config_baselines.update_many(
        {"agent_id": agent_id, "tenantId": current_user.tenant_id},
        {"$set": {"is_active": False}},
    )
    await db.config_baselines.insert_one({**snapshot})
    _strip_id(snapshot)
    return snapshot


@router.get("/snapshots")
async def list_snapshots(
    agent_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    """List configuration baseline snapshots."""
    db = get_database()
    query: dict = {"tenantId": current_user.tenant_id, "is_active": True}
    if agent_id:
        query["agent_id"] = agent_id
    results = []
    async for doc in db.config_baselines.find(query).sort("captured_at", -1):
        _strip_id(doc)
        # Attach drift count
        doc["drift_count"] = await db.config_drift_events.count_documents(
            {"agent_id": doc["agent_id"], "tenantId": current_user.tenant_id, "status": "open"}
        )
        results.append(doc)
    return results


@router.get("/drift")
async def list_drift(
    agent_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: str = Query("open"),
    current_user: TokenData = Depends(get_current_user),
):
    """List agents with detected configuration drift."""
    db = get_database()
    query: dict = {"tenantId": current_user.tenant_id, "status": status}
    if agent_id:
        query["agent_id"] = agent_id
    if severity:
        query["severity"] = severity
    results = []
    async for doc in db.config_drift_events.find(query).sort("detected_at", -1).limit(500):
        _strip_id(doc)
        results.append(doc)
    return results


@router.get("/drift/{agent_id}")
async def agent_drift_detail(
    agent_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Detailed drift report for a specific agent — what changed vs baseline."""
    db = get_database()
    baseline = await db.config_baselines.find_one(
        {"agent_id": agent_id, "tenantId": current_user.tenant_id, "is_active": True}
    )
    if not baseline:
        raise HTTPException(status_code=404, detail="No baseline found for this agent")
    _strip_id(baseline)
    current_config = await db.agent_config.find_one(
        {"agent_id": agent_id, "tenantId": current_user.tenant_id}
    ) or {}
    drift_items = []
    for key in baseline.get("monitored_keys", []):
        expected = baseline["config_values"].get(key, "unknown")
        actual = current_config.get(key, "unknown")
        if expected != actual and actual != "unknown":
            drift_items.append({
                "key": key,
                "expected": expected,
                "actual": actual,
                "severity": _classify_severity(key),
                "detected_at": datetime.now(timezone.utc).isoformat(),
            })
    return {
        "agent_id": agent_id,
        "hostname": baseline.get("hostname"),
        "baseline_captured_at": baseline.get("captured_at"),
        "drift_count": len(drift_items),
        "drift_items": drift_items,
    }


@router.post("/remediate/{agent_id}")
async def mark_remediated(
    agent_id: str,
    body: RemediateRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Mark all open drift events for an agent as remediated."""
    db = get_database()
    result = await db.config_drift_events.update_many(
        {"agent_id": agent_id, "tenantId": current_user.tenant_id, "status": "open"},
        {"$set": {
            "status": "remediated",
            "remediated_at": datetime.now(timezone.utc).isoformat(),
            "remediated_by": current_user.email,
            "notes": body.notes,
        }},
    )
    return {"agent_id": agent_id, "remediated_count": result.modified_count}


@router.get("/stats")
async def drift_stats(current_user: TokenData = Depends(get_current_user)):
    """Tenant-level drift statistics."""
    db = get_database()
    total_baselines = await db.config_baselines.count_documents(
        {"tenantId": current_user.tenant_id, "is_active": True}
    )
    open_drifts = await db.config_drift_events.count_documents(
        {"tenantId": current_user.tenant_id, "status": "open"}
    )
    pipeline = [
        {"$match": {"tenantId": current_user.tenant_id, "status": "open"}},
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]
    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    async for row in db.config_drift_events.aggregate(pipeline):
        if row["_id"] in by_severity:
            by_severity[row["_id"]] = row["count"]
    agents_with_drift = await db.config_drift_events.distinct(
        "agent_id", {"tenantId": current_user.tenant_id, "status": "open"}
    )
    return {
        "total_baselines": total_baselines,
        "open_drifts": open_drifts,
        "agents_with_drift": len(agents_with_drift),
        "by_severity": by_severity,
    }


def _classify_severity(key: str) -> str:
    critical_keys = {"ssh.permit_root_login", "firewall.enabled", "disk_encryption.enabled", "selinux.mode"}
    high_keys = {"password.min_length", "ssh.password_auth", "ntlm_auth.restricted", "smb_signing.required"}
    if key in critical_keys:
        return "critical"
    if key in high_keys:
        return "high"
    return "medium"
