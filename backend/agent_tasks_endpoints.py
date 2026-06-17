from fastapi import APIRouter, Depends, HTTPException, Body, Request, Response
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from database import get_database, mongodb
from authentication_service import get_current_user
from datetime import datetime, timezone
import uuid
from agent_auth import verify_agent_key
from rate_limiter import limiter
from tickets_service import tickets_service
import logging

router = APIRouter(prefix="/api/agents", tags=["Agents"])
logger = logging.getLogger("agent_tasks_endpoints")

_TASK_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}




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

        # REM-04: broadcast remediation_update for any open tasks matching these controls
        try:
            from websocket_manager import broadcast_remediation_update
            tenant_id = _tenant.get("tenant_id") or _tenant.get("tenantId") or _tenant.get("id", "")
            control_ids = [
                c.get("control_id") or c.get("check") or c.get("name", "")
                for c in result.get("compliance_checks", [])
                if isinstance(c, dict)
            ]
            for ctrl_id in set(filter(None, control_ids)):
                open_tasks = await db.compliance_remediation_tasks.find(
                    {"control_id": ctrl_id, "tenantId": tenant_id, "status": {"$in": ["open", "in_progress"]}}
                ).to_list(length=50)
                for t in open_tasks:
                    await broadcast_remediation_update(
                        tenant_id,
                        {"task_id": t.get("id", ""), "control_id": ctrl_id, "status": "evidence_updated"},
                    )
        except Exception as exc:
            logger.warning("REM-04 broadcast failed (non-fatal): %s", exc)

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


class RaiseTicketRequest(BaseModel):
    title: str = Field(..., max_length=500)
    description: Optional[str] = Field("", max_length=5000)
    type: Optional[str] = Field("task", max_length=50)       # bug|feature|task|incident|security
    priority: Optional[str] = Field("medium", max_length=20) # critical|high|medium|low
    assignee: Optional[str] = Field("", max_length=200)
    tags: Optional[List[str]] = []
    endpoint_info: Optional[Dict[str, Any]] = None           # hostname, IP, OS, username from endpoint


@router.post("/{agent_id}/raise-ticket")
async def raise_ticket_via_agent(
    agent_id: str,
    body: RaiseTicketRequest,
    current_user: Any = Depends(get_current_user),
):
    """
    Create a ticket immediately in the tickets collection, then optionally
    queue a follow-up instruction for the agent (notifications, asset linkage).
    Ticket visibility does not depend on the agent being online.
    """
    db = get_database()
    caller_role = getattr(current_user, "role", None)
    agent_query: dict = {"$or": [{"id": agent_id}, {"hostname": agent_id}]}
    if caller_role not in _TASK_SUPER_ROLES:
        caller_tenant = getattr(current_user, "tenant_id", None)
        if not caller_tenant:
            raise HTTPException(status_code=403, detail="Tenant context required")
        agent_query["tenantId"] = caller_tenant

    agent = await db.agents.find_one(agent_query)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    tenant_id      = agent.get("tenantId") or getattr(current_user, "tenant_id", "") or ""
    agent_hostname = agent.get("hostname") or agent.get("id", agent_id)
    agent_real_id  = agent.get("id", agent_id)
    reporter       = getattr(current_user, "email", None) or getattr(current_user, "username", "unknown")

    # Resolve tenant display name for the ticket (best-effort; non-fatal if not found)
    tenant_name = tenant_id
    try:
        tenant_doc = await mongodb.db.tenants.find_one({"id": tenant_id}, {"name": 1})
        if tenant_doc:
            tenant_name = tenant_doc.get("name", tenant_id)
    except Exception:
        pass

    # ── 1. Create ticket immediately so it appears in the dashboard now ───────
    ticket_data = {
        "title":          body.title,
        "description":    body.description or "",
        "type":           body.type or "task",
        "priority":       body.priority or "medium",
        "assignee":       body.assignee or "",
        "tags":           body.tags or ["agent-raised"],
        "endpoint_info":  body.endpoint_info or {},
        "agent_id":       agent_real_id,
        "agent_hostname": agent_hostname,
        "tenant_name":    tenant_name,
    }
    ticket = await tickets_service.create_ticket(
        data=ticket_data,
        reporter=reporter,
        tenant_id=tenant_id,
    )

    # ── 2. Also queue an instruction so the agent can do follow-up work ───────
    instr_id = str(uuid.uuid4())
    await db.agent_instructions.insert_one({
        "id":          instr_id,
        "agent_id":    agent.get("id", agent_id),
        "tenantId":    tenant_id,
        "instruction": "ticket_created",      # notification-only; ticket already exists
        "payload":     {"ticket_id": ticket["id"], "ticket_number": ticket["ticket_number"]},
        "status":      "pending",
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "created_by":  reporter,
    })

    logger.info(
        "Ticket %s created for agent %s by %s: %s",
        ticket["ticket_number"], agent_id, reporter, body.title,
    )
    return {
        "success":        True,
        "ticket":         ticket,
        "instruction_id": instr_id,
        "message":        f"Ticket {ticket['ticket_number']} created successfully",
    }


@router.post("/{agent_id}/discovery/results")
@limiter.limit("30/minute")
async def report_network_scan_results(
    request: Request,
    response: Response,
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

