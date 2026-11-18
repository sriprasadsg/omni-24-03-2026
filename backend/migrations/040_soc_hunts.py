"""Migration 040: indexes for saved hunts (soc_hunts) and for hunting agent logs by tenant and time (logs).

soc_hunts is new and starts empty. logs only gains an index (it had _id alone); no row is read or changed, so a
second run changes nothing.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Indexes for saved hunts and agent-log hunting. Nothing existing changed."

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    import soc_hunt

    await soc_hunt.ensure_indexes(db)
    logger.info("migration 040: saved hunt and agent-log indexes in place")
