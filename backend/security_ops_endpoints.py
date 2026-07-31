import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from authentication_service import get_current_user
from database import get_database
from rbac_utils import verify_permission

logger = logging.getLogger("security_ops_endpoints")
router = APIRouter(prefix="/api/security-ops", tags=["Security Ops"])

async def check_ops_permission(current_user=Depends(get_current_user)):
    if not await verify_permission(current_user, "manage:active_response"):
        raise HTTPException(status_code=403, detail="Permission denied")
    return current_user

@router.get("/findings", dependencies=[Depends(check_ops_permission)])
async def get_findings(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    scans = await db.security_scan_results.find({"tenantId": tenant_id}).to_list(length=200)
    vulns = await db.vulnerabilities.find({"tenantId": tenant_id}).to_list(length=200)
    fim = await db.fim_events.find({"tenantId": tenant_id}).to_list(length=200)

    findings = []
    for s in scans:
        findings.append({"source": "scan", "severity": s.get("severity", "medium"), "hostname": s.get("agentId"), "target": s.get("target"), "verdict_or_detail": s.get("verdict"), "ts": s.get("created_at")})
    for v in vulns:
        findings.append({"source": "vulnerability", "severity": v.get("severity", "medium"), "hostname": v.get("assetId"), "target": v.get("cveId"), "verdict_or_detail": v.get("status"), "ts": v.get("created_at")})
    for f in fim:
        findings.append({"source": "fim", "severity": "medium", "hostname": f.get("agent_id"), "target": f.get("path"), "verdict_or_detail": f.get("change_type"), "ts": f.get("timestamp")})

    findings.sort(key=lambda x: x["ts"], reverse=True)
    return {"findings": findings[offset:offset + limit]}

@router.get("/remediation-queue", dependencies=[Depends(check_ops_permission)])
async def get_remediation_queue(current_user=Depends(get_current_user)):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    return await db.remediation_requests.find({
        "tenantId": tenant_id, "status": {"$in": ["pending_approval", "dispatched", "in_progress"]}
    }).to_list(length=200)

@router.post("/trigger-scan", dependencies=[Depends(check_ops_permission)])
async def trigger_scan(body: Dict[str, Any] = Body(...), current_user=Depends(get_current_user)):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    agent = await db.agents.find_one({"id": body.get("agent_id"), "tenantId": tenant_id})
    if not agent: raise HTTPException(status_code=404, detail="Agent not found")

    cmd_map = {"file": "scan_file", "vuln": "vuln-scan", "fim": "fim"}
    if body.get("type") not in cmd_map: raise HTTPException(status_code=400, detail="Invalid type")

    await db.agent_instructions.insert_one({
        "type": cmd_map[body["type"]],
        "agent_id": body["agent_id"],
        "payload": {"path": body.get("target")} if body.get("target") else {},
        "status": "pending", "triggered_by": "operator", "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"queued": True}

@router.get("/fim-status", dependencies=[Depends(check_ops_permission)])
async def get_fim_status(current_user=Depends(get_current_user)):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    agents = await db.agents.find({"tenantId": tenant_id, "meta.capabilities.fim.enabled": True}).to_list(length=100)
    status = []
    for a in agents:
        status.append({"agent_id": a["id"], "hostname": a.get("hostname"), "events_count": await db.fim_events.count_documents({"agent_id": a["id"], "tenantId": tenant_id})})
    return status
