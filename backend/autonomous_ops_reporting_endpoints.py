"""Autonomous Ops reporting routes (Phase 86, plan 86-01, D-05..D-12): /api/autonomous-ops.

GET /api/autonomous-ops/statistics  per-rule counts and the time-saved estimate for one organization

Mounted under the Autonomous Ops catalogue guard (catalogue_mounts_autonomous_ops), so a caller needs
view:autonomous_ops. Nothing here writes the ledger. A tenant role always means its own organization;
platform staff name one with tenantId; the platform organization has nothing to count and answers 409.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api_key_auth import get_current_user_or_api_key
from autonomous_ops import PLATFORM_TENANT_ID, messages, views
from autonomous_ops.reporting import DEFAULT_WINDOW, WINDOWS, stats
from autonomous_ops_endpoints import _tenant_for, _unavailable
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autonomous-ops", tags=["Autonomous Ops"])


@router.get("/statistics", summary="Autonomous Ops statistics and time saved for an organization")
async def get_statistics(
    days: int = Query(DEFAULT_WINDOW),
    tenantId: Optional[str] = Query(None, max_length=views.TENANT_ID_MAX),
    user=Depends(get_current_user_or_api_key),
):
    """Decisions per rule over the last 7, 30 or 90 days (default 30) and the time-saved estimate.
    Simulation rows are reported apart as wouldHaveDone and never counted as real. Platform staff name an
    organization with tenantId."""
    if days not in WINDOWS:
        raise HTTPException(status_code=422, detail="days must be 7, 30 or 90")
    try:
        db = get_database()
        tenant = await _tenant_for(db, user, tenantId, write=False)
        if tenant == PLATFORM_TENANT_ID:
            raise HTTPException(status_code=409, detail=messages.API_DETAIL["platform_tenant"])
        return await stats.statistics_payload(db, await views.build_caller(user), tenant, days)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc
