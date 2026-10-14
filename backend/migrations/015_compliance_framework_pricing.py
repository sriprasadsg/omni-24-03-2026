"""Migration 015: persisted service pricing with one price per compliance framework.

Seeds the global service_pricing collection from the built-in list (existing rows are
kept as they are), removes the generic compliance entries that per-framework prices
replace (they were never billed), and makes service ids unique. Framework prices need no
rows: a framework without one is priced at $5.00 until the Super Admin changes it.
Tenants get no purchasedFrameworks field, which means no frameworks until one is ticked.
"""
from motor.motor_asyncio import AsyncIOMotorDatabase

import compliance_purchases

DESCRIPTION = "Persisted service pricing; per-framework compliance prices replace the generic entries"


async def up(db: AsyncIOMotorDatabase) -> None:
    from finops_service import finops_service

    await db.service_pricing.delete_many({"id": {"$in": sorted(compliance_purchases.LEGACY_PRICE_IDS)}})
    # Older installs could hold duplicate ids (see remove_pricing_duplicates.py): keep the
    # first row of each id so the unique index can be built.
    async for group in db.service_pricing.aggregate([
            {"$group": {"_id": "$id", "rows": {"$push": "$_id"}, "n": {"$sum": 1}}}, {"$match": {"n": {"$gt": 1}}}]):
        await db.service_pricing.delete_many({"_id": {"$in": group["rows"][1:]}})
    await finops_service._ensure_seeded(db)
    await db.service_pricing.create_index("id", unique=True, name="id_unique")
