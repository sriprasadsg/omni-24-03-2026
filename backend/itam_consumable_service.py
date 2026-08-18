"""ITAM Consumable service (Phase 60, ITAM-LIC-02).

Handles quantity-aware checkout and inventory management for consumables.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from pymongo import ReturnDocument

from database import get_database
from errors import APIError, NotFoundError
from itam_models import Consumable, ConsumableCreate, ConsumableUpdate, ConsumableCheckoutRequest, ConsumableCheckoutRecord
from itam_webhook_events import EVENT_CONSUMABLE_LOW_STOCK
from webhook_service import WebhookService

# Module-level singleton — mirrors itam_lifecycle_endpoints.py's own
# WebhookService() instance shape (never one-per-call).
_webhook_service = WebhookService()


class ConsumableNotFoundError(NotFoundError):
    def __init__(self, consumable_id: str):
        super().__init__(detail=f"Consumable not found: {consumable_id}")


async def get_consumable_service() -> "ConsumableService":
    return ConsumableService()


def _is_low_stock(available: Optional[int], threshold: Optional[int]) -> bool:
    """The exact rule itam_reporting_prebuilt.py's low_stock_consumables
    report applies: when a `reorderThreshold` is configured (including an
    explicit 0), low means `available` is at or below it; when none is
    configured, low means `available` is at or below the shared default.
    Never redefines the default number itself — imports it, so the event
    and the report can never drift apart.

    Import is deliberately deferred to call time, not module top level:
    itam_reporting_prebuilt imports from several itam_*_endpoints modules,
    and a top-level import here risks a circular import at app startup
    (confirmed clean via a real `import app` run, not by reasoning alone).
    """
    if available is None:
        return False
    from itam_reporting_prebuilt import DEFAULT_LOW_STOCK_QUANTITY
    effective_threshold = threshold if threshold is not None else DEFAULT_LOW_STOCK_QUANTITY
    return available <= effective_threshold


class ConsumableService:
    def __init__(self):
        self.db = get_database()

    def _tenant_id(self, current_user) -> str:
        return getattr(current_user, "tenant_id", "platform-admin")

    async def create_consumable(self, consumable_data: ConsumableCreate, current_user=None) -> Consumable:
        consumable_dict = consumable_data.model_dump(by_alias=True)
        consumable_dict["tenantId"] = self._tenant_id(current_user)
        consumable_dict["availableQuantity"] = consumable_data.initialQuantity
        consumable_dict["checkoutRecords"] = []

        try:
            result = await self.db.itam_consumables.insert_one(consumable_dict)
            new_consumable = await self.db.itam_consumables.find_one({"_id": result.inserted_id})
            if not new_consumable:
                raise APIError(status_code=500, detail="Failed to retrieve newly created consumable")
            return Consumable(**new_consumable)
        except Exception as e:
            raise APIError(status_code=500, detail=f"Failed to create consumable: {e}")

    async def get_consumables(self, skip: int = 0, limit: int = 100, current_user=None, is_super_admin=False) -> list[Consumable]:
        if is_super_admin:
            consumables = await self.db.itam_consumables.find({}) \
                .skip(skip).limit(limit).to_list(limit)
        else:
            consumables = await self.db.itam_consumables.find({"tenantId": self._tenant_id(current_user)}) \
                .skip(skip).limit(limit).to_list(limit)
        return [Consumable(**c) for c in consumables]

    async def get_consumable(self, consumable_id, current_user=None, is_super_admin=False) -> Optional[Consumable]:
        if is_super_admin:
            consumable = await self.db.itam_consumables.find_one({"_id": consumable_id})
        else:
            consumable = await self.db.itam_consumables.find_one({
                "_id": consumable_id,
                "tenantId": self._tenant_id(current_user)
            })
        if not consumable:
            return None
        return Consumable(**consumable)

    async def update_consumable(self, consumable_id, consumable_data: ConsumableUpdate, current_user=None) -> Optional[Consumable]:
        consumable_dict = consumable_data.model_dump(by_alias=True, exclude_unset=True)
        if "initial_quantity" in consumable_dict:
            raise APIError(status_code=400, detail="Cannot update initial_quantity directly. Adjust availableQuantity via checkout/checkin.")

        update_result = await self.db.itam_consumables.update_one(
            {"_id": consumable_id, "tenantId": self._tenant_id(current_user)},
            {"$set": consumable_dict}
        )
        if update_result.matched_count == 0:
            return None
        return await self.get_consumable(consumable_id, current_user)

    async def delete_consumable(self, consumable_id, current_user=None) -> bool:
        delete_result = await self.db.itam_consumables.delete_one({
            "_id": consumable_id,
            "tenantId": self._tenant_id(current_user)
        })
        return delete_result.deleted_count > 0

    async def checkout_consumable(self, consumable_id, request: ConsumableCheckoutRequest, current_user=None) -> Consumable:
        consumable = await self.db.itam_consumables.find_one_and_update(
            {
                "_id": consumable_id,
                "tenantId": self._tenant_id(current_user),
                "availableQuantity": {"$gte": request.quantity}
            },
            {
                "$inc": {"availableQuantity": -request.quantity},
                "$push": {
                    "checkoutRecords": {
                        "$each": [
                            ConsumableCheckoutRecord(
                                checkoutDate=datetime.now(timezone.utc),
                                quantity=request.quantity,
                                assignedTo=request.assignedTo,
                                assignedToType=request.assignedToType,
                                notes=request.notes
                            ).model_dump(by_alias=True)
                        ]
                    }
                }
            },
            return_document=ReturnDocument.AFTER
        )

        if not consumable:
            exists = await self.db.itam_consumables.find_one({
                "_id": consumable_id,
                "tenantId": self._tenant_id(current_user)
            })
            if exists:
                raise APIError(status_code=400, detail="Insufficient quantity available for checkout")
            else:
                raise APIError(status_code=404, detail="Consumable not found")

        # D-05/D-06: fire-and-forget webhook dispatch, evaluated against the
        # post-decrement document find_one_and_update just returned — never
        # awaited inline (RESEARCH Pitfall 8). This runs inside a request
        # handler where ambient tenant context is already established (no
        # set_tenant_id bracketing here; that applies only to the
        # background sweeps in plans 73-03/73-05).
        available = consumable.get("availableQuantity")
        threshold = consumable.get("reorderThreshold")
        if _is_low_stock(available, threshold):
            if threshold is not None:
                effective_threshold = threshold
            else:
                from itam_reporting_prebuilt import DEFAULT_LOW_STOCK_QUANTITY
                effective_threshold = DEFAULT_LOW_STOCK_QUANTITY
            webhook_payload = {
                "consumableId": str(consumable["_id"]),
                "name": consumable.get("name"),
                "availableQuantity": available,
                "reorderThreshold": effective_threshold,
            }
            asyncio.create_task(_webhook_service.trigger_webhook(EVENT_CONSUMABLE_LOW_STOCK, webhook_payload))

        return Consumable(**consumable)

    async def checkin_consumable(self, consumable_id, quantity: int, current_user=None) -> Consumable:
        if quantity <= 0:
            raise APIError(status_code=400, detail="Check-in quantity must be positive")

        consumable = await self.db.itam_consumables.find_one_and_update(
            {
                "_id": consumable_id,
                "tenantId": self._tenant_id(current_user)
            },
            {
                "$inc": {"availableQuantity": quantity},
                "$push": {
                    "checkoutRecords": {
                        "$each": [
                            ConsumableCheckoutRecord(
                                checkoutDate=datetime.now(timezone.utc),
                                quantity=-quantity,
                                assignedTo="system",
                                assignedToType="system",
                                notes=f"Check-in of {quantity} units"
                            ).model_dump(by_alias=True)
                        ]
                    }
                }
            },
            return_document=ReturnDocument.AFTER
        )

        if not consumable:
            raise APIError(status_code=404, detail="Consumable not found")

        return Consumable(**consumable)
