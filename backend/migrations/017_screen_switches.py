"""Migration 017: per-screen switches for the Security and Compliance screens (spec C6).

Every tenant keeps every screen of the features it already has (Security Operations,
Compliance Management), so no one loses a screen on deploy; the Super Admin then
switches individual screens off in Manage Tenant.
"""
from motor.motor_asyncio import AsyncIOMotorDatabase

import tenant_features

DESCRIPTION = "Switch on every Security/Compliance screen a tenant's features already include"


async def up(db: AsyncIOMotorDatabase) -> None:
    async for tenant in db.tenants.find({"enabledFeatures": {"$type": "array"}}, {"_id": 0, "id": 1, "enabledFeatures": 1}):
        screens = tenant_features.with_all_screens(tenant["enabledFeatures"])[len(tenant["enabledFeatures"]):]
        if screens:
            await db.tenants.update_one({"id": tenant["id"]}, {"$addToSet": {"enabledFeatures": {"$each": screens}}})
