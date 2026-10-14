"""Migration 013: enrollment controls (spec C4).

Each tenant's registrationKey becomes a "Legacy key" install key with no use limit,
so installers already in the field keep enrolling until a platform user revokes it.
Tenants that already have that row are skipped, so re-running is a no-op. Also the
indexes: install keys by hash (unique) and tenant; allowlist values unique per tenant.
"""
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

import enrollment_keys

DESCRIPTION = "Install keys (Legacy key per tenant) and allowlist indexes"


async def up(db: AsyncIOMotorDatabase) -> None:
    await db.enrollment_keys.create_index("keyHash", unique=True, name="key_hash_unique")
    await db.enrollment_keys.create_index([("tenantId", 1), ("createdAt", -1)], name="tenant_created")
    for field in ("serialNumber", "smbiosUuid", "macAddress"):
        await db.agent_allowlist.create_index(
            [("tenantId", 1), (field, 1)], unique=True, name=f"tenant_{field}_unique",
            partialFilterExpression={field: {"$type": "string"}})
    await db.agent_allowlist.create_index([("tenantId", 1), ("addedAt", -1)], name="tenant_added")

    now = datetime.now(timezone.utc).isoformat()
    async for tenant in db.tenants.find({"registrationKey": {"$type": "string", "$ne": ""}},
                                        {"_id": 0, "id": 1, "registrationKey": 1}):
        key = tenant["registrationKey"]
        await db.enrollment_keys.update_one(
            {"keyHash": enrollment_keys.hash_key(key)},
            {"$setOnInsert": {
                "id": f"ek-{uuid.uuid4().hex[:16]}", "tenantId": tenant["id"], "name": enrollment_keys.LEGACY_KEY_NAME,
                "prefix": key[:8], "legacy": True, "maxUses": None, "uses": 0, "expiresAt": None,
                "defaultGroupId": None, "revokedAt": None, "createdBy": "migration", "createdAt": now}},
            upsert=True)
