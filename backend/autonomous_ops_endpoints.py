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
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api_key_auth import get_current_user_or_api_key
from autonomous_ops import PLATFORM_TENANT_ID, ledger, views
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
                                     viewer_is_platform_staff=caller.staff)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc
