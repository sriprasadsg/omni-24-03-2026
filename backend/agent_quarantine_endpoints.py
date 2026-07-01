"""
Agent Quarantine Endpoints — /api/agents/{agent_id}/quarantine
Allows admins to isolate a compromised agent so its heartbeats are rejected
and commands are not dispatched to it until it is explicitly released.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from rbac_service import rbac_service
from tenant_context import get_tenant_id
import logging

router = APIRouter(prefix="/api/agents", tags=["Agent Quarantine"])
logger = logging.getLogger(__name__)


class QuarantineRequest(BaseModel):
    reason: str
    notify: bool = True


@router.post("/{agent_id}/quarantine")
async def quarantine_agent(
    agent_id: str,
    req: QuarantineRequest,
    current_user=Depends(rbac_service.has_permission("remediate:agents")),
):
    """Quarantine an agent — rejects subsequent heartbeats with 403."""
    db = get_database()
    tenant_id = get_tenant_id()

    query: dict = {"id": agent_id}
    if tenant_id:
        query["tenantId"] = tenant_id

    agent = await db.agents.find_one(query, {"_id": 0, "id": 1, "hostname": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    now = datetime.now(timezone.utc).isoformat()
    caller = getattr(current_user, "username", "admin")

    await db.agents.update_one(query, {"$set": {
        "quarantined": True,
        "quarantine_reason": req.reason,
        "quarantined_by": caller,
        "quarantined_at": now,
        "status": "Quarantined",
    }})

    await db.audit_logs.insert_one({
        "action": "agent_quarantined",
        "agent_id": agent_id,
        "hostname": agent.get("hostname"),
        "reason": req.reason,
        "performed_by": caller,
        "tenantId": tenant_id,
        "timestamp": now,
    })

    if req.notify:
        try:
            from notification_manager import notification_manager
            import asyncio
            asyncio.create_task(notification_manager.send_notification(
                "security.alert",
                {
                    "title": f"Agent Quarantined: {agent.get('hostname', agent_id)}",
                    "severity": "high",
                    "description": f"Agent {agent_id} quarantined by {caller}. Reason: {req.reason}",
                },
                tenant_id or "platform-admin",
            ))
        except Exception as e:
            logger.debug("Quarantine notification failed (non-fatal): %s", e)

    logger.warning("AGENT QUARANTINED: %s by %s — %s", agent_id, caller, req.reason)
    return {"success": True, "agent_id": agent_id, "status": "Quarantined"}


@router.post("/{agent_id}/release")
async def release_agent(
    agent_id: str,
    current_user=Depends(rbac_service.has_permission("remediate:agents")),
):
    """Release an agent from quarantine."""
    db = get_database()
    tenant_id = get_tenant_id()

    query: dict = {"id": agent_id}
    if tenant_id:
        query["tenantId"] = tenant_id

    agent = await db.agents.find_one(query, {"_id": 0, "quarantined": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent.get("quarantined"):
        raise HTTPException(status_code=400, detail="Agent is not quarantined")

    caller = getattr(current_user, "username", "admin")
    now = datetime.now(timezone.utc).isoformat()

    await db.agents.update_one(query, {"$set": {
        "quarantined": False,
        "quarantine_reason": None,
        "released_by": caller,
        "released_at": now,
        "status": "Offline",
    }})

    await db.audit_logs.insert_one({
        "action": "agent_released",
        "agent_id": agent_id,
        "performed_by": caller,
        "tenantId": tenant_id,
        "timestamp": now,
    })

    logger.info("AGENT RELEASED from quarantine: %s by %s", agent_id, caller)
    return {"success": True, "agent_id": agent_id, "status": "Offline"}


@router.get("/{agent_id}/quarantine-status")
async def get_quarantine_status(
    agent_id: str,
    current_user=Depends(rbac_service.has_permission("view:agents")),
):
    db = get_database()
    tenant_id = get_tenant_id()

    query: dict = {"id": agent_id}
    if tenant_id:
        query["tenantId"] = tenant_id

    agent = await db.agents.find_one(
        query,
        {"_id": 0, "quarantined": 1, "quarantine_reason": 1, "quarantined_by": 1, "quarantined_at": 1},
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {
        "agent_id": agent_id,
        "quarantined": agent.get("quarantined", False),
        "reason": agent.get("quarantine_reason"),
        "quarantined_by": agent.get("quarantined_by"),
        "quarantined_at": agent.get("quarantined_at"),
    }
