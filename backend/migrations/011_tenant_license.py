"""Migration 011: agent seat license sub-document on every tenant (spec C2).

license.maxAgents comes from the legacy top-level maxAgents (default 5);
license.seatsUsed is counted from the tenant's seat-holding agents. Tenants that
already carry license.seatsUsed are left alone, so re-running is a no-op.
"""
from motor.motor_asyncio import AsyncIOMotorDatabase

import licensing

DESCRIPTION = "Add license {maxAgents, seatsUsed, inactiveReclaimDays} to tenants"


async def up(db: AsyncIOMotorDatabase) -> None:
    async for tenant in db.tenants.find({"license.seatsUsed": {"$exists": False}}, {"_id": 0, "id": 1, "maxAgents": 1}):
        tenant_id = tenant.get("id")
        if not tenant_id:
            continue
        max_agents = tenant.get("maxAgents") if isinstance(tenant.get("maxAgents"), int) else licensing.DEFAULT_MAX_AGENTS
        used = await db.agents.count_documents(licensing.seat_holding_filter(tenant_id))
        await db.tenants.update_one(
            {"id": tenant_id, "license.seatsUsed": {"$exists": False}},
            {"$set": {"license.maxAgents": max_agents, "license.seatsUsed": used,
                      "license.inactiveReclaimDays": licensing.DEFAULT_RECLAIM_DAYS}},
        )
