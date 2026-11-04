"""The Autonomous Ops sweep and its parts (Phase 83, plan 83-01, RESP-01 / RESP-06).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the sweep only ever acts for a ticked, running tenant; hostnames resolve to one agent of
the same tenant or to nothing; an agent's result is cut down to whitelisted, bounded fields before it is
stored; a malformed setting reads as the safe default; fails_when=a stopped or Off tenant gets a row, a
shared hostname picks a host, an unknown outcome or an oversized list is stored, or a bad setting
raises; no_claim=a real agent (the contract examples stand in for it, see test_autonomous_ops_block_contract.py).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tenant_context
from autonomous_ops import agent_support, ledger, protected, response_settings, signals, sweep, verify
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import (seed_agent, seed_feed_ioc, seed_native_verdict, seed_platform_stop,
                                    seed_response_agent, seed_tenant)

IP = "45.33.32.156"
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


async def _world(db, tenant="t1", **kw):
    await ledger.ensure_indexes(db)
    await signals.ensure_indexes(db)
    await seed_tenant(db, tenant, shadow=False, **kw)
    await seed_response_agent(db, tenant, f"a-{tenant}", hostname=f"host-{tenant}", tokens=["block_ip_ttl"])
    await seed_native_verdict(db, tenant, f"host-{tenant}", kind="ip", target=IP)
    await seed_feed_ioc(db, ioc_type="url", value=f"http://{IP}/x", source_ip=IP, feed="urlhaus")


async def _rows(db, tenant):
    return [r async for r in db.autonomy_actions.find({"tenantId": tenant}, {"_id": 0})]


# ------------------------------------------------------------------ the tick decides who is swept

async def test_an_empty_database_ticks_cleanly(mongo_db):
    counts = await sweep.tick(mongo_db)
    assert counts["tenants"] == 0 and tenant_context.get_tenant_id() is None
    for name in await mongo_db.list_collection_names():
        assert await mongo_db[name].count_documents({}) == 0, name


async def test_one_tick_acts_once_per_ticked_tenant_and_leaves_the_context_clear(mongo_db):
    await _world(mongo_db, "t1")
    counts = await sweep.tick(mongo_db)
    assert counts["tenants"] == 1 and counts["blocked"] == 1
    assert len(await _rows(mongo_db, "t1")) == 1 and tenant_context.get_tenant_id() is None


async def test_a_failing_stage_does_not_skip_the_later_stages(mongo_db, monkeypatch):
    """83 WR-07: protects=restarts and the isolation revert bookkeeping keep running for a tenant whose
    security stage raises; fails_when=one exception ends the tenant's whole tick; no_claim=why it raised."""
    await _world(mongo_db, "t1")
    ran = []

    async def broken(db, tenant_id, tenant, response, now):
        raise RuntimeError("a malformed signal document")

    async def later(db, tenant_id, tenant, response, now):
        ran.append(tenant_id)
        return {"later": 1}

    monkeypatch.setattr(sweep, "_STAGES", (broken, later))
    counts = await sweep.tick(mongo_db)
    assert ran == ["t1"] and counts["later"] == 1 and tenant_context.get_tenant_id() is None


@pytest.mark.parametrize("kw", [{"ticked": False}, {"level": "off"}, {"stop": {"active": True}}])
async def test_an_unticked_off_or_stopped_tenant_gets_nothing(mongo_db, kw):
    await _world(mongo_db, "t1", **kw)
    await sweep.tick(mongo_db)
    assert await _rows(mongo_db, "t1") == [] and await mongo_db.agent_instructions.count_documents({}) == 0


async def test_the_platform_stop_makes_the_pass_do_nothing(mongo_db):
    await _world(mongo_db, "t1")
    await seed_platform_stop(mongo_db)
    await sweep.tick(mongo_db)
    assert await _rows(mongo_db, "t1") == []


async def test_the_platform_tenant_is_never_swept(mongo_db):
    await _world(mongo_db, "platform-admin")
    await sweep.tick(mongo_db)
    assert await _rows(mongo_db, "platform-admin") == []


async def test_a_second_tick_repeats_nothing(mongo_db):
    await _world(mongo_db, "t1")
    for _ in range(3):
        await sweep.tick(mongo_db)
    assert len(await _rows(mongo_db, "t1")) == 1 and await mongo_db.agent_instructions.count_documents({}) == 1


# ------------------------------------------------------------------ signals

def test_resolve_picks_one_agent_by_id_or_casefolded_hostname_and_none_when_shared():
    agents = [{"id": "a1", "hostname": "Host-One"}, {"id": "a2", "hostname": "host-two"},
              {"id": "a3", "hostname": "DUP"}, {"id": "a4", "hostname": "dup"}]
    index = signals.index_agents(agents)
    assert signals.resolve(index, "a1")["id"] == "a1"
    assert signals.resolve(index, "host-one")["id"] == "a1" and signals.resolve(index, "HOST-ONE")["id"] == "a1"
    assert signals.resolve(index, "Host-Two")["id"] == "a2"
    assert signals.resolve(index, "dup") is None and signals.resolve(index, "DUP") is None
    assert signals.resolve(index, "nobody") is None and signals.resolve(index, "") is None
    assert signals.resolve(index, None) is None


def _doc(**origins):
    return {"origins": {k: {"firstSeenAt": v} for k, v in origins.items()}}


def test_corroborated_needs_two_origins_within_a_day_unless_one_is_enough():
    assert signals.corroborated(_doc(native=NOW, **{"feed:urlhaus": NOW + timedelta(hours=24)}), two_signal=True)
    assert not signals.corroborated(_doc(native=NOW, **{"feed:urlhaus": NOW + timedelta(hours=24, seconds=1)}),
                                    two_signal=True)
    assert not signals.corroborated(_doc(native=NOW), two_signal=True)
    assert signals.corroborated(_doc(native=NOW), two_signal=False)
    assert not signals.corroborated({"origins": {}}, two_signal=False)


async def test_observe_keeps_the_first_sighting_and_moves_the_last(mongo_db):
    await _world(mongo_db, "t1")
    agents = await signals.agents_of(mongo_db, "t1")
    first = await signals.observe(mongo_db, "t1", agents, NOW)
    later = await signals.observe(mongo_db, "t1", agents, NOW + timedelta(hours=2))
    assert [c.indicator for c in first] == [IP] and set(first[0].origins) == {"native", "feed:urlhaus"}
    native = later[0].origins["native"]
    assert native["firstSeenAt"] == NOW and native["lastSeenAt"] == NOW + timedelta(hours=2)
    assert await mongo_db.autonomy_signals.count_documents({}) == 1


async def test_observe_ignores_private_and_loopback_and_unparsable_addresses(mongo_db):
    await _world(mongo_db, "t1")
    await mongo_db.security_scan_results.delete_many({})
    for bad in ("203.0.113.5", "10.1.2.3", "127.0.0.1", "010.1.1.1", "not-an-ip", "45.33.32.156/32"):
        await seed_native_verdict(mongo_db, "t1", "host-t1", kind="ip", target=bad)
    agents = await signals.agents_of(mongo_db, "t1")
    assert await signals.observe(mongo_db, "t1", agents, NOW) == []


async def test_observe_never_reads_another_tenants_rows_or_tenant_feed_rows(mongo_db):
    await _world(mongo_db, "t1")
    await mongo_db.edr_ioc.delete_many({})
    await mongo_db.edr_ioc.insert_one({"tenantId": "t1", "ioc_type": "url", "ioc_value": "x", "source_ip": IP,
                                       "source_feed": "urlhaus", "updated_at": NOW.isoformat()})   # a tenant row
    agents = await signals.agents_of(mongo_db, "t1")
    (cand,) = await signals.observe(mongo_db, "t1", agents, NOW)
    assert set(cand.origins) == {"native"}


async def test_remember_stores_the_decision_on_the_signal(mongo_db):
    await _world(mongo_db, "t1")
    agents = await signals.agents_of(mongo_db, "t1")
    (cand,) = await signals.observe(mongo_db, "t1", agents, NOW)
    key = {"tenantId": "t1", "agentId": cand.agent_id, "kind": "ip", "indicator": IP}
    await signals.remember(mongo_db, key, {"actionId": "AO-1", "at": NOW, "outcome": "blocked"})
    (again,) = await signals.observe(mongo_db, "t1", agents, NOW)
    assert again.decision["actionId"] == "AO-1" and again.decision["outcome"] == "blocked"


# ------------------------------------------------------------------ agent support

@pytest.mark.real_agent_capabilities       # conftest otherwise switches every capability on
async def test_check_names_the_first_reason_a_host_cannot_act(mongo_db):
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_response_agent(mongo_db, "t1", "a1", hostname="h1", tokens=["block_ip_ttl"], capable=False)
    agent = (await signals.agents_of(mongo_db, "t1"))[0]
    assert await agent_support.check(mongo_db, "t1", agent, "block_ip", now=NOW) == "capability_off"
    await mongo_db.tenants.update_one({"id": "t1"}, {"$set": {"agentCapabilities": ["all"]}})
    live = datetime.now(timezone.utc)
    assert await agent_support.check(mongo_db, "t1", agent, "block_ip", now=live) is None
    assert await agent_support.check(mongo_db, "t1", agent, "block_ip", now=live + timedelta(minutes=6)) == "agent_offline"
    assert await agent_support.check(mongo_db, "t1", dict(agent, status="offline"), "block_ip", now=live) == "agent_offline"
    assert await agent_support.check(mongo_db, "t1", dict(agent, lastSeen=None), "block_ip", now=live) == "agent_offline"
    assert await agent_support.check(mongo_db, "t1", dict(agent, lastSeen="garbage"), "block_ip", now=live) == "agent_offline"
    assert await agent_support.check(mongo_db, "t1", agent, "quarantine_file", now=live) == "agent_unsupported"
    assert await agent_support.check(mongo_db, "t1", agent, "block_ip", now=live) is None


def test_token_helpers_read_the_contract():
    assert agent_support.token_for("block_ip") == "block_ip_ttl" and agent_support.token_for("unblock_ip") == "block_ip_ttl"
    assert agent_support.token_for("kill_process") == "kill_process_exe" and agent_support.token_for("nope") is None
    assert agent_support.tokens_of({"meta": {"response_actions": {"tokens": ["a", "b", 3]}}}) == {"a", "b"}
    assert agent_support.tokens_of({}) == set() and agent_support.tokens_of({"meta": {"response_actions": "x"}}) == set()
    assert agent_support.CONTRACT["version"] == 1


# ------------------------------------------------------------------ response settings

async def test_response_settings_default_to_on_and_a_day_and_never_raise(mongo_db):
    s = await response_settings.load(mongo_db, "t1")
    assert (s.two_signal, s.block_hours, s.watched_services, s.readable) == (True, 24, [], True)
    assert response_settings.DEFAULT_TWO_SIGNAL is True and response_settings.DEFAULT_BLOCK_HOURS == 24
    await mongo_db.autonomy_settings.insert_one({"tenantId": "t1", "response": {"twoSignal": False, "blockHours": 48,
                                                                                "watchedServices": ["nginx"]}})
    s = await response_settings.load(mongo_db, "t1")
    assert (s.two_signal, s.block_hours, s.watched_services, s.readable) == (False, 48, ["nginx"], True)
    for bad in ({"twoSignal": "no"}, {"blockHours": 0}, {"blockHours": 169}, {"blockHours": True},
                {"watchedServices": "nginx"}, {"blockHours": "24"}):
        await mongo_db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"response": bad}})
        s = await response_settings.load(mongo_db, "t1")
        assert s.readable is False and s.two_signal is True and s.block_hours == 24 and s.watched_services == []


# ------------------------------------------------------------------ the stored result is bounded

def test_bounded_result_keeps_only_whitelisted_fields_inside_their_ranges():
    nested = {"status": "success", "outcome": "applied", "verify": {"ok": True, "check": "firewall_rule_present"},
              "expires_in": 86400, "healthy_after": 30, "script": "curl x | sh", "message": "m",
              "still_running": [{"pid": 4242, "name": "evil.exe", "start_time": 1761900000}]}
    got = verify.bounded_result(nested)
    assert got == {"outcome": "applied", "verify": {"ok": True, "check": "firewall_rule_present"}, "expires_in": 86400,
                   "healthy_after": 30, "still_running": [{"pid": 4242, "name": "evil.exe", "start_time": 1761900000}]}
    assert verify.bounded_result({}) == {} and verify.bounded_result(None) == {} and verify.bounded_result("x") == {}


@pytest.mark.parametrize("bad", [
    {"outcome": "rm -rf"}, {"outcome": 7}, {"outcome": ["applied"]},
    {"verify": {"ok": "yes", "check": "firewall_rule_present"}}, {"verify": {"ok": True, "check": "nope"}},
    {"verify": "ok"}, {"expires_in": -1}, {"expires_in": 604801}, {"expires_in": True}, {"expires_in": "5"},
    {"healthy_after": 3601}, {"healthy_after": -2}, {"still_running": "all"}])
def test_bounded_result_drops_a_value_outside_its_range(bad):
    assert verify.bounded_result(bad) == {}


def test_bounded_result_caps_the_list_and_drops_bad_entries():
    good = {"pid": 5, "name": "a", "start_time": 10}
    entries = [good] * 130 + [{"pid": 1, "name": "init", "start_time": 5}, {"pid": 7, "name": "x" * 129, "start_time": 5},
                              {"pid": 7, "name": "y", "start_time": 0}, {"pid": "7", "name": "y", "start_time": 5},
                              {"pid": 7, "name": "y"}, "string", None]
    got = verify.bounded_result({"still_running": entries})["still_running"]
    assert len(got) == 128 and all(e == good for e in got)
    assert verify.bounded_result({"still_running": [{"pid": 1, "name": "init", "start_time": 5}]}) == {"still_running": []}
    assert json.dumps(verify.bounded_result({"still_running": entries}))      # serialisable


# ------------------------------------------------------------------ one runner, a lost lock, a crash (Task 2)

async def test_only_one_sweep_runner_ticks_at_a_time(mongo_db):
    """Edge RESP-01 concurrency: lock autonomous_ops_sweep through lock_with_renewal."""
    import asyncio
    from unittest.mock import patch
    assert sweep.LOCK_NAME == "autonomous_ops_sweep"
    entered = []

    async def slow(db, *, now=None, lost=None):
        entered.append(1)
        await asyncio.sleep(0.4)
        return {"tenants": 0}

    with patch.object(sweep, "tick", slow):
        results = await asyncio.gather(sweep.run_once(mongo_db), sweep.run_once(mongo_db))
    assert len(entered) == 1 and results.count(None) == 1
    with patch.object(sweep, "tick", slow):
        assert await sweep.run_once(mongo_db) is not None                 # released, so the next runner proceeds
    assert await mongo_db["_distributed_locks"].count_documents({"_id": sweep.LOCK_NAME}) == 0


async def test_a_held_sweep_lock_makes_run_once_return_none_and_touch_nothing(mongo_db):
    from types import SimpleNamespace
    from distributed_lock import acquire_lock
    await _world(mongo_db, "t1")
    assert await acquire_lock(SimpleNamespace(_db=mongo_db), sweep.LOCK_NAME, ttl_seconds=30)
    assert await sweep.run_once(mongo_db) is None
    assert await _rows(mongo_db, "t1") == []


async def test_a_lost_lock_stops_the_sweep_between_tenants(mongo_db):
    for tenant in ("t-a", "t-b"):
        await _world(mongo_db, tenant)
    polls = iter([False, True, True])
    counts = await sweep.tick(mongo_db, lost=lambda: next(polls))
    assert counts["tenants"] == 1
    assert len(await _rows(mongo_db, "t-a")) == 1 and await _rows(mongo_db, "t-b") == []


async def test_a_stage_that_fails_for_one_tenant_does_not_stop_the_next(mongo_db, caplog):
    from unittest.mock import patch
    for tenant in ("t-a", "t-b"):
        await _world(mongo_db, tenant)
    real = sweep.sweep_security.run

    async def flaky(db, tenant_id, tenant, response, now):
        if tenant_id == "t-a":
            raise RuntimeError("boom")
        return await real(db, tenant_id, tenant, response, now)

    with patch.object(sweep, "_STAGES", (flaky,)), caplog.at_level("ERROR"):
        await sweep.tick(mongo_db)
    assert await _rows(mongo_db, "t-a") == [] and len(await _rows(mongo_db, "t-b")) == 1
    assert "t-a" in caplog.text and tenant_context.get_tenant_id() is None


async def test_a_crash_between_decide_and_execute_ends_as_not_delivered(mongo_db):
    """Edge RESP-01: a dispatching row with no instruction is ended by the reconciler after the stuck bound."""
    from unittest.mock import AsyncMock, patch
    from autonomous_ops import reconciler, response_dispatch
    await _world(mongo_db, "t1")
    with patch.object(response_dispatch, "send", AsyncMock(side_effect=RuntimeError("crashed"))):
        await sweep.tick(mongo_db)
    (row,) = await _rows(mongo_db, "t1")
    assert row["state"] == "dispatching" and row["instructionIds"] == []
    assert await mongo_db.agent_instructions.count_documents({}) == 0
    later = datetime.now(timezone.utc) + timedelta(minutes=31)
    await reconciler.tick(mongo_db, now=later)
    done = (await _rows(mongo_db, "t1"))[0]
    assert (done["state"], done["reasonCode"]) == ("failed", "not_delivered")


def test_the_loop_reads_its_interval_from_the_environment(monkeypatch):
    assert sweep._interval() == 60
    monkeypatch.setenv("AUTONOMOUS_OPS_SWEEP_INTERVAL_SEC", "5")
    assert sweep._interval() == 5
    monkeypatch.setenv("AUTONOMOUS_OPS_SWEEP_INTERVAL_SEC", "x")
    assert sweep._interval() == 60


async def test_the_loop_survives_a_failing_pass_and_keeps_going(monkeypatch):
    import asyncio
    from unittest.mock import patch
    calls = []

    async def flaky(db, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("down")
        raise asyncio.CancelledError

    monkeypatch.setenv("AUTONOMOUS_OPS_SWEEP_INTERVAL_SEC", "0.01")
    with patch("database.get_database", lambda: object()), patch.object(sweep, "run_once", flaky):
        with pytest.raises(asyncio.CancelledError):
            await sweep.sweep_loop()
    assert len(calls) == 2


def test_the_backend_starts_the_sweep_beside_the_reconciler():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app_startup.py"),
               encoding="utf-8").read()
    assert "sweep_loop" in src and '"autonomous_ops_sweep"' in src
    assert src.index("autonomous_ops_reconciler") < src.index("autonomous_ops_sweep")
