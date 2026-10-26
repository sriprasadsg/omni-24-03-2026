"""Migration 024: Autonomous Ops settings and indexes (phase 81).

Every tenant with an id gets an explicit stored autonomy level (Undoable-auto, shadow on, no
stop); the Platform tenant is stored Off. ``settings.ensure_tenant`` is a $setOnInsert upsert,
so a tenant that already holds a level keeps it and a second run changes nothing. The decision
ledger, settings and never-touch indexes come from the modules that own them, and the stamp
indexes serve the per-tenant lookups on instructions and response tasks written by the gate.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Autonomous Ops: explicit autonomy level for every tenant, ledger and stamp indexes"

logger = logging.getLogger(__name__)

_STAMPED = ("agent_instructions", "response_tasks")


async def up(db: AsyncIOMotorDatabase) -> None:
    from autonomous_ops import ledger, protected, settings

    count = 0
    async for tenant in db.tenants.find({}, {"_id": 0, "id": 1}):
        tenant_id = tenant.get("id")
        if not tenant_id:
            continue
        await settings.ensure_tenant(db, tenant_id)
        count += 1

    await settings.ensure_indexes(db)
    await ledger.ensure_indexes(db)
    await protected.ensure_indexes(db)
    for name in _STAMPED:
        await db[name].create_index(
            [("autonomy.tenantId", 1), ("status", 1)], name="autonomy_stamp",
            partialFilterExpression={"autonomy.actionId": {"$exists": True}})
    logger.info("migration 024: autonomy settings ensured for %d tenants", count)
