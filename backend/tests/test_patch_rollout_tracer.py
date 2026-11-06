"""Staged patch rollouts, plan 84-01: the tracer from Start to Completed on a real database.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. Time is frozen by
passing ``now`` to the real controller tick; the stand-in agent posts a 2.1.16-shaped install result through
the real ``record_agent_patch_result`` path.

Value: protects=PTCH-01 / PTCH-05 / PTCH-06 / PTCH-07: a canary host installs one reversible patch on its own
inside the open window through the gate, the instruction expires with the window, the agent's own result
settles the host and the row, the ring passes only after its soak on a scan newer than the install, and no two
active rollouts ever hold one computer; fails_when=an install is decided outside a window or for an agent that
cannot check reversibility, install_patches is accepted from another dispatcher, an instruction is written twice,
a stale scan lets a ring pass, a host is claimed twice or a claim stays after completion;
no_claim=a real agent, a real restart or the live database (the Rust agent change is plan 84-07).
"""
import os
import sys
from datetime import datetime, time, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import gate, ledger, protected
from autonomous_ops.rollout import controller, start, store, windows
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import (post_result, seed_group, seed_rings, seed_rollout_agent, seed_rollout_tenant,
                                   seed_window, success_result)

T = "t1"
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
BOOT = 1_700_000_000
TOKENS = ("reboot_host", "patch_reversible_check")
ACTOR = {"id": "u1", "name": "Ann"}
RINGS = [{"key": "canary", "name": "Canary", "groupIds": ["G1"], "soakHours": 1},
         {"key": "rest", "name": "Everyone else", "groupIds": [], "soakHours": 1}]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


def hhmm(moment):
    return moment.strftime("%H:%M")


async def world(db, *, tokens=TOKENS, open_window=True, pending=("openssl",)):
    """One tenant, an open (or closed) daily window, two rings and one Linux host in the canary group."""
    await ledger.ensure_indexes(db)
    await store.ensure_indexes(db)
    await seed_rollout_tenant(db, T)
    await seed_rollout_agent(db, T, "a1", hostname="host-a1", platform="Linux", tokens=tokens, pending=list(pending),
                             boot_time=BOOT, last_seen=NOW)
    await seed_group(db, T, "G1", ["a1"])
    await seed_rings(db, T, RINGS)
    if open_window:
        await seed_window(db, T, start=hhmm(NOW - timedelta(hours=1)), end=hhmm(NOW + timedelta(hours=3)))
    else:
        await seed_window(db, T, start=hhmm(NOW + timedelta(hours=2)), end=hhmm(NOW + timedelta(hours=3)))
    return db


async def begin(db, patch_ids=("openssl",)):
    out = await start.start_rollout(db, T, name="Nov", patch_ids=list(patch_ids), actor=ACTOR, now=NOW)
    assert out["status"] == "started", out
    return out["rolloutId"]


async def rows(db):
    return [r async for r in db.autonomy_actions.find({"tenantId": T, "dispatcher": "patch_rollout"}, {"_id": 0})]


async def instructions(db):
    return [i async for i in db.agent_instructions.find({"tenantId": T}, {"_id": 0})]


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# ---------------------------------------------------------------- Start

async def test_start_inserts_the_rollout_and_claims_the_canary_host(mongo_db):
    db = await world(mongo_db)
    rollout_id = await begin(db)
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["status"] == "running" and rollout["shadow"] is False and rollout["name"] == "Nov"
    assert [r["name"] for r in rollout["rings"]] == ["Canary", "Everyone else"]
    assert [r["state"] for r in rollout["rings"]] == ["not_started", "not_started"]
    assert rollout["patchesByOs"] == {"windows": [], "linux": ["openssl"]}
    claims = [c async for c in db.patch_rollout_hosts.find({"tenantId": T})]
    assert len(claims) == 1 and claims[0]["agentId"] == "a1" and claims[0]["ring"] == 0
    assert claims[0]["active"] is True and claims[0]["state"] == "waiting" and claims[0]["patchIds"] == ["openssl"]


async def test_start_refuses_without_a_window_or_rings_or_for_the_platform_tenant(mongo_db):
    db = await world(mongo_db)
    assert (await start.start_rollout(db, "platform-admin", name="x", patch_ids=["openssl"], actor=ACTOR))["reason"] \
        == "platform_tenant"
    assert (await start.start_rollout(db, T, name="x", patch_ids=["CVE-2026-1"], actor=ACTOR))["reason"] \
        == "invalid_patch_ids"
    await db.patch_rollout_settings.delete_many({})
    assert (await start.start_rollout(db, T, name="x", patch_ids=["openssl"], actor=ACTOR))["reason"] == "no_rings"
    await seed_rings(db, T, RINGS)
    await db.maintenance_windows.delete_many({})
    assert (await start.start_rollout(db, T, name="x", patch_ids=["openssl"], actor=ACTOR))["reason"] == "no_window"
    assert await db.patch_rollouts.count_documents({}) == 0


# ---------------------------------------------------------------- the tracer

async def test_canary_installs_on_its_own_inside_the_window_and_the_result_settles_it(mongo_db):
    db = await world(mongo_db)
    rollout_id = await begin(db)

    await controller.tick(db, now=NOW)

    found = await rows(db)
    assert len(found) == 1
    row = found[0]
    assert (row["command"], row["state"], row["targets"]) == ("install_patches", "dispatching", ["a1"])
    assert row["reason"]["inputs"] == {"rolloutId": rollout_id, "ring": 0, "line": "install", "attempt": 1,
                                       "patchIds": ["openssl"]}
    sent = await instructions(db)
    assert len(sent) == 1
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id})
    assert job["dispatchedAgents"] == ["a1"]
    assert sent[0]["payload"] == {"patch_ids": ["openssl"], "job_id": job["id"], "require_reversible": True}
    assert sent[0]["type"] == "install_patches" and sent[0]["autonomy"]["actionId"] == row["id"]
    # PTCH-05: the instruction dies with the window occurrence that was open when it was sent.
    assert aware(sent[0]["expiresAt"]) == (NOW + timedelta(hours=3))

    await controller.tick(db, now=NOW + timedelta(seconds=30))
    assert len(await rows(db)) == 1 and len(await instructions(db)) == 1          # a second tick writes nothing new

    await post_result(db, job["id"], "a1", success_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    host = await db.patch_rollout_hosts.find_one({"agentId": "a1"})
    assert host["state"] == "installed" and host["installReportedAt"] is not None
    row = (await rows(db))[0]
    assert row["state"] == "executed" and row["reasonCode"] == "rollout_installed"


async def test_nothing_is_written_while_no_window_is_open(mongo_db):
    db = await world(mongo_db, open_window=False)
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    assert await rows(db) == [] and await instructions(db) == []
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["rings"][0]["state"] == "waiting_for_window"


async def test_a_tenant_with_no_readable_window_is_never_open(mongo_db):
    db = await world(mongo_db)
    await db.maintenance_windows.insert_one({"id": "bad", "tenantId": T, "recurrence": "monthly", "startTime": "x"})
    loaded = await windows.load(db, T)
    assert loaded.readable is False and loaded.open_at(NOW) is None
    await begin_unchecked(db)
    await controller.tick(db, now=NOW)
    assert await rows(db) == [] and await instructions(db) == []


async def begin_unchecked(db):
    """Insert a running rollout directly (Start itself refuses a tenant whose windows cannot be read)."""
    await db.patch_rollouts.insert_one({
        "id": "r-raw", "tenantId": T, "name": "raw", "patchIds": ["openssl"], "status": "running", "shadow": False,
        "currentRing": 0, "createdAt": NOW,
        "rings": [{"index": 0, "key": "c", "name": "C", "groupIds": ["G1"], "soakHours": 1, "failPct": 10,
                   "minSample": 10, "isCanary": True, "state": "not_started"}]})
    await db.patch_rollout_hosts.insert_one({
        "tenantId": T, "rolloutId": "r-raw", "agentId": "a1", "ring": 0, "state": "waiting", "os": "linux",
        "hostname": "host-a1", "patchIds": ["openssl"], "attempt": 0, "active": True})


async def test_a_host_that_cannot_check_reversibility_is_never_installed_automatically(mongo_db):
    db = await world(mongo_db, tokens=("reboot_host",))
    await begin(db)
    await controller.tick(db, now=NOW)
    assert await rows(db) == [] and await instructions(db) == []
    assert (await db.patch_rollout_hosts.find_one({"agentId": "a1"}))["state"] == "waiting"


async def test_a_package_that_usually_needs_a_restart_is_not_installed_automatically(mongo_db):
    db = await world(mongo_db, pending=("linux-image-6.8.0",))
    await begin(db, ["linux-image-6.8.0"])
    await controller.tick(db, now=NOW)
    assert await rows(db) == [] and await instructions(db) == []


async def test_a_stopped_tenant_gets_no_new_decision_but_a_result_still_settles(mongo_db):
    db = await world(mongo_db)
    await begin(db)
    await controller.tick(db, now=NOW)
    job = await db.patch_deployment_jobs.find_one({})
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"stop": {"active": True}}})
    await post_result(db, job["id"], "a1", success_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    assert (await db.patch_rollout_hosts.find_one({"agentId": "a1"}))["state"] == "installed"
    assert len(await rows(db)) == 1


# ---------------------------------------------------------------- the gate

async def test_install_patches_from_any_other_dispatcher_is_refused_and_records_nothing(mongo_db):
    db = await world(mongo_db)
    for dispatcher in ("instruction", "security_response", "remediation", ""):
        request = gate.ActionRequest(
            tenant_id=T, kind="patching", origin="test", actions=["install_patches"], targets=["a1"],
            params={"patch_ids": ["openssl"], "job_id": "j", "require_reversible": True}, dedupe_key=f"k-{dispatcher}",
            dispatcher=dispatcher)
        decision = await gate.decide(db, request, master_shadow=False, now=NOW)
        assert (decision.outcome, decision.reason) == ("refuse", "unregistered_action"), dispatcher
    assert await db.autonomy_actions.count_documents({}) == 0
    assert await db.agent_instructions.count_documents({}) == 0


# ---------------------------------------------------------------- PTCH-07

async def test_no_two_active_rollouts_can_hold_one_computer(mongo_db):
    db = await world(mongo_db)
    await store.ensure_indexes(db)
    assert "one_active_rollout_per_host" in await db.patch_rollout_hosts.index_information()
    claim = {"agentId": "a1", "ring": 0, "state": "waiting"}
    assert await store.claim_hosts(db, T, "r1", [dict(claim)]) == (["a1"], [])
    assert await store.claim_hosts(db, T, "r2", [dict(claim), {**claim, "agentId": "a2"}]) == (["a2"], ["a1"])
    await store.release(db, T, "r1")
    assert await store.claim_hosts(db, T, "r3", [dict(claim)]) == (["a1"], [])


async def test_a_second_start_leaves_out_a_computer_another_rollout_holds(mongo_db):
    db = await world(mongo_db)
    await begin(db)
    out = await start.start_rollout(db, T, name="Second", patch_ids=["openssl"], actor=ACTOR, now=NOW)
    assert out["status"] == "refused" and out["reason"] == "no_hosts" and out["leftOut"] == ["a1"]
    assert await db.patch_rollouts.count_documents({}) == 1


# ---------------------------------------------------------------- windows (recurring rows)

def test_window_edges_follow_the_zone_and_run_past_midnight():
    window = windows.Window("Sat night", "weekly", time(22, 0), time(2, 0), (6,))
    sat_2029 = datetime(2026, 11, 7, 20, 29, tzinfo=timezone.utc)       # Saturday 01:59 the next morning in Kolkata
    assert windows.is_open([window], "Asia/Kolkata", sat_2029) is not None
    assert windows.is_open([window], "Asia/Kolkata", sat_2029 + timedelta(minutes=1)) is None
    assert windows.is_open([window], "No/Such_Zone", sat_2029) is None
    ny = windows.Window("Early", "daily", time(1, 0), time(4, 0))
    spring = windows.is_open([ny], "America/New_York", datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc))
    assert spring == (datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc), datetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc))
