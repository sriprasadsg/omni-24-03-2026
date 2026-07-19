from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Dict, Any
from database import get_database
from authentication_service import get_current_user
from datetime import datetime, timezone
import uuid
from agent_auth import verify_agent_key
import logging

router = APIRouter(prefix="/api/agents", tags=["Agents"])
logger = logging.getLogger("agent_security_endpoints")

# Cap on agent-supplied arrays fanned out into per-item DB writes
_MAX_ARRAY = 500


@router.post("/{agent_id}/fim-events")
async def ingest_fim_event(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    _auth=Depends(verify_agent_key),
):
    """Receive FIM events via HTTP when Socket.IO is unavailable."""
    tenant_id = _auth.get("tenant_id") or _auth.get("tenantId") or ""
    doc = {
        "id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "path": payload.get("path", ""),
        "event_type": payload.get("event_type", "unknown"),
        "severity": payload.get("severity", "high"),
        "message": payload.get("message", ""),
        "source": payload.get("source", "FileWatcher"),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.fim_events.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "event_id": doc["id"]}


@router.get("/{agent_id}/fim-events")
async def list_fim_events(
    agent_id: str,
    limit: int = 100,
    db=Depends(get_database),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Retrieve FIM events for a given agent (operator view)."""
    _SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
    user_role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)
    query: Dict[str, Any] = {"agent_id": agent_id}
    if user_role not in _SUPER_ROLES:
        # Verify agent belongs to caller's tenant before returning events
        agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 1})
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        query["tenantId"] = tenant_id
    cursor = db.fim_events.find(query, {"_id": 0}).sort("received_at", -1).limit(limit)
    return {"events": await cursor.to_list(limit)}


@router.post("/{agent_id}/shadow-ai-scan")
async def post_shadow_ai_scan(
    agent_id: str,
    body: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent posts Shadow AI detection results (local AI processes, ports, cloud connections)."""
    db = get_database()
    tenant_id = _tenant.get("id") or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    scanned_at = datetime.now(timezone.utc).isoformat()
    doc = {
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "scanned_at": scanned_at,
        "detected_count": body.get("detected_count", 0),
        "ai_connections": body.get("ai_connections", []),
        "local_ai_processes": body.get("local_ai_processes", []),
        "local_ai_ports": body.get("local_ai_ports", []),
    }
    await db.shadow_ai_scans.insert_one(doc)
    doc.pop("_id", None)

    for conn in body.get("ai_connections", [])[:_MAX_ARRAY]:
        await db.shadow_ai_events.update_one(
            {"agent_id": agent_id, "remote_host": conn.get("remote_host"), "process": conn.get("process")},
            {"$set": {
                "agent_id": agent_id,
                "tenantId": tenant_id,
                "process": conn.get("process"),
                "remote_ip": conn.get("remote_ip"),
                "remote_host": conn.get("remote_host"),
                "timestamp": scanned_at,
            }},
            upsert=True,
        )

    for proc in body.get("local_ai_processes", [])[:_MAX_ARRAY]:
        await db.security_alerts.insert_one({
            "tenantId": tenant_id,
            "agent_id": agent_id,
            "type": "shadow_ai_process",
            "severity": "medium",
            "title": f"Unauthorized AI process: {proc.get('name', 'unknown')}",
            "description": f"Local AI process '{proc.get('name')}' (PID {proc.get('pid')}) detected on agent {agent_id}",
            "created_at": scanned_at,
            "status": "open",
        })

    return {"success": True, "detected_count": doc["detected_count"]}


@router.get("/{agent_id}/shadow-ai-scans")
async def get_shadow_ai_scans(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Retrieve recent Shadow AI scan history for an agent."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
    scans = await db.shadow_ai_scans.find(query, {"_id": 0}).sort("scanned_at", -1).to_list(length=limit)
    return scans


@router.post("/{agent_id}/vulnerability-scan")
async def post_vulnerability_scan(
    agent_id: str,
    body: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent posts its latest vulnerability scan results (OSV-backed)."""
    db = get_database()
    tenant_id = _tenant.get("id") or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    doc = {
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "total_packages": body.get("total_packages", 0),
        "vulnerable_packages": body.get("vulnerable_packages", []),
        "total_cves": body.get("total_cves", 0),
        "scan_source": body.get("scan_source", "osv"),
        "os_patches": body.get("os_patches", {}),
    }

    await db.agent_vulnerability_scans.insert_one(doc)
    doc.pop("_id", None)

    for pkg in body.get("vulnerable_packages", [])[:_MAX_ARRAY]:
        for cve in pkg.get("cves", []):
            severity = cve.get("severity", "Unknown")
            if severity in ("CRITICAL", "HIGH"):
                await db.vulnerabilities.update_one(
                    {"cveId": cve.get("id"), "agentId": agent_id},
                    {"$set": {
                        "cveId": cve.get("id"),
                        "agentId": agent_id,
                        "tenantId": tenant_id,
                        "affectedSoftware": pkg.get("name", ""),
                        "severity": severity,
                        "description": cve.get("summary", ""),
                        "source": "agent_osv_scan",
                        "reported_at": doc["scanned_at"],
                    }},
                    upsert=True,
                )

    return {"success": True, "scan_id": str(doc.get("_id", "")), "total_cves": doc["total_cves"]}


@router.get("/{agent_id}/vulnerability-scans")
async def get_vulnerability_scans(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Retrieve recent vulnerability scan history for an agent."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
    scans = await db.agent_vulnerability_scans.find(query, {"_id": 0}).sort("scanned_at", -1).to_list(length=limit)
    return scans


@router.post("/{agent_id}/persistence-findings")
async def post_persistence_findings(
    agent_id: str,
    body: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent posts persistence mechanism findings (registry, cron, startup entries)."""
    db = get_database()
    tenant_id = _tenant.get("id") or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    doc = {
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "total_entries": body.get("total_entries", 0),
        "suspicious_entries": body.get("suspicious_entries", []),
        "critical_count": body.get("critical_count", 0),
        "high_count": body.get("high_count", 0),
        "platform": body.get("platform", "unknown"),
    }

    await db.agent_persistence_findings.insert_one(doc)
    doc.pop("_id", None)

    for entry in body.get("suspicious_entries", [])[:_MAX_ARRAY]:
        if entry.get("severity") in ("Critical", "High"):
            await db.security_alerts.insert_one({
                "tenantId": tenant_id,
                "agent_id": agent_id,
                "type": "persistence_mechanism",
                "severity": entry.get("severity", "High").lower(),
                "title": f"Suspicious persistence: {entry.get('name', 'unknown')}",
                "description": entry.get("command", entry.get("path", "")),
                "location": entry.get("location", ""),
                "risk_score": entry.get("risk_score", 0),
                "created_at": doc["scanned_at"],
                "status": "open",
            })

    return {"success": True, "critical_count": doc["critical_count"], "high_count": doc["high_count"]}


@router.get("/{agent_id}/persistence-findings")
async def get_persistence_findings(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Retrieve recent persistence scan history for an agent."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
    findings = await db.agent_persistence_findings.find(query, {"_id": 0}).sort("scanned_at", -1).to_list(length=limit)
    return findings
