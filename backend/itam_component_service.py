"""ITAM Component service (Phase 60, ITAM-LIC-03).

Handles catalog of installable components (CPU, RAM, GPU, ...) and their
attach/detach to parent assets.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from database import get_database
from errors import APIError, NotFoundError
from itam_models import Component, ComponentCreate, ComponentUpdate


class ComponentNotFoundError(NotFoundError):
    def __init__(self, component_id: str):
        super().__init__(detail=f"Component not found: {component_id}")


class AssetNotFoundError(NotFoundError):
    def __init__(self, asset_id: str):
        super().__init__(detail=f"Asset not found: {asset_id}")


class ComponentNotAttachedError(APIError):
    def __init__(self, component_id: str, asset_id: str):
        super().__init__(status_code=400, detail=f"Component {component_id} is not attached to asset {asset_id}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


async def get_component_service() -> "ComponentService":
    return ComponentService()


class ComponentService:
    def __init__(self):
        self.db = get_database()

    def _tenant_id(self, current_user) -> str:
        return getattr(current_user, "tenant_id", "platform-admin")

    async def create_component(self, data: ComponentCreate, current_user=None) -> Component:
        tenant_id = self._tenant_id(current_user)
        component_id = f"comp-{ObjectId()}"[:20]
        now = _now_iso()
        doc = data.model_dump(by_alias=True, exclude_none=True)
        doc.update({
            "id": component_id,
            "tenantId": tenant_id,
            "createdAt": now,
            "updatedAt": now,
        })
        await self.db.components.insert_one(doc)
        doc.pop("_id", None)
        return Component(**doc)

    async def get_components(self, skip: int = 0, limit: int = 100, current_user=None, is_super_admin: bool = False) -> List[Component]:
        if is_super_admin:
            cursor = self.db.components.find({})
        else:
            tenant_id = self._tenant_id(current_user)
            cursor = self.db.components.find({"tenantId": tenant_id})
        docs = await cursor.skip(skip).limit(limit).to_list(length=limit)
        for d in docs:
            d.pop("_id", None)
        return [Component(**d) for d in docs]

    async def get_component(self, component_id: str, current_user=None, is_super_admin: bool = False) -> Optional[Component]:
        flt = {"id": component_id}
        if not is_super_admin:
            flt["tenantId"] = self._tenant_id(current_user)
        doc = await self.db.components.find_one(flt)
        if not doc:
            return None
        doc.pop("_id", None)
        return Component(**doc)

    async def update_component(self, component_id: str, data: ComponentUpdate, current_user=None) -> Optional[Component]:
        tenant_id = self._tenant_id(current_user)
        update = data.model_dump(by_alias=True, exclude_none=True, exclude_unset=True)
        update["updatedAt"] = _now_iso()
        doc = await self.db.components.find_one_and_update(
            {"id": component_id, "tenantId": tenant_id},
            {"$set": update},
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            return None
        doc.pop("_id", None)
        return Component(**doc)

    async def delete_component(self, component_id: str, current_user=None) -> bool:
        result = await self.db.components.delete_one({
            "id": component_id,
            "tenantId": self._tenant_id(current_user),
        })
        return result.deleted_count > 0

    async def attach_component(self, component_id: str, asset_id: str, current_user=None) -> Component:
        tenant_id = self._tenant_id(current_user)
        component = await self.db.components.find_one({"id": component_id, "tenantId": tenant_id})
        if not component:
            raise ComponentNotFoundError(component_id)
        asset = await self.db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
        if not asset:
            raise AssetNotFoundError(asset_id)

        now = _now_iso()
        await self.db.assets.update_one(
            {"id": asset_id, "tenantId": tenant_id},
            {"$addToSet": {"components": component_id}, "$set": {"updatedAt": now}},
        )
        updated = await self.db.components.find_one_and_update(
            {"id": component_id, "tenantId": tenant_id},
            {"$set": {"parentAssetId": asset_id, "updatedAt": now}},
            return_document=ReturnDocument.AFTER,
        )
        updated.pop("_id", None)
        return Component(**updated)

    async def detach_component(self, component_id: str, asset_id: str, current_user=None) -> Component:
        tenant_id = self._tenant_id(current_user)
        component = await self.db.components.find_one({"id": component_id, "tenantId": tenant_id})
        if not component:
            raise ComponentNotFoundError(component_id)
        if component.get("parentAssetId") != asset_id:
            raise ComponentNotAttachedError(component_id, asset_id)

        now = _now_iso()
        await self.db.assets.update_one(
            {"id": asset_id, "tenantId": tenant_id},
            {"$pull": {"components": component_id}, "$set": {"updatedAt": now}},
        )
        updated = await self.db.components.find_one_and_update(
            {"id": component_id, "tenantId": tenant_id},
            {"$unset": {"parentAssetId": ""}, "$set": {"updatedAt": now}},
            return_document=ReturnDocument.AFTER,
        )
        updated.pop("_id", None)
        return Component(**updated)
