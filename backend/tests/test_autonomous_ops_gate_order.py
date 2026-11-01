"""Autonomous Ops gate: the edges of the GATE-03 decision order (Phase 81, plan 81-11). Real
MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the host cap, the rolling-hour rate limit (and its once-per-window notice),
dedupe / cooldown / undo suppression, the empty and invalid inputs, the order in which hard
refusals and soft escalations win, BSON-datetime precision and unreadable settings (Suggest);
fails_when=the 20th automatic action in an hour is held or the 21st is allowed, a row exactly
60 minutes old still counts, a duplicate request is recorded or accepted while its twin is open
or inside the cooldown, a later check wins over an earlier one, a timestamp is stored as a
string, or an unreadable setting is treated as Auto or Off;
no_claim=the exhaustive input table (test_autonomous_ops_gate.py), the never-touch list itself
(test_autonomous_ops_protected.py).
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import gate, ledger, notify, protected, settings
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_platform_stop, seed_tenant
from tests.test_autonomous_ops_gate import IP, _FlakyDb

NOW = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
OFF = {"master_shadow": False}


def _req(tenant="t1", *, actions=("block_ip",), targets=("a1",), ip=IP, key=None, **extra):
    return gate.ActionRequest(tenant_id=tenant, kind="security", origin="test", actions=list(actions),
                              targets=list(targets), params={"ip_address": ip} if ip else {},
                              dedupe_key=key or f"{tenant}|{'+'.join(actions)}|{ip}|{len(targets)}", **extra)


@pytest.fixture(autouse=True)
def _clear_cache():
    protected.cache_clear()
    yield
    protected.cache_clear()


@pytest.fixture
async def world(mongo_db):  # noqa: F811
    await ledger.ensure_indexes(mongo_db)
    await protected.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1", ip="198.51.100.11")
    await seed_agent(mongo_db, "t1", "a2", ip="198.51.100.12")
    return mongo_db


def _auto_row(n, created, **extra):
    return {"id": f"AO-seed-{n}", "tenantId": "t1", "kind": "security", "state": "executed", "autoDispatched": True,
            "createdAt": created, "updatedAt": created, "finishedAt": created, **extra}


# ---------------------------------------------------------------- blast radius and rate limit

async def test_host_cap_one_target_passes_two_escalate_zero_refuse(world):
    """Edge GATE-03 boundary (D-17): exactly 1 distinct target is automatic, 2 need approval,
    0 are refused; the same id twice is still one host."""
    one = await gate.decide(world, _req(), **OFF)
    assert (one.outcome, one.reason) == ("allow_auto", "class_auto")
    twice = await gate.decide(world, _req(targets=("a1", "a1"), key="dup-target"), **OFF)
    assert (twice.outcome, twice.reason) == ("allow_auto", "class_auto")
    two = await gate.decide(world, _req(targets=("a1", "a2"), key="two"), **OFF)
    assert (two.outcome, two.state, two.reason) == ("needs_approval", "awaiting_approval", "blast_radius")
    none = await gate.decide(world, _req(targets=(), key="none"), **OFF)
    assert (none.outcome, none.reason) == ("refuse", "no_target")


async def test_twentieth_automatic_action_in_the_hour_is_allowed_the_twenty_first_waits(world):
    """Edge GATE-03 boundary (D-20): shadow, control and 60-minute-old rows do not count; the
    window is strict greater-than on createdAt."""
    rows = [_auto_row(n, NOW - timedelta(minutes=10)) for n in range(19)]
    rows += [_auto_row("edge", NOW - timedelta(minutes=60)),                       # exactly 60 minutes: out
             {**_auto_row("shadow", NOW - timedelta(minutes=5)), "autoDispatched": False, "state": "shadow"},
             {**_auto_row("control", NOW - timedelta(minutes=5)), "kind": "control", "state": "recorded"}]
    await world.autonomy_actions.insert_many(rows)
    assert await ledger.count_auto_since(world, "t1", NOW - timedelta(minutes=60)) == 19

    twentieth = await gate.decide(world, _req(key="n20"), now=NOW, **OFF)
    assert (twentieth.outcome, twentieth.state) == ("allow_auto", "dispatching")
    twenty_first = await gate.decide(world, _req(key="n21"), now=NOW + timedelta(seconds=1), **OFF)
    assert (twenty_first.outcome, twenty_first.state, twenty_first.reason) == \
        ("needs_approval", "awaiting_approval", "rate_limit")
    # one millisecond inside the window still counts
    inside = _auto_row("inside", NOW + timedelta(seconds=1) - timedelta(minutes=60) + timedelta(milliseconds=1))
    await world.autonomy_actions.delete_many({})
    await world.autonomy_actions.insert_many([_auto_row(n, NOW - timedelta(minutes=10)) for n in range(19)] + [inside])
    held = await gate.decide(world, _req(key="n22"), now=NOW + timedelta(seconds=1), **OFF)
    assert held.reason == "rate_limit"


async def test_rate_limit_notice_is_sent_once_per_window(world):
    """T-81-46: two escalations in one window post one notice (platform feed plus the tenant's
    admins); a marker older than the window lets the next escalation post again."""
    await world.autonomy_actions.insert_many([_auto_row(n, NOW - timedelta(minutes=10)) for n in range(20)])
    spy = AsyncMock()
    with patch.object(notify, "notify", spy):
        for key in ("r1", "r2"):
            d = await gate.decide(world, _req(key=key), now=NOW, **OFF)
            assert d.reason == "rate_limit"
        assert spy.await_count == 1 and spy.await_args.args[1] == "t1"
        stored = await world.autonomy_settings.find_one({"tenantId": "t1"})
        assert stored["rateLimitNotifiedAt"] == NOW.replace(tzinfo=None)
        await settings.update(world, "t1", {"rateLimitNotifiedAt": NOW - timedelta(minutes=61)}, actor="test")
        await gate.decide(world, _req(key="r3"), now=NOW, **OFF)
        assert spy.await_count == 2
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$unset": {"rateLimitNotifiedAt": ""}})
    await gate.decide(world, _req(key="r4"), now=NOW, **OFF)      # the real notice path
    assert await world.notifications.count_documents({"tenantId": {"$in": ["platform-admin", "t1"]}}) == 2


async def test_notify_never_raises_and_posts_to_the_platform_and_the_tenant(world):
    await notify.notify(world, "t1", title="x", message="y", severity="info")
    assert {n["tenantId"] async for n in world.notifications.find({})} == {"platform-admin", "t1"}

    class _Broken:
        notifications = type("N", (), {"insert_one": AsyncMock(side_effect=RuntimeError("down"))})()

    assert await notify.notify(_Broken(), "t1", title="x", message="y") is None


# ---------------------------------------------------------------- dedupe, cooldown, undo suppression

async def test_a_twin_of_an_open_request_is_refused_and_not_recorded(world):
    """Edge GATE-03 adjacency (T-81-47): open twin refused duplicate with no new row; once the
    first is terminal the key is accepted again."""
    first = await gate.decide(world, _req(), **OFF)
    second = await gate.decide(world, _req(), **OFF)
    assert (second.outcome, second.reason, second.recorded) == ("refuse", "duplicate", False)
    assert await world.autonomy_actions.count_documents({"tenantId": "t1"}) == 1
    await ledger.transition(world, "t1", first.action_id, ("dispatching",), "executed")
    third = await gate.decide(world, _req(), **OFF)
    assert (third.outcome, third.recorded) == ("allow_auto", True)
    assert third.action_id != first.action_id


async def test_the_open_dedupe_index_catches_a_race_the_check_missed(world):
    without_check = tuple(s for s in gate._STEPS if s is not gate._step_dedupe)
    await gate.decide(world, _req(), **OFF)
    with patch.object(gate, "_STEPS", without_check):
        racer = await gate.decide(world, _req(), **OFF)
    assert (racer.outcome, racer.reason, racer.recorded) == ("refuse", "duplicate", False)
    assert await world.autonomy_actions.count_documents({"tenantId": "t1"}) == 1


async def test_a_simulation_younger_than_24_hours_blocks_the_same_request(world):
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": True}})
    first = await gate.decide(world, _req(), now=NOW, **OFF)
    assert (first.state, first.would_have) == ("shadow", "allow_auto")
    inside = await gate.decide(world, _req(), now=NOW + timedelta(hours=23, minutes=59), **OFF)
    assert (inside.outcome, inside.reason, inside.recorded) == ("refuse", "duplicate", False)
    after = await gate.decide(world, _req(), now=NOW + timedelta(hours=24, minutes=1), **OFF)
    assert (after.state, after.recorded) == ("shadow", True)


async def test_an_undone_action_is_not_repeated_for_24_hours(world):
    first = await gate.decide(world, _req(), **OFF)
    await ledger.transition(world, "t1", first.action_id, ("dispatching",), "undone",
                            **{"undo.undoneAt": datetime.now(timezone.utc)})
    suppressed = await gate.decide(world, _req(), **OFF)
    assert (suppressed.outcome, suppressed.reason, suppressed.recorded) == ("refuse", "suppressed_by_undo", False)
    later = await gate.decide(world, _req(), now=datetime.now(timezone.utc) + timedelta(hours=25), **OFF)
    assert (later.outcome, later.state) == ("allow_auto", "dispatching")


# ---------------------------------------------------------------- empty and invalid input

async def test_empty_requests_are_refused_and_write_nothing(world):
    """Edge GATE-03 empty: no tenant, no actions, undo-only or probe actions, no targets."""
    cases = [(_req(tenant=""), "no_tenant"), (_req(tenant=None), "no_tenant"),
             (_req(actions=()), "unregistered_action"), (_req(actions=("unblock_ip",)), "unregistered_action"),
             (_req(actions=("scan_ip",)), "unregistered_action"), (_req(targets=()), "no_target")]
    for request, code in cases:
        d = await gate.decide(world, request, **OFF)
        assert (d.outcome, d.reason) == ("refuse", code), code
    assert await world.agent_instructions.count_documents({}) == 0
    assert await world.response_tasks.count_documents({}) == 0
    assert await world.audit_logs.count_documents({"tenantId": None}) == 0


@pytest.mark.parametrize("bad", ["010.0.0.1", "not-an-ip", "198.51.100.0/24", "1.2.3", "", 167772161])
async def test_an_unparsable_ip_parameter_is_invalid_target(world, bad):
    """Edge GATE-08 precision: refused invalid_target, recorded, never matched as a string."""
    request = _req(key=f"bad-{bad}")
    request.params = {"ip_address": bad}
    d = await gate.decide(world, request, **OFF)
    assert (d.outcome, d.reason, d.recorded) == ("refuse", "invalid_target", True)


# ---------------------------------------------------------------- order of refusals and escalations

async def test_the_earliest_hard_refusal_in_gate_03_order_is_the_reason(world):
    """Edge GATE-03 ordering: platform_stop, tenant_stop, level_off, unregistered_action,
    protected_target, then (for an Off tenant) the same reason with nothing recorded."""
    await world.autonomy_settings.update_one(
        {"tenantId": "t1"}, {"$set": {"level": "off", "maxLevel": "off", "stop": {"active": True, "scope": "tenant"}}})
    await seed_platform_stop(world)
    request = _req(actions=("rm_rf",), ip="127.0.0.1")
    expected = []
    for step in ("platform_stop", "tenant_stop", "level_off", "unregistered_action", "protected_target"):
        d = await gate.decide(world, request, **OFF)
        expected.append(d.reason)
        if step == "platform_stop":
            await world.system_settings.delete_many({})
        elif step == "tenant_stop":
            await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": None}})
        elif step == "level_off":
            await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"level": "undoable_auto",
                                                                                 "maxLevel": "undoable_auto"}})
        else:
            request = _req(ip="127.0.0.1", key="last")
    assert expected == ["platform_stop", "tenant_stop", "level_off", "unregistered_action", "protected_target"]
    assert [r["reasonCode"] async for r in world.autonomy_actions.find({}).sort("createdAt", 1)] == \
        ["unregistered_action", "protected_target"]      # while the level is Off nothing is recorded


async def test_platform_stop_outranks_eligibility_but_an_unticked_tenant_still_leaves_no_row(world):
    await seed_tenant(world, "t3", ticked=False)
    await seed_platform_stop(world)
    d = await gate.decide(world, _req("t3"), **OFF)
    assert (d.outcome, d.reason, d.recorded) == ("refuse", "platform_stop", False)
    assert await world.autonomy_actions.count_documents({"tenantId": "t3"}) == 0
    assert await world.audit_logs.count_documents({"tenantId": "t3"}) == 0
    assert await world.notifications.count_documents({}) == 0


async def test_the_strongest_soft_escalation_wins(world):
    """Edge GATE-03 ordering: suggest over needs_approval over allow_auto; ties keep the first."""
    two_approve = _req(actions=("isolate_host",), targets=("a1", "a2"), ip=None)
    d = await gate.decide(world, two_approve, **OFF)
    assert (d.outcome, d.reason) == ("needs_approval", "class_approve")          # first of the two ties
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"level": "suggest"}})
    d = await gate.decide(world, _req(actions=("isolate_host",), targets=("a1", "a2"), ip=None, key="s"), **OFF)
    assert (d.outcome, d.state, d.reason) == ("suggest", "suggested", "level_suggest")
    forced = await gate.suggest(world, _req(key="forced"), **OFF)
    assert forced.outcome == "suggest"


# ---------------------------------------------------------------- precision and unreadable settings

async def test_timestamps_are_bson_datetimes_and_approval_expires_after_exactly_24_hours(world):
    """Edge GATE-03 precision (D-16)."""
    d = await gate.decide(world, _req(actions=("isolate_host",), ip=None), now=NOW, **OFF)
    assert d.state == "awaiting_approval"
    stored = await world.autonomy_actions.find_one({"id": d.action_id})
    for value in (stored["createdAt"], stored["updatedAt"], stored["approval"]["expiresAt"]):
        assert isinstance(value, datetime)
    assert stored["approval"]["expiresAt"] - stored["createdAt"] == timedelta(hours=24)
    assert await world.autonomy_actions.count_documents(
        {"createdAt": {"$type": "date"}, "updatedAt": {"$type": "date"}, "approval.expiresAt": {"$type": "date"}}) == 1
    audited = (await ledger.get(world, "t1", d.action_id))["createdAt"]
    assert audited == NOW and audited.tzinfo is not None


async def test_unreadable_settings_are_suggest_not_auto_and_not_off(world):
    """GATE-02 / D-23: a bad stored level, or a tenant document that cannot be read, is Suggest
    (recorded, nothing dispatched); a features list holding "all" is still not ticked."""
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"level": "bogus"}})
    d = await gate.decide(world, _req(), **OFF)
    assert (d.outcome, d.state, d.reason, d.recorded) == ("suggest", "suggested", "settings_unreadable", True)
    d = await gate.decide(_FlakyDb(world), _req(key="flaky"), **OFF)
    assert (d.outcome, d.state, d.would_have, d.recorded) == ("suggest", "shadow", "suggest", True)
    await world.tenants.update_one({"id": "t1"}, {"$set": {"enabledFeatures": ["all"]}})
    d = await gate.decide(world, _req(key="all"), **OFF)
    assert (d.outcome, d.reason, d.recorded) == ("refuse", "not_enabled", False)
    assert await world.agent_instructions.count_documents({}) == 0


def test_reason_codes_are_unique():
    assert len(set(gate.REASON_CODES)) == len(gate.REASON_CODES)


def test_the_steps_run_in_the_decision_order_with_agent_support_after_the_protected_targets():
    """Phase 83 (RESP-10): the dormancy step sits between the protected-target and blast-radius steps, so a
    host that cannot carry an action is refused before it can use up the rate limit."""
    assert [s.__name__ for s in gate._STEPS] == [
        "_step_platform_stop", "_step_eligibility", "_step_tenant_stop", "_step_level", "_step_class",
        "_step_protected_targets", "gate_step", "_step_blast_radius", "_step_dedupe", "_step_shadow"]
