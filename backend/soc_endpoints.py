"""SOC console routes (Security Overview) and the shared alert queue Alert Management reads.

``/api/security/soc/*`` belongs to the Security Overview catalogue (view:security; changes need
manage:security_cases), ``/api/alerts/queue*`` to Alert Management, so each screen keeps working
when only that screen is switched on. A tenant user only ever sees their tenant; a Super Admin sees
the tenant they are viewing (X-Tenant-ID), or every tenant, or the one named in ``tenantId``.
"""
import logging
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_types import TokenData
from authentication_service import get_current_user
from catalogue_mounts_secops import ALERT_MANAGEMENT_GUARD, SECURITY_GUARD
from database import get_database
from rbac_utils import is_super_admin, require_permission, verify_permission
from tenant_context import get_tenant_id
import soc_actions
import soc_response
import soc_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/security/soc", tags=["SOC"])
queue_router = APIRouter(prefix="/api/alerts/queue", tags=["Alerts"])

StatusKey = Literal["active", "open", "acknowledged", "closed", "all"]
SeverityKey = Literal["critical", "high", "medium", "low", "info"]


class ActionIn(BaseModel):
    action: Literal["acknowledge", "assign", "unassign", "close", "reopen", "archive"]
    resolution: Optional[Literal["resolved", "false_positive", "benign"]] = None
    note: Optional[str] = Field(None, max_length=2000)
    assignee: Optional[str] = Field(None, max_length=120)

    model_config = {"extra": "forbid"}


class BulkIn(BaseModel):
    ids: List[str] = Field(..., min_length=1, max_length=soc_actions.MAX_BULK)
    action: Literal["acknowledge", "close", "archive"]
    resolution: Optional[Literal["resolved", "false_positive", "benign"]] = None
    note: Optional[str] = Field(None, max_length=2000)

    model_config = {"extra": "forbid"}


class ApproveIn(BaseModel):
    allEndpoints: bool = False
    reason: Optional[str] = Field(None, max_length=500)

    model_config = {"extra": "forbid"}


class RespondIn(BaseModel):
    action: Literal["isolate_host", "quarantine_file", "block_ip", "kill_process"]
    ttl: Optional[Literal["1h", "24h", "7d"]] = None

    model_config = {"extra": "forbid"}


# Response actions change endpoints: they also need the Active Response permission (tenant_admin holds it).
RESPOND = [Depends(SECURITY_GUARD), Depends(require_permission("manage:active_response"))]


def soc_scope(current_user: Any, tenant_param: Optional[str] = None) -> Optional[str]:
    """Tenant the caller acts on; None is a Super Admin's all-tenant view."""
    if is_super_admin(getattr(current_user, "role", "") or ""):
        viewing = get_tenant_id()
        if viewing and viewing != "platform-admin":
            return viewing
        return tenant_param or None
    tenant = getattr(current_user, "tenant_id", None)
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant


async def _run(coro):
    try:
        return await coro
    except (soc_actions.ActionError, soc_response.ResponseError) as e:
        raise HTTPException(status_code=e.status, detail=str(e))


async def _actor(user: Any):
    from autonomous_ops import views
    return await views.actor_for(get_database(), await views.build_caller(user))


@router.get("/summary", dependencies=[Depends(SECURITY_GUARD)])
async def get_soc_summary(
    range_key: str = Query("24h", alias="range", pattern="^(1h|24h|7d|30d)$"),
    tenant: Optional[str] = Query(None, alias="tenantId", max_length=128),
    current_user: TokenData = Depends(get_current_user),
):
    """Security Overview: open alerts, trend, top detections, endpoints at risk, MITRE techniques, source health."""
    return await soc_service.soc_summary(soc_scope(current_user, tenant), range_key)


async def _queue(current_user, tenant, status, severity, alert_type, agent_id, q, limit, offset):
    return await soc_service.alert_queue(soc_scope(current_user, tenant), status, severity, alert_type, agent_id, q,
                                         limit, offset)


@router.get("/alerts", dependencies=[Depends(SECURITY_GUARD)])
async def get_soc_alerts(
    status: StatusKey = "active",
    severity: Optional[SeverityKey] = None,
    alert_type: Optional[str] = Query(None, alias="type", max_length=100),
    agent_id: Optional[str] = Query(None, alias="agentId", max_length=128),
    q: Optional[str] = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100000),
    tenant: Optional[str] = Query(None, alias="tenantId", max_length=128),
    current_user: TokenData = Depends(get_current_user),
):
    """The alert queue: active first, then by severity, newest activity first."""
    return await _queue(current_user, tenant, status, severity, alert_type, agent_id, q, limit, offset)


@router.patch("/alerts/{alert_id}", dependencies=[Depends(SECURITY_GUARD)])
async def patch_soc_alert(alert_id: str, body: ActionIn, current_user: TokenData = Depends(get_current_user)):
    """Acknowledge, assign, close (with a resolution), reopen or archive one alert."""
    return await _run(soc_actions.apply_action(soc_scope(current_user), alert_id[:128], body.action, current_user,
                                               body.resolution, body.note, body.assignee))


@router.post("/alerts/bulk", dependencies=[Depends(SECURITY_GUARD)])
async def bulk_soc_alerts(body: BulkIn, current_user: TokenData = Depends(get_current_user)):
    return await _run(soc_actions.bulk_action(soc_scope(current_user), body.ids, body.action, current_user,
                                              body.resolution, body.note))


@router.post("/alerts/{alert_id}/case", dependencies=[Depends(SECURITY_GUARD)])
async def case_from_alert(alert_id: str, current_user: TokenData = Depends(get_current_user)):
    """Open a security case for the alert (or return the case it already has)."""
    return await _run(soc_actions.open_case(soc_scope(current_user), alert_id[:128], current_user))


@router.post("/alerts/{alert_id}/approve", dependencies=[Depends(SECURITY_GUARD)])
async def approve_ai_process(alert_id: str, body: ApproveIn, current_user: TokenData = Depends(get_current_user)):
    """Approve the AI process an alert names, on its endpoint or all endpoints; its alerts close as approved."""
    return await _run(soc_actions.approve_ai(soc_scope(current_user), alert_id[:128], current_user,
                                             body.allEndpoints, body.reason))


@router.get("/alerts/{alert_id}/response", dependencies=[Depends(SECURITY_GUARD)])
async def get_response_options(alert_id: str, current_user: TokenData = Depends(get_current_user)):
    """Response actions this alert supports, whether its endpoint can carry each out, and what was done."""
    out = await _run(soc_response.options(soc_scope(current_user), alert_id[:128]))
    out["canRespond"] = await verify_permission(current_user, "manage:active_response")
    return out


@router.post("/alerts/{alert_id}/respond", dependencies=RESPOND)
async def respond_to_alert(alert_id: str, body: RespondIn, current_user: TokenData = Depends(get_current_user)):
    """Isolate the host, quarantine the file, block the IP or end the process the alert names; the click is the approval."""
    return await _run(soc_response.respond(soc_scope(current_user), alert_id[:128], body.action,
                                           await _actor(current_user), current_user, body.ttl))


@router.post("/alerts/{alert_id}/response/{action_id}/undo", dependencies=RESPOND)
async def undo_alert_response(alert_id: str, action_id: str, current_user: TokenData = Depends(get_current_user)):
    return await _run(soc_response.undo(soc_scope(current_user), alert_id[:128], action_id[:128],
                                        await _actor(current_user), current_user))


@router.post("/alerts/{alert_id}/response/{action_id}/keep-isolated", dependencies=RESPOND)
async def keep_alert_host_isolated(alert_id: str, action_id: str, current_user: TokenData = Depends(get_current_user)):
    """Keep the host isolated past the 4-hour automatic reconnect."""
    return await _run(soc_response.keep_isolated(soc_scope(current_user), alert_id[:128], action_id[:128],
                                                 await _actor(current_user), current_user))


@router.get("/approved-ai", dependencies=[Depends(SECURITY_GUARD)])
async def get_approved_ai(current_user: TokenData = Depends(get_current_user)):
    return {"items": await soc_actions.list_approvals(soc_scope(current_user))}


@router.delete("/approved-ai/{approval_id}", dependencies=[Depends(SECURITY_GUARD)])
async def delete_approved_ai(approval_id: str, current_user: TokenData = Depends(get_current_user)):
    """Stop approving an AI process; its next detection raises an alert again."""
    await _run(soc_actions.revoke_approval(soc_scope(current_user), approval_id[:128], current_user))
    return {"success": True}


@queue_router.get("", dependencies=[Depends(ALERT_MANAGEMENT_GUARD)])
async def get_alert_queue(
    status: StatusKey = "all",
    severity: Optional[SeverityKey] = None,
    q: Optional[str] = Query(None, max_length=100),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100000),
    current_user: TokenData = Depends(get_current_user),
):
    """Alert Management's list: the same alerts the SOC console shows."""
    return await _queue(current_user, None, status, severity, None, None, q, limit, offset)


@queue_router.post("/bulk", dependencies=[Depends(ALERT_MANAGEMENT_GUARD)])
async def bulk_alert_queue(body: BulkIn, current_user: TokenData = Depends(get_current_user)):
    return await _run(soc_actions.bulk_action(soc_scope(current_user), body.ids, body.action, current_user,
                                              body.resolution, body.note))
