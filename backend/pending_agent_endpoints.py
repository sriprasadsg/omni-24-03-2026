"""Pending agents screen API (spec C3).

Platform staff see every tenant's Pending and Rejected agents; the Platform Owner and
Platform Billing (manage:pending_agents, spec C1) decide on them. Tenant users with
view:agents see their own tenant's list read-only.
"""
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import licensing
import pending_agents
from authentication_service import get_current_user
from cache_service import invalidate_cache
from catalogue_guards import catalogue_exempt, check_catalogue_access
from catalogue_mounts_agents import AGENTS_READ, AGENTS_WRITE
from database import get_database
from rbac_utils import can_read_all_tenants, has_platform_permission

router = APIRouter(prefix="/api/agents/pending", tags=["Agents"])

MAX_RAISE = 10_000
MAX_BULK = 100


def _actor(user) -> str:
    return getattr(user, "username", None) or getattr(user, "email", None) or "unknown"


# Platform Billing holds manage:pending_agents but not view:agents, so these routes cannot
# sit behind the agents catalogue guard: tenant users get exactly that guard's check here,
# platform staff go on to the route's own platform-permission check.
_PLATFORM_DECISIONS = catalogue_exempt(
    "platform staff decide Pending agents across tenants (manage:pending_agents); "
    "tenant users get the agents catalogue check in pending_agent_endpoints._require_pending_access")


async def _require_pending_access(request: Request, user=Depends(get_current_user), _exempt=Depends(_PLATFORM_DECISIONS)):
    if not can_read_all_tenants(user):
        await check_catalogue_access(user, request.method, AGENTS_READ, AGENTS_WRITE)
    return user


async def _require_decider(user, raise_limit: bool = False) -> None:
    if not await has_platform_permission(user, "manage:pending_agents"):
        raise HTTPException(status_code=403, detail="Only Platform Owner or Billing can approve or reject agents")
    if raise_limit and not await has_platform_permission(user, "manage:tenant_license"):
        raise HTTPException(status_code=403, detail="Raising the seat limit needs manage:tenant_license")


def _decision_response(err: pending_agents.DecisionError) -> JSONResponse:
    body: Dict[str, Any] = {"error": err.detail, "status_code": err.status_code}
    if err.extra:
        body["license"] = err.extra
    return JSONResponse(status_code=err.status_code, content=body)


@router.get("", dependencies=[Depends(_require_pending_access)])
async def list_pending_agents(
    tenant_id: Optional[str] = Query(None, alias="tenantId"),
    status: Optional[Literal["Pending", "Rejected"]] = None,
    reason: Optional[str] = Query(None, max_length=64),
    current_user=Depends(get_current_user),
):
    """Agents waiting for approval (and rejected ones), with each tenant's seat usage."""
    db = get_database()
    platform = can_read_all_tenants(current_user)
    decider = await has_platform_permission(current_user, "manage:pending_agents")
    scope = tenant_id if platform else getattr(current_user, "tenant_id", None)
    if not platform and not scope:
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


@router.post("/{agent_id}/approve", dependencies=[Depends(_require_pending_access)])
async def approve_pending_agent(agent_id: str, body: Optional[ApproveBody] = None,
                                current_user=Depends(get_current_user)):
    """Admit the agent (it claims a seat). 409 ``no_free_seat`` carries the tenant's license
    so the UI can offer "approve and raise the limit"."""
    await _require_decider(current_user, raise_limit=bool(body and body.raiseLimitBy))
    try:
        result = await pending_agents.approve(get_database(), agent_id, _actor(current_user),
                                              (body or ApproveBody()).raiseLimitBy)
    except pending_agents.DecisionError as err:
        return _decision_response(err)
    invalidate_cache("agents:*")
    return result


@router.post("/{agent_id}/reject", dependencies=[Depends(_require_pending_access)])
async def reject_pending_agent(agent_id: str, current_user=Depends(get_current_user)):
    """Refuse the agent; its machine cannot enroll in this tenant again until approved."""
    await _require_decider(current_user)
    try:
        return await pending_agents.reject(get_database(), agent_id, _actor(current_user))
    except pending_agents.DecisionError as err:
        return _decision_response(err)


class BulkBody(BaseModel):
    action: Literal["approve", "reject"]
    agentIds: List[str] = Field(..., min_length=1, max_length=MAX_BULK)
    raiseLimit: bool = False  # approve: add one seat for each agent that finds none free


@router.post("/bulk", dependencies=[Depends(_require_pending_access)])
async def bulk_decide(body: BulkBody, current_user=Depends(get_current_user)):
    """Approve or reject several agents; each result is reported on its own."""
    await _require_decider(current_user, raise_limit=body.action == "approve" and body.raiseLimit)
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
