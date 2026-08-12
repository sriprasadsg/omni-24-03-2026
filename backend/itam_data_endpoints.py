"""ITAM CSV import/export routes (Phase 65 Plan 03, ITAM-DAT-03).

Both routes route safety through code that already exists rather than
reimplementing it:
  - customFields validation reuses `itam_catalog_service.collect_field_defs`
    + `validate_custom_field_values`, the identical pair
    `itam_asset_endpoints.create_manual_asset` calls (T-65-03-03).
  - document assembly reuses `itam_asset_endpoints.build_asset_document` and
    `next_asset_tag`, the same helpers the manual-create route uses.
  - every query runs through the tenant-isolated `get_database()` wrapper,
    never a raw internal database handle (T-65-03-04).
  - both routes depend on `_require_itam_admin`, imported from
    `itam_asset_endpoints` rather than a new gate (T-65-03-05).

Task 1 (this tracer) wires the export half only. Task 2 adds `POST /import`.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from auth_types import TokenData
from database import get_database
from itam_asset_endpoints import _require_itam_admin
from itam_audit_service import log_itam_action
from itam_catalog_service import collect_field_defs
from itam_data_service import generate_assets_csv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/itam/data", tags=["ITAM Data"])

# Bounds a single export response — a separate, independent cap from the
# import side's MAX_IMPORT_ROWS (Task 2).
MAX_EXPORT_ROWS = 10000


@router.get("/export")
async def export_assets(
    entity: str = Query("assets"),
    modelId: Optional[str] = Query(None),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Export the tenant's asset inventory to CSV.

    `entity` is reserved for future entity types; only `"assets"` is
    supported today. The query runs through `get_database()` — the
    tenant-isolated wrapper — never a raw internal database handle, so an
    export can never carry another tenant's rows (T-65-03-04).
    """
    if entity != "assets":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported entity for export. Only 'assets' is supported.",
        )

    db = get_database()
    query: Dict[str, Any] = {"modelId": modelId} if modelId else {}
    assets = await db.assets.find(query, {"_id": 0}).limit(MAX_EXPORT_ROWS).to_list(length=MAX_EXPORT_ROWS)

    if modelId:
        model_doc = await db.asset_models.find_one({"id": modelId})
        custom_field_keys = sorted(collect_field_defs(model_doc or {}).keys())
    else:
        keys = set()
        for asset in assets:
            keys.update((asset.get("customFields") or {}).keys())
        custom_field_keys = sorted(keys)

    csv_text = generate_assets_csv(assets, custom_field_keys)
    filename = f"itam-assets-{datetime.now(timezone.utc).date().isoformat()}.csv"

    await log_itam_action(
        current_user,
        action="itam_export.assets",
        resource_type="itam_export",
        resource_id="assets",
        details=f"Exported {len(assets)} assets",
    )

    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
