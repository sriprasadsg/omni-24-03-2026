from fastapi import APIRouter, Depends, HTTPException, Body, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from database import get_database
from authentication_service import get_current_user
from datetime import datetime, timezone
import uuid
from agent_auth import verify_agent_key
from rate_limiter import limiter
import logging

router = APIRouter(prefix="/api/agents", tags=["Agents"])
logger = logging.getLogger("agent_tasks_endpoints")

APPROVALS_COLLECTION = "agent_approvals"
_TASK_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}


class ApprovalRequestModel(BaseModel):
    agent_id: str = Field(..., max_length=100)
    action_type: str = Field(..., max_length=100)
    description: str = Field(..., max_length=2000)
    risk_score: float
    reasoning: str = Field(..., max_length=5000)
    details: Dict[str, Any]

class ApprovalDecisionModel(BaseModel):
    decision: str = Field(..., max_length=20)  # "approve" or "reject"
    reason: Optional[str] = Field(None, max_length=2000)


@router.get("/{hostname}/instructions")
async def get_agent_instructions(
    hostname: str,
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """Get pending instructions for a specific agent (by hostname). Polled by the agent."""
    db = get_database()
    tenant_id = _tenant.get("tenant_id") or _tenant.get("tenantId") or _tenant.get("id", "")

    agent = await db.agents.find_one({"hostname": hostname, "tenantId": tenant_id})
    agent_id = agent["id"] if agent else hostname

    query = {
        "$or": [{"agent_id": hostname}, {"agent_id": agent_id}],
        "status": "pending",
        "tenantId": tenant_id,
    }

    instructions = await db.agent_instructions.find(query).to_list(length=10)

    if instructions:
        ids = [i["_id"] for i in instructions]
        await db.agent_instructions.update_many(
            {"_id": {"$in": ids}},
            {"$set": {"status": "sent", "sent_at": datetime.now(timezone.utc).isoformat()}}
        )

    return [
        {"task_id": i.get("id") or str(i.get("_id", "")), "instruction": i.get("instruction") or i.get("type"), "payload": i.get("payload")}
        for i in instructions
    ]


@router.post("/{hostname}/instructions/result")
async def report_instruction_result(
    hostname: str,
    result: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """Agent reports the result of an instruction execution."""
    logger.info("Agent %s reported instruction result: type=%s status=%s", hostname, result.get("type"), result.get("status"))

    db = get_database()

    task_id = result.get("task_id")
    if task_id:
        raw_status = result.get("status", "unknown")
        mapped = "SUCCESS" if raw_status == "success" else ("FAILURE" if raw_status == "error" else raw_status.upper())
        await db.agent_instructions.update_one(
            {"id": task_id},
            {"$set": {
                "status": mapped,
                "result": {
                    "message": result.get("message") or result.get("details", ""),
                    "error": result.get("error"),
                    "raw_status": raw_status,
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )

    if result.get("compliance_checks"):
        try:
            from compliance_endpoints import process_automated_evidence
            await process_automated_evidence(hostname, result, db)
        except Exception as e:
            logger.error("Failed to process compliance results: %s", e)

    return {"status": "ok"}


@router.post("/dispatch")
async def dispatch_agent_task(
    task: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Dispatch a task to an agent."""
    db = get_database()
    task_id = f"task-{datetime.now(timezone.utc).timestamp()}"

    new_task = {
        "id": task_id, "description": task.get("description"), "agentId": task.get("agentId"),
        "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": getattr(current_user, "username", None) or (current_user.get("username") if isinstance(current_user, dict) else None),
    }

    await db.agent_tasks.insert_one(new_task)
    return {"success": True, "taskId": task_id}


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, current_user=Depends(get_current_user)):
    """Frontend polls this for deployment task status."""
    db = get_database()
    user_role = getattr(current_user, "role", "")
    is_super_admin = user_role in {"Super Admin", "super_admin", "platform-admin"}
    user_tenant = getattr(current_user, "tenant_id", None)

    task_filter: Dict[str, Any] = {"id": task_id}
    if not is_super_admin and user_tenant:
        task_filter["tenantId"] = user_tenant

    task = await db.agent_instructions.find_one(task_filter)
    if task:
        return {
            "task_id": task.get("id", task_id), "status": task.get("status", "unknown"),
            "agent_id": task.get("agent_id"), "instruction": task.get("instruction"),
            "payload": task.get("payload"), "result": task.get("result"),
            "created_at": task.get("created_at"), "updated_at": task.get("updated_at"),
        }

    task = await db.agent_tasks.find_one(task_filter, {"_id": 0})
    if task:
        return task

    raise HTTPException(status_code=404, detail="Task not found")


@router.post("/{agent_id}/discovery/scan")
async def trigger_network_scan(
    agent_id: str,
    current_user: Any = Depends(get_current_user)
):
    """Trigger a network scan on the agent."""
    db = get_database()
    _scan_role = getattr(current_user, "role", None)
    _scan_query: dict = {"id": agent_id}
    if _scan_role not in _TASK_SUPER_ROLES:
        _scan_tid = getattr(current_user, "tenant_id", None) or None
        if not _scan_tid:
            raise HTTPException(status_code=403, detail="Tenant context required")
        _scan_query["tenantId"] = _scan_tid

    agent = await db.agents.find_one(_scan_query)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_instruction = {
        "agent_id": agent_id, "instruction": "Start Network Scan", "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": getattr(current_user, "email", "unknown")
    }
    result = await db.agent_instructions.insert_one(new_instruction)
    return {"success": True, "message": "Network scan initiated", "instruction_id": str(result.inserted_id)}


@router.post("/{agent_id}/discovery/results")
@limiter.limit("30/minute")
async def report_network_scan_results(
    request: Request,
    agent_id: str,
    results: List[Dict[str, Any]] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """Agent reports network scan results."""
    db = get_database()

    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    tenant_id = agent.get("tenantId") or _tenant.get("id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Agent has no tenant association")

    processed_count = 0

    for device in results:
        mac = device.get("mac")
        ip = device.get("ip")
        if not ip:
            continue

        device_id = f"net-dev-{uuid.uuid5(uuid.NAMESPACE_DNS, mac if mac and mac != 'Unknown' else ip)}"

        hostname = device.get("hostname") or ""
        import re as _re
        vuln_query: dict = {"tenantId": tenant_id, "status": {"$in": ["pending", "Pending", "open", "Open"]}}
        if hostname:
            vuln_query["affectedSoftware"] = {"$regex": _re.escape(hostname), "$options": "i"}
        elif ip:
            vuln_query["affectedSoftware"] = {"$regex": _re.escape(ip), "$options": "i"}
        device_vulns = await db.patches.find(
            vuln_query, {"_id": 0, "cveId": 1, "severity": 1, "description": 1}
        ).to_list(length=20)

        live_fields = {
            "id": device_id,
            "tenantId": tenant_id,
            "discoveredBy": agent_id,
            "ipAddress": ip,
            "macAddress": mac,
            "hostname": hostname or device.get("hostname"),
            "type": device.get("device_type", "Unknown"),
            "status": device.get("status", "Up"),
            "lastSeen": datetime.now(timezone.utc).isoformat(),
            "vulnerabilities": device_vulns,
        }

        await db.network_devices.update_one(
            {"id": device_id, "tenantId": tenant_id},
            {"$set": live_fields, "$setOnInsert": {"interfaces": [], "configBackups": []}},
            upsert=True,
        )
        processed_count += 1

    return {"success": True, "processed": processed_count}


@router.post("/{agent_id}/approval-request")
async def request_approval(
    agent_id: str,
    request: ApprovalRequestModel,
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """Agent requests approval for an autonomous action."""
    request_id = str(uuid.uuid4())
    approval_tenant = _tenant.get("tenant_id") or _tenant.get("tenantId") or _tenant.get("id", "")
    approval_entry = {
        "id": request_id, "agent_id": agent_id, "tenantId": approval_tenant, "status": "pending",
        "action_type": request.action_type, "description": request.description,
        "risk_score": request.risk_score, "reasoning": request.reasoning,
        "details": request.details, "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    db = get_database()
    await db[APPROVALS_COLLECTION].insert_one(approval_entry)
    return {"status": "queued", "request_id": request_id}


@router.get("/approvals/pending")
async def get_pending_approvals(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db=Depends(get_database),
):
    """Get all pending approval requests for the dashboard."""
    query: Dict[str, Any] = {"status": "pending"}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        _tid = getattr(current_user, "tenant_id", None) or None
        if not _tid:
            raise HTTPException(status_code=403, detail="Tenant context required")
        query["tenantId"] = _tid
    approvals = await db[APPROVALS_COLLECTION].find(query, {"_id": 0}).to_list(length=500)
    return approvals


@router.post("/approvals/{request_id}/decide")
async def decide_approval(
    request_id: str,
    decision: ApprovalDecisionModel,
    current_user: dict = Depends(get_current_user),
):
    """Approve or Reject a pending request. Requires authenticated operator."""
    if decision.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")
    db = get_database()
    approval = await db[APPROVALS_COLLECTION].find_one({"id": request_id, "status": "pending"})
    if not approval:
        raise HTTPException(status_code=404, detail="Request not found or already processed")
    user_role = getattr(current_user, "role", "")
    if user_role not in {"Super Admin", "super_admin", "admin", "platform-admin"}:
        user_tenant = getattr(current_user, "tenant_id", None)
        if approval.get("tenantId") and approval.get("tenantId") != user_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to decide this request")
    result = await db[APPROVALS_COLLECTION].update_one(
        {"id": request_id, "status": "pending"},
        {"$set": {
            "status": decision.decision,
            "decision_timestamp": datetime.now(timezone.utc).isoformat(),
            "decision_reason": decision.reason,
            "decided_by": getattr(current_user, "username", str(current_user)),
        }}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Request not found or already processed")

    return {"status": "success", "decision": decision.decision}


@router.get("/agentic-decisions/all")
async def list_all_agentic_decisions(
    limit: int = 100,
    status: str = None,
    db=Depends(get_database),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Global view of all agentic decisions across every agent (operator overview)."""
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        _tid = getattr(current_user, "tenant_id", None) or None
        if not _tid:
            raise HTTPException(status_code=403, detail="Tenant context required")
        query["tenantId"] = _tid
    cursor = db.agentic_decisions.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    decisions = await cursor.to_list(limit)
    return {
        "decisions": decisions,
        "total": len(decisions),
        "pending": sum(1 for d in decisions if d.get("status") == "pending_approval"),
    }


@router.get("/{agent_id}/pending-playbooks")
async def get_pending_playbooks_for_agent(
    agent_id: str,
    db=Depends(get_database),
    _auth: Dict[str, Any] = Depends(verify_agent_key),
):
    """
    Agent polls this endpoint to discover playbooks assigned directly to it
    or triggered by agent-side events. Returned once per pending cycle.
    """
    agent = await db.agents.find_one({"id": agent_id}, {"tenantId": 1})
    if not agent:
        return []

    tenant_id = agent.get("tenantId") or None
    if not tenant_id:
        return []

    cursor = db.playbooks.find(
        {
            "tenant_id": tenant_id,
            "enabled": True,
            "$or": [
                {"assigned_agents": agent_id},
                {"trigger_type": {"$in": ["on_agent_start", "on_heartbeat", "on_threat_detected"]}},
            ],
            "acked_agents": {"$ne": agent_id},
        },
        {"_id": 0, "id": 1, "name": 1, "steps": 1, "trigger_type": 1, "trigger_conditions": 1},
    )
    return await cursor.to_list(length=20)


@router.post("/{agent_id}/playbook-ack")
@limiter.limit("60/minute")
async def ack_playbook(
    request: Request,
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    _auth: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent acknowledges receipt/execution of a playbook so it isn't re-delivered."""
    playbook_id = payload.get("playbook_id")
    status = payload.get("status", "received")
    if not playbook_id:
        return {"success": False, "reason": "playbook_id required"}

    await db.playbooks.update_one(
        {"id": playbook_id},
        {
            "$addToSet": {"acked_agents": agent_id},
            "$push": {
                "execution_log": {
                    "agent_id": agent_id,
                    "status": status,
                    "acked_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        },
    )
    return {"success": True}


@router.get("/{agent_id}/safety-rules")
async def get_safety_rules(
    agent_id: str,
    db=Depends(get_database),
    _auth: Dict[str, Any] = Depends(verify_agent_key),
):
    """
    Return tenant-specific safety guardrail rules for the agent.
    Falls back to empty lists (agent uses built-in defaults) when no record exists.
    """
    agent = await db.agents.find_one({"id": agent_id}, {"tenantId": 1})
    tenant_id = agent.get("tenantId") if agent else None
    doc = None
    if tenant_id:
        doc = await db.agent_safety_rules.find_one({"tenant_id": tenant_id}, {"_id": 0})
    return {
        "forbidden_actions": (doc or {}).get("forbidden_actions", []),
        "approval_required": (doc or {}).get("approval_required", []),
        "safe_actions": (doc or {}).get("safe_actions", []),
    }


@router.put("/{agent_id}/safety-rules")
async def update_safety_rules(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Operators update tenant-level safety rules via this endpoint."""
    agent = await db.agents.find_one({"id": agent_id}, {"tenantId": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    tenant_id = agent.get("tenantId")
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        caller_tenant = getattr(current_user, "tenant_id", None)
        if caller_tenant and caller_tenant != tenant_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this agent's rules")
    _safe_payload = {k: v for k, v in payload.items() if k not in ("tenant_id", "tenantId", "_id", "id")}
    await db.agent_safety_rules.update_one(
        {"tenant_id": tenant_id},
        {"$set": {**_safe_payload, "tenant_id": tenant_id, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "tenant_id": tenant_id}


@router.post("/{agent_id}/agentic-decision")
async def record_agentic_decision(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    _auth: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent submits an agentic reasoning decision for audit logging and optional human approval."""
    doc = {
        "id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "context": payload.get("context", {}),
        "recommended_action": payload.get("recommended_action", "none"),
        "confidence": float(payload.get("confidence", 0.0)),
        "reasoning": payload.get("reasoning", ""),
        "requires_approval": bool(payload.get("requires_approval", False)),
        "status": "pending_approval" if payload.get("requires_approval") else "auto_approved",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.agentic_decisions.insert_one(doc)
    doc.pop("_id", None)
    return {"decision_id": doc["id"], "status": doc["status"]}


@router.get("/{agent_id}/agentic-decisions")
async def list_agentic_decisions(
    agent_id: str,
    limit: int = 50,
    db=Depends(get_database),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Operators view the agent's autonomous decision history."""
    cursor = db.agentic_decisions.find(
        {"agent_id": agent_id}, {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    return {"decisions": await cursor.to_list(limit)}


@router.patch("/{agent_id}/agentic-decisions/{decision_id}")
async def approve_agentic_decision(
    agent_id: str,
    decision_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Operator approves or rejects a pending agentic decision."""
    approved = bool(payload.get("approved", False))
    await db.agentic_decisions.update_one(
        {"id": decision_id, "agent_id": agent_id},
        {"$set": {
            "status": "approved" if approved else "rejected",
            "reviewer_note": payload.get("reviewer_note", ""),
            "reviewed_by": current_user.get("sub"),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"ok": True, "approved": approved}


@router.get("/{agent_id}/approvals/{request_id}")
async def get_approval_status(
    agent_id: str,
    request_id: str,
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent polls this to check whether a pending approval has been decided."""
    db = get_database()
    from bson import ObjectId

    query: Dict[str, Any] = {"agent_id": agent_id}
    try:
        query["_id"] = ObjectId(request_id)
    except Exception:
        query["$or"] = [{"_id": request_id}, {"request_id": request_id}]

    record = await db.playbook_approvals.find_one(query, {"_id": 0})
    if not record:
        record = await db.agent_approval_requests.find_one(
            {"agent_id": agent_id, "request_id": request_id}, {"_id": 0}
        )
    if not record:
        raise HTTPException(status_code=404, detail="Approval request not found")

    return {
        "request_id": request_id, "status": record.get("status", "pending"),
        "approved_by": record.get("approved_by"), "approved_at": record.get("approved_at"),
        "params": record.get("params", {}),
    }
