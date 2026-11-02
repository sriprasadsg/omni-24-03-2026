"""Autonomous Ops response settings, tenant routes (Phase 83, plan 83-07, RESP-04, RESP-08, D-04, D-10, D-13, D-22).

GET /api/autonomous-ops/response-settings   the three settings of the caller's organization
PUT /api/autonomous-ops/response-settings   change any of them: twoSignal, blockHours, watchedServices

The two settings routes need manage:autonomous_ops in a signed-in session; an API key and Platform Support are
refused.

GET  /api/autonomous-ops/incidents                       the Needs your decision cards (view access; the flags on
                                                          every line say what the caller may do)
The mount guard (catalogue_mounts_autonomous_ops) checks the catalogue strings; the dependencies below add
the exact permission. A change takes effect for new decisions only (a block already in place keeps its
length). Every value that changes leaves one control row in the activity list and one audit event, naming
the person; turning the two-source rule off is one of them (PROH-83-09).

The platform router (autonomous_ops_response_platform_endpoints) writes the same settings for every
organization at once, one organization at a time.
"""
import logging
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, StrictBool, StrictInt, StringConstraints

import agent_capabilities
from api_key_auth import get_current_user_or_api_key
from autonomous_ops import PLATFORM_TENANT_ID, incident_views, messages, response_settings, views
from autonomous_ops.scope import raw
from autonomous_ops_endpoints import _require_interactive_session, _require_manage, _tenant_for, _unavailable
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


# ---------------------------------------------------------------- the cards

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
