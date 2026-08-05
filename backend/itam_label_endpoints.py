"""ITAM Label endpoints (Phase 58) — offline asset-tag label generation.

Shares the /api/assets prefix with backend/asset_endpoints.py,
backend/itam_asset_endpoints.py, and backend/itam_lifecycle_endpoints.py.
Routes on this router: GET /{asset_id}/label/qr (this plan), and
GET /{asset_id}/label/barcode + POST /labels/sheet (later plans in this
phase). All are multi-segment, so none can be shadowed by or shadow
asset_endpoints.py's single-segment GET /{asset_id} under any registration
order.

This module reuses `_require_itam_admin` from itam_asset_endpoints.py rather
than redefining the manage:assets RBAC gate.
"""
import io
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from auth_types import TokenData
from database import get_database
from itam_asset_endpoints import _require_itam_admin
from itam_label_service import LabelEncodingError, generate_qr_png

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assets", tags=["ITAM Labels"])

_SAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _safe_filename_part(value: str) -> str:
    """Sanitize `value` for use inside a Content-Disposition filename.

    Every character outside [A-Za-z0-9._-] is mapped to `_`, the result is
    capped at 64 characters, and the literal "asset" is returned when
    nothing survives. An assetTag is a caller-suppliable string (see
    ManualAssetCreate.assetTag), so an unfiltered tag reaching a response
    header is a response-splitting vector (T-58-05).
    """
    sanitized = _SAFE_FILENAME_CHARS.sub("_", value or "")[:64]
    return sanitized or "asset"


async def _load_asset_for_label(db, asset_id: str) -> dict:
    """Load one asset by id through the tenant-isolated db handle.

    Because `db.assets` is auto-tenant-scoped, an asset id belonging to
    another tenant resolves to nothing here and produces exactly the same
    404 as a genuinely unknown id, so the response never discloses that the
    id exists elsewhere.
    """
    asset = await db.assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


@router.get("/{asset_id}/label/qr")
async def get_asset_qr_label(
    asset_id: str,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Return a PNG QR code encoding one asset's bare assetTag (D-02)."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    db = get_database()

    asset = await _load_asset_for_label(db, asset_id)

    asset_tag = asset.get("assetTag")
    if not asset_tag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Asset has no assetTag value to encode.",
        )

    try:
        png = generate_qr_png(asset_tag)
    except LabelEncodingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"assetTag could not be encoded: {exc}",
        )

    filename = f"asset-label-{_safe_filename_part(asset_tag)}-qr.png"
    return StreamingResponse(
        io.BytesIO(png),
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
