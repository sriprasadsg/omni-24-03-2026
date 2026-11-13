"""Migration 035: activity reporting indexes (phase 86, ACTV-04, ACTV-05, ACTV-06, GATE-11).

Indexes only, nothing is backfilled and nothing is deleted. Two modules make them all:
* ``autonomous_ops.reporting.digest.ensure_indexes``: the unique ``digest_once_per_day`` (tenantId, day) on
  ``autonomy_digests``, which is the once-per-day guard (a restart, a retry or a second worker cannot send a second
  digest), and ``tenant_finished`` (tenantId, finishedAt -1) on ``autonomy_actions``, which serves the digest window
  queries;
* ``autonomous_ops.reporting.golive.ensure_indexes``: ``check_recorded`` (checkId, recordedAt -1), the latest record
  per go-live check, and the unique ``id_unique`` on ``autonomy_golive_checks``.

No existing document needs a new field. ``create_index`` with an unchanged definition is a no-op, so a second run
changes nothing. The digest loop and the go-live module make the same indexes themselves, so this migration is the
first, not the only, place they are created. It depends on nothing migration 034 creates.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Activity reporting indexes (Phase 86). Indexes only, nothing is backfilled."

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    from autonomous_ops.reporting import digest, golive

    await digest.ensure_indexes(db)
    await golive.ensure_indexes(db)
    logger.info("migration 035: activity reporting indexes ensured")
