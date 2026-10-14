"""Migration 018: per-screen switches for the System Settings screens (spec C6).

Same as migration 017, for the screens that share manage:settings: every tenant keeps every
settings screen it can reach today; the Super Admin then switches screens off per tenant.
"""
from motor.motor_asyncio import AsyncIOMotorDatabase

import tenant_features

DESCRIPTION = "Switch on every System Settings screen a tenant's features already include"


async def up(db: AsyncIOMotorDatabase) -> None:
    async for tenant in db.tenants.find({"enabledFeatures": {"$type": "array"}}, {"_id": 0, "id": 1, "enabledFeatures": 1}):
        screens = tenant_features.with_all_screens(tenant["enabledFeatures"])[len(tenant["enabledFeatures"]):]
        if screens:
            await db.tenants.update_one({"id": tenant["id"]}, {"$addToSet": {"enabledFeatures": {"$each": screens}}})
