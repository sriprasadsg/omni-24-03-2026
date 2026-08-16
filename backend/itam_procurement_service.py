import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from database import TenantIsolatedDatabase
from itam_models import PurchaseOrder, PurchaseOrderCreate, PurchaseOrderUpdate

logger = logging.getLogger(__name__)

class ItamProcurementService:
    def __init__(self, db: TenantIsolatedDatabase):
        self.db = db

    async def create_purchase_order(self, tenant_id: str, po_data: PurchaseOrderCreate) -> PurchaseOrder:
        now = datetime.now(timezone.utc)
        doc = po_data.model_dump()
        doc.update({
            "id": f"po-{uuid.uuid4().hex[:8]}",
            "tenantId": tenant_id,
            "createdAt": now,
            "updatedAt": now,
        })
        # "id" is explicitly set above (not left to Mongo's auto _id) since
        # get/update/delete all query by {"id": ...}
        result = await self.db.purchase_orders.insert_one(doc)
        created_po = await self.db.purchase_orders.find_one({"_id": result.inserted_id})
        return PurchaseOrder.model_validate(created_po)

    async def get_purchase_order(self, tenant_id: str, po_id: str) -> Optional[PurchaseOrder]:
        doc = await self.db.purchase_orders.find_one({"id": po_id, "tenantId": tenant_id})
        if doc:
            return PurchaseOrder.model_validate(doc)
        return None

    async def list_purchase_orders(self, tenant_id: str, skip: int = 0, limit: int = 100) -> List[PurchaseOrder]:
        cursor = self.db.purchase_orders.find({"tenantId": tenant_id}).skip(skip).limit(limit)
        pos = await cursor.to_list(length=limit)
        return [PurchaseOrder.model_validate(po) for po in pos]

    async def update_purchase_order(self, tenant_id: str, po_id: str, po_data: PurchaseOrderUpdate) -> Optional[PurchaseOrder]:
        now = datetime.now(timezone.utc)
        update_data = po_data.model_dump(exclude_unset=True)
        update_data["updatedAt"] = now

        result = await self.db.purchase_orders.find_one_and_update(
            {"id": po_id, "tenantId": tenant_id},
            {"$set": update_data},
            return_document=True
        )
        if result:
            return PurchaseOrder.model_validate(result)
        return None

    async def delete_purchase_order(self, tenant_id: str, po_id: str) -> bool:
        result = await self.db.purchase_orders.delete_one({"id": po_id, "tenantId": tenant_id})
        return result.deleted_count == 1
