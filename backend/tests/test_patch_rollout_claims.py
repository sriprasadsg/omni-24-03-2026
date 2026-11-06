"""Staged patch rollouts, plan 84-06 task 2: the check before Start, and the atomic claim.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; time is frozen by
passing ``now``.

Value: protects=PTCH-01 / PTCH-05 / PTCH-07: Start names every blocker (no window, no canary computer, no canary
computer for an operating system, Autonomous Ops off, a stop, nothing to install, too many computers), lists every
computer that was left out and why, never claims a computer twice, and never claims the platform's own computers
or a never-touch computer; fails_when=a rollout starts with a blocker, a computer is dropped without a reason,
two rollouts hold one computer, a platform or never-touch computer is claimed, or a failed Start leaves a claim
behind; no_claim=the HTTP route (plan 84-09) and the controller (tests/test_patch_rollout_tracer.py).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import PLATFORM_TENANT_ID, ledger, protected
from autonomous_ops.rollout import messages, start, store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import (seed_group, seed_rings, seed_rollout_agent, seed_rollout_tenant, seed_window)

T = "t1"
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
BOOT = 1_700_000_000
TOKENS = ("reboot_host", "patch_reversible_check")
ACTOR = {"id": "u1", "name": "Ann"}
RINGS = [{"key": "canary", "name": "Canary", "groupIds": ["G1"], "soakHours": 1},
         {"key": "pilot", "name": "Pilot", "groupIds": ["G2"], "soakHours": 1},
         {"key": "rest", "name": "Everyone else", "groupIds": [], "soakHours": 1}]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


def hhmm(moment):
    return moment.strftime("%H:%M")


async def agent(db, agent_id, *, platform="Linux", pending=("openssl",), tokens=TOKENS, boot=BOOT, seen=NOW,
                tenant=T, group=None):
    await seed_rollout_agent(db, tenant, agent_id, hostname=f"host-{agent_id}", platform=platform,
                             tokens=tokens, pending=list(pending), boot_time=boot, last_seen=seen)
    if group:
        await db.agent_group_members.replace_one({"group_id": group, "agent_id": agent_id},
                                                 {"group_id": group, "agent_id": agent_id, "tenantId": tenant},
                                                 upsert=True)


async def world(db, *, window=True, rings=True):
    """A ticked tenant, three rings (Canary G1, Pilot G2, the rest), an open window; no computers yet."""
    await ledger.ensure_indexes(db)
    await store.ensure_indexes(db)
    await seed_rollout_tenant(db, T)
    for group in ("G1", "G2"):
        await seed_group(db, T, group, [])
    await db.agent_groups.update_one({"id": "G1"}, {"$set": {"name": "Canary"}})
    if rings:
        await seed_rings(db, T, RINGS)
    if window:
        await seed_window(db, T, start=hhmm(NOW - timedelta(hours=1)), end=hhmm(NOW + timedelta(hours=3)))
    return db


async def basic(db):
    """One Linux computer in each of the first two rings and two ungrouped ones."""
    await world(db)
    await agent(db, "a1", group="G1")
    await agent(db, "a2", group="G2")
    await agent(db, "a3")
    await agent(db, "a4")
    return db


def row(out, check):
    return [r for r in out["rows"] if r["check"] == check]


def blockers(out):
    return [r for r in out["rows"] if r["blocker"]]


async def active_claims(db):
    return [c async for c in db.patch_rollout_hosts.find({"tenantId": T, "active": True}, {"_id": 0})]


async def pre(db, ids=("openssl",), tenant=T):
    return await start.preflight(db, tenant, list(ids), now=NOW)


async def go(db, ids=("openssl",), name="Nov"):
    return await start.start_rollout(db, T, name=name, patch_ids=list(ids), actor=ACTOR, now=NOW)


# ---------------------------------------------------------------- the happy check

async def test_a_ready_tenant_gets_ok_rows_in_the_documented_order_and_can_start(mongo_db):
    db = await basic(mongo_db)
    out = await pre(db)
    assert [r["check"] for r in out["rows"]] == ["window", "rings", "canary"]
    assert out["canStart"] is True and out["firstBlocker"] is None and blockers(out) == []
    assert all(r["ok"] for r in out["rows"]) and out["nextWindowText"]
    assert row(out, "window")[0]["detail"].startswith("Next window: ")
    assert row(out, "rings")[0]["detail"] == "4 computers in 3 rings: Canary 1, Pilot 1, Everyone else 2."
    assert row(out, "canary")[0]["detail"] == "The canary ring has a Linux computer."
    assert row(out, "canary")[0]["title"] == messages.PREFLIGHT["titles"]["canary"]


async def test_start_claims_every_eligible_computer_in_the_ring_it_belongs_to_and_records_nothing_else(mongo_db):
    db = await basic(mongo_db)
    out = await go(db)
    assert out["status"] == "started" and sorted(out["claimed"]) == ["a1", "a2", "a3", "a4"] and out["leftOut"] == []
    rings_of = {c["agentId"]: c["ring"] for c in await active_claims(db)}
    assert rings_of == {"a1": 0, "a2": 1, "a3": 2, "a4": 2}
    rollout = await db.patch_rollouts.find_one({"id": out["rolloutId"]})
    assert rollout["leftOut"] == [] and [r["name"] for r in rollout["rings"]] == ["Canary", "Pilot", "Everyone else"]


# ---------------------------------------------------------------- blockers

async def test_no_window_blocks_with_the_window_sentence_and_start_claims_nothing(mongo_db):
    db = await basic(mongo_db)
    await db.maintenance_windows.delete_many({})
    out = await pre(db)
    assert out["canStart"] is False and out["firstBlocker"] == messages.PREFLIGHT["window_blocker"]
    window = row(out, "window")[0]
    assert window["blocker"] and window["detail"] == "Add a maintenance window first." and window["link"] == "maintenance"
    with pytest.raises(start.PreflightBlocked) as caught:
        await go(db)
    assert any(r["check"] == "window" and r["blocker"] for r in caught.value.rows)
    assert await active_claims(db) == [] and await db.patch_rollouts.count_documents({}) == 0


async def test_an_unreadable_window_row_blocks_the_same_way(mongo_db):
    db = await basic(mongo_db)
    await db.maintenance_windows.update_many({}, {"$set": {"startTime": "garbage"}})
    out = await pre(db)
    assert out["canStart"] is False and row(out, "window")[0]["blocker"]


async def test_rings_not_saved_or_canary_without_computers_block_with_the_rings_link(mongo_db):
    db = await basic(mongo_db)
    await db.patch_rollout_settings.delete_many({})
    out = await pre(db)
    ring = row(out, "rings")[0]
    assert ring["blocker"] and ring["detail"] == messages.PREFLIGHT["rings_not_set"] and ring["link"] == "rings"
    await seed_rings(db, T, RINGS)
    await db.agent_group_members.delete_many({"group_id": "G1"})
    ring = row(await pre(db), "rings")[0]
    assert ring["blocker"] and ring["detail"] == messages.PREFLIGHT["canary_empty"] and ring["link"] == "rings"
    with pytest.raises(start.PreflightBlocked):
        await go(db)


async def test_a_canary_group_that_was_deleted_blocks_a_new_rollout(mongo_db):
    db = await basic(mongo_db)
    await db.agent_groups.delete_one({"id": "G1"})                   # the members stay behind in the database
    out = await pre(db)
    assert row(out, "rings")[0]["detail"] == messages.PREFLIGHT["canary_empty"] and out["canStart"] is False


async def test_the_canary_needs_a_computer_for_each_operating_system_in_the_selection(mongo_db):
    db = await world(mongo_db)
    await agent(db, "w1", platform="Windows 11", pending=("KB5034441",), group="G1")
    await agent(db, "l1", pending=("openssl",), group="G2")
    out = await pre(db, ("KB5034441", "openssl"))
    canary = row(out, "canary")
    assert [(r["ok"], r["detail"]) for r in canary] == [
        (True, "The canary ring has a Windows computer."),
        (False, "The canary ring has no Linux host; add one to the Canary group.")]
    assert canary[1]["blocker"] and canary[1]["link"] == "agentGroups"
    assert out["canStart"] is False and out["firstBlocker"] == canary[1]["detail"]
    with pytest.raises(start.PreflightBlocked):
        await start.start_rollout(db, T, name="x", patch_ids=["KB5034441", "openssl"], actor=ACTOR, now=NOW)
    assert (await pre(db, ("KB5034441",)))["canStart"] is True        # only the Windows patch: no gap


async def test_a_canary_ring_with_several_groups_says_a_group_in_the_canary_ring(mongo_db):
    db = await world(mongo_db)
    await seed_rings(db, T, [{**RINGS[0], "groupIds": ["G1", "G2"]}, {**RINGS[2]}])
    await agent(db, "w1", platform="Windows 11", pending=("KB5034441",), group="G1")
    await agent(db, "l1", pending=("openssl",))
    text = row(await pre(db, ("KB5034441", "openssl")), "canary")[1]["detail"]
    assert text == "The canary ring has no Linux host; add one to a group in the canary ring."


async def test_autonomous_ops_off_or_not_ticked_blocks(mongo_db):
    db = await basic(mongo_db)
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"level": "off"}})
    out = await pre(db)
    assert row(out, "autonomous_ops")[0]["detail"] == messages.PREFLIGHT["autonomy_off"] and out["canStart"] is False
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"level": "undoable_auto"}})
    assert (await pre(db))["canStart"] is True
    await db.tenants.update_one({"id": T}, {"$set": {"enabledFeatures": ["view:overview"]}})
    assert row(await pre(db), "autonomous_ops")[0]["blocker"]
    with pytest.raises(start.PreflightBlocked):
        await go(db)


async def test_a_stop_blocks_whether_it_is_the_tenants_or_the_whole_platforms(mongo_db):
    db = await basic(mongo_db)
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"stop": {"active": True}}})
    out = await pre(db)
    assert row(out, "stopped")[0]["detail"] == messages.PREFLIGHT["stopped"] and out["canStart"] is False
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"stop": None}})
    assert (await pre(db))["canStart"] is True
    await db.system_settings.insert_one({"type": "autonomous_ops", "stop": {"active": True}})
    assert row(await pre(db), "stopped")[0]["blocker"]


async def test_nothing_selected_or_nothing_pending_blocks_with_the_patches_row(mongo_db):
    db = await basic(mongo_db)
    out = await pre(db, ())
    assert row(out, "patches")[0]["detail"] == messages.VALIDATION["patches"] and out["canStart"] is False
    out = await pre(db, ("curl",))
    assert row(out, "patches")[0]["detail"] == messages.PREFLIGHT["nothing_pending"]
    with pytest.raises(start.PreflightBlocked):
        await go(db, ("curl",))
    assert await db.patch_rollouts.count_documents({}) == 0


async def test_more_computers_than_the_cap_block(mongo_db, monkeypatch):
    db = await basic(mongo_db)
    monkeypatch.setattr(start, "MAX_HOSTS_PER_ROLLOUT", 3)
    out = await pre(db)
    assert row(out, "cap")[0]["detail"] == messages.PREFLIGHT["cap"] and out["canStart"] is False
    monkeypatch.setattr(start, "MAX_HOSTS_PER_ROLLOUT", 4)
    assert (await pre(db))["canStart"] is True


# ---------------------------------------------------------------- left out, never silently dropped

async def test_a_computer_in_another_active_rollout_is_left_out_with_that_rollouts_name(mongo_db):
    db = await basic(mongo_db)
    await agent(db, "h3", group="G2")
    await agent(db, "h5", group="G2")
    await agent(db, "h6", group="G2")
    await db.patch_rollouts.insert_one({"id": "R0", "tenantId": T, "name": "November security", "status": "running"})
    await store.claim_hosts(db, T, "R0", [{"agentId": a, "ring": 1, "state": "waiting"} for a in ("h3", "h5", "h6")])
    out = await pre(db)
    left = row(out, "left_out")
    assert [r["detail"] for r in left] == ['3 hosts are in "November security" and were left out.']
    assert left[0]["ok"] is True and left[0]["blocker"] is False and left[0]["hostTotal"] == 3
    assert sorted(left[0]["hosts"]) == ["host-h3", "host-h5", "host-h6"]
    assert out["canStart"] is True
    started = await go(db)
    assert started["status"] == "started" and sorted(started["claimed"]) == ["a1", "a2", "a3", "a4"]
    stored = (await db.patch_rollouts.find_one({"id": started["rolloutId"]}))["leftOut"]
    assert sorted((l["agentId"], l["reason"], l["rolloutName"]) for l in stored) == [
        ("h3", "in_rollout", "November security"), ("h5", "in_rollout", "November security"),
        ("h6", "in_rollout", "November security")]
    assert all(l["hostname"] == f"host-{l['agentId']}" for l in stored)


async def test_one_computer_left_out_reads_in_the_singular(mongo_db):
    db = await basic(mongo_db)
    await agent(db, "h3", group="G2")
    await db.patch_rollouts.insert_one({"id": "R0", "tenantId": T, "name": "Nov", "status": "halted"})
    await store.claim_hosts(db, T, "R0", [{"agentId": "h3", "ring": 1, "state": "waiting"}])
    assert row(await pre(db), "left_out")[0]["detail"] == '1 host is in "Nov" and was left out.'


async def test_computers_that_cannot_take_a_rollout_are_listed_with_their_reason_and_never_claimed(mongo_db):
    db = await basic(mongo_db)
    await agent(db, "old", tokens=(), group="G2")                          # no reboot_host token
    await agent(db, "noboot", boot=None, group="G2")                       # no boot time
    await agent(db, "mac", platform="macOS 14", group="G2")
    await agent(db, "busy", group="G2")
    await agent(db, "touch", group="G2")
    await db.patch_deployment_jobs.insert_one({"id": "J1", "tenantId": T, "status": "In Progress",
                                               "dispatchedAgents": ["busy"], "agentResults": {}})
    await protected.add_entry(db, scope="tenant", tenant_id=T, kind="agent", value="touch", note="n",
                              actor={"username": "u"})
    out = await pre(db)
    reasons = {}
    for r in row(out, "left_out"):
        for name in r["hosts"]:
            reasons[name] = r["detail"]
    assert reasons == {"host-old": messages.CANNOT_TAKE["agent_too_old"],
                       "host-noboot": messages.CANNOT_TAKE["agent_too_old"],
                       "host-mac": messages.CANNOT_TAKE["unsupported_os"],
                       "host-busy": messages.CANNOT_TAKE["busy"],
                       "host-touch": messages.CANNOT_TAKE["never_touch"]}
    assert out["canStart"] is True
    started = await go(db)
    assert sorted(started["claimed"]) == ["a1", "a2", "a3", "a4"]
    stored = {l["agentId"]: l["reason"] for l in (await db.patch_rollouts.find_one({"id": started["rolloutId"]}))["leftOut"]}
    assert stored == {"old": "agent_too_old", "noboot": "agent_too_old", "mac": "unsupported_os", "busy": "busy",
                      "touch": "never_touch"}


async def test_a_job_that_already_reported_does_not_make_a_computer_busy(mongo_db):
    db = await basic(mongo_db)
    await db.patch_deployment_jobs.insert_one({"id": "J1", "tenantId": T, "status": "In Progress",
                                               "dispatchedAgents": ["a3"], "agentResults": {"a3": {"status": "completed"}}})
    assert row(await pre(db), "left_out") == []


async def test_a_tenant_whose_patch_installer_is_not_ticked_has_every_computer_left_out(mongo_db):
    db = await basic(mongo_db)
    await db.tenants.update_one({"id": T}, {"$set": {"agentCapabilities": ["remote_access"]}})
    out = await pre(db)
    left = row(out, "left_out")
    assert [r["detail"] for r in left] == [messages.CANNOT_TAKE["capability_off"]] and left[0]["hostTotal"] == 4
    assert out["canStart"] is False and row(out, "patches")[0]["blocker"]


async def test_an_offline_computer_is_still_in_the_rollout_and_is_counted_in_the_offline_row(mongo_db):
    db = await basic(mongo_db)
    await agent(db, "off", seen=NOW - timedelta(days=1), group="G2")
    out = await pre(db)
    assert [r["detail"] for r in row(out, "offline")] == [messages.offline_now(1)] and out["canStart"] is True
    assert row(out, "offline")[0]["hosts"] == ["host-off"]
    assert "off" in (await go(db))["claimed"]


async def test_a_platform_computer_under_a_customer_group_is_never_claimed(mongo_db):
    db = await basic(mongo_db)
    await agent(db, "plat", tenant=PLATFORM_TENANT_ID)
    await db.agent_group_members.replace_one({"group_id": "G2", "agent_id": "plat"},
                                             {"group_id": "G2", "agent_id": "plat", "tenantId": T}, upsert=True)
    out = await go(db)
    assert "plat" not in out["claimed"] and not any(c["agentId"] == "plat" for c in await active_claims(db))
    assert await db.patch_rollout_hosts.count_documents({"agentId": "plat"}) == 0


async def test_the_platform_tenant_is_refused_and_its_check_cannot_start(mongo_db):
    db = await basic(mongo_db)
    out = await start.start_rollout(db, PLATFORM_TENANT_ID, name="x", patch_ids=["openssl"], actor=ACTOR, now=NOW)
    assert out == {"status": "refused", "reason": "platform_tenant"}
    assert (await start.preflight(db, PLATFORM_TENANT_ID, ["openssl"], now=NOW))["canStart"] is False
    assert await db.patch_rollouts.count_documents({}) == 0


# ---------------------------------------------------------------- atomic claims

async def test_two_starts_at_once_claim_each_computer_once_and_the_loser_holds_nothing(mongo_db):
    db = await world(mongo_db)
    await agent(db, "a1", group="G1")
    for n in range(2, 9):
        await agent(db, f"a{n}", group="G2" if n < 4 else None)
    results = await asyncio.gather(go(db, name="One"), go(db, name="Two"), return_exceptions=True)
    won = [r for r in results if isinstance(r, dict)]
    lost = [r for r in results if isinstance(r, start.AlreadyInRollout)]
    assert len(won) == 1 and len(lost) == 1, results
    claims = await active_claims(db)
    assert len(claims) == 8 and len({c["agentId"] for c in claims}) == 8
    assert {c["rolloutId"] for c in claims} == {won[0]["rolloutId"]}
    assert await db.patch_rollouts.count_documents({}) == 1
    assert await db.patch_rollout_hosts.count_documents({"rolloutId": {"$ne": won[0]["rolloutId"]}}) == 0


async def test_a_start_that_loses_a_race_midway_releases_what_it_claimed(mongo_db, monkeypatch):
    db = await basic(mongo_db)
    real = store.claim_hosts
    seen = []

    async def rival(db_, tenant, rollout_id, docs):
        seen.append(docs[0]["agentId"])
        if len(seen) == 3:                                  # a rival takes a computer just before this start does
            await real(db_, tenant, "RIVAL", [dict(docs[0])])
        return await real(db_, tenant, rollout_id, docs)

    monkeypatch.setattr(start.store, "claim_hosts", rival)
    with pytest.raises(start.AlreadyInRollout):
        await go(db)
    mine = [c async for c in db.patch_rollout_hosts.find({"tenantId": T, "rolloutId": {"$ne": "RIVAL"}})]
    assert mine == [] and await db.patch_rollouts.count_documents({"tenantId": T}) == 0
    assert len(await active_claims(db)) == 1


async def test_a_second_start_for_the_same_patch_finds_nothing_left_to_install(mongo_db):
    db = await basic(mongo_db)
    await go(db)
    with pytest.raises(start.PreflightBlocked) as caught:
        await go(db, name="Second")
    assert any(r["check"] == "patches" and r["blocker"] for r in caught.value.rows)
    assert await db.patch_rollouts.count_documents({}) == 1
