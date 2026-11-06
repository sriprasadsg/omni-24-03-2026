"""Staged patch rollouts, the Rollouts tab API (plan 84-09): /api/patch-rollouts.

Part of the Patching screen: the mount guard (catalogue_mounts_devices) checks view:patching on reads and
manage:patches on writes, and the dependencies below add the exact permission. Starting a rollout and saving rings
also need a signed-in session; an API key is refused (T-84-30). A rollout or suggestion of another organization
answers 404 (T-84-29). The tenant comes from the token; ``tenantId`` is honoured only for platform staff.

GET  /                  the Rollouts tab: cards, window strip, flags, rings summary (10 per page)
GET  /window            open, closed or none
GET  /pending-patches   patches waiting on a computer that can take a rollout (50 per page, searchable)
GET  /rings, PUT /rings the rollout rings and the groups they can use
POST /preflight         the check before Start, one row per check
POST /                  start a rollout (422 with the blocker rows, 409 when another rollout took a computer)
GET  /draft             a vulnerability suggestion turned into a name and patch list; stores nothing
GET  /{id}              one rollout card

The platform organization has no rollouts: reads answer an empty page, writes answer 409.
"""
import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StrictStr, StringConstraints

import rbac_defaults
from api_key_auth import get_current_user_or_api_key
from autonomous_ops import PLATFORM_TENANT_ID, settings, views as ops_views
from autonomous_ops.rollout import MIN_RINGS, picker, rings as rings_mod, start, store, views
from autonomous_ops.rollout import messages as rm
from autonomous_ops.scope import raw
from autonomous_ops_endpoints import _require_interactive_session, _tenant_for, _unavailable
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patch-rollouts", tags=["Patch rollouts"])

ROLLOUT_ID_MAX = 64
PatchId = Annotated[StrictStr, StringConstraints(max_length=200)]


class StartBody(BaseModel):
    """A name of 1 to 60 characters and 1 to 200 patch ids; fields not listed here are ignored."""
    name: Annotated[StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    patchIds: List[PatchId] = Field(min_length=1, max_length=200)


class PreflightBody(BaseModel):
    patchIds: List[PatchId] = Field(default_factory=list, max_length=200)


class RingsBody(BaseModel):
    """The rings as the form sends them; every value is checked again, with the sentence the screen shows, by
    ``rings.validate``."""
    rings: List[Dict[str, Any]] = Field(max_length=50)


async def _require_manage_patches(user=Depends(get_current_user_or_api_key)):
    """Starting a rollout, saving rings and the check before Start need manage:patches; Platform Support never."""
    if rbac_defaults.platform_tier(getattr(user, "role", None)) == "support" \
            or not await ops_views.holds(user, views.MANAGE_PERMISSION):
        raise HTTPException(status_code=403, detail=f"Missing required permission: {views.MANAGE_PERMISSION}")
    return user


async def _write_tenant(db, user, tenant_id: Optional[str]) -> str:
    tenant = await _tenant_for(db, user, tenant_id, write=True)
    if tenant == PLATFORM_TENANT_ID:
        raise HTTPException(status_code=409, detail=rm.API_DETAIL["platform_tenant"])
    return tenant


async def _actor(db, user) -> Dict[str, str]:
    """{id, name, username, display} of the person: the display name is a courtesy, the username always works."""
    username = str(getattr(user, "username", None) or "unknown")
    display = username
    try:
        doc = await raw(db).users.find_one({"email": username}, {"_id": 0, "name": 1})
        if doc and doc.get("name"):
            display = str(doc["name"])
    except Exception as exc:
        logger.debug("patch rollouts: display name for %s not read: %s", username, exc)
    return {"id": username, "name": display, "username": username, "display": display}


async def _caller(db, user, tenant: str):
    return await views.build_caller(user, tenant, await settings.load(db, tenant))


def _now() -> datetime:
    return datetime.now(timezone.utc)


TenantQuery = Query(None, max_length=ops_views.TENANT_ID_MAX)


@router.get("", summary="Rollouts of an organization")
async def list_rollouts(offset: int = Query(0, ge=0, le=100000), limit: int = Query(10, ge=1, le=50),
                        tenantId: Optional[str] = TenantQuery, user=Depends(get_current_user_or_api_key)):
    """Rollout cards (halted first, then waiting for approval, running, waiting for a window, finished), the
    maintenance window strip, what the caller may do and the rings summary."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=False)
        return await views.rollout_page(db, tenant, await _caller(db, user, tenant), offset, limit, _now())
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.get("/window", summary="Is the maintenance window open")
async def get_window(tenantId: Optional[str] = TenantQuery, user=Depends(get_current_user_or_api_key)):
    """open (closes at), closed (next opens) or none, in the organization's time zone."""
    try:
        db = get_database()
        return await views.window_strip(db, await _tenant_for(db, user, tenantId, write=False), _now())
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.get("/pending-patches", summary="Patches a rollout can install")
async def get_pending_patches(search: str = Query("", max_length=100), offset: int = Query(0, ge=0, le=100000),
                              limit: int = Query(picker.PAGE, ge=1, le=picker.PAGE),
                              tenantId: Optional[str] = TenantQuery, user=Depends(get_current_user_or_api_key)):
    """Patches pending on at least one Windows or Linux computer that can take a rollout, with the computer count."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=False)
        return await picker.pending_patches(db, tenant, search=search, offset=offset, limit=limit, now=_now())
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.get("/rings", summary="Rollout rings")
async def get_rings(tenantId: Optional[str] = TenantQuery, user=Depends(get_current_user_or_api_key)):
    """The saved rings and the organization's groups with the ring each one is in."""
    try:
        db = get_database()
        return await picker.rings_settings(db, await _tenant_for(db, user, tenantId, write=False))
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.put("/rings", summary="Save the rollout rings")
async def put_rings(body: RingsBody, tenantId: Optional[str] = TenantQuery, user=Depends(_require_manage_patches),
                    _session=Depends(_require_interactive_session)):
    """Save 2 to 4 rings built from the organization's own groups. Refused with the sentence the screen shows."""
    try:
        db = get_database()
        tenant = await _write_tenant(db, user, tenantId)
        await rings_mod.save(db, tenant, body.rings, actor=await _actor(db, user))
        return await picker.rings_settings(db, tenant)
    except HTTPException:
        raise
    except rings_mod.PlatformRingsError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except rings_mod.RingsError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/preflight", summary="Check before starting a rollout")
async def post_preflight(body: PreflightBody, tenantId: Optional[str] = TenantQuery,
                         user=Depends(_require_manage_patches)):
    """One row per check (window, rings, canary computers, computers left out, offline, Autonomous Ops, size,
    patches) and whether Start is possible. Reads only; nothing is claimed."""
    try:
        db = get_database()
        tenant = await _write_tenant(db, user, tenantId)
        return await start.preflight(db, tenant, list(body.patchIds), now=_now())
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("", status_code=201, summary="Start a rollout")
async def post_rollout(body: StartBody, tenantId: Optional[str] = TenantQuery, user=Depends(_require_manage_patches),
                       _session=Depends(_require_interactive_session)):
    """Start a rollout of the chosen patches. The canary ring goes first; nothing installs outside the
    maintenance window. Answers 422 with the check's rows when something blocks, 409 when another rollout took a
    computer first."""
    try:
        db = get_database()
        tenant = await _write_tenant(db, user, tenantId)
        out = await start.start_rollout(db, tenant, name=body.name, patch_ids=list(body.patchIds),
                                        actor=await _actor(db, user), now=_now())
        if out["status"] != "started":
            code = 409 if out.get("reason") == "platform_tenant" else 422
            raise HTTPException(status_code=code, detail=rm.API_DETAIL["platform_tenant"] if code == 409
                                else rm.VALIDATION["patches"])
        made = await store.rollouts(db).find_one({"id": out["rolloutId"], "tenantId": tenant},
                                                 {"_id": 0, "name": 1, "shadow": 1})
        return {"id": out["rolloutId"], "name": (made or {}).get("name") or body.name,
                "simulation": bool((made or {}).get("shadow"))}
    except HTTPException:
        raise
    except start.PreflightBlocked as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc), "rows": exc.rows})
    except start.AlreadyInRollout as exc:
        return JSONResponse(status_code=409, content={"detail": str(exc), "code": "already_in_rollout"})
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.get("/draft", summary="Draft a rollout from a vulnerability suggestion")
async def get_draft(suggestion: str = Query(..., min_length=1, max_length=128), tenantId: Optional[str] = TenantQuery,
                    user=Depends(get_current_user_or_api_key)):
    """The suggested patches that are still pending on the suggestion's computer, with a name. Nothing is stored:
    a rollout exists only after a person presses Start."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=False)
        found = await picker.draft(db, tenant, suggestion)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=rm.API_DETAIL["suggestion_not_found"])
    return found


@router.get("/{rollout_id}", summary="One rollout")
async def get_rollout(rollout_id: str = Path(..., max_length=ROLLOUT_ID_MAX), tenantId: Optional[str] = TenantQuery,
                      user=Depends(get_current_user_or_api_key)):
    """One rollout card of the caller's organization; another organization's id answers 404."""
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=False)
        doc = None if tenant == PLATFORM_TENANT_ID else store.normalise(
            await store.rollouts(db).find_one({"id": rollout_id, "tenantId": tenant}))
        if doc is None:
            raise HTTPException(status_code=404, detail=rm.API_DETAIL["rollout_not_found"])
        return await views.rollout_card(db, tenant, doc, await _caller(db, user, tenant), _now())
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc
