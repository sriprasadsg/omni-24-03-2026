"""Staged patch rollouts, plan 84-20: a rollout under the two global safety switches, on a real database.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. Time is frozen by
passing ``now`` to the real controller tick; shadow mode is the tenant's real settings flag and a stop is pressed
and cleared through the real ``stop.press`` / ``stop.clear``.

Value: protects=PTCH-06 / PTCH-05 / PTCH-01 / GATE-06 / 81 D-02: a rollout started in shadow mode is a simulation for
its whole life (would-install and would-restart rows, no instruction, no job, still a simulation after shadow is
lifted); a live rollout whose organization enters shadow mode records one shadow row per computer and attempt and
waits; a stop freezes the rollout without writing a refused row, still settles results and still reverts, and
clearing it offers the cancelled work again as a new attempt without halting; fails_when=a simulation writes to an
agent queue or turns live, shadow rows flood the ledger every tick, a stop makes a decision or a refused row, a
stop-cancelled or stop-expired row halts the rollout, or a cancelled instruction and its re-issue both reach the agent;
no_claim=a real agent, a real restart or the live database.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent_tasks_endpoints
from autonomous_ops import approvals, ledger, protected, stop
from autonomous_ops.rollout import controller, dispatcher, lifecycle, lines, start, store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import (fresh_scan, post_result, seed_group, seed_rings, seed_rollout_agent,
                                   seed_rollout_tenant, seed_window, success_result)

T = "t1"
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
BOOT = 1_700_000_000
TOKENS = ("reboot_host", "patch_reversible_check")
ACTOR = {"id": "u1", "name": "Ann"}
APPROVER = {"id": "u2", "name": "Bo", "username": "bo"}
RINGS = [{"key": "canary", "name": "Canary", "groupIds": ["G1"], "soakHours": 1},
         {"key": "rest", "name": "Everyone else", "groupIds": [], "soakHours": 1}]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


def hhmm(moment):
    return moment.strftime("%H:%M")


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def world(db, *, shadow=False, canary=("a1",), rest=("b1", "b2"), pending=("openssl",)):
    """A ticked tenant, two rings (the canary ring is group G1), an open window and Linux computers."""
    await ledger.ensure_indexes(db)
    await store.ensure_indexes(db)
    await seed_rollout_tenant(db, T, shadow=shadow)
    await seed_rings(db, T, RINGS)
    await seed_window(db, T, start=hhmm(NOW - timedelta(hours=1)), end=hhmm(NOW + timedelta(hours=3)))
    for agent in canary + rest:
        await seed_rollout_agent(db, T, agent, hostname=f"host-{agent}", platform="Linux", tokens=TOKENS,
                                 pending=list(pending), boot_time=BOOT, last_seen=NOW)
    await seed_group(db, T, "G1", list(canary))


async def begin(db, patch_ids=("openssl",)):
    out = await start.start_rollout(db, T, name="Nov", patch_ids=list(patch_ids), actor=ACTOR, now=NOW)
    assert out["status"] == "started", out
    return out["rolloutId"]


async def rows(db, **extra):
    flt = {"tenantId": T, "dispatcher": "patch_rollout", **extra}
    return [r async for r in db.autonomy_actions.find(flt, {"_id": 0}).sort([("createdAt", 1), ("id", 1)])]


async def instructions(db, **extra):
    return [i async for i in db.agent_instructions.find({"tenantId": T, **extra}, {"_id": 0})]


async def host_doc(db, agent_id):
    return await db.patch_rollout_hosts.find_one({"tenantId": T, "agentId": agent_id}, {"_id": 0})


async def rollout_of(db, rollout_id):
    return await db.patch_rollouts.find_one({"id": rollout_id}, {"_id": 0})


async def online_at(db, moment):
    await db.agents.update_many({"tenantId": T}, {"$set": {"lastSeen": moment.isoformat(), "status": "Online"}})


async def set_shadow(db, on):
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"shadow": on}})


# ---------------------------------------------------------------- Task 1: simulation rollouts

async def test_a_simulation_rollout_records_would_install_rows_ring_by_ring_and_never_touches_a_computer(mongo_db):
    db = mongo_db
    await world(db, shadow=True)
    rollout_id = await begin(db)
    assert (await rollout_of(db, rollout_id))["shadow"] is True

    await controller.tick(db, now=NOW)                      # the window is open: the canary is recorded, not sent
    found = await rows(db)
    assert [(r["state"], r["targets"], r["wouldHave"]) for r in found] == [("shadow", ["a1"], "allow_auto")]
    assert (await host_doc(db, "a1"))["state"] == "would_install"
    ring0 = (await rollout_of(db, rollout_id))["rings"][0]
    assert ring0["state"] == "soaking" and aware(ring0["soakEndsAt"]) == NOW + timedelta(hours=1)

    await controller.tick(db, now=NOW + timedelta(minutes=30))     # still soaking, no new row
    assert len(await rows(db)) == 1 and (await rollout_of(db, rollout_id))["rings"][0]["state"] == "soaking"

    later = NOW + timedelta(minutes=61)                     # no scan, no health data: the soak alone passes the ring
    await online_at(db, later)
    await controller.tick(db, now=later)
    rollout = await rollout_of(db, rollout_id)
    assert rollout["rings"][0]["state"] == "passed" and rollout["currentRing"] == 1
    ring_one = [r for r in await rows(db) if r["reason"]["inputs"]["ring"] == 1]
    assert sorted(r["targets"][0] for r in ring_one) == ["b1", "b2"]
    assert {(r["state"], r["wouldHave"]) for r in ring_one} == {("shadow", "needs_approval")}
    assert rollout["rings"][1]["state"] == "soaking"

    end = later + timedelta(minutes=61)
    await online_at(db, end)
    await controller.tick(db, now=end)
    rollout = await rollout_of(db, rollout_id)
    assert rollout["status"] == "completed" and [r["state"] for r in rollout["rings"]] == ["passed", "passed"]
    assert {r["state"] for r in await rows(db)} == {"shadow"} and len(await rows(db)) == 3
    assert await instructions(db) == []                      # nothing was ever written to an agent queue
    assert await db.patch_deployment_jobs.count_documents({}) == 0
    assert await db.autonomy_actions.count_documents({"state": {"$nin": ["shadow"]}}) == 0


async def test_lifting_shadow_in_the_middle_never_turns_a_simulation_live(mongo_db):
    db = mongo_db
    await world(db, shadow=True)
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    await set_shadow(db, False)                             # shadow is lifted while the canary soaks
    later = NOW + timedelta(minutes=61)
    await online_at(db, later)
    await controller.tick(db, now=later)

    rollout = await rollout_of(db, rollout_id)
    assert rollout["shadow"] is True and rollout["currentRing"] == 1
    assert {r["state"] for r in await rows(db)} == {"shadow"} and len(await rows(db)) == 3
    assert await instructions(db) == [] and await db.patch_deployment_jobs.count_documents({}) == 0


async def test_a_simulation_row_is_never_sent_even_if_it_were_approved(mongo_db):
    db = mongo_db
    await world(db, shadow=True)
    await begin(db)
    await controller.tick(db, now=NOW)
    row = (await rows(db))[0]
    await db.autonomy_actions.update_one({"id": row["id"]}, {"$set": {"state": "approved"}})   # a hand edit
    row = (await rows(db))[0]
    answer = await dispatcher.send(db, row, NOW)
    assert answer["status"] == "deferred" and answer["reason"] == "rollout_simulation"
    assert await instructions(db) == []


async def test_a_package_that_usually_needs_a_restart_gets_a_would_restart_row_in_a_simulation(mongo_db):
    db = mongo_db
    await world(db, shadow=True, pending=("linux-image-6.8.0",), rest=())
    await begin(db, ["linux-image-6.8.0"])
    await controller.tick(db, now=NOW)

    found = await rows(db)
    assert {(r["command"], r["state"]) for r in found} == {("install_patches", "shadow"), ("reboot_host", "shadow")}
    assert (await host_doc(db, "a1"))["state"] == "would_restart"
    assert await instructions(db) == [] and await db.patch_deployment_jobs.count_documents({}) == 0
    await controller.tick(db, now=NOW + timedelta(minutes=5))        # a second pass adds nothing
    assert len(await rows(db)) == 2


async def installed_canary(db, rollout_id):
    """The canary computer installed and its soak is over on a fresh scan, so the next tick passes ring 0."""
    await controller.tick(db, now=NOW)
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id})
    await post_result(db, job["id"], "a1", success_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    installed = aware((await host_doc(db, "a1"))["installReportedAt"])
    await fresh_scan(db, "a1", [], installed + timedelta(minutes=10))
    later = installed + timedelta(minutes=61)
    await online_at(db, later)
    return later


async def test_a_live_rollout_whose_organization_enters_shadow_records_once_and_waits_until_shadow_is_lifted(mongo_db):
    db = mongo_db
    await world(db)
    rollout_id = await begin(db)
    later = await installed_canary(db, rollout_id)
    await set_shadow(db, True)                              # shadow mode comes on before ring 1 is raised

    await controller.tick(db, now=later)
    ring_one = await rows(db, **{"reason.inputs.ring": 1})
    assert sorted(r["targets"][0] for r in ring_one) == ["b1", "b2"] and {r["state"] for r in ring_one} == {"shadow"}
    assert {(await host_doc(db, a))["state"] for a in ("b1", "b2")} == {"would_install"}

    before = await db.autonomy_actions.count_documents({})
    await controller.tick(db, now=later + timedelta(minutes=5))
    await controller.tick(db, now=later + timedelta(minutes=10))
    assert await db.autonomy_actions.count_documents({}) == before          # once per computer and attempt
    rollout = await rollout_of(db, rollout_id)
    assert rollout["status"] == "running" and rollout["currentRing"] == 1 and rollout["rings"][1]["state"] != "passed"

    await set_shadow(db, False)
    await controller.tick(db, now=later + timedelta(minutes=15))
    live = [r for r in await rows(db, **{"reason.inputs.ring": 1}) if r["state"] != "shadow"]
    assert sorted(r["targets"][0] for r in live) == ["b1", "b2"]
    assert {(r["state"], r["reason"]["inputs"]["attempt"]) for r in live} == {("awaiting_approval", 2)}
    assert (await rollout_of(db, rollout_id))["shadow"] is False
