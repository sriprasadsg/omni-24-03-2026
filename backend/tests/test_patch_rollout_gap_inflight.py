"""Staged patch rollouts, gap plan 84-27: no install, revert or dispatch hangs in flight for ever.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. Time is frozen by
passing ``now`` to the real controller tick; the stand-in agent changes the instruction document the way the
delivery hook and the instruction result route do (status FAILURE, delivered_at, an expiry that passed).

Value: protects=PTCH-02 / PTCH-04 / PTCH-06 / WR-02 / WR-03 / WR-04 / WR-06: an install the agent answers FAILURE, or
never answers within RESULT_DEADLINE, fails the computer so the ring halts; an expired instruction is not a failure
of the computer; a revert in flight always ends; a computer whose approval was denied is never called installed; a
dispatching row with no instruction is recovered; an abandoned job never keeps a computer busy;
fails_when=a FAILURE instruction leaves the host installing, the host is failed before RESULT_DEADLINE, a silent
revert keeps Resume blocked, a denied computer reads installed, a dispatching row stays for ever, or a job stays In
Progress after its install was abandoned; no_claim=a real agent, a real install or the live database.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import gate, ledger, protected
from autonomous_ops.rollout import controller, dispatcher, lifecycle, lines, messages as rm, start, store
from tests import test_patch_rollout_revert as rv
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_platform_stop
from tests.rollout_support import (fresh_scan, post_result, seed_rings, seed_rollout_agent, seed_rollout_tenant,
                                   seed_window, success_result)

T = "t1"
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
BOOT = 1_700_000_000
TOKENS = ("reboot_host", "patch_reversible_check")
ACTOR = {"id": "u1", "name": "Ann"}
APPROVER = {"id": "u2", "name": "Bo"}
DEADLINE = timedelta(hours=6)          # RESULT_DEADLINE: how long a delivered install may stay silent
RINGS = [{"key": "canary", "name": "Canary", "groupIds": ["G1"], "soakHours": 1},
         {"key": "rest", "name": "Everyone else", "groupIds": [], "soakHours": 1}]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def base(db, *, level="undoable_auto"):
    """A ticked tenant at ``level``, two rings (the canary ring is group G1) and a window open at NOW."""
    await ledger.ensure_indexes(db)
    await store.ensure_indexes(db)
    await seed_rollout_tenant(db, T)
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"level": level}})
    await seed_rings(db, T, RINGS)
    await seed_window(db, T, start=(NOW - timedelta(hours=1)).strftime("%H:%M"),
                      end=(NOW + timedelta(hours=3)).strftime("%H:%M"))


async def host(db, agent_id, *, canary=False, tokens=TOKENS, pending=("openssl",)):
    await seed_rollout_agent(db, T, agent_id, hostname=f"host-{agent_id}", platform="Linux", tokens=tokens,
                             pending=list(pending), boot_time=BOOT, last_seen=NOW)
    if canary:
        await db.agent_group_members.replace_one({"group_id": "G1", "agent_id": agent_id},
                                                 {"group_id": "G1", "agent_id": agent_id, "tenantId": T}, upsert=True)
        await db.agent_groups.replace_one({"id": "G1"}, {"id": "G1", "tenantId": T, "name": "G1"}, upsert=True)


async def begin(db, patch_ids=("openssl",)):
    out = await start.start_rollout(db, T, name="Nov", patch_ids=list(patch_ids), actor=ACTOR, now=NOW)
    assert out["status"] == "started", out
    return out["rolloutId"]


async def rows(db, **extra):
    flt = {"tenantId": T, "dispatcher": "patch_rollout", **extra}
    return [r async for r in db.autonomy_actions.find(flt, {"_id": 0}).sort([("createdAt", 1), ("id", 1)])]


async def host_doc(db, agent_id):
    return await db.patch_rollout_hosts.find_one({"tenantId": T, "agentId": agent_id}, {"_id": 0})


async def instruction(db, agent_id, kind="install_patches"):
    return await db.agent_instructions.find_one({"tenantId": T, "agent_id": agent_id, "type": kind}, {"_id": 0})


async def set_instruction(db, instruction_id, **fields):
    await db.agent_instructions.update_one({"id": instruction_id}, {"$set": fields})


async def online_at(db, moment):
    await db.agents.update_many({"tenantId": T}, {"$set": {"lastSeen": moment.isoformat(), "status": "Online"}})


async def canary_in_flight(db):
    """One canary computer a1 that was sent its automatic install; returns the rollout id."""
    await base(db)
    await host(db, "a1", canary=True)
    rollout_id = await begin(db)
    await controller.tick(db, now=NOW)
    doc = await host_doc(db, "a1")
    assert doc["state"] == "installing" and doc["installInstructionId"]
    return rollout_id


# ---------------------------------------------------------------- Task 1: the tracer

async def test_a_canary_install_the_agent_answers_failure_fails_the_computer_and_halts_the_ring(mongo_db):
    db = mongo_db
    rollout_id = await canary_in_flight(db)
    sent = await instruction(db, "a1")
    await set_instruction(db, sent["id"], status="FAILURE", result={"error": "dpkg was interrupted"})

    await controller.tick(db, now=NOW + timedelta(minutes=2))
    doc = await host_doc(db, "a1")
    assert doc["state"] == "failed" and doc["failureMessage"]
    row = (await rows(db))[0]
    assert (row["state"], row["reasonCode"]) == ("failed", "rollout_install_failed")
    assert row["reasonText"] and row["reasonText"] != rm.fill(rm.ACTIVITY["canary_why"], rollout="Nov", patch="openssl")
    await controller.tick(db, now=NOW + timedelta(minutes=3))
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["status"] == "halted" and rollout["haltReason"]["code"] == "canary_failed"


async def test_a_canary_install_nobody_answers_for_six_hours_fails_the_computer_and_not_a_second_sooner(mongo_db):
    db = mongo_db
    await canary_in_flight(db)
    sent = await instruction(db, "a1")
    await set_instruction(db, sent["id"], status="ACCEPTED", delivered_at=NOW.isoformat())

    await controller.tick(db, now=NOW + DEADLINE - timedelta(seconds=1))
    assert (await host_doc(db, "a1"))["state"] == "installing"
    assert (await rows(db))[0]["state"] == "dispatching"

    await controller.tick(db, now=NOW + DEADLINE + timedelta(seconds=1))
    doc = await host_doc(db, "a1")
    assert doc["state"] == "failed" and doc["failureCode"] == "rollout_no_result"
    assert doc["failureMessage"] == "The computer did not answer within 6 hours."
    row = (await rows(db))[0]
    assert (row["state"], row["reasonCode"]) == ("failed", "rollout_no_result")
    assert row["reasonText"] == "The computer did not answer within 6 hours."


async def test_an_install_instruction_that_expired_unread_is_not_delivered_and_the_computer_is_tried_again(mongo_db):
    db = mongo_db
    rollout_id = await canary_in_flight(db)
    assert (await instruction(db, "a1"))["status"] == "pending"

    await controller.tick(db, now=NOW + timedelta(hours=3, minutes=1))          # past the window the instruction ended with
    doc = await host_doc(db, "a1")
    assert doc["state"] == "waiting" and doc.get("installActionId") is None and doc["attempt"] == 1
    row = (await rows(db))[0]
    assert (row["state"], row["reasonCode"]) == ("failed", "rollout_not_delivered")
    assert (await db.patch_rollouts.find_one({"id": rollout_id}))["status"] == "running"       # not a failure of the computer


async def test_an_install_nobody_answered_does_not_count_toward_the_circuit_breaker(mongo_db):
    db = mongo_db
    await base(db)
    for n in range(3):
        at = NOW - timedelta(minutes=n + 1)
        await db.autonomy_actions.insert_one({
            "id": f"AO-nr-{n}", "tenantId": T, "kind": "patching", "dispatcher": "patch_rollout", "state": "failed",
            "autoDispatched": True, "createdAt": at, "updatedAt": at, "finishedAt": at, "command": "install_patches",
            "targets": ["a1"], "reasonCode": "rollout_no_result"})
    assert await ledger.recent_finished_auto(db, T, 3) == []
