"""How a rollout moves on and ends: pass a ring, complete the rollout (PTCH-01).

``advance`` marks the current ring passed and moves to the next; past the last ring it completes the
rollout. ``complete`` sets the status and releases every computer's claim so another rollout may take
them. Plan 84-03 adds halting and closing here.

Raw Mongo handle with an explicit tenantId only.
"""
from datetime import datetime
from typing import Any, Dict

from . import store


async def complete(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> None:
    """The rollout is finished: status completed, claims released."""
    await store.set_rollout(db, tenant_id, rollout, {"status": "completed", "completedAt": now})
    await store.release(db, tenant_id, rollout["id"])


async def advance(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> None:
    """The current ring passed: record it and move to the next ring, or complete the rollout after the last."""
    index = int(rollout.get("currentRing") or 0)
    await store.set_ring(db, tenant_id, rollout, index, {"state": "passed", "passedAt": now})
    if index + 1 >= len(rollout["rings"]):
        await complete(db, tenant_id, rollout, now)
        return
    await store.set_rollout(db, tenant_id, rollout, {"currentRing": index + 1})
