"""Migration 026: on-call outbox and test request indexes (phase 82, plan 82-07).

``oncall_outbox`` holds the messages the watchdog pages (unique ``id``, a TTL index on ``expiresAt``
with ``expireAfterSeconds: 0`` so undelivered messages vanish after 24 hours, and ``deliveredAt``
for the pending query). ``oncall_test_requests`` holds the Super Admin's test alert requests
(unique ``id``, ``requestedAt``, and a partial unique index so only one request is pending at a
time). Both collections are created by the first insert; running this twice changes nothing.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "On-call: outbox (with expiry) and test-alert request indexes"

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    from autonomous_ops import oncall

    await oncall.ensure_indexes(db)
    logger.info("migration 026: oncall_outbox and oncall_test_requests indexes ensured")
