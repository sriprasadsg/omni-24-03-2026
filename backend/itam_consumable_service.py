
"""ITAM Consumable service (Phase 60, ITAM-LIC-02).

Handles quantity-aware checkout and inventory management for consumables.
"""

from datetime import datetime
from typing import Optional
import motor.motor_asyncio
from bson import ObjectId
from pydantic import ValidationError

from backend.database import get_database, get_tenant_db
from backend.errors import APIError
from backend.models.shared import InjectedDependencies, PyObjectId
from backend.itam_models import Consumable, ConsumableCreate, ConsumableUpdate, ConsumableCheckoutRequest, ConsumableCheckoutRecord, Asset

async def get_consumable_service(
    deps: InjectedDependencies
) -> "ConsumableService":
    return ConsumableService(deps)

class ConsumableService:
    def __init__(self, deps: InjectedDependencies):
        self.db: motor.motor_asyncio.AsyncIOMotorDatabase = deps.db
        self.tenant_id = deps.tenant_id

    async def create_consumable(self, consumable_data: ConsumableCreate) -> Consumable:
        consumable_dict = consumable_data.model_dump(by_alias=True)
        consumable_dict["tenantId"] = self.tenant_id
        consumable_dict["availableQuantity"] = consumable_data.initial_quantity
        consumable_dict["checkoutRecords"] = []

        try:
            result = await self.db.itam_consumables.insert_one(consumable_dict)
            new_consumable = await self.db.itam_consumables.find_one({"_id": result.inserted_id})
            if not new_consumable:
                raise APIError(status_code=500, detail="Failed to retrieve newly created consumable")
            return Consumable(**new_consumable)
        except ValidationError as e:
            raise APIError(status_code=400, detail=f"Validation error: {e.errors()}")
        except Exception as e:
            raise APIError(status_code=500, detail=f"Failed to create consumable: {e}")

    async def get_consumables(self, skip: int = 0, limit: int = 100) -> list[Consumable]:
        consumables = await self.db.itam_consumables.find({"tenantId": self.tenant_id}) \
                                                    .skip(skip).limit(limit).to_list(100)
        return [Consumable(**c) for c in consumables]

    async def get_consumable(self, consumable_id: PyObjectId) -> Optional[Consumable]:
        consumable = await self.db.itam_consumables.find_one({
            "_id": consumable_id,
            "tenantId": self.tenant_id
        })
        if not consumable:
            return None
        return Consumable(**consumable)

    async def update_consumable(
        self, consumable_id: PyObjectId, consumable_data: ConsumableUpdate
    ) -> Optional[Consumable]:
        consumable_dict = consumable_data.model_dump(by_alias=True, exclude_unset=True)
        if "initial_quantity" in consumable_dict:
            raise APIError(status_code=400, detail="Cannot update initial_quantity directly. Adjust availableQuantity via checkout/checkin.")

        update_result = await self.db.itam_consumables.update_one(
            {"_id": consumable_id, "tenantId": self.tenant_id},
            {"$set": consumable_dict}
        )
        if update_result.matched_count == 0:
            return None
        return await self.get_consumable(consumable_id)

    async def delete_consumable(self, consumable_id: PyObjectId) -> bool:
        delete_result = await self.db.itam_consumables.delete_one({
            "_id": consumable_id,
            "tenantId": self.tenant_id
        })
        return delete_result.deleted_count > 0

    async def checkout_consumable(self, consumable_id: PyObjectId, request: ConsumableCheckoutRequest) -> Consumable:
        async with await self.db.client.start_session() as session:
            async with session.start_transaction():
                consumable = await self.db.itam_consumables.find_one_and_update(
                    {
                        "_id": consumable_id,
                        "tenantId": self.tenant_id,
                        "availableQuantity": {"$gte": request.quantity}
                    },
                    {
                        "$inc": {"availableQuantity": -request.quantity},
                        "$push": {
                            "checkoutRecords": {
                                "$each": [
                                    ConsumableCheckoutRecord(
                                        checkoutDate=datetime.now(),
                                        quantity=request.quantity,
                                        assignedTo=request.assignedTo,
                                        assignedToType=request.assignedToType,
                                        notes=request.notes
                                    ).model_dump(by_alias=True)
                                ]
                            }
                        }
                    },
                    return_document=motor.motor_asyncio.ReturnDocument.AFTER,
                    session=session
                )

                if not consumable:
                    # Check if consumable exists but quantity is insufficient
                    exists = await self.db.itam_consumables.find_one({
                        "_id": consumable_id,
                        "tenantId": self.tenant_id
                    }, session=session)
                    if exists:
                        raise APIError(status_code=400, detail="Insufficient quantity available for checkout")
                    else:
                        raise APIError(status_code=404, detail="Consumable not found")

                return Consumable(**consumable)

    async def checkin_consumable(self, consumable_id: PyObjectId, quantity: int) -> Consumable:
        if quantity <= 0:
            raise APIError(status_code=400, detail="Check-in quantity must be positive")

        consumable = await self.db.itam_consumables.find_one_and_update(
            {
                "_id": consumable_id,
                "tenantId": self.tenant_id
            },
            {
                "$inc": {"availableQuantity": quantity},
                "$push": {
                    "checkoutRecords": {
                        "$each": [
                            ConsumableCheckoutRecord(
                                checkoutDate=datetime.now(),
                                quantity=-quantity, # Negative quantity for check-in
                                assignedTo="system", # Or a more specific user if available
                                assignedToType="system",
                                notes=f"Check-in of {quantity} units"
                            ).model_dump(by_alias=True)
                        ]
                    }
                }
            },
            return_document=motor.motor_asyncio.ReturnDocument.AFTER
        )

        if not consumable:
            raise APIError(status_code=404, detail="Consumable not found")

        return Consumable(**consumable)
