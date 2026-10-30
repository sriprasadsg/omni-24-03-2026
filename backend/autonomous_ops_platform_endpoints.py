"""Autonomous Ops platform routes (Phase 81, plan 81-09): /api/platform/autonomous-ops.

Super Admin only (control:platform_autonomous_ops, held by the platform owner): stop and resume for
every organization, a tenant's maximum level and shadow flag, and the platform-wide never-touch
entries. Every route needs that permission (``_require_platform_autonomy_control``); every route
except POST /stop also needs an interactive sign-in. An API key holding the platform scope may press
the stop; it can never resume it, lift a shadow flag or change a maximum level (D-10).

This router sits outside every catalogue prefix; it has no mount guard of its own.
Level, maximum level, shadow lift and never-touch editing are API-only in Phase 81 (D-22): the route
summaries and docstrings below are the documentation, served at /docs.
"""
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, StrictBool

from api_key_auth import get_current_user_or_api_key
from autonomous_ops import (PLATFORM_CONTROL_PERMISSION, PLATFORM_TENANT_ID, health_messages, ledger, messages, oncall,
                            protected, selfheal, settings, views)
from autonomous_ops_endpoints import (
    NeverTouchBody, ResumeBody, StopBody, _forbidden, _require_interactive_session, _unavailable,
    clear_stop, press_stop,
)
from database import get_database
from rbac_service import rbac_service as _rbac_service
from rbac_utils import has_platform_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platform/autonomous-ops", tags=["Autonomous Ops (platform)"])

# The platform list also filters on the watchdog's platform-health rows; the tenant router's Bucket never does.
PlatformBucket = Literal["all", "pending", "done", "undone", "failed", "refused", "suggested", "simulation",
                         "platform_health"]


async def _require_platform_autonomy_control(user=Depends(get_current_user_or_api_key)):
    """control:platform_autonomous_ops: platform staff only, and for an API key its scope must name it."""
    if not (await has_platform_permission(user, PLATFORM_CONTROL_PERMISSION)
            and _rbac_service._scopes_allow(user, PLATFORM_CONTROL_PERMISSION)):
        raise _forbidden(f"Missing required permission: {PLATFORM_CONTROL_PERMISSION}")
    return user


class MaxLevelBody(BaseModel):
    maxLevel: Literal["off", "suggest", "undoable_auto"]


class ShadowBody(BaseModel):
    shadow: StrictBool


async def _real_tenant(db, tenant_id: str) -> str:
    """The tenant a platform write names: the platform organization is refused (409), an unknown one is 404."""
    if tenant_id == PLATFORM_TENANT_ID:
        raise HTTPException(status_code=409, detail=messages.API_DETAIL["platform_tenant"])
    await views.require_tenant(db, tenant_id)
    return tenant_id


# ---------------------------------------------------------------- status and activity

@router.get("/status", summary="Platform-wide Autonomous Ops status")
async def get_platform_status(
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """The platform-wide stop, how many organizations have their own stop on, and what the caller may do."""
    try:
        db = get_database()
        return await views.platform_status_payload(db, await views.build_caller(user))
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.get("/actions", summary="Platform-wide Autonomous Ops activity")
async def get_platform_actions(
    bucket: PlatformBucket = Query("all"),
    limit: int = Query(25, ge=1, le=100),
    cursor: Optional[str] = Query(None, max_length=512),
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Platform-wide stop and resume events and the watchdog's platform-health events, newest first, one
    page at a time."""
    if cursor:
        try:
            ledger._decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="cursor is not valid") from exc
    try:
        return await views.list_page(get_database(), PLATFORM_TENANT_ID, bucket=bucket, limit=limit, cursor=cursor,
                                     viewer_is_platform_staff=True, include_platform_health=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


# ---------------------------------------------------------------- stop and resume for every organization

@router.post("/stop", summary="Stop automatic actions for every organization")
async def post_platform_stop(
    body: Optional[StopBody] = None,
    user=Depends(_require_platform_autonomy_control),
):
    """Stops automatic actions for every organization at once. The reason is optional (500 characters at
    most). A second press answers 409 with who pressed first. An API key holding
    control:platform_autonomous_ops may press this stop; it can never resume it."""
    try:
        db = get_database()
        caller = await views.build_caller(user)
        refused = await press_stop(db, caller, "platform", None, body.reason if body else None)
        return refused or await views.platform_status_payload(db, caller)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.get("/health", summary="Platform self-healing health")
async def get_platform_health(
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """What the watchdog last reported: the four services, certificate expiry, disk use and its forecast, the
    on-call channel (type and state only, never a key or URL) and the latest test alert. Values are the
    watchdog's own; each entry has ``stale`` true while the watchdog is silent or has never reported. Super
    Admin only, interactive session."""
    try:
        return await selfheal.health_document(get_database(), datetime.now(timezone.utc))
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/health/test-alert", summary="Ask the watchdog to send a test alert")
async def post_health_test_alert(
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Asks the watchdog to send one test message on the on-call channel. Answers
    ``{testAlert: {id, requestedAt, requestedBy, state, sentAt, error}}``; while a request is pending a second
    call returns the same one. The watchdog picks it up with its next sync and reports the result, which
    appears in the platform Activity list. 409 when no watchdog has ever reported ("Install the watchdog
    first.") or it has gone quiet. Super Admin only, interactive session."""
    try:
        db = get_database()
        now = datetime.now(timezone.utc)
        state = selfheal.watchdog_state(await selfheal.get_heartbeat(db), now, selfheal.PROCESS_STARTED_AT)
        if state == "not_installed":
            raise HTTPException(status_code=409, detail=health_messages.API_DETAIL["watchdog_not_installed"])
        if state == "silent":
            raise HTTPException(status_code=409, detail=health_messages.API_DETAIL["watchdog_silent"])
        caller = await views.build_caller(user)
        actor = await views.actor_for(db, caller)
        request = await oncall.request_test(db, actor, now)
        return {"testAlert": oncall.view(request)}
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/resume", summary="Resume automatic actions for every organization")
async def post_platform_resume(
    body: ResumeBody,
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Turns the platform-wide stop off. Needs a typed reason (500 characters at most). Organization
    stops stay as they are."""
    try:
        db = get_database()
        caller = await views.build_caller(user)
        await clear_stop(db, caller, "platform", None, body.reason)
        return await views.platform_status_payload(db, caller)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


# ---------------------------------------------------------------- maximum level and shadow flag (API only, D-22)

@router.put("/tenants/{tenant_id}/max-level", summary="Set the highest level an organization may use")
async def put_max_level(
    body: MaxLevelBody,
    tenant_id: str = Path(..., max_length=views.TENANT_ID_MAX),
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Sets the highest level (off, suggest or undoable_auto) the organization may choose; its level is
    lowered when it is above the new maximum. Only this route changes a maximum level. The platform
    organization stays off (409)."""
    try:
        db = get_database()
        tenant = await _real_tenant(db, tenant_id)
        caller = await views.build_caller(user)
        out = await settings.set_max_level(db, tenant, body.maxLevel, actor=await views.actor_for(db, caller))
        if out["status"] != "ok":
            raise HTTPException(status_code=422, detail="maxLevel is not valid")
        return await views.status_payload(db, caller, tenant)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.put("/tenants/{tenant_id}/shadow", summary="Turn an organization's own shadow mode on or off")
async def put_shadow(
    body: ShadowBody,
    tenant_id: str = Path(..., max_length=views.TENANT_ID_MAX),
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Lifts (false) or restores (true) the organization's own shadow flag. The deployment-wide switch
    still forces shadow mode on while it is set. No organization route changes this flag."""
    try:
        db = get_database()
        tenant = await _real_tenant(db, tenant_id)
        caller = await views.build_caller(user)
        out = await settings.set_shadow(db, tenant, body.shadow, actor=await views.actor_for(db, caller))
        if out["status"] != "ok":
            raise HTTPException(status_code=422, detail="shadow must be true or false")
        return await views.status_payload(db, caller, tenant)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


# ---------------------------------------------------------------- platform-wide never-touch entries (API only, D-22)

@router.get("/never-touch", summary="List the platform-wide never-touch entries")
async def get_platform_never_touch(
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Built-in and platform-wide entries. Targets that match one are never changed automatically."""
    try:
        return {"items": views.visible_entries(await protected.list_entries(get_database(), None), True)}
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/never-touch", status_code=201, summary="Add a platform-wide never-touch entry")
async def post_platform_never_touch(
    body: NeverTouchBody,
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Adds an IP address, network (CIDR), host name or agent id that is never changed automatically in
    any organization."""
    try:
        db = get_database()
        caller = await views.build_caller(user)
        try:
            entry = await protected.add_entry(db, scope="platform", tenant_id=None, kind=body.kind, value=body.value,
                                              note=body.note, actor=await views.actor_for(db, caller))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=messages.API_DETAIL["entry_limit"]) from exc
        return views.entry_view(entry)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.delete("/never-touch/{entry_id:path}", summary="Remove a platform-wide never-touch entry")
async def delete_platform_never_touch(
    entry_id: str = Path(..., max_length=128),
    user=Depends(_require_platform_autonomy_control),
    _session=Depends(_require_interactive_session),
):
    """Removes a platform-wide entry. Built-in entries answer 403; an unknown entry answers 404."""
    try:
        if entry_id.startswith("builtin:"):
            raise _forbidden(messages.API_DETAIL["builtin_entry"])
        if not await protected.remove_entry(get_database(), entry_id, scope="platform", tenant_id=None):
            raise HTTPException(status_code=404, detail=messages.API_DETAIL["entry_not_found"])
        return {"deleted": entry_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc
