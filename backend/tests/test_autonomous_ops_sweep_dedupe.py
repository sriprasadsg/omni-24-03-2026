"""Nothing repeats: the sweep's memory, the 24 hour undo window and the per-computer hourly cap
(Phase 83, plan 83-05, RESP-07 / D-14 / research default R2). Real MongoDB (skips without one) through the
throwaway database of tests/_mongo_test_db.py. The full sweep tick is the system under test; time is a
frozen value passed in, so every edge is exact.

Value: protects=the same finding creates at most one row however many cycles pass (for an automatic
action, a recorded refusal and a simulation alike), a denied or expired card, a failed row and a refused
row each wait their own window, an action a person undid is refused once and left alone for exactly 24
hours, and one computer can spend only three automatic block or quarantine actions an hour;
fails_when=a tick adds a row for a finding it already decided, a window ends a second early or late, the
undo window writes an instruction, or a restart counts toward the cap;
no_claim=a real agent (the instruction is only written, never sent).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger, protected, signals, sweep
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_feed_ioc, seed_native_verdict, seed_response_agent, seed_tenant

IP = "45.33.32.156"
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
ACT_KEY = f"t1|sweep|block_ip|a1|{IP}"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


async def _world(db, *, shadow=False, ips=(IP,)):
    await ledger.ensure_indexes(db)
    await signals.ensure_indexes(db)
    await seed_tenant(db, "t1", shadow=shadow)
    await seed_response_agent(db, "t1", "a1", hostname="host-a1", tokens=["block_ip_ttl", "quarantine_file"], last_seen=NOW)
    for ip in ips:
        await _evidence(db, ip, NOW)


async def _evidence(db, ip, at, feed="urlhaus"):
    await seed_native_verdict(db, "t1", "host-a1", kind="ip", target=ip, created_at=at - timedelta(minutes=5))
    await seed_feed_ioc(db, ioc_type="url", value=f"http://{ip}/{feed}", source_ip=ip, feed=feed, updated_at=at)


async def _tick(db, at):
    """One tick at ``at``. The evidence is kept fresh (the sources keep reporting) so a late tick is about
    the sweep's memory, not about evidence having aged out."""
    await db.agents.update_one({"id": "a1"}, {"$set": {"lastSeen": at.isoformat()}})
    await db.security_scan_results.update_many({}, {"$set": {"created_at": (at - timedelta(minutes=5)).isoformat()}})
    await db.edr_ioc.update_many({}, {"$set": {"updated_at": at.isoformat()}})
    return await sweep.tick(db, now=at)


async def _rows(db):
    return [r async for r in db.autonomy_actions.find({"tenantId": "t1", "kind": {"$ne": "control"}}, {"_id": 0}).sort("createdAt", 1)]


async def _instructions(db):
    return [d async for d in db.agent_instructions.find({"tenantId": "t1"}, {"_id": 0})]


async def _snapshot(db):
    return {name: sorted([d async for d in db[name].find({}, {"_id": 0})], key=repr)
            for name in ("autonomy_actions", "autonomy_signals", "agent_instructions")}


# ------------------------------------------------------------------ ten ticks, one row

async def test_ten_ticks_over_one_automatic_action_leave_one_row_and_one_instruction(mongo_db):
    await _world(mongo_db)
    for _ in range(10):
        await _tick(mongo_db, NOW)
    assert len(await _rows(mongo_db)) == 1 and len(await _instructions(mongo_db)) == 1


async def test_ten_ticks_over_a_recorded_refusal_leave_one_refused_row(mongo_db):
    await _world(mongo_db)
    await protected.add_entry(mongo_db, scope="tenant", tenant_id="t1", kind="ip", value=IP)
    for _ in range(10):
        await _tick(mongo_db, NOW)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "refused" and row["reasonCode"] == "protected_target" and await _instructions(mongo_db) == []


async def test_ten_ticks_for_a_tenant_in_shadow_leave_one_simulation(mongo_db):
    await _world(mongo_db, shadow=True)
    for _ in range(10):
        await _tick(mongo_db, NOW)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "shadow" and row["wouldHave"] == "allow_auto" and await _instructions(mongo_db) == []


async def test_a_tick_with_no_new_data_changes_no_document(mongo_db):
    await _world(mongo_db)
    await _tick(mongo_db, NOW)
    before = await _snapshot(mongo_db)
    await _tick(mongo_db, NOW)
    assert await _snapshot(mongo_db) == before


async def test_a_tenant_with_a_computer_and_nothing_else_ends_its_tick_with_no_writes(mongo_db):
    await _world(mongo_db, ips=())
    await _tick(mongo_db, NOW)
    for name in ("autonomy_actions", "autonomy_signals", "agent_instructions"):
        assert await mongo_db[name].count_documents({}) == 0, name


async def test_two_sweeps_racing_on_one_finding_leave_one_open_row_and_one_instruction(mongo_db):
    await _world(mongo_db)
    await asyncio.gather(_tick(mongo_db, NOW), _tick(mongo_db, NOW))
    assert len(await _rows(mongo_db)) == 1 and len(await _instructions(mongo_db)) == 1


# ------------------------------------------------------------------ how long each outcome waits

async def _decided_then(db, state, *, at=NOW, **fields):
    await _tick(db, at)
    (row,) = await _rows(db)
    await db.autonomy_actions.update_one({"id": row["id"]}, {"$set": {"state": state, "finishedAt": at, **fields}})
    return row["id"]


@pytest.mark.parametrize("state, window", [("denied", 24 * HOUR), ("expired", 24 * HOUR), ("failed", HOUR),
                                           ("refused", 24 * HOUR)])
async def test_a_finished_decision_is_left_alone_for_its_window_and_decided_again_at_its_end(mongo_db, state, window):
    await _world(mongo_db)
    await _decided_then(mongo_db, state)
    await _tick(mongo_db, NOW + window - timedelta(seconds=1))
    assert len(await _rows(mongo_db)) == 1
    await _tick(mongo_db, NOW + window)
    rows = await _rows(mongo_db)
    assert len(rows) == 2 and rows[1]["state"] == "dispatching"


async def test_a_refused_row_is_tried_again_at_once_when_a_new_origin_arrives(mongo_db):
    await _world(mongo_db)
    await _decided_then(mongo_db, "refused")
    await _tick(mongo_db, NOW + HOUR)
    assert len(await _rows(mongo_db)) == 1
    later = NOW + 2 * HOUR
    await _evidence(mongo_db, IP, later, feed="otx")
    await _tick(mongo_db, later)
    rows = await _rows(mongo_db)
    assert len(rows) == 2 and rows[1]["reason"]["inputs"]["origins"] == ["feed:otx", "feed:urlhaus", "native"]


async def test_a_finding_whose_block_is_still_running_is_not_decided_again(mongo_db):
    await _world(mongo_db)
    await _decided_then(mongo_db, "verified", blockedFrom=NOW, blockedUntil=NOW + 24 * HOUR)
    await _tick(mongo_db, NOW + 24 * HOUR - timedelta(seconds=1))
    assert len(await _rows(mongo_db)) == 1


# ------------------------------------------------------------------ an undone action stays undone for 24 hours

async def _undone_at(db, undone: datetime):
    return await _decided_then(db, "undone", at=NOW, undo={"available": False, "undoneAt": undone, "undoneBy": "admin"},
                               finishedAt=undone)


async def test_inside_24_hours_of_an_undo_the_sweep_records_one_refused_row_and_sends_nothing(mongo_db):
    await _world(mongo_db)
    undone = NOW + HOUR
    await _undone_at(mongo_db, undone)
    sent_before = len(await _instructions(mongo_db))
    for minute in range(10):
        await _tick(mongo_db, undone + timedelta(minutes=5 + minute))
    rows = await _rows(mongo_db)
    assert [r["state"] for r in rows] == ["undone", "refused"]
    refused = rows[1]
    assert refused["reasonCode"] == "suppressed_by_undo" and refused["dedupeKey"] == ACT_KEY
    assert refused["reasonText"] == "You undid this action on Oct 31. It isn't repeated for 24 hours."
    assert refused["reason"]["inputs"]["undoneAt"] and len(await _instructions(mongo_db)) == sent_before


@pytest.mark.parametrize("age, decides", [(24 * HOUR - timedelta(seconds=1), False), (24 * HOUR, True)])
async def test_an_undo_exactly_24_hours_old_no_longer_suppresses_and_one_second_younger_does(mongo_db, age, decides):
    await _world(mongo_db)
    undone = NOW + HOUR
    await _undone_at(mongo_db, undone)
    await _tick(mongo_db, undone + age)
    states = [r["state"] for r in await _rows(mongo_db)]
    assert states == (["undone", "dispatching"] if decides else ["undone", "refused"])


async def test_a_refusal_for_an_undo_ends_with_the_undo_window_not_a_day_after_the_refusal(mongo_db):
    await _world(mongo_db)
    undone = NOW + HOUR
    await _undone_at(mongo_db, undone)
    await _tick(mongo_db, undone + 20 * HOUR)                              # refused, recorded 20 hours in
    await _tick(mongo_db, undone + 24 * HOUR)                              # the window is over: decided again
    assert [r["state"] for r in await _rows(mongo_db)] == ["undone", "refused", "dispatching"]


# ------------------------------------------------------------------ three automatic actions an hour per computer (R2)

BLOCK_IPS = ("45.33.32.10", "45.33.32.20", "45.33.32.30", "45.33.32.40")


async def test_the_fourth_automatic_action_on_one_computer_in_an_hour_becomes_an_approval_card(mongo_db):
    await _world(mongo_db, ips=BLOCK_IPS)
    await _tick(mongo_db, NOW)
    rows = {r["target"]: r for r in await _rows(mongo_db)}
    assert [rows[ip]["state"] for ip in BLOCK_IPS] == ["dispatching"] * 3 + ["awaiting_approval"]
    card = rows["45.33.32.40"]
    assert card["reasonCode"] == "playbook_raised" and card["autoDispatched"] is False
    assert card["reasonText"] == "This computer already had 3 automatic actions in the last hour, so this one needs your approval."
    assert len(await _instructions(mongo_db)) == 3


async def test_a_repeat_run_makes_the_same_decisions_in_the_same_order(mongo_db):
    await _world(mongo_db, ips=BLOCK_IPS)
    await _tick(mongo_db, NOW)
    first = [(r["target"], r["state"]) for r in await _rows(mongo_db)]
    await _tick(mongo_db, NOW)
    assert [(r["target"], r["state"]) for r in await _rows(mongo_db)] == first


def _auto_row(n, command, created):
    return {"id": f"AO-seed-{n}", "tenantId": "t1", "kind": "security", "state": "verified", "autoDispatched": True,
            "command": command, "targets": ["a1"], "createdAt": created, "updatedAt": created, "finishedAt": created}


@pytest.mark.parametrize("command, age, card", [
    ("block_ip", HOUR, False),                                     # exactly an hour old no longer counts
    ("block_ip", HOUR - timedelta(seconds=1), True),
    ("quarantine_file", HOUR - timedelta(seconds=1), True),        # quarantines count with blocks
    ("restart_service", timedelta(minutes=1), False)])             # restarts do not
async def test_the_per_computer_cap_counts_blocks_and_quarantines_in_a_rolling_hour(mongo_db, command, age, card):
    await _world(mongo_db)
    await mongo_db.autonomy_actions.insert_many([_auto_row(n, command, NOW - age) for n in range(3)])
    await _tick(mongo_db, NOW)
    (new,) = [r for r in await _rows(mongo_db) if r.get("dedupeKey") == ACT_KEY]
    assert new["state"] == ("awaiting_approval" if card else "dispatching")


async def test_another_computers_actions_do_not_count_toward_the_cap(mongo_db):
    await _world(mongo_db)
    rows = [dict(_auto_row(n, "block_ip", NOW - timedelta(minutes=1)), targets=["a2"]) for n in range(3)]
    await mongo_db.autonomy_actions.insert_many(rows)
    await _tick(mongo_db, NOW)
    (new,) = [r for r in await _rows(mongo_db) if r.get("dedupeKey") == ACT_KEY]
    assert new["state"] == "dispatching"


# ------------------------------------------------------------------ the memory table itself

def _mem(**kw):
    return {"actionId": "AO-1", "at": NOW, "outcome": "blocked", "origins": ["native", "feed:urlhaus"], **kw}


@pytest.mark.parametrize("state, extra, at, holds", [
    ("verified", {"blockedFrom": NOW, "blockedUntil": NOW + 24 * HOUR}, NOW + 24 * HOUR - timedelta(seconds=1), True),
    ("verified", {"blockedFrom": NOW, "blockedUntil": NOW + 24 * HOUR}, NOW + 24 * HOUR, False),
    ("executed", {}, NOW + 24 * HOUR - timedelta(seconds=1), True),            # no window recorded: a day from the decision
    ("shadow", {}, NOW + 24 * HOUR - timedelta(seconds=1), True), ("shadow", {}, NOW + 24 * HOUR, False),
    ("denied", {}, NOW + 24 * HOUR - timedelta(seconds=1), True), ("denied", {}, NOW + 24 * HOUR, False),
    ("expired", {}, NOW + 24 * HOUR, False), ("failed", {}, NOW + HOUR - timedelta(seconds=1), True),
    ("failed", {}, NOW + HOUR, False), ("refused", {}, NOW + 24 * HOUR - timedelta(seconds=1), True),
    ("refused", {}, NOW + 24 * HOUR, False), ("cancelled_by_stop", {}, NOW, False), ("undone", {}, NOW, False),
    ("dispatching", {}, NOW + 90 * HOUR, True), ("awaiting_approval", {}, NOW + 90 * HOUR, True)])
def test_skip_reason_holds_a_decision_for_its_window(state, extra, at, holds):
    from autonomous_ops import sweep_memory
    row = {"state": state, "finishedAt": NOW, **extra}
    assert bool(sweep_memory.skip_reason(_mem(), row, ["native", "feed:urlhaus"], at)) is holds


def test_skip_reason_lets_a_refusal_through_for_a_new_origin_but_not_through_an_undo_hold():
    from autonomous_ops import sweep_memory
    row = {"state": "refused", "finishedAt": NOW}
    soon = NOW + HOUR
    assert sweep_memory.skip_reason(_mem(), row, ["feed:otx", "feed:urlhaus", "native"], soon) is None
    assert sweep_memory.skip_reason(_mem(), row, ["native"], soon)
    held = _mem(holdUntil=NOW + 5 * HOUR)
    assert sweep_memory.skip_reason(held, row, ["feed:otx", "feed:urlhaus", "native"], soon)
    assert sweep_memory.skip_reason(held, row, ["native"], NOW + 5 * HOUR) is None


def test_skip_reason_without_a_memory_or_a_row_is_quiet_or_falls_back_to_the_outcome():
    from autonomous_ops import sweep_memory
    assert sweep_memory.skip_reason(None, None, ["native"], NOW) is None and sweep_memory.skip_reason({}, None, [], NOW) is None
    assert sweep_memory.skip_reason(_mem(outcome="shadow"), None, ["native"], NOW + HOUR)
    assert sweep_memory.skip_reason(_mem(outcome="shadow"), None, ["native"], NOW + 24 * HOUR) is None
    assert set(sweep_memory.WINDOWS) == {"shadow", "denied", "expired", "failed", "refused", "cancelled_by_stop"}
