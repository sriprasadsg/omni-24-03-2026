"""ITAM Lifecycle endpoints (Phase 57) — check-out, check-in, physical audit, and the
assignment-history read route for IT assets. Mounted at /api/assets alongside
itam_asset_endpoints.py's router (Phase 56); every route here is multi-segment
(`/{asset_id}/checkout`, `/{asset_id}/history`, ...) so none can be shadowed by
asset_endpoints.py's single-segment `GET /{asset_id}` under any registration order.

This module reuses `_require_itam_admin` from itam_asset_endpoints.py rather than
redefining the manage:assets RBAC gate.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument

from auth_types import TokenData
from database import get_database
from cache_service import invalidate_cache
from itam_asset_endpoints import _require_itam_admin
from itam_models import CheckoutRequest, LifecycleStatus
from itam_lifecycle_service import write_history

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assets", tags=["ITAM Lifecycle"])

# Action constants (57-01 consumes ACTION_CHECKOUT; 57-02/57-03 consume the rest).
ACTION_CHECKOUT = "checkout"
ACTION_CHECKIN = "checkin"
ACTION_AUDIT = "audit"
AUDIT_INTERVAL_DAYS = 365  # D-03: fixed 12-month physical-audit interval (57-03).


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _deployable_guard() -> Dict[str, Any]:
    """Filter fragment matching an asset whose lifecycleStatus is deployable, or whose
    lifecycleStatus key is absent entirely. The absent case is not optional: every
    pre-existing agent-discovered asset lacks the key, and asset_endpoints.py already
    treats its absence as deployable at read time — this guard must match that.
    """
    return {
        "$or": [
            {"lifecycleStatus": LifecycleStatus.DEPLOYABLE.value},
            {"lifecycleStatus": {"$exists": False}},
        ]
    }


async def _resolve_target(db, target_type: str, target_id: str) -> None:
    """Resolve a checkout target against the caller's tenant. Raises 400 when the id
    does not resolve to a user or a location in the caller's tenant. Called strictly
    before the guarded update so an unresolvable target never mutates the asset.
    """
    if target_type == "user":
        target = await db.users.find_one({"id": target_id})
    elif target_type == "location":
        target = await db.locations.find_one({"id": target_id})
    else:  # pragma: no cover — CheckoutRequest's Literal already excludes this
        target = None
    if not target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{target_type} '{target_id}' not found.",
        )


@router.post("/{asset_id}/checkout", response_model=Dict[str, Any])
async def checkout_asset(
    asset_id: str,
    payload: CheckoutRequest,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Check a deployable asset out to a platform user or a location (ITAM-LIFE-02).

    Refused with 409 for an asset not in a deployable-typed status, 404 for an
    unknown or cross-tenant asset id, and 400 for an unresolvable target. Every
    successful check-out writes exactly one immutable assignment_history entry.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user.",
        )

    db = get_database()

    # Target resolution happens strictly before the guarded update so an
    # unresolvable target never mutates the asset.
    await _resolve_target(db, payload.targetType, payload.targetId)

    now = _now_iso()
    set_doc: Dict[str, Any] = {
        "lifecycleStatus": LifecycleStatus.DEPLOYED.value,
        "assignedToType": payload.targetType,
        "assignedToId": payload.targetId,
        "checkedOutAt": now,
        "checkedOutBy": current_user.username,
        "updatedAt": now,
    }
    if payload.targetType == "location":
        # D-02: locationId means where the asset currently is, not where it was
        # catalogued — a location check-out overwrites it. The prior value survives
        # only in assignment_history. Left untouched for a user target.
        set_doc["locationId"] = payload.targetId

    update: Dict[str, Any] = {"$set": set_doc}
    if payload.expectedReturnDate:
        set_doc["expectedReturnDate"] = payload.expectedReturnDate
    else:
        # A value from an earlier check-out can never survive into a new one.
        update["$unset"] = {"expectedReturnDate": ""}

    # The deployable guard belongs inside the find_one_and_update filter itself,
    # never in a preceding conditional read — two concurrent requests would
    # otherwise both observe a deployable asset and both write. tenantId is never
    # added by hand; the TenantIsolatedCollection wrapper injects it.
    filt: Dict[str, Any] = {"id": asset_id, **_deployable_guard()}

    updated = await db.assets.find_one_and_update(
        filt, update, return_document=ReturnDocument.AFTER
    )

    if not updated:
        # The atomic operation above has already decided the outcome; this
        # follow-up read is purely to disambiguate the failure reason and does
        # not reintroduce a race. Never write a history entry on a refused checkout.
        existing = await db.assets.find_one({"id": asset_id})
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset is not in a deployable status.",
        )

    history_record: Dict[str, Any] = {
        "assetId": asset_id,
        "action": ACTION_CHECKOUT,
        "targetType": payload.targetType,
        "targetId": payload.targetId,
        "note": payload.note,
        "expectedReturnDate": payload.expectedReturnDate,
        "actorUsername": current_user.username,
        "ts": now,
    }
    try:
        history_id = await write_history(db, tenant_id, history_record)
    except Exception as exc:
        # A check-out that returns success while its trail write failed is exactly
        # the invisible hole this plan's second authored prohibition forbids.
        logger.error(
            "Failed to write assignment_history entry for asset %s: %s", asset_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Check-out succeeded but its history entry failed to write.",
        )

    # Synchronous helper — never awaited (cache_service.invalidate_cache is a
    # plain `def` returning None).
    invalidate_cache("assets:*")

    updated.pop("_id", None)
    response_history = {**history_record, "id": history_id}
    return {**updated, "history": response_history}
