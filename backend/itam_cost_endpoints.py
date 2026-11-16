"""ITAM cost routes (Phase 78): `GET /api/itam/costs/summary`.

Read-only, tenant-scoped. Figures come from itam_cost_service, the one shared per-asset
computation. Reuses `_require_itam_viewer` from itam_asset_endpoints.py (imported, never
copied): view:itam or manage:assets, then API-key scope narrowing (D-16).

The tenant is resolved first (itam_tenant_scope, D-13), so an empty or platform-admin context
gets 400 before any database read.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from auth_types import TokenData
from database import get_database
from itam_asset_endpoints import _require_itam_viewer
from itam_cost_service import compute_tenant_costs
from itam_tenant_scope import resolve_itam_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/itam/costs", tags=["ITAM Costs"])


@router.get("/summary", response_model=Dict[str, Any])
async def get_cost_summary(
    request: Request,
    includeDisposed: bool = Query(False),
    current_user: TokenData = Depends(_require_itam_viewer),
):
    """Purchase total, book value total and coverage for one organization.

    Disposed and retired assets are left out unless includeDisposed is true (D-01..D-03). A total
    with no contributing asset is {cents: null, hasData: false}, never 0 (D-10).
    """
    tenant_id = resolve_itam_tenant(request, current_user)
    db = get_database()
    try:
        result = await compute_tenant_costs(db, tenant_id, include_inactive=includeDisposed)
        return result["summary"]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ITAM cost summary failed for tenant %s: %s", tenant_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
