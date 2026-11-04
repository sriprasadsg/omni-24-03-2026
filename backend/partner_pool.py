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
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import license_rules
import licensing

logger = logging.getLogger(__name__)

# A claim takes pool seats a moment before the customer document that uses them is written, so a
# reconcile that sees a drift looks again after this pause and only repairs one that is still there.
RECONCILE_SETTLE_SECONDS = 1.0


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
    query: Dict[str, Any] = {"id": partner_id, "type": "partner"}
    if require_active:
        query["partner.status"] = "active"
    if n == 0:  # nothing to take, but the partner must still be one that may take a customer (WR-05)
        return await _raw(db).tenants.count_documents(query, limit=1) == 1
    query["$expr"] = {"$lte": [{"$add": ["$partner.allocated", n]}, "$partner.poolSize"]}
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
        await reconcile_partner(db, partner_id)


async def free_seats(db, partner_id: str) -> int:
    """Seats still free in the pool (0 for a missing partner)."""
    doc = await _raw(db).tenants.find_one({"id": partner_id, "type": "partner"}, {"_id": 0, "partner": 1})
    pool = (doc or {}).get("partner") or {}
    return max(int(pool.get("poolSize") or 0) - int(pool.get("allocated") or 0), 0)


def pool_expired(partner_doc: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """True only when the pool's expiry is at or before ``now`` (parsed datetimes, never a string compare)."""
    expires_at = ((partner_doc or {}).get("partner") or {}).get("expiresAt")
    return license_rules.expired({"expiresAt": expires_at if isinstance(expires_at, str) else None}, now)


def _not_found() -> PartnerError:
    return PartnerError(404, "not_found", "Customer not found")


def _seats_filter(doc: Dict[str, Any], seats: int) -> Dict[str, Any]:
    """The compare-and-set condition on the customer's seat count (a legacy document has only the old field)."""
    if isinstance((doc.get("license") or {}).get("maxAgents"), int):
        return {"license.maxAgents": seats}
    return {"license.maxAgents": {"$exists": False}}


async def _claim_refusal(db, partner_id: str, require_active: bool = True) -> PartnerError:
    """Why a claim that was refused was refused: a suspended partner (only when the claim demanded an
    active one), or a pool without room."""
    doc = await _raw(db).tenants.find_one({"id": partner_id, "type": "partner"}, {"_id": 0, "partner": 1, "name": 1})
    if doc is None:
        return PartnerError(404, "not_found", "Partner not found")
    if require_active and (doc.get("partner") or {}).get("status") != "active":
        return PartnerError(409, "partner_suspended", "This partner account is suspended.")
    free = await free_seats(db, partner_id)
    return PartnerError(409, "pool_full", f"Only {free} seats are free in your pool.", free=free)


async def change_allotment(db, customer_id: str, new_seats: int, *, partner_id: str,
                           enforce_used_floor: bool, require_active: bool) -> Dict[str, int]:
    """Set a partner customer's seat count. A raise claims the pool first, a lowering writes the
    customer first; the customer write is a compare-and-set on its current count, and a lowering with
    ``enforce_used_floor`` also refuses, inside the same update, to go below ``license.seatsUsed`` (D-06)."""
    if (not isinstance(new_seats, int) or isinstance(new_seats, bool)
            or not 0 <= new_seats <= licensing.MAX_AGENTS_CEILING):
        raise PartnerError(422, "invalid_seats", f"Seats must be between 0 and {licensing.MAX_AGENTS_CEILING}.")
    tenants = _raw(db).tenants
    key = {"id": customer_id, "partnerId": partner_id}
    doc = await tenants.find_one(key, {"_id": 0})
    if doc is None:
        raise _not_found()
    current = licensing.license_of(doc)["maxAgents"]
    if new_seats == current:
        return {"before": current, "after": current}
    cas = {**key, **_seats_filter(doc, current)}
    changes = {"$set": {"license.maxAgents": new_seats, "maxAgents": new_seats}}
    if new_seats > current:
        delta = new_seats - current
        if not await claim(db, partner_id, delta, require_active=require_active):
            raise await _claim_refusal(db, partner_id, require_active)
        if (await tenants.update_one(cas, changes)).modified_count != 1:
            await release(db, partner_id, delta)
            raise PartnerError(409, "changed", "The seats changed while you were saving. Try again.")
        return {"before": current, "after": new_seats}
    if enforce_used_floor:
        cas["$expr"] = {"$gte": [new_seats, {"$ifNull": ["$license.seatsUsed", 0]}]}
    if (await tenants.update_one(cas, changes)).modified_count != 1:
        fresh = await tenants.find_one(key, {"_id": 0, "license.seatsUsed": 1, "name": 1}) or {}
        used = (fresh.get("license") or {}).get("seatsUsed") or 0
        if enforce_used_floor and used > new_seats:
            raise PartnerError(409, "below_used", f"{doc.get('name') or 'This customer'} uses {used} seats now. "
                               "You can't set fewer.", used=used)
        raise PartnerError(409, "changed", "The seats changed while you were saving. Try again.")
    await release(db, partner_id, current - new_seats)
    return {"before": current, "after": new_seats}


async def set_pool_size(db, partner_id: str, new_size: int) -> None:
    """Resize a pool; never below the seats already handed out (D-07). One conditional update."""
    if (not isinstance(new_size, int) or isinstance(new_size, bool)
            or not 1 <= new_size <= licensing.MAX_AGENTS_CEILING):
        raise PartnerError(422, "invalid_seats", f"The pool must be between 1 and {licensing.MAX_AGENTS_CEILING} seats.")
    tenants = _raw(db).tenants
    res = await tenants.update_one({"id": partner_id, "type": "partner", "partner.allocated": {"$lte": new_size}},
                                   {"$set": {"partner.poolSize": new_size}})
    if res.matched_count == 1:
        return
    doc = await tenants.find_one({"id": partner_id, "type": "partner"}, {"_id": 0, "partner.allocated": 1})
    if doc is None:
        raise PartnerError(404, "not_found", "Partner not found")
    handed_out = int((doc.get("partner") or {}).get("allocated") or 0)
    raise PartnerError(409, "pool_below_handed_out", f"The pool can't be smaller than the {handed_out} seats already "
                       "handed out. Ask the partner to take seats back first.", handedOut=handed_out)


async def move_customer(db, customer_id: str, target_partner_id: Optional[str]) -> Dict[str, Any]:
    """Move a customer into another partner's pool, or (target None) out to direct. The target's pool
    is claimed first (D-18), the customer is switched with a compare-and-set, then the old pool is released.
    The customer's screens, agents and license are never touched (D-19)."""
    tenants = _raw(db).tenants
    doc = None
    if customer_id != "platform-admin":
        doc = await tenants.find_one({"id": customer_id, "type": {"$ne": "partner"}}, {"_id": 0})
    if doc is None:
        raise _not_found()
    old = doc.get("partnerId") or None
    seats = licensing.license_of(doc)["maxAgents"]
    if old == target_partner_id:
        raise PartnerError(409, "same_partner", "This customer already belongs there.")
    target = None
    if target_partner_id is not None:
        target = await tenants.find_one({"id": target_partner_id, "type": "partner"}, {"_id": 0, "name": 1})
        if target is None:
            raise PartnerError(404, "not_found", "Partner not found")
        if not await claim(db, target_partner_id, seats, require_active=True):
            refusal = await _claim_refusal(db, target_partner_id)
            if refusal.code != "pool_full":
                raise refusal
            free = refusal.numbers["free"]
            raise PartnerError(409, "move_does_not_fit", f"{target.get('name')} has {free} seats free and "
                               f"{doc.get('name')} needs {seats}. Increase {target.get('name')}'s pool first.",
                               free=free, needed=seats)
    cas = {"id": customer_id, "type": {"$ne": "partner"}, **_seats_filter(doc, seats),
           "partnerId": old if old else {"$exists": False}}
    update = {"$set": {"partnerId": target_partner_id}} if target_partner_id else {"$unset": {"partnerId": ""}}
    if (await tenants.update_one(cas, update)).modified_count != 1:
        if target_partner_id:
            await release(db, target_partner_id, seats)
        raise PartnerError(409, "changed", "The customer changed while you were saving. Try again.")
    if old:
        await release(db, old, seats)
    return {"from": old, "to": target_partner_id, "seats": seats}


async def _true_sum(db, partner_id: str) -> int:
    rows = await _raw(db).tenants.aggregate([
        {"$match": {"partnerId": partner_id}},
        {"$group": {"_id": None, "seats": {"$sum": {"$ifNull": ["$license.maxAgents", {"$ifNull": ["$maxAgents", 0]}]}}}},
    ]).to_list(length=1)
    return int(rows[0]["seats"]) if rows else 0


async def _allocated_of(db, partner_id: str) -> Optional[int]:
    doc = await _raw(db).tenants.find_one({"id": partner_id, "type": "partner"}, {"_id": 0, "partner.allocated": 1})
    return None if doc is None else int((doc.get("partner") or {}).get("allocated") or 0)


async def reconcile_partner(db, partner_id: str) -> Optional[Dict[str, Any]]:
    """Set ``partner.allocated`` to the true sum of its customers' seats with a compare-and-set;
    returns the drift ``{partnerId, before, after}`` or None when the counter was right (or moving)."""
    before = await _allocated_of(db, partner_id)
    if before is None:
        return None
    after = await _true_sum(db, partner_id)
    if before == after:
        return None
    # A claim in flight sits ahead of its customer write; only a drift that survives a pause is real.
    await asyncio.sleep(RECONCILE_SETTLE_SECONDS)
    again_before, again_after = await _allocated_of(db, partner_id), await _true_sum(db, partner_id)
    if (again_before, again_after) != (before, after):
        return None
    res = await _raw(db).tenants.update_one({"id": partner_id, "type": "partner", "partner.allocated": before},
                                            {"$set": {"partner.allocated": after}})
    if res.modified_count != 1:
        return None
    logger.warning("partner %s: seat counter drift repaired, allocated %s -> %s", partner_id, before, after)
    import partner_store  # imported late: partner_store imports this module at load time
    await partner_store.audit("partner.pool_reconciled", actor="system", partner_id=partner_id, platform=True,
                              before=before, after=after)
    return {"partnerId": partner_id, "before": before, "after": after}


async def reconcile_pools(db) -> List[Dict[str, Any]]:
    """Repair every partner's counter; returns the drifts found."""
    drifts: List[Dict[str, Any]] = []
    ids = [d["id"] async for d in _raw(db).tenants.find({"type": "partner"}, {"_id": 0, "id": 1}) if d.get("id")]
    for partner_id in ids:
        drift = await reconcile_partner(db, partner_id)
        if drift:
            drifts.append(drift)
    return drifts
