"""Autonomous Ops tenant routes (Phase 81, plan 81-09): /api/autonomous-ops.

Reads (status, activity) need view:autonomous_ops and are open to API keys. Pressing a stop needs
control:autonomous_ops and is open to API keys too (D-10: a key can brake). Everything that decides,
resumes or changes a setting needs an interactive sign-in (``_require_interactive_session``) plus the
permission named on the route; none of it runs on an API key.

The mount guard (catalogue_mounts_autonomous_ops) checks the catalogue strings on every route; the
dependencies below add the exact permission. The tenant id comes from the token; ``tenantId`` is
honoured only for platform staff (see ``autonomous_ops.views.resolve_tenant``).

Level, maximum level, shadow lift and never-touch editing are API-only in Phase 81 (D-22): they are
documented by the summaries and docstrings of the routes below, served at /docs.
"""
import logging
from typing import Annotated, Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints, field_validator, model_validator

import rbac_defaults
from api_key_auth import get_current_user_or_api_key
from autonomous_ops import (CONTROL_PERMISSION, MANAGE_PERMISSION, PLATFORM_TENANT_ID, approvals, breaker, ledger,
                            messages, protected, settings, stop, views)
from autonomous_ops.rollout import dispatcher as _rollout_dispatcher  # noqa: F401  (registers the patch_rollout approvals dispatcher)
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autonomous-ops", tags=["Autonomous Ops"])

Bucket = Literal["all", "pending", "done", "undone", "failed", "refused", "suggested", "simulation"]


def _unavailable(exc: Exception) -> HTTPException:
    logger.error("autonomous_ops: request could not be served: %s", exc)
    return HTTPException(status_code=503, detail="Autonomous Ops is temporarily unavailable")


async def _tenant_for(db, user, tenant_id: Optional[str], *, write: bool) -> str:
    """The tenant the request means; platform staff naming a tenant must name a real one."""
    tenant = views.resolve_tenant(user, tenant_id, write=write)
    if tenant_id and views.staff_tier(user) is not None and tenant != PLATFORM_TENANT_ID:
        await views.require_tenant(db, tenant)
    return tenant


@router.get("/status", summary="Autonomous Ops status for an organization")
async def get_status(
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(get_current_user_or_api_key),
):
    """Level, maximum level, shadow mode, stop state and what the caller may do, for the caller's
    organization. Platform staff name an organization with tenantId."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=False)
        caller = await views.build_caller(user)
        return await views.status_payload(db, caller, tenant)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.get("/actions", summary="Autonomous Ops activity for an organization")
async def get_actions(
    bucket: Bucket = Query("all"),
    limit: int = Query(25, ge=1, le=100),
    cursor: Optional[str] = Query(None, max_length=512),
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(get_current_user_or_api_key),
):
    """Decisions and stop events, newest first, one page at a time. Counts and the total come with
    the first page. Platform staff name an organization with tenantId."""
    if cursor:
        try:
            ledger._decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="cursor is not valid") from exc
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=False)
        caller = await views.build_caller(user)
        return await views.list_page(db, tenant, bucket=bucket, limit=limit, cursor=cursor,
                                     viewer_is_platform_staff=caller.staff,
                                     can_act=caller.can_control and caller.interactive)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


# ---------------------------------------------------------------- permissions

def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


async def _require_interactive_session(user=Depends(get_current_user_or_api_key)):
    """Refuse an API key (D-10): approving, denying, undoing, resuming and changing a setting are
    decisions a person makes in a signed-in session."""
    if not views.is_interactive(user):
        raise _forbidden(messages.API_DETAIL["interactive"])
    return user


async def _require_stop_permission(user=Depends(get_current_user_or_api_key)):
    """Pressing a stop needs control:autonomous_ops (a key may hold it); Platform Support never does."""
    if rbac_defaults.platform_tier(getattr(user, "role", None)) == "support" \
            or not await views.holds(user, CONTROL_PERMISSION):
        raise _forbidden(f"Missing required permission: {CONTROL_PERMISSION}")
    return user


async def _require_control(user=Depends(get_current_user_or_api_key)):
    """Approve, deny and undo need control:autonomous_ops."""
    return await _require_stop_permission(user)


async def _require_manage(user=Depends(get_current_user_or_api_key)):
    """Resume, level, restore-level and never-touch writes need manage:autonomous_ops."""
    if rbac_defaults.platform_tier(getattr(user, "role", None)) == "support" \
            or not await views.holds(user, MANAGE_PERMISSION):
        raise _forbidden(f"Missing required permission: {MANAGE_PERMISSION}")
    return user


# ---------------------------------------------------------------- request bodies

Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=stop.REASON_MAX)]


class StopBody(BaseModel):
    reason: Optional[Reason] = None

    @field_validator("reason")
    @classmethod
    def _empty_is_none(cls, value):
        return value or None


class ResumeBody(BaseModel):
    reason: Reason

    @field_validator("reason")
    @classmethod
    def _required(cls, value):
        if not value:
            raise ValueError(messages.API_DETAIL["invalid_reason"])
        return value


class LevelBody(BaseModel):
    level: Literal["off", "suggest", "undoable_auto"]


class DecisionBody(BaseModel):
    reason: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=stop.REASON_MAX)]] = None


class NeverTouchBody(BaseModel):
    kind: Literal["ip", "cidr", "host", "agent"]
    value: Annotated[str, StringConstraints(max_length=253)]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""

    @model_validator(mode="after")
    def _parsed(self):
        self.value = protected._normalise(self.kind, self.value)       # ValueError -> 422; ip/cidr via ipaddress
        return self


# ---------------------------------------------------------------- shared route logic (also used by the platform router)

async def press_stop(db, caller: views.Caller, scope: str, tenant_id: Optional[str], reason: Optional[str]):
    """Press a stop and answer the way both routers do: (HTTP status, body) or an HTTPException."""
    out = await stop.press(db, scope=scope, tenant_id=tenant_id, actor=await views.actor_for(db, caller), reason=reason)
    if out["status"] == "invalid_reason":
        raise HTTPException(status_code=422, detail=messages.API_DETAIL["invalid_reason"])
    if out["status"] == "already_stopped":
        who = (out.get("stop") or {}).get("pressedBy")
        by = views.display_actor(who, scope, caller.staff)
        return JSONResponse(status_code=409, content={"detail": messages.API_DETAIL["already_stopped"], "by": by})
    return None


async def clear_stop(db, caller: views.Caller, scope: str, tenant_id: Optional[str], reason: str):
    """Clear a stop; raises the HTTP error for every refusal, returns None on success."""
    out = await stop.clear(db, scope=scope, tenant_id=tenant_id, actor=await views.actor_for(db, caller),
                           reason=reason, actor_is_super_admin=caller.is_super, actor_has_manage=caller.can_manage)
    status = out["status"]
    if status == "cleared":
        return
    if status == "invalid_reason":
        raise HTTPException(status_code=422, detail=messages.API_DETAIL["invalid_reason"])
    if status == "forbidden":
        raise _forbidden(messages.API_DETAIL["cannot_resume"])
    raise HTTPException(status_code=409, detail=messages.API_DETAIL["not_stopped"])


# ---------------------------------------------------------------- stop and resume

@router.post("/stop", summary="Stop automatic actions for an organization")
async def post_stop(
    body: Optional[StopBody] = None,
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_stop_permission),
):
    """Stops automatic actions for the organization at once. The reason is optional (500 characters at
    most). A second press answers 409 with who pressed first. API keys holding control:autonomous_ops
    may press a stop; they can never resume it."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=True)
        if tenant == PLATFORM_TENANT_ID:
            raise HTTPException(status_code=409, detail=messages.API_DETAIL["platform_tenant"])
        caller = await views.build_caller(user)
        refused = await press_stop(db, caller, "tenant", tenant, body.reason if body else None)
        return refused or await views.status_payload(db, caller, tenant)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/resume", summary="Resume automatic actions for an organization")
async def post_resume(
    body: ResumeBody,
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_manage),
    _session=Depends(_require_interactive_session),
):
    """Turns a stop off. Needs a typed reason (500 characters at most) and manage:autonomous_ops in a
    signed-in session. A stop pressed by a platform administrator can only be resumed by one."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=True)
        if tenant == PLATFORM_TENANT_ID:
            raise HTTPException(status_code=409, detail=messages.API_DETAIL["platform_tenant"])
        caller = await views.build_caller(user)
        await clear_stop(db, caller, "tenant", tenant, body.reason)
        return await views.status_payload(db, caller, tenant)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


# ---------------------------------------------------------------- level (API only in Phase 81, D-22)

@router.put("/settings/level", summary="Set the level of an organization")
async def put_level(
    body: LevelBody,
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_manage),
    _session=Depends(_require_interactive_session),
):
    """Sets the level: off, suggest or undoable_auto. A level above the organization's maximum is
    refused with 403; only the platform router changes the maximum. The platform organization stays off
    (409)."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=True)
        caller = await views.build_caller(user)
        out = await settings.set_level(db, tenant, body.level, actor=await views.actor_for(db, caller))
        if out["status"] == "above_max":
            raise _forbidden(messages.API_DETAIL["above_max"])
        if out["status"] == "platform_tenant":
            raise HTTPException(status_code=409, detail=messages.API_DETAIL["platform_tenant"])
        if out["status"] != "ok":
            raise HTTPException(status_code=422, detail="level is not valid")
        return await views.status_payload(db, caller, tenant)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/settings/restore-level", summary="Restore the level after the circuit breaker lowered it")
async def post_restore_level(
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_manage),
    _session=Depends(_require_interactive_session),
):
    """Puts the level back to what it was before the circuit breaker lowered it, capped at the maximum
    level. Answers 409 when the breaker has not lowered the level."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=True)
        caller = await views.build_caller(user)
        out = await breaker.restore(db, tenant, actor=await views.actor_for(db, caller))
        if out["status"] != "restored":
            raise HTTPException(status_code=409, detail=messages.API_DETAIL["not_tripped"])
        return await views.status_payload(db, caller, tenant)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


# ---------------------------------------------------------------- never-touch list (API only in Phase 81, D-22)

@router.get("/never-touch", summary="List the never-touch entries that apply to an organization")
async def get_never_touch(
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(get_current_user_or_api_key),
):
    """Built-in, platform-wide and organization entries. Targets that match one are never changed
    automatically."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=False)
        caller = await views.build_caller(user)
        return {"items": views.visible_entries(await protected.list_entries(db, tenant), caller.staff)}
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/never-touch", status_code=201, summary="Add a never-touch entry for an organization")
async def post_never_touch(
    body: NeverTouchBody,
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_manage),
    _session=Depends(_require_interactive_session),
):
    """Adds an IP address, network (CIDR), host name or agent id that is never changed automatically."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=True)
        if tenant == PLATFORM_TENANT_ID:
            raise HTTPException(status_code=409, detail=messages.API_DETAIL["platform_tenant"])
        caller = await views.build_caller(user)
        try:
            entry = await protected.add_entry(db, scope="tenant", tenant_id=tenant, kind=body.kind, value=body.value,
                                              note=body.note, actor=await views.actor_for(db, caller))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=messages.API_DETAIL["entry_limit"]) from exc
        return views.entry_view(entry)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.delete("/never-touch/{entry_id:path}", summary="Remove a never-touch entry of an organization")
async def delete_never_touch(
    entry_id: str = Path(..., max_length=128),
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_manage),
    _session=Depends(_require_interactive_session),
):
    """Removes one of the organization's own entries. Built-in entries answer 403; an entry that is not
    the organization's own answers 404."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=True)
        if entry_id.startswith("builtin:"):
            raise _forbidden(messages.API_DETAIL["builtin_entry"])
        if not await protected.remove_entry(db, entry_id, scope="tenant", tenant_id=tenant):
            raise HTTPException(status_code=404, detail=messages.API_DETAIL["entry_not_found"])
        return {"deleted": entry_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


# ---------------------------------------------------------------- approve, deny, undo

_CONFLICT = {"already_handled", "stopped", "expired", "no_undo", "not_undoable"}


def _decision_error(out: Dict[str, Any]) -> HTTPException:
    """The HTTP error for a service result that did not carry the decision out."""
    status, reason = out.get("status"), out.get("reason")
    if status == "not_found":
        return HTTPException(status_code=404, detail=messages.API_DETAIL["not_found"])
    if status in _CONFLICT:
        return HTTPException(status_code=409, detail=messages.API_DETAIL[status])
    if status == "refused":
        detail = messages.API_DETAIL.get(reason) or messages.REASON_TEXT.get(reason) or "This action cannot be done now."
        return HTTPException(status_code=409, detail=detail)
    return HTTPException(status_code=409, detail="This action cannot be done now.")


async def _decide(action_id: str, tenant_id: Optional[str], user, what: str, reason: Optional[str] = None):
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenant_id, write=True)
        caller = await views.build_caller(user)
        actor = await views.actor_for(db, caller)
        if what == "approve":
            out = await approvals.approve(db, tenant, action_id, approver=actor)
            ok = "dispatched"
        elif what == "deny":
            out = await approvals.deny(db, tenant, action_id, approver=actor, reason=reason or "")
            ok = "denied"
        else:
            out = await approvals.undo(db, tenant, action_id, actor=actor)
            ok = "undone"
        if out.get("status") != ok:
            raise _decision_error(out)
        body = {"status": ok, "action": await views.present_one(
            db, tenant, action_id, caller, can_act=caller.can_control and caller.interactive)}
        if what == "undo":
            body["breakerTripped"] = bool(out.get("breaker_tripped"))
        return body
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/actions/{action_id}/approve", summary="Approve an action waiting for a person")
async def post_approve(
    action_id: str = Path(..., max_length=128),
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_control),
    _session=Depends(_require_interactive_session),
):
    """Approves the action and sends it to the host once. Needs control:autonomous_ops in a signed-in
    session. Answers 409 when it was already decided, expired, or automatic actions are stopped."""
    return await _decide(action_id, tenantId, user, "approve")


@router.post("/actions/{action_id}/deny", summary="Deny an action waiting for a person")
async def post_deny(
    action_id: str = Path(..., max_length=128),
    body: Optional[DecisionBody] = None,
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_control),
    _session=Depends(_require_interactive_session),
):
    """Denies the action; nothing is sent to the host. The reason is optional (500 characters at most).
    Still allowed while automatic actions are stopped."""
    return await _decide(action_id, tenantId, user, "deny", body.reason if body else None)


@router.post("/actions/{action_id}/undo", summary="Undo an action that was carried out")
async def post_undo(
    action_id: str = Path(..., max_length=128),
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_control),
    _session=Depends(_require_interactive_session),
):
    """Sends the action's undo to the host. Still allowed while automatic actions are stopped."""
    return await _decide(action_id, tenantId, user, "undo")
