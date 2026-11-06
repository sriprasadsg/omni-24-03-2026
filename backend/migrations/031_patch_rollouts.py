"""Migration 031: staged patch rollouts (phase 84, PTCH-07).

Indexes only, nothing is backfilled and nothing is deleted:
* ``patch_rollout_hosts``: the unique partial index ``one_active_rollout_per_host`` on (tenantId, agentId)
  where ``active`` is true, so one computer can be in only one active rollout, plus the lookup by
  (tenantId, rolloutId, ring).
* ``patch_rollouts``: the lookup by (tenantId, status) and the unique ``id``.

``create_index`` with an unchanged definition is a no-op, so a second run changes nothing. The rollout
controller makes the claim index again before every pass when it is missing, so this migration is the
first, not the only, place it is created.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Patch rollouts: one active rollout per host, rollout and host lookups"

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    from autonomous_ops.rollout import store

    await store.ensure_indexes(db)
    logger.info("migration 031: patch rollout indexes ensured")
