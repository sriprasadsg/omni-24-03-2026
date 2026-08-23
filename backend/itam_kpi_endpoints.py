"""ITAM dashboard KPI route (Phase 72 Plan 04, ITAM-REP-04).

A single tenant-scoped route the dashboard tile grid consumes:
`GET /api/itam/kpis`. Deliberately a distinct prefix from
itam_reporting_endpoints.py's `/api/itam/reports` (not a sub-path of it), so
no path declared in this file can ever shadow or be shadowed by a report
route regardless of registration order.

Reuses `_require_itam_viewer` from itam_asset_endpoints.py — imported, never
redefined; this is a read-only route so it accepts view:itam (not just
manage:assets), unlike the write-gated itam_*_endpoints.py routers (D-07).
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from auth_types import TokenData
from database import get_database
from itam_asset_endpoints import _require_itam_viewer
from itam_reporting_kpis import compute_itam_kpis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/itam/kpis", tags=["ITAM KPIs"])


@router.get("", response_model=Dict[str, Any])
async def get_itam_kpis(current_user: TokenData = Depends(_require_itam_viewer)):
    """Returns the four D-16 KPI payloads for the caller's tenant.

    403 when the caller has no tenant id — mirrors
    itam_lifecycle_endpoints.overdue_audit_report's own guard. An unexpected
    exception inside KPI computation is converted into a 500 with a generic
    detail rather than leaking internals (T-72-10), matching the existing
    itam_reporting_endpoints.py error-handling convention.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    db = get_database()
    try:
        return await compute_itam_kpis(db, tenant_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ITAM KPI computation failed for tenant %s: %s", tenant_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
