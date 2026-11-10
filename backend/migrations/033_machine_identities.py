"""Migration 033: one agent id per machine, for life (machine_identity).

Creates the unique (tenantId, hardwareKey) index on ``machine_identities`` and records
each machine's current agent id, so a machine enrolled today keeps that id when it next
enrolls (after a reinstall, a rename or its agent being deleted). Only agents with a
hardware seat key (serial, SMBIOS UUID or physical MAC) are recorded; Replaced, Pending
and Rejected agents are skipped, and of two agents on one machine the one seen last wins.
Nothing is deleted, and a second run changes nothing.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Machine identities (one agent id per machine). Index + backfill from current agents."

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    import machine_identity

    await machine_identity.ensure_indexes(db)
    agents = db.agents.find(
        {"seatKey": {"$regex": "^(serial|uuid|mac):"}, "status": {"$nin": ["Replaced", "Pending", "Rejected"]}},
        {"_id": 0, "id": 1, "tenantId": 1, "seatKey": 1, "hostname": 1, "lastSeen": 1},
    ).sort("lastSeen", -1)
    recorded = 0
    async for agent in agents:
        if not agent.get("tenantId") or not agent.get("id"):
            continue
        res = await db[machine_identity.COLLECTION].update_one(
            {"tenantId": agent["tenantId"], "hardwareKey": agent["seatKey"]},
            {"$setOnInsert": {"agentId": agent["id"], "hostname": agent.get("hostname"),
                              "createdAt": agent.get("lastSeen"), "updatedAt": agent.get("lastSeen")}},
            upsert=True,
        )
        recorded += 1 if res.upserted_id else 0
    logger.info("migration 033: %d machine identities recorded", recorded)
