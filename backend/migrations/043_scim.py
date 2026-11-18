"""Migration 043: indexes for SCIM provisioning (scim_tokens, scim_groups).

Both collections are new and start empty; nothing existing is read or changed, so a second run changes nothing.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Indexes for SCIM tokens and groups. Nothing existing changed."

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    import scim_service

    await scim_service.ensure_indexes(db)
    logger.info("migration 043: SCIM token and group indexes in place")
