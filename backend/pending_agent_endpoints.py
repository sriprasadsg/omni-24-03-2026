"""Pending agents screen API (spec C3).

Super admins see every tenant's Pending and Rejected agents and decide on them;
tenant users with view:agents see their own tenant's list read-only. Until platform
roles exist (spec C1) deciding is Super Admin only, like the license PATCH (C2).
"""
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import licensing
import pending_agents
from authentication_service import get_current_user
from cache_service import invalidate_cache
from catalogue_mounts_agents import AGENTS_GUARD
from database import get_database
from rbac_utils import is_super_admin

router = APIRouter(prefix="/api/agents/pending", tags=["Agents"])

MAX_RAISE = 10_000
MAX_BULK = 100


def _actor(user) -> str:
    return getattr(user, "username", None) or getattr(user, "email", None) or "unknown"


def _require_decider(user) -> None:
    if not is_super_admin(getattr(user, "role", "")):
        raise HTTPException(status_code=403, detail="Only Super Admin can approve or reject agents")


def _decision_response(err: pending_agents.DecisionError) -> JSONResponse:
    body: Dict[str, Any] = {"error": err.detail, "status_code": err.status_code}
    if err.extra:
        body["license"] = err.extra
    return JSONResponse(status_code=err.status_code, content=body)


@router.get("", dependencies=[Depends(AGENTS_GUARD)])
async def list_pending_agents(
    tenant_id: Optional[str] = Query(None, alias="tenantId"),
    status: Optional[Literal["Pending", "Rejected"]] = None,
    reason: Optional[str] = Query(None, max_length=64),
    current_user=Depends(get_current_user),
):
    """Agents waiting for approval (and rejected ones), with each tenant's seat usage."""
    db = get_database()
    decider = is_super_admin(getattr(current_user, "role", ""))
    scope = tenant_id if decider else getattr(current_user, "tenant_id", None)
    if not decider and not scope:
        raise HTTPException(status_code=403, detail="Tenant context required")
    agents = await pending_agents.list_not_admitted(db, scope, status, reason)
    tenants: Dict[str, Any] = {}
    for tid in sorted({a.get("tenantId") for a in agents if a.get("tenantId")} | ({scope} if scope else set())):
        tenant = await getattr(db, "_db", db).tenants.find_one({"id": tid}, {"_id": 0, "id": 1, "name": 1})
        if tenant:
            tenants[tid] = {"name": tenant.get("name"), "license": await licensing.license_summary(db, tid)}
    return {"agents": agents, "tenants": tenants, "canDecide": decider}


class ApproveBody(BaseModel):
    raiseLimitBy: int = Field(0, ge=0, le=MAX_RAISE)


@router.post("/{agent_id}/approve", dependencies=[Depends(AGENTS_GUARD)])
async def approve_pending_agent(agent_id: str, body: Optional[ApproveBody] = None,
                                current_user=Depends(get_current_user)):
    """Admit the agent (it claims a seat). 409 ``no_free_seat`` carries the tenant's license
    so the UI can offer "approve and raise the limit"."""
    _require_decider(current_user)
    try:
        result = await pending_agents.approve(get_database(), agent_id, _actor(current_user),
                                              (body or ApproveBody()).raiseLimitBy)
    except pending_agents.DecisionError as err:
        return _decision_response(err)
    invalidate_cache("agents:*")
    return result


@router.post("/{agent_id}/reject", dependencies=[Depends(AGENTS_GUARD)])
async def reject_pending_agent(agent_id: str, current_user=Depends(get_current_user)):
    """Refuse the agent; its machine cannot enroll in this tenant again until approved."""
    _require_decider(current_user)
    try:
        return await pending_agents.reject(get_database(), agent_id, _actor(current_user))
    except pending_agents.DecisionError as err:
        return _decision_response(err)


class BulkBody(BaseModel):
    action: Literal["approve", "reject"]
    agentIds: List[str] = Field(..., min_length=1, max_length=MAX_BULK)
    raiseLimit: bool = False  # approve: add one seat for each agent that finds none free


@router.post("/bulk", dependencies=[Depends(AGENTS_GUARD)])
async def bulk_decide(body: BulkBody, current_user=Depends(get_current_user)):
    """Approve or reject several agents; each result is reported on its own."""
    _require_decider(current_user)
    db = get_database()
    actor = _actor(current_user)
    results = []
    for agent_id in dict.fromkeys(body.agentIds):
        try:
            if body.action == "reject":
                await pending_agents.reject(db, agent_id, actor)
            else:
                try:
                    await pending_agents.approve(db, agent_id, actor)
                except pending_agents.DecisionError as err:
                    if not (body.raiseLimit and err.detail.startswith("no_free_seat")):
                        raise
                    await pending_agents.approve(db, agent_id, actor, raise_limit_by=1)
            results.append({"agentId": agent_id, "ok": True})
        except pending_agents.DecisionError as err:
            results.append({"agentId": agent_id, "ok": False, "error": err.detail})
    if body.action == "approve":
        invalidate_cache("agents:*")
    return {"results": results, "succeeded": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results)}
