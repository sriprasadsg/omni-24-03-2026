"""ITAM Finance endpoints (Phase 59) — purchase record write and computed
book-value read for IT assets. Mounted at /api/assets alongside
asset_endpoints.py, itam_asset_endpoints.py, itam_lifecycle_endpoints.py and
itam_label_endpoints.py.

Routes: PATCH /{asset_id}/purchase and GET /{asset_id}/book-value (Plan
59-01); GET /{asset_id}/warranty (this plan). All are multi-segment, so none
can shadow or be shadowed by asset_endpoints.py's single-segment
GET /{asset_id} under any registration order.

This module reuses `_require_itam_admin` from itam_asset_endpoints.py rather
than redefining the manage:assets RBAC gate.

This is a new file rather than an extension of itam_lifecycle_endpoints.py
(534 lines) or asset_endpoints.py (511 lines), both of which are already
over the 500-line CLAUDE.md cap.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument

from auth_types import TokenData
from database import get_database
from itam_asset_endpoints import _require_itam_admin, _require_itam_viewer
from itam_audit_service import log_itam_action
from itam_models import AssetPurchaseUpdate
from itam_finance_service import (
    REASON_NO_DEPRECIATION_POLICY,
    REASON_NO_PURCHASE_RECORD,
    compute_book_value,
    compute_warranty_status,
    get_warranty_alert_window,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assets", tags=["ITAM Finance"])


async def _load_asset(db, asset_id: str) -> Dict[str, Any]:
    """Loads one asset by id through the tenant-isolated db handle. Because
    db.assets is auto-tenant-scoped, an asset id belonging to another tenant
    resolves to nothing here and produces exactly the same 404 as a
    genuinely unknown id, so a probe can never learn that the id exists in
    another tenant."""
    asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


@router.patch("/{asset_id}/purchase", status_code=status.HTTP_200_OK, response_model=Dict[str, Any])
async def update_asset_purchase(
    asset_id: str,
    payload: AssetPurchaseUpdate,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Sets or corrects an asset's purchase/warranty record (ITAM-FIN-01).

    exclude_none=True means this contract sets and corrects values but does
    not clear them to null. When purchaseDate or warrantyMonths is among the
    supplied keys, this also clears warrantyAlertSentAt — the reset half of
    the idempotency contract Plan 59-04's sweep depends on, so a renewed or
    corrected warranty becomes alertable again.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    db = get_database()

    update_data = payload.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    if "supplierId" in update_data:
        supplier = await db.suppliers.find_one({"id": update_data["supplierId"]})
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"supplierId '{update_data['supplierId']}' not found.",
            )

    if "purchase_order_id" in update_data:
        # T-71-04 (71-01-PLAN.md, declared mitigate but never implemented):
        # without this check any tenant could link an asset to an arbitrary
        # or another tenant's purchase_order_id string, since it was
        # previously accepted and persisted with no existence/ownership
        # check at all. db is the tenant-isolated handle, so this can only
        # ever resolve a PO belonging to the caller's own tenant.
        po = await db.purchase_orders.find_one({"id": update_data["purchase_order_id"]})
        if not po:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"purchase_order_id '{update_data['purchase_order_id']}' not found.",
            )

    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    mutation: Dict[str, Any] = {"$set": update_data}
    if "purchaseDate" in update_data or "warrantyMonths" in update_data:
        mutation["$unset"] = {"warrantyAlertSentAt": ""}

    result = await db.assets.find_one_and_update(
        {"id": asset_id},
        mutation,
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    await log_itam_action(
        current_user,
        action="itam_asset.purchase_update",
        resource_type="itam_asset",
        resource_id=asset_id,
        details=f"Updated fields: {', '.join(sorted(update_data.keys()))}",
    )
    return result


@router.get("/{asset_id}/book-value", status_code=status.HTTP_200_OK, response_model=Dict[str, Any])
async def get_asset_book_value(
    asset_id: str,
    current_user: TokenData = Depends(_require_itam_viewer),
):
    """Computes an asset's current straight-line book value at read time
    (ITAM-FIN-03). Never writes anything — the book value is computed per
    request and never stored (D-04). A missing or partial depreciation
    policy is a routine, expected state for pre-Phase-59 data, so it always
    returns 200 with a structured reason, never a 500 and never a
    silently-wrong number.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    db = get_database()
    asset = await _load_asset(db, asset_id)

    base = {
        "assetId": asset_id,
        "modelId": asset.get("modelId"),
        "purchaseCostCents": asset.get("purchaseCostCents"),
        "purchaseDate": asset.get("purchaseDate"),
        "computedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    }

    if asset.get("purchaseCostCents") is None or asset.get("purchaseDate") is None:
        return {**base, "bookValueCents": None, "reason": REASON_NO_PURCHASE_RECORD}

    model_id = asset.get("modelId")
    model_doc = await db.asset_models.find_one({"id": model_id}) if model_id else None
    if (
        not model_doc
        or model_doc.get("usefulLifeYears") is None
        or model_doc.get("salvageValueCents") is None
    ):
        return {**base, "bookValueCents": None, "reason": REASON_NO_DEPRECIATION_POLICY}

    try:
        result = compute_book_value(
            purchase_date=asset["purchaseDate"],
            purchase_cost_cents=asset["purchaseCostCents"],
            useful_life_years=model_doc["usefulLifeYears"],
            salvage_value_cents=model_doc["salvageValueCents"],
            now=datetime.now(timezone.utc),
        )
    except ValueError:
        return {**base, "bookValueCents": None, "reason": REASON_NO_DEPRECIATION_POLICY}

    return {
        **base,
        **result,
        "usefulLifeYears": model_doc["usefulLifeYears"],
        "salvageValueCents": model_doc["salvageValueCents"],
    }


@router.get("/{asset_id}/warranty", status_code=status.HTTP_200_OK, response_model=Dict[str, Any])
async def get_asset_warranty(
    asset_id: str,
    current_user: TokenData = Depends(_require_itam_viewer),
):
    """Reports an asset's warranty expiry, status, remaining days, and the
    tenant's configured alert window (ITAM-FIN-02). Read-only — performs no
    write of any kind. Classifies nothing itself: compute_warranty_status
    and get_warranty_alert_window are the single definition of warranty
    status and window this route and Plan 59-04's background sweep both
    call, so an operator's on-screen status and the alert they receive can
    never disagree (PD-04).

    warrantyAlertSentAt is echoed as-is so an admin can tell "no alert has
    fired for this asset yet" apart from "the alert already went out" — it
    is the marker Plan 59-04's sweep writes.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    db = get_database()
    asset = await _load_asset(db, asset_id)
    window = await get_warranty_alert_window(db, tenant_id)
    status_result = compute_warranty_status(
        asset.get("purchaseDate"),
        asset.get("warrantyMonths"),
        datetime.now(timezone.utc),
        window,
    )

    return {
        "assetId": asset_id,
        "purchaseDate": asset.get("purchaseDate"),
        "warrantyMonths": asset.get("warrantyMonths"),
        "alertWindowDays": window,
        "warrantyAlertSentAt": asset.get("warrantyAlertSentAt"),
        "computedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        **status_result,
    }
