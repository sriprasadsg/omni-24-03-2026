"""Staged patch rollouts, gap plan 84-27: no install, revert or dispatch hangs in flight for ever.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. Time is frozen by
passing ``now`` to the real controller tick; the stand-in agent changes the instruction document the way the
delivery hook, the poll route and the instruction result route do (status FAILURE, sent_at, an expiry that passed).

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

from autonomous_ops import approvals, gate, ledger, protected
from autonomous_ops.rollout import controller, installs, lifecycle, lines, messages as rm, start, store
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
    await set_instruction(db, sent["id"], status="ACCEPTED", sent_at=NOW.isoformat())

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
    assert (await instruction(db, "a1"))["status"] == "cancelled"                  # a late fetch can not run it (WR-27)


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


# ---------------------------------------------------------------- Task 2: reverts that end, denied computers

async def silent_revert(db, how):
    """A halted ring whose revert instruction the agent answers FAILURE, never reads before it expired, or never
    answers after reading it. Returns the time to tick at."""
    await rv.world(db)
    await rv.add(db, "l1")
    await rv.halt(db)
    sent = (await rv.undo_instructions(db))[0]
    assert (await rv.host_doc(db, "l1"))["state"] == "reverting"
    if how == "failure":
        await set_instruction(db, sent["id"], status="FAILURE")
        return rv.NOW + timedelta(minutes=1)
    if how == "expired":
        await set_instruction(db, sent["id"], expiresAt=rv.NOW - timedelta(minutes=1))
        return rv.NOW + timedelta(minutes=1)
    await set_instruction(db, sent["id"], status="ACCEPTED", sent_at=rv.NOW.isoformat())
    return rv.NOW + DEADLINE + timedelta(minutes=1)


@pytest.mark.parametrize("how", ["failure", "expired", "silent"])
async def test_a_revert_the_agent_fails_or_never_answers_reads_not_reverted_and_resume_is_unblocked(mongo_db, how):
    db = mongo_db
    at = await silent_revert(db, how)
    await controller.tick(db, now=at)

    got = await rv.host_doc(db, "l1")
    code, words = ("agent_failed", "reported an error") if how == "failure" else ("no_answer", "did not answer")   # WR-28
    assert (got["state"], got["notRevertedReason"]) == ("not_reverted", code)
    assert rm.not_reverted(code) == f"Not reverted: the computer {words}. The patch is still installed."
    block = rv_block(await db.patch_rollouts.find_one({"id": "r1"}), await store.host_docs(db, T, "r1"))
    assert f"1 computer could not be reverted: the computer {words}. The patch is still installed on it." in block["reverts"]
    job = await db.patch_deployment_jobs.find_one({"id": got["revertJobId"]})
    assert job["status"] == "Failed" and job["statusLog"][-1]["level"] == "error"
    try:
        await lifecycle.resume(db, T, "r1", actor=ACTOR, reason="Again", now=at)
    except lifecycle.RevertRunning:
        pytest.fail("Resume is still blocked by a revert that ended")


def rv_block(rollout, hosts):
    from autonomous_ops.rollout import views
    return views.halt_block(store.normalise(rollout), hosts)


async def pass_the_canary(db, rollout_id):
    """Tick the canary host through install, result, soak and a fresh scan so ring 1 is current."""
    await controller.tick(db, now=NOW)
    job = await db.patch_deployment_jobs.find_one({"rolloutId": rollout_id, "dispatchedAgents": "a1"})
    await post_result(db, job["id"], "a1", success_result(["openssl"]))
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    installed = aware((await host_doc(db, "a1"))["installReportedAt"])
    await fresh_scan(db, "a1", [], installed + timedelta(minutes=10))
    later = installed + timedelta(minutes=61)
    await online_at(db, later)
    await controller.tick(db, now=later)
    return later


async def ring_one_line(db):
    await base(db)
    await host(db, "a1", canary=True)
    await host(db, "b1")
    rollout_id = await begin(db)
    later = await pass_the_canary(db, rollout_id)
    found = await rows(db, **{"reason.inputs.ring": 1})
    assert [(r["state"], r["targets"]) for r in found] == [("awaiting_approval", ["b1"])]
    return rollout_id, later


async def test_a_computer_whose_install_line_was_denied_is_never_shown_installed(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_line(db)
    assert (await lines.deny_line(db, T, rollout_id, 1, "install", approver=APPROVER))["status"] == "denied"

    for minutes in (1, 2):
        await online_at(db, later + timedelta(minutes=minutes))
        await controller.tick(db, now=later + timedelta(minutes=minutes))
        doc = await host_doc(db, "b1")
        assert (doc["state"], doc["waitReason"]) == ("waiting", "not_approved")
        assert not doc.get("installedIds")
    rollout = await db.patch_rollouts.find_one({"id": rollout_id})
    assert rollout["status"] == "halted" and rollout["haltReason"]["code"] == "install_denied"


async def test_a_computer_whose_install_line_expired_unanswered_is_never_shown_installed(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_line(db)
    after = later + timedelta(hours=25)
    assert await approvals.expire_due(db, now=after, tenant_id=T) == 1
    await online_at(db, after)
    await controller.tick(db, now=after)
    doc = await host_doc(db, "b1")
    assert (doc["state"], doc["waitReason"]) == ("waiting", "not_approved")
    assert (await db.patch_rollouts.find_one({"id": rollout_id}))["haltReason"]["code"] == "approval_expired"


async def test_an_install_line_that_expired_inside_a_stop_is_still_offered_again(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_line(db)
    await seed_platform_stop(db)
    await online_at(db, later + timedelta(hours=1))
    await controller.tick(db, now=later + timedelta(hours=1))                          # the stop is noticed
    assert await approvals.expire_due(db, now=later + timedelta(hours=30), tenant_id=T) == 1
    await online_at(db, later + timedelta(hours=31))
    await controller.tick(db, now=later + timedelta(hours=31))
    doc = await host_doc(db, "b1")
    assert doc["state"] == "waiting" and doc["waitReason"] != "not_approved"
    assert (await db.patch_rollouts.find_one({"id": rollout_id}))["status"] == "running"

    await seed_platform_stop(db, active=False)
    after = later + timedelta(hours=48)
    for minutes in (0, 5):
        await online_at(db, after + timedelta(minutes=minutes))
        await controller.tick(db, now=after + timedelta(minutes=minutes))
    fresh = await rows(db, state="awaiting_approval", **{"reason.inputs.ring": 1})
    assert [r["targets"] for r in fresh] == [["b1"]] and fresh[0]["reason"]["inputs"]["attempt"] == 2


# ---------------------------------------------------------------- Task 3: stuck rows and abandoned jobs

async def job_of(db, agent_id="a1"):
    return await db.patch_deployment_jobs.find_one({"tenantId": T, "dispatchedAgents": agent_id}, {"_id": 0})


async def test_a_dispatching_row_with_no_instruction_is_recovered_and_the_computer_is_decided_again(mongo_db):
    db = mongo_db
    await canary_in_flight(db)
    first = (await rows(db))[0]
    stuck_job = (await job_of(db))["id"]
    assert first["state"] == "dispatching" and "a1" in await start._busy_agents(db, T)
    # A process died between the claim and the instruction: no instruction, no host record of the row.
    await db.agent_instructions.delete_many({"tenantId": T})
    await db.autonomy_actions.update_one({"id": first["id"]}, {"$set": {
        "instructionIds": [], "updatedAt": NOW - timedelta(minutes=11)}})
    await db.patch_rollout_hosts.update_one({"tenantId": T, "agentId": "a1"}, {"$set": {
        "state": "waiting", "installActionId": None, "installJobId": None, "installInstructionId": None}})

    await online_at(db, NOW + timedelta(minutes=1))
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    found = await rows(db)
    old = next(r for r in found if r["id"] == first["id"])
    assert (old["state"], old["reasonCode"]) == ("failed", "rollout_not_delivered")
    fresh = [r for r in found if r["id"] != first["id"]]
    assert len(fresh) == 1 and fresh[0]["reason"]["inputs"]["attempt"] == 2 and fresh[0]["state"] == "dispatching"
    doc = await host_doc(db, "a1")
    assert doc["state"] == "installing" and doc["installActionId"] == fresh[0]["id"]
    closed = await db.patch_deployment_jobs.find_one({"id": stuck_job})
    assert closed["status"] == "Failed" and closed["statusLog"][-1]["level"] == "error"


async def test_a_dispatching_row_younger_than_the_claim_bound_is_left_alone(mongo_db):
    db = mongo_db
    await canary_in_flight(db)
    first = (await rows(db))[0]
    await db.agent_instructions.delete_many({"tenantId": T})
    await db.autonomy_actions.update_one({"id": first["id"]}, {"$set": {
        "instructionIds": [], "updatedAt": NOW - timedelta(minutes=9)}})
    await controller.tick(db, now=NOW + timedelta(seconds=30))
    assert (await rows(db))[0]["state"] == "dispatching" and (await host_doc(db, "a1"))["state"] == "installing"


@pytest.mark.parametrize("path", ["automatic", "approved"])
async def test_a_send_that_raises_ends_the_row_and_the_computer_waits_to_be_tried_again(mongo_db, monkeypatch, path):
    db = mongo_db
    await base(db, level="undoable_auto" if path == "automatic" else "suggest")
    await host(db, "a1", canary=True)
    rollout_id = await begin(db)

    async def broken(*args, **kwargs):
        raise RuntimeError("queue unavailable")

    if path == "automatic":
        monkeypatch.setattr(gate, "execute", broken)
        await controller.tick(db, now=NOW)
    else:
        await controller.tick(db, now=NOW)                                        # the held canary row, nothing sent
        monkeypatch.setattr(gate, "execute", broken)
        await lines.approve_line(db, T, rollout_id, 0, "install", approver=APPROVER, now=NOW)
        await controller.tick(db, now=NOW + timedelta(seconds=30))                # no exception escapes the tick
    found = await rows(db)
    first = found[0]
    assert (first["state"], first["reasonCode"]) == ("failed", "rollout_not_delivered")
    assert (await host_doc(db, "a1"))["state"] == "waiting"
    assert (await job_of(db))["status"] == "Failed" and "a1" not in await start._busy_agents(db, T)


async def test_an_expired_canary_instruction_closes_its_job_so_the_computer_is_not_busy(mongo_db):
    db = mongo_db
    await canary_in_flight(db)
    assert "a1" in await start._busy_agents(db, T) and (await job_of(db))["status"] == "In Progress"

    await controller.tick(db, now=NOW + timedelta(hours=3, minutes=1))
    job = await job_of(db)
    assert job["status"] == "Failed" and job["statusLog"][-1]["level"] == "error"
    assert "a1" not in await start._busy_agents(db, T)


# ---------------------------------------------------------------- WR-26 / WR-27: what "not delivered" and the deadline mean

async def test_an_install_the_agent_fetched_is_not_called_undelivered_when_the_window_closes(mongo_db):
    db = mongo_db
    await canary_in_flight(db)
    sent = await instruction(db, "a1")
    await set_instruction(db, sent["id"], status="sent", sent_at=NOW.isoformat())      # fetched; its accepted post was lost

    await controller.tick(db, now=NOW + timedelta(hours=3, minutes=1))                 # past expiresAt (the window close)
    doc = await host_doc(db, "a1")
    assert doc["state"] == "installing" and doc["installActionId"]
    row = (await rows(db))[0]
    assert row["state"] == "dispatching" and row.get("reasonCode") != "rollout_not_delivered"
    assert (await job_of(db))["status"] == "In Progress"                                # the computer still reads busy

    await controller.tick(db, now=NOW + DEADLINE + timedelta(seconds=1))                # the deadline decides, from sent_at
    assert (await host_doc(db, "a1"))["failureCode"] == "rollout_no_result"


async def test_a_queued_revert_that_was_never_fetched_keeps_waiting_and_is_not_declared_unanswered(mongo_db):
    db = mongo_db
    await rv.world(db)
    await rv.add(db, "l1")
    await rv.halt(db)
    sent = (await rv.undo_instructions(db))[0]
    assert sent["status"] == "pending" and "expiresAt" not in sent

    await controller.tick(db, now=rv.NOW + DEADLINE + timedelta(hours=18))              # the laptop has been off for a day
    assert (await rv.host_doc(db, "l1"))["state"] == "reverting"
    assert (await db.agent_instructions.find_one({"id": sent["id"]}))["status"] == "pending"


async def test_a_revert_the_agent_fetched_is_timed_from_the_poll_not_from_the_row(mongo_db):
    db = mongo_db
    await rv.world(db)
    await rv.add(db, "l1")
    await rv.halt(db)
    sent = (await rv.undo_instructions(db))[0]
    fetched = rv.NOW + timedelta(hours=20)
    await set_instruction(db, sent["id"], status="sent", sent_at=fetched.isoformat())

    await controller.tick(db, now=fetched + DEADLINE - timedelta(seconds=1))
    assert (await rv.host_doc(db, "l1"))["state"] == "reverting"
    await controller.tick(db, now=fetched + DEADLINE + timedelta(seconds=1))
    assert (await rv.host_doc(db, "l1"))["notRevertedReason"] == "no_answer"


def test_the_outcome_of_an_instruction_follows_its_status_and_the_poll_time():
    from autonomous_ops.rollout import inflight
    at, sent = NOW, (NOW - timedelta(hours=1)).isoformat()
    past, future = at - timedelta(minutes=1), at + timedelta(minutes=1)
    outcome = inflight.instruction_outcome
    assert outcome({"status": "pending", "expiresAt": past}, at) == "not_delivered"
    assert outcome({"status": "pending", "expiresAt": future}, at) == "pending"
    assert outcome({"status": "pending", "created_at": at - timedelta(days=2)}, at) == "pending"      # no clock before the poll
    assert outcome({"status": "sent", "expiresAt": past, "sent_at": sent}, at) == "pending"           # WR-26
    assert outcome({"status": "sent", "sent_at": (at - DEADLINE).isoformat()}, at) == "no_result"
    accepted = {"status": "ACCEPTED", "sent_at": (at - DEADLINE).isoformat(), "updated_at": (at - timedelta(hours=5)).isoformat()}
    assert outcome(accepted, at) == "pending"                                                         # the accept time wins
    assert outcome({"status": "cancelled"}, at) == "not_delivered"


async def test_only_a_pending_instruction_is_cancelled(mongo_db):
    from autonomous_ops import delivery
    db = mongo_db
    await db.agent_instructions.insert_many([{"id": "i-p", "tenantId": T, "status": "pending"},
                                             {"id": "i-s", "tenantId": T, "status": "sent"}])
    assert await delivery.cancel_unfetched(db, T, "i-p", NOW) is True
    assert await delivery.cancel_unfetched(db, T, "i-s", NOW) is False
    assert await delivery.cancel_unfetched(db, "other", "i-p", NOW) is False
    assert [(await db.agent_instructions.find_one({"id": i}))["status"] for i in ("i-p", "i-s")] == ["cancelled", "sent"]


# ---------------------------------------------------------------- WR-31: a Cancel that lands after the controller loaded the rollout

async def loaded(db, *, ring=0):
    """The rollout and the hosts of ``ring`` as a controller pass read them (before any Cancel stamp)."""
    rollout = (await store.active_rollouts(db, T, ("running",)))[0]
    return rollout, [h for h in await store.host_docs(db, T, rollout["id"]) if h.get("ring") == ring]


async def stamp_cancel(db, rollout):
    await db.patch_rollouts.update_one({"id": rollout["id"]}, {"$set": {"cancelRequested": {"by": ACTOR, "at": NOW}}})


async def test_a_cancel_after_the_rollout_was_loaded_still_stops_the_canary_install(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "a1", canary=True)
    await begin(db)
    rollout, hosts = await loaded(db)
    await stamp_cancel(db, rollout)
    assert "cancelRequested" not in rollout                                            # the copy the pass works from is stale

    made = await installs.canary_auto(db, T, rollout, 0, hosts, NOW, NOW + timedelta(hours=3))
    assert made["sent"] == made["raised"] == made["held"] == 0
    assert await rows(db) == [] and await instruction(db, "a1") is None and (await host_doc(db, "a1"))["state"] == "waiting"


async def test_a_cancel_between_the_claim_and_the_send_ends_the_row_and_sends_nothing(mongo_db, monkeypatch):
    db = mongo_db
    await base(db)
    await host(db, "a1", canary=True)
    await begin(db)
    rollout, hosts = await loaded(db)
    answers = iter([False, True])                       # clear when the pass starts the host, stamped by the time it sends

    async def stamped(*args):
        return next(answers)

    monkeypatch.setattr(installs, "cancel_stamped", stamped)
    made = await installs.canary_auto(db, T, rollout, 0, hosts, NOW, NOW + timedelta(hours=3))
    assert made["sent"] == 0 and await instruction(db, "a1") is None and await db.patch_deployment_jobs.count_documents({}) == 0
    assert [(r["state"], r["reasonCode"]) for r in await rows(db)] == [("failed", "rollout_closed")]


async def test_a_cancel_after_the_rollout_was_loaded_raises_no_approval_line_for_a_later_ring(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "a1", canary=True)
    await host(db, "b1")
    await begin(db)
    rollout, ring_one = await loaded(db, ring=1)
    await stamp_cancel(db, rollout)
    made = await installs.raise_ring(db, T, rollout, 1, ring_one, NOW)
    assert made["raised"] == 0 and await rows(db) == []
