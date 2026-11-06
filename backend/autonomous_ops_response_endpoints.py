"""Autonomous Ops response settings, tenant routes (Phase 83, plan 83-07, RESP-04, RESP-08, D-04, D-10, D-13, D-22).

GET /api/autonomous-ops/response-settings   the three settings of the caller's organization
PUT /api/autonomous-ops/response-settings   change any of them: twoSignal, blockHours, watchedServices

The two settings routes need manage:autonomous_ops in a signed-in session; an API key and Platform Support are
refused.

GET  /api/autonomous-ops/incidents                       the Needs your decision cards (view access; the flags on
                                                          every line say what the caller may do)
POST /api/autonomous-ops/actions/{id}/confirm-isolation  keep an isolated computer isolated (control:autonomous_ops,
                                                          signed-in session, single use, refused during a stop)
GET  /api/autonomous-ops/rollout-cards                   the patch rollout cards for Needs your decision (Phase 84;
                                                          view access, flags per line as for the incident cards)
POST /api/autonomous-ops/rollout-lines/{rolloutId}/{ring}/{line}/approve   approve one line of one ring of one
                                                          rollout, one approval per computer (control:autonomous_ops,
                                                          signed-in session, refused during a stop)
POST /api/autonomous-ops/rollout-lines/{rolloutId}/{ring}/{line}/deny      deny that line (allowed during a stop)
The mount guard (catalogue_mounts_autonomous_ops) checks the catalogue strings; the dependencies below add
the exact permission. A change takes effect for new decisions only (a block already in place keeps its
length). Every value that changes leaves one control row in the activity list and one audit event, naming
the person; turning the two-source rule off is one of them (PROH-83-09).

The platform router (autonomous_ops_response_platform_endpoints) writes the same settings for every
organization at once, one organization at a time.
"""
import logging
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictBool, StrictInt, StringConstraints

import agent_capabilities
from api_key_auth import get_current_user_or_api_key
from autonomous_ops import PLATFORM_TENANT_ID, incident_views, isolation, messages, response_settings, views
from autonomous_ops.rollout import cards as rollout_cards, lines as rollout_lines, messages as rollout_messages
from autonomous_ops.scope import raw
from autonomous_ops_endpoints import (DecisionBody, _decision_error, _require_control, _require_interactive_session,
                                      _require_manage, _tenant_for, _unavailable)
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autonomous-ops", tags=["Autonomous Ops"])

RESTART_CAPABILITY = "remediation_executor"        # D-21: the tick Phase 81 mapped to restart_service

ServiceName = Annotated[str, StringConstraints(max_length=200)]


class ResponseSettingsBody(BaseModel):
    """Any of the three; the values are checked again, with the sentences the screen shows, by
    ``response_settings.validate_changes``."""
    twoSignal: Optional[StrictBool] = None
    blockHours: Optional[StrictInt] = None
    watchedServices: Optional[List[ServiceName]] = None


def settings_payload(s: response_settings.ResponseSettings, *, restart_available: bool) -> Dict[str, Any]:
    return {"twoSignal": s.two_signal, "blockHours": s.block_hours, "watchedServices": list(s.watched_services),
            "readable": s.readable, "restartAvailable": restart_available}


async def restart_available(db, tenant_id: str) -> bool:
    """True when remediation is ticked for the organization; the list can be saved either way (D-21)."""
    try:
        return RESTART_CAPABILITY in await agent_capabilities.allowed_for(raw(db), tenant_id)
    except Exception as exc:                       # allowed_for already fails closed; this is belt and braces
        logger.warning("autonomous_ops: capability lookup for %s failed: %s", tenant_id, exc)
        return False


def refuse(exc: response_settings.SettingsError) -> HTTPException:
    """The HTTP answer for a refused change: 409 for the platform organization, else 422."""
    status = 409 if isinstance(exc, response_settings.PlatformTenantError) else 422
    return HTTPException(status_code=status, detail=exc.detail)


async def _tenant(db, user, tenant_id: Optional[str]) -> str:
    tenant = await _tenant_for(db, user, tenant_id, write=True)
    if tenant == PLATFORM_TENANT_ID:
        raise HTTPException(status_code=409, detail=messages.API_DETAIL["platform_tenant"])
    return tenant


@router.get("/response-settings", summary="Response settings of an organization")
async def get_response_settings(
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_manage),
    _session=Depends(_require_interactive_session),
):
    """The two-source switch (twoSignal), the block length in hours (blockHours) and the watched services,
    with `readable` (false when a stored value could not be understood and the safe default is shown) and
    `restartAvailable` (false when remediation is not ticked for the organization; the list can still be
    saved). Platform staff name an organization with tenantId."""
    try:
        db = get_database()
        tenant = await _tenant(db, user, tenantId)
        s = await response_settings.load(db, tenant)
        return settings_payload(s, restart_available=await restart_available(db, tenant))
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.put("/response-settings", summary="Change the response settings of an organization")
async def put_response_settings(
    body: ResponseSettingsBody,
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_manage),
    _session=Depends(_require_interactive_session),
):
    """Changes any of twoSignal (true or false), blockHours (a whole number from 1 to 168) and
    watchedServices (at most 50 names, no duplicates, no system service). Blocks already in place keep
    their length. Each value that really changes is recorded in the activity list and the audit log with
    the person's name; sending the current values changes and records nothing."""
    changes = body.model_dump(exclude_none=True)
    try:
        db = get_database()
        tenant = await _tenant(db, user, tenantId)
        caller = await views.build_caller(user)
        try:
            s = await response_settings.save(db, tenant, changes, actor=await views.actor_for(db, caller),
                                             scope="platform" if caller.tier == "owner" else "tenant")
        except response_settings.SettingsError as exc:
            raise refuse(exc) from exc
        return settings_payload(s, restart_available=await restart_available(db, tenant))
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


# ---------------------------------------------------------------- the cards and the one new decision

@router.get("/incidents", summary="Incidents that need a decision")
async def get_incidents(
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(10, ge=1, le=50),
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(get_current_user_or_api_key),
):
    """One card per incident that has an action waiting for a person or an isolation nobody confirmed yet,
    soonest deadline first (ties: the newer incident first), 10 a page. Every line carries canApprove,
    canDeny and canConfirmIsolation, all false for a view-only role, Platform Support or an API key. `stopped`
    names the stop that disables Approve. Platform staff name an organization with tenantId."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=False)
        caller = await views.build_caller(user)
        return await incident_views.list_cards(db, tenant, offset=offset, limit=limit, staff=caller.staff,
                                               can_act=caller.can_control and caller.interactive)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/actions/{action_id}/confirm-isolation", summary="Keep an isolated computer isolated")
async def post_confirm_isolation(
    action_id: str = Path(..., max_length=128),
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_control),
    _session=Depends(_require_interactive_session),
):
    """Keeps the computer isolated until a person restores it; the agent hears at its next heartbeat. Needs
    control:autonomous_ops in a signed-in session. Single use: a second click answers 409. Answers 409 during a
    stop, once the computer has returned to the network (or is about to), and for an action that is not an
    isolation."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=True)
        caller = await views.build_caller(user)
        out = await isolation.confirm(db, tenant, action_id, await views.actor_for(db, caller))
        if out.get("status") != "confirmed":
            raise _decision_error(out)
        return {"status": "confirmed", "action": await views.present_one(
            db, tenant, action_id, caller, can_act=caller.can_control and caller.interactive)}
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


# ---------------------------------------------------------------- patch rollout cards and their lines (Phase 84)

@router.get("/rollout-cards", summary="Patch rollout steps that need a decision")
async def get_rollout_cards(
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(10, ge=1, le=50),
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(get_current_user_or_api_key),
):
    """One card per ring of a patch rollout that has a step waiting for a person (or one decided a moment ago),
    soonest expiry first, 10 a page. A card has an Install line, a Restart line once the installs are done and
    only for computers that need one, and a Revert restart line when a revert needs one. Every line carries its
    own canApprove and canDeny, all false for a view-only role, Platform Support or an API key; `stopped` names the
    stop that disables Approve. Platform staff name an organization with tenantId."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=False)
        return await rollout_cards.list_cards(db, tenant, await views.build_caller(user), offset=offset, limit=limit)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


def _line_answer(out: Dict[str, Any]):
    """The answer for a whole-line decision: the result itself when something was decided, 404 for a rollout
    that is not the caller's, and 409 (the result plus `detail`, the sentence) when nothing could be decided."""
    if out.get("status") in ("approved", "denied"):
        return out
    if out.get("message") == rollout_messages.LINE_RESULT["not_found"]:
        raise HTTPException(status_code=404, detail=out["message"])
    return JSONResponse(status_code=409, content={**out, "detail": out.get("message")})


async def _decide_line(rollout_id: str, ring: int, line: str, tenant_id: Optional[str], user, what: str,
                       reason: Optional[str] = None):
    try:
        db = get_database()
        tenant = await _tenant(db, user, tenant_id)
        actor = await views.actor_for(db, await views.build_caller(user))
        if what == "approve":
            out = await rollout_lines.approve_line(db, tenant, rollout_id, ring, line, approver=actor)
        else:
            out = await rollout_lines.deny_line(db, tenant, rollout_id, ring, line, approver=actor, reason=reason or "")
        return _line_answer(out)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


RolloutLine = Literal["install", "reboot", "revert_reboot"]


@router.post("/rollout-lines/{rollout_id}/{ring}/{line}/approve", summary="Approve one step of a patch rollout")
async def post_approve_rollout_line(
    rollout_id: str = Path(..., min_length=1, max_length=64),
    ring: int = Path(..., ge=0, le=3),
    line: RolloutLine = Path(...),
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_control),
    _session=Depends(_require_interactive_session),
):
    """Approves every computer of one step (install, restart or revert restart) of one ring of one rollout, one
    approval per computer, so one click is one approval per stage. Needs control:autonomous_ops in a signed-in
    session; an API key is refused. A computer is sent its work inside the maintenance window only. Answers 409
    when the step was already decided or automatic actions are stopped, 404 for a rollout that is not yours."""
    return await _decide_line(rollout_id, ring, line, tenantId, user, "approve")


@router.post("/rollout-lines/{rollout_id}/{ring}/{line}/deny", summary="Deny one step of a patch rollout")
async def post_deny_rollout_line(
    rollout_id: str = Path(..., min_length=1, max_length=64),
    ring: int = Path(..., ge=0, le=3),
    line: RolloutLine = Path(...),
    body: Optional[DecisionBody] = None,
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_control),
    _session=Depends(_require_interactive_session),
):
    """Denies every computer of that step; nothing is sent to any computer and the rollout halts at the ring.
    The reason is optional (500 characters at most). Still allowed while automatic actions are stopped."""
    return await _decide_line(rollout_id, ring, line, tenantId, user, "deny", body.reason if body else None)
