"""ITAM Consumable service (Phase 60, ITAM-LIC-02).

Handles quantity-aware checkout and inventory management for consumables.
"""

from datetime import datetime, timezone
from typing import Optional

from pymongo import ReturnDocument

from database import get_database
from errors import APIError, NotFoundError
from itam_models import Consumable, ConsumableCreate, ConsumableUpdate, ConsumableCheckoutRequest, ConsumableCheckoutRecord


class ConsumableNotFoundError(NotFoundError):
    def __init__(self, consumable_id: str):
        super().__init__(detail=f"Consumable not found: {consumable_id}")


async def get_consumable_service() -> "ConsumableService":
    return ConsumableService()


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
