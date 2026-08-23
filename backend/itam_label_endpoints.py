"""ITAM Label endpoints (Phase 58) — offline asset-tag label generation.

Shares the /api/assets prefix with backend/asset_endpoints.py,
backend/itam_asset_endpoints.py, and backend/itam_lifecycle_endpoints.py.
Routes on this router: GET /{asset_id}/label/qr (present), GET
/{asset_id}/label/barcode (present), and POST /labels/sheet (present). All
are multi-segment, so none can be shadowed by or shadow
asset_endpoints.py's single-segment GET /{asset_id} under any registration
order. POST /labels/sheet is a fully literal two-segment path, so it cannot
be captured by itam_lifecycle_endpoints.py's POST /{asset_id}/checkout,
/checkin or /audit under any registration order, since none of those
literal second segments is "sheet".

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
from itam_asset_endpoints import _require_itam_admin, _require_itam_viewer
from itam_label_service import LabelEncodingError, generate_barcode_png, generate_label_sheet_pdf, generate_qr_png
from itam_models import MAX_LABEL_SHEET_ASSETS, LabelSheetRequest

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


async def _resolve_tag_for_label(current_user: TokenData, asset_id: str) -> str:
    """Shared prelude for every label route: tenant guard, asset load, tag
    extraction. Factored out so the QR and barcode routes (and any future
    label route) cannot drift apart in their failure behavior — one 403,
    one 404, and one missing-assetTag 400 shape for all of them.
    """
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
    return asset_tag


@router.get("/{asset_id}/label/qr")
async def get_asset_qr_label(
    asset_id: str,
    current_user: TokenData = Depends(_require_itam_viewer),
):
    """Return a PNG QR code encoding one asset's bare assetTag (D-02)."""
    asset_tag = await _resolve_tag_for_label(current_user, asset_id)

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


@router.get("/{asset_id}/label/barcode")
async def get_asset_barcode_label(
    asset_id: str,
    current_user: TokenData = Depends(_require_itam_viewer),
):
    """Return a PNG Code128 barcode encoding one asset's bare assetTag (D-02)."""
    asset_tag = await _resolve_tag_for_label(current_user, asset_id)

    try:
        png = generate_barcode_png(asset_tag)
    except LabelEncodingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"assetTag could not be encoded: {exc}",
        )

    filename = f"asset-label-{_safe_filename_part(asset_tag)}-barcode.png"
    return StreamingResponse(
        io.BytesIO(png),
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


async def _resolve_assets_for_sheet(db, asset_ids: list) -> tuple:
    """Resolve `asset_ids` (order- and duplicate-preserving) against the
    tenant-isolated db.assets handle. Returns `(assets, unresolved_ids)`.

    Queries once with `$in` over the de-duplicated id set — one round trip,
    not one per id — then walks the caller's original `asset_ids` list in
    order, duplicates included, appending the matching document each time.
    This ordering step is not cosmetic: a $in query returns rows in
    arbitrary order, and a caller who lists ids in shelf order expects the
    printed sheet in shelf order. De-duplication is only for the query; the
    returned list preserves duplicates, because asking for two copies of
    one label is a legitimate request and quietly collapsing it to one
    would be a silent drop.
    """
    unique_ids = list(set(asset_ids))
    cursor = db.assets.find({"id": {"$in": unique_ids}}, {"_id": 0})
    docs = await cursor.to_list(length=MAX_LABEL_SHEET_ASSETS)
    by_id = {doc["id"]: doc for doc in docs}

    resolved = []
    unresolved_ids = []
    for asset_id in asset_ids:
        doc = by_id.get(asset_id)
        if doc is None:
            unresolved_ids.append(asset_id)
        else:
            resolved.append(doc)
    return resolved, unresolved_ids


@router.post("/labels/sheet")
async def post_labels_sheet(
    payload: LabelSheetRequest,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Return a printable Avery-5160 PDF label sheet for the given asset ids
    (D-01/D-03). No request is ever partially served: an empty list, an
    over-cap list, unresolved ids, and untagged assets are all refused
    outright with a 400 naming exactly what was wrong (T-58-08) — never a
    silently shorter sheet than what was asked for.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    if not payload.assetIds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one asset id is required.",
        )

    # Deliberate departure from bulk_delete_assets_route's `ids[:500]`
    # truncation convention (asset_endpoints.py): silently serving a
    # shorter sheet than was asked for means the operator prints it, walks
    # to the shelf, and only then discovers labels are missing, with
    # nothing in the response having told them.
    if len(payload.assetIds) > MAX_LABEL_SHEET_ASSETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"assetIds exceeds the {MAX_LABEL_SHEET_ASSETS}-id cap "
                f"({len(payload.assetIds)} supplied); the request was refused, "
                "not trimmed."
            ),
        )

    db = get_database()
    assets, unresolved_ids = await _resolve_assets_for_sheet(db, payload.assetIds)
    if unresolved_ids:
        # The lookup ran through the tenant-isolated db.assets handle, so a
        # cross-tenant id and a genuinely nonexistent id land in this list
        # identically — the response discloses nothing about whether an id
        # exists in another tenant (T-58-01).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "One or more asset ids could not be resolved.",
                "unresolvedAssetIds": unresolved_ids,
            },
        )

    missing_tag_ids = [a["id"] for a in assets if not a.get("assetTag")]
    if missing_tag_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "One or more assets have no assetTag to encode.",
                "assetIdsMissingTag": missing_tag_ids,
            },
        )

    try:
        pdf = generate_label_sheet_pdf(assets)
    except LabelEncodingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Label sheet could not be generated: {exc}",
        )

    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=asset-labels.pdf"},
    )
