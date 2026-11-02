"""The partner seat pool (Phase 87, D-05): an atomic counter on the partner's own tenants document.

A partner organization stores ``partner.poolSize`` and ``partner.allocated`` (the seats handed out to
its customers; each customer's allotment is its ``license.maxAgents``). The invariant:
``partner.allocated`` is never below the true sum of the customers' allotments, and never above
``poolSize``. To keep it without a transaction (the local mongod is a standalone), an INCREASE claims
the pool first and only then writes the customer, and a DECREASE writes the customer first and only
then releases the pool. A crash between the two steps can therefore only leak seats (allocated too
high), never over-sell them; a reconcile pass repairs a leak.

Every query names the partner explicitly and runs on the raw collections (``tenants`` is exempt from
the tenant wrapper); nothing here switches the request to the platform tenant context.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class PartnerError(Exception):
    """A refusal the partner or the Super Admin sees verbatim: HTTP status, stable code, message."""

    def __init__(self, status: int, code: str, message: str, **numbers: Any) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.numbers: Dict[str, Any] = numbers


def _raw(db):
    return getattr(db, "_db", db)


async def claim(db, partner_id: str, n: int, *, require_active: bool = True) -> bool:
    """Atomically take ``n`` seats from the pool; False when the pool cannot fit them (or, with
    ``require_active``, when the partner is not an active partner)."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError("seat count must be a non-negative integer")
    if n == 0:
        return True
    query: Dict[str, Any] = {
        "id": partner_id,
        "type": "partner",
        "$expr": {"$lte": [{"$add": ["$partner.allocated", n]}, "$partner.poolSize"]},
    }
    if require_active:
        query["partner.status"] = "active"
    res = await _raw(db).tenants.update_one(query, {"$inc": {"partner.allocated": n}})
    return res.modified_count == 1


async def release(db, partner_id: str, n: int) -> None:
    """Give ``n`` seats back to the pool; the counter never goes below zero."""
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        return
    res = await _raw(db).tenants.update_one(
        {"id": partner_id, "type": "partner", "partner.allocated": {"$gte": n}},
        {"$inc": {"partner.allocated": -n}},
    )
    if res.modified_count == 0:
        logger.warning("partner %s: could not release %s seats (counter lower than that or no such partner)",
                       partner_id, n)


async def free_seats(db, partner_id: str) -> int:
    """Seats still free in the pool (0 for a missing partner)."""
    doc = await _raw(db).tenants.find_one({"id": partner_id, "type": "partner"}, {"_id": 0, "partner": 1})
    pool = (doc or {}).get("partner") or {}
    return max(int(pool.get("poolSize") or 0) - int(pool.get("allocated") or 0), 0)
