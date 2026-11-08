"""Service desk settings, tenant routes (Phase 85, plan 85-11, DESK-02, DESK-05, D-03, D-22, D-23, D-25).

GET  /api/autonomous-ops/service-desk          the desk's switch, words, breaker, posting readiness, model status
                                               and typical answer time for the caller's organization
PUT  /api/autonomous-ops/service-desk          change the switch (off, drafts, post) and/or the words
POST /api/autonomous-ops/service-desk/restore  restore Post answers after the desk dropped to Drafts only

All three need manage:autonomous_ops in a signed-in session; an API key and Platform Support are refused. The
mount guard (catalogue_mounts_autonomous_ops) checks the catalogue strings; the dependencies below add the exact
permission. Every value that changes leaves one control row in the activity list and one audit event naming the
person, and saving the current values records nothing. The platform organization has no service desk (409).
Moving Autonomous Ops to Undoable-auto never starts posting answers by itself; this switch does.
"""
import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from autonomous_ops import PLATFORM_TENANT_ID, views
from autonomous_ops_endpoints import (_require_interactive_session, _require_manage, _tenant_for, _unavailable)
from database import get_database
from service_desk import settings as desk_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autonomous-ops", tags=["Autonomous Ops"])

CONFLICT_CODES = ("platform_tenant", "breaker_tripped", "not_tripped")


class DeskSettingsBody(BaseModel):
    """Either or both; the words are checked again, with the sentences the screen shows, by
    ``service_desk.settings.validate_changes``. An unknown field is refused."""
    model_config = ConfigDict(extra="forbid")

    mode: Optional[Literal["off", "drafts", "post"]] = None
    words: Optional[List[str]] = None


def refuse(exc: desk_settings.SettingsError) -> HTTPException:
    """The HTTP answer for a refused change: 409 for the platform organization and for the breaker, else 422."""
    return HTTPException(status_code=409 if exc.code in CONFLICT_CODES else 422, detail=exc.detail)


async def _tenant(db, user, tenant_id: Optional[str]) -> str:
    tenant = await _tenant_for(db, user, tenant_id, write=True)
    if tenant == PLATFORM_TENANT_ID:
        raise HTTPException(status_code=409, detail=desk_settings.PlatformTenantError().detail)
    return tenant


async def _view(db, tenant: str):
    """The caller holds manage to be here, so the same flag lets them restore."""
    return await desk_settings.status_view(db, tenant, can_manage=True, can_restore=True)


@router.get("/service-desk", summary="Service desk settings of an organization")
async def get_service_desk(
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_manage),
    _session=Depends(_require_interactive_session),
):
    """The saved mode (off, drafts or post) and what applies now, the extra words, whether Post answers is
    being posted and which conditions are not met, whether the local model is running and the typical answer
    time. `readable` is false when a stored value could not be understood and Drafts only is shown. Platform
    staff name an organization with tenantId."""
    try:
        db = get_database()
        tenant = await _tenant(db, user, tenantId)
        return await _view(db, tenant)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.put("/service-desk", summary="Change the service desk settings of an organization")
async def put_service_desk(
    body: DeskSettingsBody,
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_manage),
    _session=Depends(_require_interactive_session),
):
    """Changes the mode (off, drafts, post) and/or the words (at most 50, 2 to 40 characters each). Post answers
    is refused while the service desk is at Drafts only after 3 withdrawn answers; use restore instead. Each value
    that really changes is recorded in the activity list and the audit log with the person's name; sending the
    current values records nothing. Returns the same view as GET."""
    changes = body.model_dump(exclude_none=True)
    try:
        db = get_database()
        tenant = await _tenant(db, user, tenantId)
        caller = await views.build_caller(user)
        try:
            await desk_settings.save(db, tenant, changes, actor=await views.actor_for(db, caller),
                                     scope="platform" if caller.tier == "owner" else "tenant")
        except desk_settings.SettingsError as exc:
            raise refuse(exc) from exc
        return await _view(db, tenant)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/service-desk/restore", summary="Restore Post answers after the service desk dropped to Drafts only")
async def restore_service_desk(
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(_require_manage),
    _session=Depends(_require_interactive_session),
):
    """Clears the drop to Drafts only and sets Post answers again; answers post again once every condition is
    met. Recorded in the activity list and the audit log with the person's name. Refused with 409 when nothing
    needs restoring."""
    try:
        db = get_database()
        tenant = await _tenant(db, user, tenantId)
        caller = await views.build_caller(user)
        try:
            await desk_settings.restore(db, tenant, actor=await views.actor_for(db, caller),
                                        scope="platform" if caller.tier == "owner" else "tenant")
        except desk_settings.SettingsError as exc:
            raise refuse(exc) from exc
        return await _view(db, tenant)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc
