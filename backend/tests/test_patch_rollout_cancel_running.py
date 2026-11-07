"""Staged patch rollouts, gap plan 84-28: an operator can Cancel a running rollout (WR-03, D-16, KD-84-G3).

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. The rollout, its
computers, install rows and instructions are written straight into the collections the controller owns; Cancel is
the real lifecycle function and the real route, the controller tick is the real one with time frozen by ``now``.

Value: protects=PTCH-04 / PTCH-06 / PTCH-07 / D-16 / T-84-77 / T-84-78: Cancel of a running rollout stops new work at
once, reverts nothing, and ends the rollout once the installs in progress settle (at the latest RESULT_DEADLINE after
the request) with every claim released and the requester named; Resume and a second Cancel are refused meanwhile;
fails_when=a revert row or restart line appears after Cancel, a tick decides or sends anything after the request, a
failure that settles while cancelling halts the rollout, claims stay held after the installs settle or after
RESULT_DEADLINE, the rollout ends before RESULT_DEADLINE with an install still in flight, Resume succeeds while
cancelling, or the halted Cancel changes; no_claim=a real agent, a real install or the live database.
"""
import os
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger, protected
from autonomous_ops.rollout import controller, inflight, lifecycle, messages as rm
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.test_patch_rollout_lifecycle import ACTOR, BASE, NOW, T, Api, add, controls, host, rollout, world

SIX_HOURS = inflight.RESULT_DEADLINE


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


async def row(db, action_id, state, *, agent, ring=1, instruction=None, job=None, line="install"):
    await ledger.create_intent(db, {
        "id": action_id, "tenantId": T, "kind": "patching", "origin": "rollout", "dispatcher": "patch_rollout",
        "state": state, "command": "install_patches", "actions": ["install_patches"], "targets": [agent],
        "params": {"job_id": job} if job else {}, "steps": [], "reasonText": "A row.", "reasonCode": "playbook_raised",
        "instructionIds": [instruction] if instruction else [],
        "reason": {"ruleId": "rollout:install", "inputs": {"rolloutId": "r1", "ring": ring, "line": line}},
        "approval": {"expiresAt": NOW + timedelta(hours=5)}})


async def instruction(db, instruction_id, agent, status, **extra):
    await db.agent_instructions.insert_one({"id": instruction_id, "tenantId": T, "agent_id": agent, "type": "install_patches",
                                            "status": status, "created_at": NOW, **extra})


async def job(db, job_id):
    await db.patch_deployment_jobs.insert_one({"id": job_id, "tenantId": T, "status": "In Progress", "patchIds": ["openssl"]})


async def running_world(db, *, delivered=None):
    """Ring 0 passed (a healthy computer), ring 1 under way: h1 installed, h2 installing (instruction fetched),
    h3 waiting with an Install row approved but not sent, h4 installing with an instruction nobody fetched."""
    await world(db, status="running", ring=1, rings=3)
    await add(db, "h0", ring=0, state="healthy")
    await add(db, "h1", state="installed")
    await add(db, "h2", state="installing", installActionId="A-sent", installJobId="j2", installInstructionId="I-sent",
              installDispatchedAt=NOW, autoSettled=False, installedIds=[], installReportedAt=None)
    await add(db, "h3", state="waiting", waitReason="approval", installedIds=[], installReportedAt=None,
              lineActionIds={"install": ["AO-appr"]})
    await add(db, "h4", state="installing", installActionId="A-pend", installJobId="j4", installInstructionId="I-pend",
              installDispatchedAt=NOW, autoSettled=False, installedIds=[], installReportedAt=None)
    await job(db, "j2")
    await job(db, "j4")
    await instruction(db, "I-sent", "h2", "delivered", delivered_at=delivered or NOW)
    await instruction(db, "I-pend", "h4", "pending")
    await row(db, "A-sent", "dispatching", agent="h2", instruction="I-sent", job="j2")
    await row(db, "A-pend", "dispatching", agent="h4", instruction="I-pend", job="j4")
    await row(db, "AO-appr", "approved", agent="h3")


async def counts(db):
    return (await db.autonomy_actions.count_documents({"tenantId": T}),
            await db.agent_instructions.count_documents({"tenantId": T}))


async def undone_work(db):
    """Revert rows and restart lines: none may exist after a Cancel of a running rollout (D-16)."""
    return await db.autonomy_actions.count_documents({"tenantId": T, "$or": [
        {"command": "rollback_patches"}, {"reason.inputs.line": {"$in": ["reboot", "revert_reboot"]}}]})


# ---------------------------------------------------------------- Test A: the request

async def test_cancel_of_a_running_rollout_stops_new_work_closes_rows_and_reverts_nothing(mongo_db):
    db = mongo_db
    await running_world(db)

    out = await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)

    assert out == {"status": "cancelling", "reason": None, "ring": "Pilot"}
    got = await rollout(db)
    assert got["status"] == "running" and got["cancelRequested"]["by"] == {"id": ACTOR["id"], "name": "Ann"}
    assert (await db.autonomy_actions.find_one({"id": "AO-appr"}))["state"] == "expired"
    assert (await db.autonomy_actions.find_one({"id": "AO-appr"}))["reasonCode"] == "rollout_closed"
    unfetched = await db.autonomy_actions.find_one({"id": "A-pend"})
    assert unfetched["state"] == "failed" and unfetched["reasonCode"] == "rollout_halted"
    assert (await host(db, "h4"))["state"] == "not_reached"
    assert (await db.autonomy_actions.find_one({"id": "A-sent"}))["state"] == "dispatching"     # on the computer
    assert (await host(db, "h2"))["state"] == "installing"
    assert await undone_work(db) == 0
    assert len(await controls(db, "rollout_cancel_requested")) == 1

    before = await counts(db)
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    assert await counts(db) == before                       # nothing decided, raised or sent
    assert (await rollout(db))["status"] == "running" and await undone_work(db) == 0


# ---------------------------------------------------------------- Test B: it ends once the installs settle

async def test_the_rollout_ends_cancelled_when_the_installs_settle_and_every_patch_stays(mongo_db):
    db = mongo_db
    await running_world(db)
    await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)
    await db.patch_deployment_jobs.update_one({"id": "j2"}, {"$set": {"agentResults.h2": {
        "status": "completed", "reportedAt": (NOW + timedelta(minutes=5)).isoformat(),
        "results": [{"patch_id": "openssl", "status": "success", "reboot_required": False}]}}})

    await controller.tick(db, now=NOW + timedelta(minutes=10))

    got = await rollout(db)
    assert got["status"] == "cancelled" and got["cancelledBy"] == {"id": ACTOR["id"], "name": "Ann"}
    assert [r["state"] for r in got["rings"]] == ["passed", "cancelled", "cancelled"]
    assert await db.patch_rollout_hosts.count_documents({"tenantId": T, "active": True}) == 0
    assert [(await host(db, a))["state"] for a in ("h0", "h1", "h2")] == ["healthy", "installed", "installed"]
    assert await undone_work(db) == 0
    done = await controls(db, "rollout_cancelled")
    assert len(done) == 1 and done[0]["actor"]["display"] == "Ann"
    assert "haltReason" not in got and got["revertOpen"] is False


# ---------------------------------------------------------------- Test B2: bounded, and never a halt

async def test_an_install_nobody_answers_ends_the_cancel_without_a_halt_or_a_revert(mongo_db):
    db = mongo_db
    await running_world(db)
    await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)

    await controller.tick(db, now=NOW + SIX_HOURS + timedelta(seconds=1))      # 84-27 fails h2: rollout_no_result

    got = await rollout(db)
    assert got["status"] == "cancelled" and "haltedAt" not in got and "haltReason" not in got
    assert (await host(db, "h2"))["state"] == "failed" and (await host(db, "h2"))["failureCode"] == "rollout_no_result"
    assert await undone_work(db) == 0
    assert await db.patch_rollout_hosts.count_documents({"tenantId": T, "active": True}) == 0


async def test_an_install_still_in_flight_does_not_hold_the_cancel_past_the_deadline(mongo_db):
    db = mongo_db
    await running_world(db, delivered=NOW + timedelta(hours=5, minutes=30))
    await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)

    await controller.tick(db, now=NOW + SIX_HOURS - timedelta(seconds=1))
    still = await rollout(db)
    assert still["status"] == "running" and still["cancelRequested"]
    assert (await host(db, "h2"))["state"] == "installing"

    await controller.tick(db, now=NOW + SIX_HOURS + timedelta(seconds=1))
    got = await rollout(db)
    assert got["status"] == "cancelled" and "haltReason" not in got
    assert await db.patch_rollout_hosts.count_documents({"tenantId": T, "active": True}) == 0
    left = await host(db, "h2")
    assert left["state"] == "failed" and left["failureCode"] == "rollout_no_result"
    assert (await db.patch_deployment_jobs.find_one({"id": "j2"}))["status"] == "Failed"
    assert (await db.autonomy_actions.find_one({"id": "A-sent"}))["state"] == "failed"
    assert await undone_work(db) == 0


async def test_a_rollout_with_a_cancel_requested_can_not_be_halted(mongo_db):
    db = mongo_db
    await running_world(db)
    await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)
    fresh = await rollout(db)

    assert await lifecycle.halt(db, T, fresh, 1, code="host_failed", now=NOW) is False
    assert (await rollout(db))["status"] == "running"


# ---------------------------------------------------------------- Test C: the halted Cancel is unchanged

async def test_cancel_of_a_halted_rollout_still_ends_it_at_once(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "h1")

    out = await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)

    assert out["status"] == "cancelled"
    got = await rollout(db)
    assert got["status"] == "cancelled" and "cancelRequested" not in got
    assert await db.patch_rollout_hosts.count_documents({"tenantId": T, "active": True}) == 0


# ---------------------------------------------------------------- Test D: the route and the refusals

@pytest.fixture
async def api(mongo_db, monkeypatch):
    await running_world(mongo_db)
    return Api(mongo_db, monkeypatch)


async def test_the_cancel_route_asks_for_the_manage_permission_and_a_session(api):
    scopes = ["view:patching", "manage:patches"]
    for role, kwargs in (("user", {}), ("tenant_admin", {"auth": "api_key", "scopes": scopes})):
        assert (await api.call("POST", f"{BASE}/r1/cancel", role=role, **kwargs)).status_code == 403
    assert "cancelRequested" not in await rollout(api.db)

    got = await api.call("POST", f"{BASE}/r1/cancel")
    assert got.status_code == 200 and got.json()["status"] == "cancelling"


async def test_a_second_cancel_and_a_resume_are_refused_while_the_cancel_settles(api):
    assert (await api.call("POST", f"{BASE}/r1/cancel")).status_code == 200

    again = await api.call("POST", f"{BASE}/r1/cancel")
    assert again.status_code == 409 and again.json()["detail"] == rm.API_DETAIL["cancel_requested"]
    resume = await api.call("POST", f"{BASE}/r1/resume", json={"reason": "Go on"})
    assert resume.status_code == 409 and resume.json()["detail"] == rm.API_DETAIL["cancel_requested"]

    await api.db.patch_rollouts.update_one({"id": "r1"}, {"$set": {"status": "halted"}})      # forced: halted + requested
    resume = await api.call("POST", f"{BASE}/r1/resume", json={"reason": "Go on"})
    assert resume.status_code == 409 and resume.json()["detail"] == rm.API_DETAIL["cancel_requested"]


async def test_cancel_of_a_finished_rollout_is_refused(mongo_db):
    db = mongo_db
    await running_world(db)
    await db.patch_rollouts.update_one({"id": "r1"}, {"$set": {"status": "completed"}})
    with pytest.raises(lifecycle.NotHalted):
        await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)
    assert "cancelRequested" not in await rollout(db)
