"""Autonomous Ops circuit breaker (Phase 81, plan 81-04, GATE-14 / D-18).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=three bad automatic outcomes in a day drop a tenant to Suggest and it stays
there until a person restores it; fails_when=the breaker trips on two bad outcomes, counts
simulations or control rows, trips twice, re-arms itself, or restores above the maximum level;
no_claim=the restore route and the permission check (plan 81-09).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import BREAKER_WINDOW, breaker, ledger, settings
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant

ACTOR = {"username": "carol", "display": "Carol", "tier": "tenant"}
NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture
async def live(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    return mongo_db


async def _row(db, state, *, tenant="t1", finished=None, auto=True, kind="security", n=[0]):
    n[0] += 1
    finished = finished or NOW - timedelta(minutes=n[0] % 50)
    await db.autonomy_actions.insert_one({
        "id": f"AO-b{n[0]}", "tenantId": tenant, "kind": kind, "state": state, "autoDispatched": auto,
        "createdAt": finished - timedelta(seconds=30), "updatedAt": finished, "finishedAt": finished,
        "command": "block_ip", "targets": ["a1"], "params": {}, "reason": {"ruleId": "t", "inputs": {}}})
    return f"AO-b{n[0]}"


async def _bad(db, count, **kw):
    states = ["failed", "rolled_back", "undone", "failed", "undone"]
    return [await _row(db, states[i % len(states)], **kw) for i in range(count)]


async def _tenant(db, tenant="t1"):
    return await settings.load(db, tenant)


async def _controls(db, tenant="t1"):
    return [r["controlEvent"] async for r in db.autonomy_actions.find({"tenantId": tenant, "kind": "control"})]


@pytest.fixture
def notices():
    with patch("autonomous_ops.breaker.notify.notify", AsyncMock()) as mocked:
        yield mocked


async def test_tracer_three_bad_outcomes_drop_the_tenant_to_suggest(live, notices):
    ids = await _bad(live, 3)
    assert await breaker.evaluate(live, "t1", now=NOW) is True
    s = await _tenant(live)
    assert s.level == "suggest" and s.max_level == "undoable_auto"
    assert s.breaker["previousLevel"] == "undoable_auto" and set(s.breaker["actionIds"]) == set(ids)
    assert s.breaker["trippedAt"] is not None
    assert await _controls(live) == ["breaker_tripped"]
    notices.assert_awaited_once()
    assert notices.await_args.args[1] == "t1"


async def test_two_bad_and_one_executed_do_not_trip(live, notices):
    await _bad(live, 2)
    await _row(live, "executed")
    assert await breaker.evaluate(live, "t1", now=NOW) is False
    assert (await _tenant(live)).level == "undoable_auto" and (await _tenant(live)).breaker is None
    notices.assert_not_awaited()


async def test_two_bad_of_two_do_not_trip(live, notices):
    await _bad(live, 2)
    assert await breaker.evaluate(live, "t1", now=NOW) is False


async def test_a_good_outcome_between_bad_ones_blocks_the_trip(live, notices):
    """The 3 most RECENT finished rows decide: a success among them means no trip."""
    await _row(live, "failed", finished=NOW - timedelta(minutes=30))
    await _row(live, "executed", finished=NOW - timedelta(minutes=20))
    await _row(live, "failed", finished=NOW - timedelta(minutes=10))
    await _row(live, "failed", finished=NOW - timedelta(minutes=5))
    assert await breaker.evaluate(live, "t1", now=NOW) is False


async def test_oldest_exactly_24_hours_trips_and_one_second_older_does_not(live, notices):
    await _row(live, "failed", finished=NOW - BREAKER_WINDOW)
    await _row(live, "failed", finished=NOW - timedelta(hours=3))
    await _row(live, "failed", finished=NOW - timedelta(hours=1))
    assert await breaker.evaluate(live, "t1", now=NOW) is True

    await live.autonomy_actions.delete_many({"tenantId": "t1"})
    await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"level": "undoable_auto", "breaker": None}})
    await _row(live, "failed", finished=NOW - BREAKER_WINDOW - timedelta(seconds=1))
    await _row(live, "failed", finished=NOW - timedelta(hours=3))
    await _row(live, "failed", finished=NOW - timedelta(hours=1))
    assert await breaker.evaluate(live, "t1", now=NOW) is False
    assert (await _tenant(live)).level == "undoable_auto"


async def test_shadow_control_and_manual_rows_never_count(live, notices):
    await _bad(live, 2)
    await _row(live, "shadow")
    await _row(live, "failed", kind="control")
    await _row(live, "failed", auto=False)
    assert await breaker.evaluate(live, "t1", now=NOW) is False
    await _bad(live, 1)
    assert await breaker.evaluate(live, "t1", now=NOW) is True


async def test_other_tenants_rows_never_count(live, notices):
    await seed_tenant(live, "t2", shadow=False)
    await _bad(live, 2)
    await _bad(live, 3, tenant="t2")
    assert await breaker.evaluate(live, "t1", now=NOW) is False
    assert (await _tenant(live)).level == "undoable_auto"
    assert await breaker.evaluate(live, "t2", now=NOW) is True
    assert (await _tenant(live, "t1")).breaker is None and (await _tenant(live, "t2")).level == "suggest"
    assert await _controls(live, "t1") == []


async def test_a_second_evaluate_does_not_trip_again_or_re_arm(live, notices):
    await _bad(live, 3)
    assert await breaker.evaluate(live, "t1", now=NOW) is True
    first = (await _tenant(live)).breaker
    await _bad(live, 3)
    assert await breaker.evaluate(live, "t1", now=NOW + timedelta(hours=1)) is False
    s = await _tenant(live)
    assert s.breaker == first and s.level == "suggest"
    assert await _controls(live) == ["breaker_tripped"]
    notices.assert_awaited_once()


async def test_concurrent_evaluates_trip_once(live, notices):
    await _bad(live, 3)
    results = await asyncio.gather(*(breaker.evaluate(live, "t1", now=NOW) for _ in range(4)))
    assert results.count(True) == 1
    assert await _controls(live) == ["breaker_tripped"]
    notices.assert_awaited_once()


async def test_a_tenant_already_at_suggest_or_off_is_not_touched(live, notices):
    await _bad(live, 3)
    for level in ("suggest", "off"):
        await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"level": level}})
        assert await breaker.evaluate(live, "t1", now=NOW) is False
        assert (await _tenant(live)).level == level and (await _tenant(live)).breaker is None


async def test_no_finished_rows_and_unknown_tenant_do_not_trip(live, notices):
    assert await breaker.evaluate(live, "t1", now=NOW) is False
    assert await breaker.evaluate(live, "nobody", now=NOW) is False


async def test_restore_puts_the_previous_level_back_and_records_it(live, notices):
    await _bad(live, 3)
    await breaker.evaluate(live, "t1", now=NOW)
    out = await breaker.restore(live, "t1", actor=ACTOR)
    assert out == {"status": "restored", "level": "undoable_auto"}
    s = await _tenant(live)
    assert s.level == "undoable_auto" and s.breaker is None
    assert sorted(await _controls(live)) == ["breaker_tripped", "level_restored"]
    assert (await breaker.restore(live, "t1", actor=ACTOR))["status"] == "not_tripped"


async def test_restore_is_capped_at_the_maximum_level(live, notices):
    await _bad(live, 3)
    await breaker.evaluate(live, "t1", now=NOW)
    await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"maxLevel": "suggest"}})
    assert await breaker.restore(live, "t1", actor=ACTOR) == {"status": "restored", "level": "suggest"}
    assert (await _tenant(live)).level == "suggest"


async def test_restore_of_an_untripped_tenant_changes_nothing(live):
    assert await breaker.restore(live, "t1", actor=ACTOR) == {"status": "not_tripped", "level": "undoable_auto"}
    assert await _controls(live) == []


async def test_old_bad_rows_do_not_re_trip_after_a_restore_when_a_good_one_follows(live, notices):
    """No self re-arm: after a restore the same three rows trip again only through a new evaluate call."""
    await _bad(live, 3)
    await breaker.evaluate(live, "t1", now=NOW)
    await breaker.restore(live, "t1", actor=ACTOR)
    await _row(live, "executed", finished=NOW + timedelta(minutes=1))
    assert await breaker.evaluate(live, "t1", now=NOW + timedelta(minutes=2)) is False
    assert (await _tenant(live)).level == "undoable_auto"
