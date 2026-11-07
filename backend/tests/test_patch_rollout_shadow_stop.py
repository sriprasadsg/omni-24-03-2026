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
    await online_at(db, later + timedelta(minutes=15))
    await controller.tick(db, now=later + timedelta(minutes=15))
    live = [r for r in await rows(db, **{"reason.inputs.ring": 1}) if r["state"] != "shadow"]
    assert sorted(r["targets"][0] for r in live) == ["b1", "b2"]
    assert {(r["state"], r["reason"]["inputs"]["attempt"]) for r in live} == {("awaiting_approval", 2)}
    assert (await rollout_of(db, rollout_id))["shadow"] is False


# ---------------------------------------------------------------- Task 2: stops freeze rollouts without failing them

TENANT_ACTOR = {"username": "alice", "display": "Alice", "tier": "tenant"}
PLATFORM_ACTOR = {"username": "root", "display": "Root", "tier": "platform"}


async def press(db, scope):
    return await stop.press(db, scope=scope, tenant_id=T if scope == "tenant" else None,
                            actor=TENANT_ACTOR if scope == "tenant" else PLATFORM_ACTOR)


async def clear(db, scope):
    out = await stop.clear(db, scope=scope, tenant_id=T if scope == "tenant" else None,
                           actor=PLATFORM_ACTOR, reason="all clear", actor_is_super_admin=True, actor_has_manage=True)
    assert out["status"] == "cleared", out


def _request():
    req = MagicMock()
    req.headers = {"host": "10.0.0.1"}
    req.url.scheme = "http"
    return req


async def poll(db, agent="a1"):
    """What the agent receives from its instruction poll (the task ids)."""
    with patch.object(agent_tasks_endpoints, "get_database", return_value=db):
        delivered = await agent_tasks_endpoints.get_agent_instructions(
            agent, request=_request(), _tenant={"tenant_id": T, "authenticated_agent_id": agent})
    return [d.get("task_id") or d.get("id") for d in delivered]


@pytest.mark.parametrize("scope", ["tenant", "platform"])
async def test_a_stop_freezes_the_canary_and_clearing_it_offers_the_cancelled_installs_again(mongo_db, scope):
    db = mongo_db
    await world(db, canary=("a1", "a2"), rest=("b1",))
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    first = await rows(db)
    assert [r["state"] for r in first] == ["dispatching", "dispatching"]
    cancelled_ids = {i["id"] for i in await instructions(db)}
    assert len(cancelled_ids) == 2

    await press(db, scope)
    assert {r["state"] for r in await rows(db)} == {"cancelled_by_stop"}
    assert {i["status"] for i in await instructions(db)} == {"cancelled_by_stop"}
    before_rows = await db.autonomy_actions.count_documents({})
    before_instructions = await db.agent_instructions.count_documents({})

    for minutes in (1, 10, 30):
        await online_at(db, NOW + timedelta(minutes=minutes))
        await controller.tick(db, now=NOW + timedelta(minutes=minutes))
    assert await db.autonomy_actions.count_documents({}) == before_rows          # no decision, no refused row
    assert await db.autonomy_actions.count_documents({"state": "refused"}) == 0
    assert await db.agent_instructions.count_documents({}) == before_instructions
    frozen = await rollout_of(db, rollout_id)
    assert frozen["status"] == "running" and frozen["stoppedSince"] is not None

    await clear(db, scope)
    await online_at(db, NOW + timedelta(minutes=40))
    await controller.tick(db, now=NOW + timedelta(minutes=40))
    rollout = await rollout_of(db, rollout_id)
    assert rollout["status"] == "running" and rollout.get("stoppedSince") is None
    again = [r for r in await rows(db) if r["state"] == "dispatching"]
    assert sorted(r["targets"][0] for r in again) == ["a1", "a2"]
    assert {r["reason"]["inputs"]["attempt"] for r in again} == {2}
    assert len({r["dedupeKey"] for r in await rows(db)}) == 4                    # every attempt has its own key
    pending = await instructions(db, status="pending")
    assert len(pending) == 2 and not ({i["id"] for i in pending} & cancelled_ids)
    delivered = await poll(db, "a1")                     # the cancelled instruction is terminal at delivery
    assert len(delivered) == 1 and delivered[0] not in cancelled_ids
    assert delivered[0] in {i["id"] for i in pending if i["agent_id"] == "a1"}


async def pass_the_canary_and_approve_ring_one(db, rollout_id):
    """Ring 1 has an approval row per computer and a person approved the line (the instructions are pending)."""
    later = await installed_canary(db, rollout_id)
    await controller.tick(db, now=later)
    awaiting = await rows(db, state="awaiting_approval", **{"reason.inputs.ring": 1})
    assert sorted(r["targets"][0] for r in awaiting) == ["b1", "b2"]
    done = await lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=later)
    assert done["status"] == "approved" and done["approved"] == 2, done
    return later


@pytest.mark.parametrize("scope", ["tenant", "platform"])
async def test_an_approved_line_a_stop_cancelled_is_raised_again_as_a_new_approval_and_the_rollout_does_not_halt(mongo_db, scope):
    db = mongo_db
    await world(db)
    rollout_id = await begin(db)
    later = await pass_the_canary_and_approve_ring_one(db, rollout_id)
    await press(db, scope)
    ring_one = await rows(db, **{"reason.inputs.ring": 1})
    assert {r["state"] for r in ring_one} == {"cancelled_by_stop"}
    before = await db.autonomy_actions.count_documents({})

    for minutes in (5, 20):
        await online_at(db, later + timedelta(minutes=minutes))
        await controller.tick(db, now=later + timedelta(minutes=minutes))
    assert await db.autonomy_actions.count_documents({}) == before
    assert (await rollout_of(db, rollout_id))["status"] == "running"

    await clear(db, scope)
    await online_at(db, later + timedelta(minutes=30))
    await controller.tick(db, now=later + timedelta(minutes=30))
    rollout = await rollout_of(db, rollout_id)
    assert rollout["status"] == "running" and rollout["currentRing"] == 1 and "haltReason" not in rollout
    fresh = await rows(db, state="awaiting_approval", **{"reason.inputs.ring": 1})
    assert sorted(r["targets"][0] for r in fresh) == ["b1", "b2"]
    assert {r["reason"]["inputs"]["attempt"] for r in fresh} == {2}


@pytest.mark.parametrize("scope", ["tenant", "platform"])
async def test_a_line_that_expired_during_a_long_stop_is_raised_again_and_never_halts_the_rollout(mongo_db, scope):
    db = mongo_db
    await world(db)
    rollout_id = await begin(db)
    later = await installed_canary(db, rollout_id)
    await controller.tick(db, now=later)
    assert len(await rows(db, state="awaiting_approval", **{"reason.inputs.ring": 1})) == 2

    await press(db, scope)
    await online_at(db, later + timedelta(hours=1))
    await controller.tick(db, now=later + timedelta(hours=1))                    # the stop is noticed
    assert await approvals.expire_due(db, now=later + timedelta(hours=30), tenant_id=T) == 2      # the 24 h ran out
    before = await db.autonomy_actions.count_documents({})
    await online_at(db, later + timedelta(hours=31))
    await controller.tick(db, now=later + timedelta(hours=31))
    rollout = await rollout_of(db, rollout_id)
    assert rollout["status"] == "running" and "haltReason" not in rollout        # not a deny, not an approval_expired
    assert await db.autonomy_actions.count_documents({}) == before
    assert {(await host_doc(db, a))["state"] for a in ("b1", "b2")} == {"waiting"}      # never read as installed

    await clear(db, scope)
    after = later + timedelta(hours=48)                                          # inside the daily window again
    for minutes in (0, 5):
        await online_at(db, after + timedelta(minutes=minutes))
        await controller.tick(db, now=after + timedelta(minutes=minutes))
    rollout = await rollout_of(db, rollout_id)
    assert rollout["status"] == "running" and rollout["currentRing"] == 1 and "haltReason" not in rollout
    assert rollout.get("stoppedSince") is None
    fresh = await rows(db, state="awaiting_approval", **{"reason.inputs.ring": 1})
    assert sorted(r["targets"][0] for r in fresh) == ["b1", "b2"]
    assert {r["reason"]["inputs"]["attempt"] for r in fresh} == {2}
    assert len(await rows(db, state="expired", **{"reason.inputs.ring": 1})) == 2       # the old cards stay as history


async def test_an_expired_line_outside_any_stop_still_halts_the_rollout(mongo_db):
    db = mongo_db
    await world(db)
    rollout_id = await begin(db)
    later = await installed_canary(db, rollout_id)
    await controller.tick(db, now=later)
    assert await approvals.expire_due(db, now=later + timedelta(hours=25), tenant_id=T) == 2
    await online_at(db, later + timedelta(hours=25))
    await controller.tick(db, now=later + timedelta(hours=25))
    assert (await rollout_of(db, rollout_id))["haltReason"]["code"] == "approval_expired"


async def test_a_revert_of_a_halted_rollout_still_goes_out_during_a_stop(mongo_db):
    db = mongo_db
    await world(db, rest=())
    await db.agents.update_one({"id": "a1"}, {"$set": {"meta.response_actions.tokens": [*TOKENS, "patch_revert_by_job"]}})
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id})
    await post_result(db, job["id"], "a1", success_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    assert (await host_doc(db, "a1"))["state"] == "installed"

    await press(db, "tenant")
    rollout = store.normalise(await db.patch_rollouts.find_one({"id": rollout_id}))
    assert await lifecycle.halt(db, T, rollout, 0, code="host_failed", host="a1", now=NOW + timedelta(minutes=3)) is True
    undo = await instructions(db, type="rollback_patches")
    assert len(undo) == 1 and undo[0]["status"] == "pending"
    before = await db.autonomy_actions.count_documents({})
    await online_at(db, NOW + timedelta(minutes=5))
    await controller.tick(db, now=NOW + timedelta(minutes=5))
    assert await db.autonomy_actions.count_documents({}) == before and await db.autonomy_actions.count_documents({"state": "refused"}) == 0
    assert [i["status"] for i in await instructions(db, type="rollback_patches")] == ["pending"]
    assert (await rollout_of(db, rollout_id))["status"] == "halted"
