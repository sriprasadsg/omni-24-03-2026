"""Migration 012: indexes for Pending enrollment (spec C3).

agent_denylist holds one row per rejected machine (seat key) per tenant; the unique
index makes a repeated reject a no-op. agent_pending_alert_windows keeps one alert
window per tenant; the unique index lets concurrent first arrivals upsert safely.
(agents already has a (tenantId, status) index from migration 001.)
"""
from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Indexes for agent_denylist and agent_pending_alert_windows"


async def up(db: AsyncIOMotorDatabase) -> None:
    await db.agent_denylist.create_index([("tenantId", 1), ("seatKey", 1)], unique=True,
                                         name="tenant_seatkey_unique")
    await db.agent_pending_alert_windows.create_index("tenantId", unique=True, name="tenant_unique")
