"""Phase 87 seat pool completion: allotment changes, pool resize, moves and reconcile (real MongoDB).

Value: protects=a partner pool is never over-allocated under concurrency, a customer is never lowered
below the seats its agents hold (D-06), a pool never shrinks under what is handed out (D-07), a move
only happens when it fits (D-18), and the counter is repaired without ever inventing seats;
fails_when=a raise or claim is a check-then-write, a refusal leaves either document changed, a lost
race keeps seats claimed, or a partner organization is given seats by the licensing loops;
no_claim=multi-process timing (one event loop) and the HTTP layer (the functions are called directly,
the audit writer is mocked).
"""
import asyncio
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import licensing
import partner_pool
from partner_pool import PartnerError
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def audit(monkeypatch):
    """The reconcile settle pause is skipped and the audit writer never reaches a real ledger."""
    monkeypatch.setattr(partner_pool, "RECONCILE_SETTLE_SECONDS", 0, raising=False)
    with patch("partner_store.audit", new=AsyncMock()) as mocked:
        yield mocked


async def _partner(db, pool=100, allocated=0, status="active", pid="p1", name="Retailer A", expires=None):
    doc = {"id": pid, "name": name, "type": "partner", "license": {"maxAgents": 0},
           "partner": {"poolSize": pool, "allocated": allocated, "status": status, "screenCeiling": ["all"]}}
    if expires:
        doc["partner"]["expiresAt"] = expires
    await db.tenants.insert_one(doc)
    return pid


async def _customer(db, partner_id, seats, used=0, cid="c1", name="Cafe One"):
    doc = {"id": cid, "name": name, "maxAgents": seats, "license": {"maxAgents": seats, "seatsUsed": used}}
    if partner_id:
        doc["partnerId"] = partner_id
    await db.tenants.insert_one(doc)
    return cid


async def _snap(db, *ids):
    return [await db.tenants.find_one({"id": i}, {"_id": 0}) for i in ids]


async def _allocated(db, pid):
    return (await db.tenants.find_one({"id": pid}))["partner"]["allocated"]


def _change(db, cid, seats, pid="p1", floor=True, active=True):
    return partner_pool.change_allotment(db, cid, seats, partner_id=pid,
                                         enforce_used_floor=floor, require_active=active)


async def _refused(coro):
    with pytest.raises(PartnerError) as exc:
        await coro
    return exc.value


# --- PART-03: concurrency ----------------------------------------------------------------------

async def test_twenty_concurrent_claims_fill_the_pool_exactly(mongo_db):
    await _partner(mongo_db, pool=100, allocated=90)
    await _customer(mongo_db, "p1", 90)
    results = await asyncio.gather(*(partner_pool.claim(mongo_db, "p1", 1) for _ in range(20)))
    assert sum(results) == 10
    assert await _allocated(mongo_db, "p1") == 100


async def test_twenty_concurrent_raises_of_one_customer_succeed_once(mongo_db):
    await _partner(mongo_db, pool=100, allocated=10)
    await _customer(mongo_db, "p1", 10)
    results = await asyncio.gather(*(_change(mongo_db, "c1", 11) for _ in range(20)), return_exceptions=True)
    changed = [r for r in results if isinstance(r, dict) and r["before"] != r["after"]]
    assert changed == [{"before": 10, "after": 11}]
    others = [r for r in results if r not in changed]
    assert all((isinstance(r, dict)) or (isinstance(r, PartnerError) and r.code == "changed") for r in others)
    customer = (await _snap(mongo_db, "c1"))[0]
    assert customer["license"]["maxAgents"] == 11 and customer["maxAgents"] == 11
    assert await _allocated(mongo_db, "p1") == 11


async def test_a_claim_after_suspension_is_refused(mongo_db):
    await _partner(mongo_db, pool=10)
    assert await partner_pool.claim(mongo_db, "p1", 2, require_active=True) is True
    await mongo_db.tenants.update_one({"id": "p1"}, {"$set": {"partner.status": "suspended"}})
    assert await partner_pool.claim(mongo_db, "p1", 1, require_active=True) is False
    assert await partner_pool.claim(mongo_db, "p1", 1, require_active=False) is True
    assert await _allocated(mongo_db, "p1") == 3


# --- PART-03: change_allotment ------------------------------------------------------------------

async def test_raise_past_the_pool_is_refused_and_changes_nothing(mongo_db):
    await _partner(mongo_db, pool=20, allocated=15)
    await _customer(mongo_db, "p1", 5)
    before = await _snap(mongo_db, "p1", "c1")
    err = await _refused(_change(mongo_db, "c1", 11))
    assert (err.status, err.code, err.numbers["free"]) == (409, "pool_full", 5)
    assert "5" in err.message
    assert await _snap(mongo_db, "p1", "c1") == before


async def test_raise_within_the_pool_claims_the_difference(mongo_db):
    await _partner(mongo_db, pool=20, allocated=15)
    await _customer(mongo_db, "p1", 5)
    assert await _change(mongo_db, "c1", 10) == {"before": 5, "after": 10}
    assert await _allocated(mongo_db, "p1") == 20


async def test_lowering_stops_exactly_at_the_used_floor(mongo_db):
    await _partner(mongo_db, pool=100, allocated=10)
    await _customer(mongo_db, "p1", 10, used=6)
    before = await _snap(mongo_db, "p1", "c1")
    err = await _refused(_change(mongo_db, "c1", 5))
    assert (err.status, err.code, err.numbers["used"]) == (409, "below_used", 6)
    assert "Cafe One" in err.message and "6" in err.message
    assert await _snap(mongo_db, "p1", "c1") == before  # a refusal changes neither document
    assert await _change(mongo_db, "c1", 6) == {"before": 10, "after": 6}
    assert await _allocated(mongo_db, "p1") == 6


async def test_without_the_floor_lowering_below_used_keeps_the_agents_untouched(mongo_db):
    await _partner(mongo_db, pool=100, allocated=10)
    await _customer(mongo_db, "p1", 10, used=6)
    await mongo_db.agents.insert_many([
        {"id": f"a{i}", "hostname": f"h{i}", "tenantId": "c1", "status": "Online"} for i in range(6)])
    await _change(mongo_db, "c1", 2, floor=False)
    assert await mongo_db.agents.count_documents({"tenantId": "c1", "status": "Online"}) == 6
    customer = (await _snap(mongo_db, "c1"))[0]
    assert customer["license"]["seatsUsed"] == 6 and customer["license"]["maxAgents"] == 2


async def test_same_value_is_a_no_op(mongo_db):
    await _partner(mongo_db, pool=100, allocated=10)
    await _customer(mongo_db, "p1", 10)
    before = await _snap(mongo_db, "p1", "c1")
    assert await _change(mongo_db, "c1", 10) == {"before": 10, "after": 10}
    assert await _snap(mongo_db, "p1", "c1") == before


async def test_a_customer_of_another_partner_is_not_found(mongo_db):
    await _partner(mongo_db, pid="p1")
    await _partner(mongo_db, pid="p2", name="Retailer B")
    await _customer(mongo_db, "p2", 5)
    for call in (_change(mongo_db, "c1", 6, pid="p1"), _change(mongo_db, "nope", 6, pid="p1")):
        err = await _refused(call)
        assert (err.status, err.code, err.message) == (404, "not_found", "Customer not found")


async def test_invalid_seat_counts_are_refused(mongo_db):
    await _partner(mongo_db)
    await _customer(mongo_db, "p1", 5)
    for bad in (-1, 1_000_001):
        err = await _refused(_change(mongo_db, "c1", bad))
        assert (err.status, err.code) == (422, "invalid_seats")


async def test_a_suspended_partner_cannot_raise_unless_the_platform_does(mongo_db):
    await _partner(mongo_db, pool=20, allocated=5, status="suspended")
    await _customer(mongo_db, "p1", 5)
    before = await _snap(mongo_db, "p1", "c1")
    err = await _refused(_change(mongo_db, "c1", 8, active=True))
    assert err.status == 409 and err.code == "partner_suspended"
    assert await _snap(mongo_db, "p1", "c1") == before
    assert await _change(mongo_db, "c1", 8, active=False) == {"before": 5, "after": 8}


async def test_a_lost_compare_and_set_gives_the_claimed_seats_back(mongo_db):
    await _partner(mongo_db, pool=50, allocated=10)
    await _customer(mongo_db, "p1", 10)
    real_claim = partner_pool.claim

    async def claim_then_race(db, partner_id, n, **kw):
        ok = await real_claim(db, partner_id, n, **kw)
        await db.tenants.update_one({"id": "c1"}, {"$set": {"license.maxAgents": 12}})  # a rival write lands
        return ok

    with patch.object(partner_pool, "claim", new=claim_then_race):
        err = await _refused(_change(mongo_db, "c1", 15))
    assert (err.status, err.code) == (409, "changed")
    assert await _allocated(mongo_db, "p1") == 10  # the 5 claimed seats went back


# --- PART-03 (D-07): set_pool_size --------------------------------------------------------------

async def test_pool_can_shrink_to_exactly_what_is_handed_out(mongo_db):
    await _partner(mongo_db, pool=100, allocated=40)
    await partner_pool.set_pool_size(mongo_db, "p1", 40)
    assert (await mongo_db.tenants.find_one({"id": "p1"}))["partner"]["poolSize"] == 40


async def test_pool_below_handed_out_is_refused_unchanged(mongo_db):
    await _partner(mongo_db, pool=100, allocated=40)
    before = await _snap(mongo_db, "p1")
    err = await _refused(partner_pool.set_pool_size(mongo_db, "p1", 39))
    assert (err.status, err.code, err.numbers["handedOut"]) == (409, "pool_below_handed_out", 40)
    assert "40" in err.message
    assert await _snap(mongo_db, "p1") == before


async def test_pool_resize_validates_and_finds_the_partner(mongo_db):
    await _partner(mongo_db)
    await _customer(mongo_db, None, 3, cid="direct")
    for bad in (0, 1_000_001):
        assert (await _refused(partner_pool.set_pool_size(mongo_db, "p1", bad))).code == "invalid_seats"
    for missing in ("ghost", "direct"):  # a customer is never resized as a pool
        err = await _refused(partner_pool.set_pool_size(mongo_db, missing, 10))
        assert (err.status, err.code) == (404, "not_found")


# --- PART-07 (D-18): move_customer --------------------------------------------------------------

async def test_move_to_a_partner_with_exactly_enough_free_seats(mongo_db):
    await _partner(mongo_db, pid="p1", pool=100, allocated=10)
    await _partner(mongo_db, pid="p2", name="Retailer B", pool=30, allocated=20)
    await _customer(mongo_db, "p1", 10, used=4)
    assert await partner_pool.move_customer(mongo_db, "c1", "p2") == {"from": "p1", "to": "p2", "seats": 10}
    assert (await _snap(mongo_db, "c1"))[0]["partnerId"] == "p2"
    assert (await _allocated(mongo_db, "p1"), await _allocated(mongo_db, "p2")) == (0, 30)
    assert (await _snap(mongo_db, "c1"))[0]["license"]["seatsUsed"] == 4  # the customer is otherwise untouched


async def test_move_that_needs_one_more_seat_than_is_free_changes_nothing(mongo_db):
    await _partner(mongo_db, pid="p1", pool=100, allocated=10)
    await _partner(mongo_db, pid="p2", name="Retailer B", pool=29, allocated=20)
    await _customer(mongo_db, "p1", 10)
    before = await _snap(mongo_db, "p1", "p2", "c1")
    err = await _refused(partner_pool.move_customer(mongo_db, "c1", "p2"))
    assert (err.status, err.code) == (409, "move_does_not_fit")
    assert (err.numbers["free"], err.numbers["needed"]) == (9, 10)
    assert "Retailer B" in err.message and "Cafe One" in err.message
    assert await _snap(mongo_db, "p1", "p2", "c1") == before


async def test_moving_a_customer_with_no_seats_leaves_both_counters_alone(mongo_db):
    await _partner(mongo_db, pid="p1", pool=10, allocated=3)
    await _partner(mongo_db, pid="p2", name="Retailer B", pool=10, allocated=4)
    await _customer(mongo_db, "p1", 0)
    assert (await partner_pool.move_customer(mongo_db, "c1", "p2"))["seats"] == 0
    assert (await _snap(mongo_db, "c1"))[0]["partnerId"] == "p2"
    assert (await _allocated(mongo_db, "p1"), await _allocated(mongo_db, "p2")) == (3, 4)


async def test_moving_to_none_makes_a_direct_customer_and_returns_the_seats(mongo_db):
    await _partner(mongo_db, pid="p1", pool=10, allocated=7)
    await _customer(mongo_db, "p1", 7)
    assert await partner_pool.move_customer(mongo_db, "c1", None) == {"from": "p1", "to": None, "seats": 7}
    assert "partnerId" not in (await _snap(mongo_db, "c1"))[0]
    assert await _allocated(mongo_db, "p1") == 0


async def test_a_direct_customer_moves_into_a_pool(mongo_db):
    await _partner(mongo_db, pid="p2", pool=10, allocated=0)
    await _customer(mongo_db, None, 6)
    assert await partner_pool.move_customer(mongo_db, "c1", "p2") == {"from": None, "to": "p2", "seats": 6}
    assert (await _snap(mongo_db, "c1"))[0]["partnerId"] == "p2"
    assert await _allocated(mongo_db, "p2") == 6


async def test_move_refusals(mongo_db):
    await _partner(mongo_db, pid="p1")
    await _partner(mongo_db, pid="p2", name="Retailer B", status="suspended")
    await _customer(mongo_db, "p1", 3)
    await _customer(mongo_db, None, 3, cid="direct", name="Direct Co")
    same = await _refused(partner_pool.move_customer(mongo_db, "c1", "p1"))
    assert (same.status, same.code) == (409, "same_partner")
    still_direct = await _refused(partner_pool.move_customer(mongo_db, "direct", None))
    assert still_direct.code == "same_partner"
    for cid in ("p1", "platform-admin", "ghost"):  # a partner organization is not a customer
        assert (await _refused(partner_pool.move_customer(mongo_db, cid, "p2"))).code == "not_found"
    assert (await _refused(partner_pool.move_customer(mongo_db, "c1", "ghost"))).code == "not_found"
    suspended = await _refused(partner_pool.move_customer(mongo_db, "c1", "p2"))
    assert (suspended.status, suspended.code) == (409, "partner_suspended")
    assert (await _snap(mongo_db, "c1"))[0]["partnerId"] == "p1"


# --- reconcile and expiry -----------------------------------------------------------------------

async def test_reconcile_sets_allocated_to_the_true_sum_and_reports_each_drift(mongo_db, audit):
    await _partner(mongo_db, pid="p1", pool=100, allocated=80)       # leaked 50
    await _partner(mongo_db, pid="p2", name="Retailer B", pool=100, allocated=5)  # under-counted by 20
    await _partner(mongo_db, pid="p3", name="Retailer C", pool=100, allocated=7)  # exact
    await _customer(mongo_db, "p1", 20, cid="c1")
    await _customer(mongo_db, "p1", 10, cid="c2", name="Cafe Two")
    await _customer(mongo_db, "p2", 25, cid="c3", name="Cafe Three")
    await _customer(mongo_db, "p3", 7, cid="c4", name="Cafe Four")
    await _customer(mongo_db, None, 99, cid="direct", name="Direct Co")  # never counted
    drifts = await partner_pool.reconcile_pools(mongo_db)
    assert sorted(drifts, key=lambda d: d["partnerId"]) == [
        {"partnerId": "p1", "before": 80, "after": 30}, {"partnerId": "p2", "before": 5, "after": 25}]
    assert [await _allocated(mongo_db, p) for p in ("p1", "p2", "p3")] == [30, 25, 7]
    assert audit.await_count == 2 and audit.await_args_list[0].args[0] == "partner.pool_reconciled"
    assert await partner_pool.reconcile_pools(mongo_db) == []  # a second run changes nothing


async def test_release_of_more_than_is_held_repairs_the_counter(mongo_db):
    await _partner(mongo_db, pool=50, allocated=5)
    await _customer(mongo_db, "p1", 3)
    await partner_pool.release(mongo_db, "p1", 9)
    await partner_pool.settle_repairs()  # the repair runs off the request path (WR-07)
    assert await _allocated(mongo_db, "p1") == 3


async def test_pool_expiry_compares_parsed_datetimes():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)

    def doc(value):
        return {"partner": {"expiresAt": value}}

    assert partner_pool.pool_expired(doc(None), now) is False
    assert partner_pool.pool_expired(doc((now - timedelta(seconds=1)).isoformat()), now) is True
    assert partner_pool.pool_expired(doc(now.isoformat()), now) is True
    assert partner_pool.pool_expired(doc((now + timedelta(seconds=1)).isoformat()), now) is False
    assert partner_pool.pool_expired(doc("2026-11-02T14:00:00+02:00"), now) is True  # 12:00 UTC, at the instant
    assert partner_pool.pool_expired(doc("2026-11-02T14:00:01+02:00"), now) is False  # 12:00:01 UTC
    assert importlib.import_module("partner_pool").pool_expired({}, now) is False


# --- migration 029 and the licensing loops ------------------------------------------------------

async def test_migration_029_adds_indexes_only_and_a_second_run_changes_nothing(mongo_db):
    migration = importlib.import_module("migrations.029_partner_channel")
    await mongo_db.tenants.insert_many([
        {"id": "old-a", "name": "Old A", "license": {"maxAgents": 5}},
        {"id": "old-b", "name": "Old B", "maxAgents": 3},
    ])
    before = await _snap(mongo_db, "old-a", "old-b")
    await migration.up(mongo_db)
    assert await _snap(mongo_db, "old-a", "old-b") == before  # no partnerId and no type were added
    assert await mongo_db.tenants.count_documents({"$or": [{"partnerId": {"$exists": True}},
                                                           {"type": {"$exists": True}}]}) == 0
    tenant_ix = await mongo_db.tenants.index_information()
    assert tenant_ix["partnerId_1"]["partialFilterExpression"] == {"partnerId": {"$type": "string"}}
    assert tenant_ix["type_1"]["partialFilterExpression"] == {"type": {"$type": "string"}}
    invite_ix = await mongo_db.invites.index_information()
    assert invite_ix["tokenHash_1"]["unique"] is True and "email_1_createdAt_-1" in invite_ix
    snapshot = (tenant_ix, invite_ix)
    await migration.up(mongo_db)
    assert (await mongo_db.tenants.index_information(), await mongo_db.invites.index_information()) == snapshot
    assert await _snap(mongo_db, "old-a", "old-b") == before
    assert migration.DESCRIPTION


async def test_the_licensing_loops_never_read_a_partner_organization(mongo_db):
    await _partner(mongo_db, pool=50, allocated=5)
    await _customer(mongo_db, "p1", 5, cid="c1")
    await mongo_db.tenants.update_one({"id": "c1"}, {"$unset": {"license.seatsUsed": ""}})
    stale = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    await mongo_db.agents.insert_one({"id": "a1", "hostname": "h1", "tenantId": "p1", "status": "Online",
                                      "lastSeen": stale})
    before = await _snap(mongo_db, "p1")
    assert await licensing.reclaim_inactive_agents(mongo_db) == 0
    assert await licensing.reconcile_all(mongo_db) == []
    assert await _snap(mongo_db, "p1") == before  # no license.seatsUsed, no invented seats
    assert "seatsUsed" not in (before[0].get("license") or {})
    assert (await mongo_db.agents.find_one({"id": "a1"}))["status"] == "Online"
    assert (await _snap(mongo_db, "c1"))[0]["license"]["seatsUsed"] == 0  # customers are still counted


async def test_a_failing_pool_repair_never_skips_the_other_seat_upkeep(monkeypatch):
    """87 WR-07: protects=agent-seat reclaim and expiry reminders run every hour; fails_when=a raising
    partner pool repair ends the whole hourly pass; no_claim=why the repair raised."""
    import app_background_tasks
    import license_rules
    import licensing

    ran = []

    def step(name, fail=False):
        async def run(db):
            ran.append(name)
            if fail:
                raise RuntimeError("a malformed partner document")
        return run

    monkeypatch.setattr(licensing, "reconcile_all", step("reconcile_all"))
    monkeypatch.setattr(partner_pool, "reconcile_pools", step("reconcile_pools", fail=True))
    monkeypatch.setattr(licensing, "reclaim_inactive_agents", step("reclaim"))
    monkeypatch.setattr(license_rules, "send_expiry_reminders", step("reminders"))
    await app_background_tasks.license_seat_tick(object(), 0)
    assert ran == ["reconcile_all", "reconcile_pools", "reclaim", "reminders"]
    ran.clear()
    await app_background_tasks.license_seat_tick(object(), 1)
    assert ran == ["reclaim", "reminders"]  # reconcile only every 24th hour


async def test_a_claim_refused_by_seats_another_request_is_giving_back_succeeds(mongo_db):
    """87 WR-06: protects=a valid raise is not refused because a concurrent request briefly held seats
    it was about to return (a losing compare-and-set); fails_when=the claim answers pool_full at once;
    no_claim=a real concurrent request (the give-back is scheduled instead)."""
    import asyncio

    await _partner(mongo_db, pool=10, allocated=10)

    async def give_back():
        await asyncio.sleep(0.01)
        await partner_pool.release(mongo_db, "p1", 2)

    giver = asyncio.create_task(give_back())
    assert await partner_pool.claim(mongo_db, "p1", 2) is True
    await giver
    assert await _allocated(mongo_db, "p1") == 10
