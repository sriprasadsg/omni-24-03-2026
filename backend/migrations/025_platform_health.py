"""Migration 025: platform health indexes (phase 82).

The watchdog's heartbeat and latest status snapshot live in two singleton documents of the
``platform_health`` collection (fixed ``_id`` values, created by an upsert on the first sync), so
the only schema work is the index the dead-man check reads. Watchdog events are rows of the
existing ``autonomy_actions`` ledger (kind ``platform_health``), already covered by the ledger
indexes from migration 024 (unique ``id`` makes a re-sent event idempotent). Running this twice
changes nothing.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Platform health: indexes for the watchdog heartbeat and status snapshot collection"

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    from autonomous_ops import selfheal

    await selfheal.ensure_indexes(db)
    logger.info("migration 025: platform_health indexes ensured")
