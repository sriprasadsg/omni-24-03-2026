"""ITAM cost routes (Phase 78): GET /api/itam/costs/summary, /assets and /assets/{id}.

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
from itam_cost_service import compute_asset_cost_detail, compute_tenant_costs
from itam_tenant_scope import resolve_itam_tenant
from pagination_utils import paginate

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


@router.get("/assets", response_model=Dict[str, Any])
async def list_cost_assets(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    includeDisposed: bool = Query(False),
    agentOnly: bool = Query(False),
    current_user: TokenData = Depends(_require_itam_viewer),
):
    """Every in-scope asset of one organization with its cost, book value and joined agent (D-05).

    Book value is not stored, so the whole tenant set is computed, sorted (D-08) and then paged;
    no total depends on the page. agentOnly keeps only assets an agent document names.
    """
    tenant_id = resolve_itam_tenant(request, current_user)
    db = get_database()
    try:
        result = await compute_tenant_costs(db, tenant_id, include_inactive=includeDisposed, with_agents=True)
        rows = result["rows"]
        if agentOnly:
            rows = [r for r in rows if r.get("agent") is not None]
        envelope = paginate(rows, page, page_size)
        envelope.update(
            tenantId=tenant_id,
            computedAt=result["summary"]["computedAt"],
            includeDisposed=includeDisposed,
            agentOnly=agentOnly,
        )
        return envelope
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ITAM cost asset list failed for tenant %s: %s", tenant_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/assets/{asset_id}", response_model=Dict[str, Any])
async def get_cost_asset(
    asset_id: str,
    request: Request,
    current_user: TokenData = Depends(_require_itam_viewer),
):
    """One asset's cost row, disposed and retired included. An unknown id and another organization's
    id both get the same 404 body, so the route is no existence oracle."""
    tenant_id = resolve_itam_tenant(request, current_user)
    db = get_database()
    try:
        detail = await compute_asset_cost_detail(db, tenant_id, asset_id)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        return detail
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ITAM cost asset detail failed for tenant %s: %s", tenant_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
