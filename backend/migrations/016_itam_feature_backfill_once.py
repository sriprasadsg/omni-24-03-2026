"""Migration 016: give tenants created before ITAM the ITAM features, once.

This used to run on every startup, which re-enabled ITAM for any tenant a Super Admin
had switched it off for (ITAM is a per-tenant feature switch since spec C6).
"""
from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "One-time ITAM feature backfill for tenants created before ITAM"


async def up(db: AsyncIOMotorDatabase) -> None:
    await db.tenants.update_many(
        {"id": {"$ne": "platform-admin"}, "enabledFeatures": {"$type": "array", "$nin": ["manage:itam"]}},
        {"$addToSet": {"enabledFeatures": {"$each": ["view:itam", "manage:itam"]}}},
    )
