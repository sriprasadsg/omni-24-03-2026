"""Migration 022: a Super Admin ticks each Security and Compliance screen (spec C6).

Migrations 017-019 switched on every screen of the features a tenant already had, so tenants
saw every Security and Compliance screen although no Super Admin chose them. The user decided
(2026-10-15) that those two sidebar sections hold only what a Super Admin ticks: this removes
every Security/Compliance screen switch from every tenant. The tenant's feature switches
(Security Operations, Compliance Management, MDR ...) stay. Each tenant's removed list is kept in
tenant_switch_archive first (archive, not delete), so it can be put back.
"""
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

import tenant_features

DESCRIPTION = "Clear the auto-enabled Security and Compliance screens; a Super Admin ticks them"


async def up(db: AsyncIOMotorDatabase) -> None:
    explicit = {f"{tenant_features.SCREEN_PREFIX}{view}" for view in tenant_features.EXPLICIT_SCREENS}
    async for tenant in db.tenants.find({"enabledFeatures": {"$type": "array"}}, {"_id": 0, "id": 1, "enabledFeatures": 1}):
        removed = sorted(explicit.intersection(tenant["enabledFeatures"]))
        if not removed:
            continue
        await db.tenant_switch_archive.insert_one({
            "tenantId": tenant["id"], "migration": "022", "removed": removed,
            "archivedAt": datetime.now(timezone.utc).isoformat(),
        })
        await db.tenants.update_one({"id": tenant["id"]}, {"$pull": {"enabledFeatures": {"$in": removed}}})
