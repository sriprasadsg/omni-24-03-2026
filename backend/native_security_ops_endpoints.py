import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from authentication_service import get_current_user
from database import get_database
from rbac_utils import verify_permission

logger = logging.getLogger("native_security_ops_endpoints")
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
    # Status vocabulary set by autonomous_remediation_service.remediate()/
    # _dispatch_and_verify() (Phase 53): pending_approval (awaiting operator
    # approve/deny) and dispatching/deferred (in flight) are the "queue";
    # resolved/failed/unverified/denied/dry_run are terminal.
    return await db.remediation_requests.find(
        {"tenantId": tenant_id, "status": {"$in": ["pending_approval", "dispatching", "deferred"]}},
        {"_id": 0},
    ).to_list(length=200)

@router.post("/trigger-scan", dependencies=[Depends(check_ops_permission)])
async def trigger_scan(body: Dict[str, Any] = Body(...), current_user=Depends(get_current_user)):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    agent = await db.agents.find_one({"id": body.get("agent_id"), "tenantId": tenant_id})
    if not agent: raise HTTPException(status_code=404, detail="Agent not found")

    cmd_map = {"file": "scan_file", "vuln": "vuln-scan", "fim": "fim"}
    if body.get("type") not in cmd_map: raise HTTPException(status_code=400, detail="Invalid type")

    task_id = f"SCAN-{uuid.uuid4().hex}"
    payload = {"path": body.get("target")} if body.get("target") else {}
    await db.agent_instructions.insert_one({
        "id": task_id,
        "type": cmd_map[body["type"]],
        "agent_id": body["agent_id"],
        "payload": payload,
        "parameters": payload,
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

@router.get("/summary", dependencies=[Depends(check_ops_permission)])
async def get_security_summary(current_user=Depends(get_current_user)):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)

    scans = await db.security_scan_results.find({"tenantId": tenant_id}).to_list(length=1000)
    vulns = await db.vulnerabilities.find({"tenantId": tenant_id}).to_list(length=1000)

    critical_findings = sum(1 for v in vulns if v.get("severity") == "critical")
    critical_findings += sum(1 for s in scans if s.get("severity") == "critical")

    open_remediations = await db.remediation_requests.count_documents({
        "tenantId": tenant_id, "status": {"$in": ["pending_approval", "dispatching", "deferred"]}
    })

    fim_agents = await db.agents.find({"tenantId": tenant_id, "meta.capabilities.fim.enabled": True}).to_list(length=200)
    # Rust agent's DriftEvent serde tag emits exact variant names (Changed/
    # Added/Removed/BaselineReset) — see fim_baseline.rs.
    fim_drift_detected = await db.fim_events.count_documents(
        {"tenantId": tenant_id, "change_type": {"$in": ["Changed", "Added", "Removed"]}}
    ) > 0

    return {
        "totalFindings": len(scans) + len(vulns),
        "criticalFindings": critical_findings,
        "openRemediations": open_remediations,
        "agentsWithFim": len(fim_agents),
        "fimDriftDetected": fim_drift_detected,
    }
