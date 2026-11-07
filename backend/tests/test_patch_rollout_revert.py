"""Staged patch rollouts, plan 84-13: a halted ring is put back on its own, honestly, on a real database.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. Rollouts, jobs and
install rows are written straight into the collections the controller owns; the halt is the real
``lifecycle.halt``; the stand-in agent answers a revert by posting a result shaped like the shared contract's
``patchExamples`` through the real ``record_agent_patch_result`` path; the controller tick is the real one.

Value: protects=PTCH-04 / D-14 / D-15 / R13 / T-84-40..43: a halted ring is reverted on its own where the
computer can do it (also during a stop and outside the window), only the ids the computer itself installed are
put back, a computer is Reverted only when its agent said so, and a rollout row can never be put back by hand;
fails_when=a computer that could not be reverted reads Reverted, the halt block counts instructions instead of
results, a revert is held by a stop or a window, a revert restart can be approved during a stop, one bad patch
trips the breaker through its own revert, or an Undo button is offered on a rollout row; no_claim=a real agent,
a real revert or restart, or the live database.
"""
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import approvals, breaker, decision_row, delivery, ledger, protected, registry, response_views
from autonomous_ops.rollout import controller, lifecycle, lines, messages as rm, revert, store, views
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_platform_stop
from tests.rollout_support import post_result, seed_rollout_agent, seed_rollout_tenant, seed_window, success_result

T = "t1"
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
BOOT = 1_700_000_000
ACTOR = {"id": "u1", "name": "Ann"}
APPROVER = {"id": "u2", "name": "Bo"}
WITH_TOKEN = ("patch_reversible_check", "patch_revert_by_job", "reboot_host")
NO_TOKEN = ("patch_reversible_check", "reboot_host")
CONTRACT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "shared", "agent-response-contract.json")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


def example(name, patch_id=None, reboot=None):
    """A revert result exactly as the contract shows it, optionally for another patch id."""
    with open(CONTRACT, encoding="utf-8") as handle:
        body = copy.deepcopy(json.load(handle)["patchExamples"][name])
    for item in body["results"]:
        item["patch_id"] = patch_id or item["patch_id"]
        item["reboot_required"] = item["reboot_required"] if reboot is None else reboot
    return body


async def world(db, *, window=True):
    await ledger.ensure_indexes(db)
    await store.ensure_indexes(db)
    await seed_rollout_tenant(db, T, shadow=False)
    if window:
        await seed_window(db, T, start=(NOW - timedelta(hours=1)).strftime("%H:%M"),
                          end=(NOW + timedelta(hours=3)).strftime("%H:%M"))
    rings = [{"index": i, "key": k, "name": k.title(), "groupIds": [], "soakHours": 1, "failPct": 10, "minSample": 10,
              "isCanary": i == 0, "state": "installing" if i == 1 else "passed"} for i, k in enumerate(("canary", "pilot"))]
    await db.patch_rollouts.insert_one({
        "id": "r1", "tenantId": T, "name": "Nov", "patchIds": ["openssl"], "patchesByOs": {"linux": ["openssl"]},
        "status": "running", "shadow": False, "currentRing": 1, "rings": rings, "leftOut": [],
        "createdAt": NOW - timedelta(hours=3), "createdBy": ACTOR})


async def add(db, agent, *, os_name="linux", tokens=WITH_TOKEN, ring=1, ids=("openssl",), results=None,
              row_state="executed", host_state="installed", line=False, online=True):
    """A computer of the rollout that ran its install: the agent, the job with the agent's result, the ledger
    row and the host document."""
    from patch_core_endpoints import new_patch_job
    await seed_rollout_agent(db, T, agent, hostname=f"host-{agent}", platform="Windows 11" if os_name == "windows" else "Linux",
                             tokens=tokens, pending=[], boot_time=BOOT, last_seen=NOW if online else NOW - timedelta(days=1))
    results = results if results is not None else [{"patch_id": i, "status": "success", "reboot_required": False}
                                                   for i in ids]
    job_id, action_id = f"job-{agent}", f"AO-{agent}"
    job = new_patch_job(job_id, T, list(ids), [agent], [agent], "Autonomous Ops", "Rollout", None, NOW.isoformat(), "Completed")
    job["rolloutId"] = "r1"
    job["agentResults"] = {agent: {"status": "Completed", "successful": 1, "failed": 0, "total": len(results),
                                   "rebootRequired": False, "error": None, "results": results,
                                   "reportedAt": NOW.isoformat()}}
    await db.patch_deployment_jobs.insert_one(job)
    params = {"patch_ids": list(ids), "job_id": job_id}
    spec = registry.resolve("install_patches")
    await ledger.create_intent(db, {
        "id": action_id, "tenantId": T, "kind": "patching", "origin": "rollout", "dispatcher": "patch_rollout",
        "state": row_state, "command": "install_patches", "actions": ["install_patches"], "targets": [agent],
        "params": params, "steps": [{"command": "install_patches", "params": params}], "autoDispatched": not line,
        "reasonCode": "rollout_install_failed" if row_state == "failed" else "rollout_installed",
        "reasonText": "The install row.", "reason": {"ruleId": "rollout:install", "inputs": {
            "rolloutId": "r1", "ring": ring, "line": "install", "patchIds": list(ids)}},
        "undo": decision_row.undo_block(spec, params)})
    done = [r["patch_id"] for r in results if r.get("status") == "success"]
    doc = {"tenantId": T, "rolloutId": "r1", "agentId": agent, "ring": ring, "state": host_state, "os": os_name,
           "hostname": f"host-{agent}", "patchIds": list(ids), "installedIds": done, "active": True, "waitReason": None}
    doc.update({"lineActionIds": {"install": [action_id]}} if line else {"installActionId": action_id,
                                                                          "installJobId": job_id})
    await db.patch_rollout_hosts.insert_one(doc)


async def halt(db, ring=1):
    rollout = store.normalise(await db.patch_rollouts.find_one({"id": "r1"}))
    assert await lifecycle.halt(db, T, rollout, ring, code="host_failed", host="host-x1", now=NOW) is True
    return rollout


async def undo_instructions(db):
    return [i async for i in db.agent_instructions.find({"tenantId": T, "type": "rollback_patches"}, {"_id": 0})]


async def host_doc(db, agent):
    return await db.patch_rollout_hosts.find_one({"tenantId": T, "agentId": agent}, {"_id": 0})


async def row(db, agent):
    return await db.autonomy_actions.find_one({"id": f"AO-{agent}"}, {"_id": 0})


async def answer(db, agent, body):
    """The agent posts its answer to the revert it was given."""
    assert await post_result(db, (await host_doc(db, agent))["revertJobId"], agent, body)


# ---------------------------------------------------------------- Task 1: the halt starts the revert

async def test_a_halted_ring_reverts_the_computers_that_can_and_says_so_for_the_rest(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "w1", os_name="windows", tokens=NO_TOKEN, ids=("KB5034441",))
    await add(db, "l1", ids=("openssl",))
    await add(db, "l2", tokens=NO_TOKEN)
    await add(db, "x1", ids=("openssl",), results=[{"patch_id": "openssl", "status": "failed"}], row_state="failed",
              host_state="failed")
    await add(db, "p1", ring=0)
    await halt(db)

    for agent in ("w1", "l1"):
        got = await row(db, agent)
        assert got["state"] == "undone" and got["reasonCode"] == "ring_reverted"
        undo = got["undo"]
        assert undo["available"] is True and undo["action"] == "rollback_patches" and undo["undoneBy"]["id"] == "autonomous_ops"
        assert undo["params"]["patch_ids"] == (["KB5034441"] if agent == "w1" else ["openssl"])
        host = await host_doc(db, agent)
        assert host["state"] == "reverting" and host["revertActionId"] == f"AO-{agent}" and host["revertJobId"] == undo["params"]["job_id"]
    found = {i["agent_id"]: i for i in await undo_instructions(db)}
    assert sorted(found) == ["l1", "w1"]
    for agent, item in found.items():
        assert "expiresAt" not in item and item["autonomy"]["kind"] == "undo" and item["autonomy"]["actionId"] == f"AO-{agent}"
        assert item["payload"] == (await row(db, agent))["undo"]["params"]
    assert found["l1"]["payload"]["revert_of"] == "job-l1" and "revert_of" not in found["w1"]["payload"]
    job = await db.patch_deployment_jobs.find_one({"id": found["l1"]["payload"]["job_id"]})
    assert (job["type"], job["revertOf"], job["rolloutId"], job["dispatchedAgents"]) == ("Patch Rollback", "job-l1", "r1", ["l1"])

    l2 = await host_doc(db, "l2")
    assert (l2["state"], l2["notRevertedReason"]) == ("not_reverted", "agent_unsupported")
    assert (await row(db, "l2"))["state"] == "executed"
    assert rm.NOT_REVERTED["agent_unsupported"].startswith("Not reverted: this computer's agent doesn't support it yet")
    for untouched in ("x1", "p1"):
        assert (await host_doc(db, untouched))["state"] in ("failed", "installed")
        assert "revertJobId" not in await host_doc(db, untouched)
    assert (await row(db, "x1"))["state"] == "failed" and (await row(db, "p1"))["state"] == "executed"
    assert len(await undo_instructions(db)) == 2


@pytest.mark.parametrize("stop", ["platform", "tenant"])
async def test_the_revert_is_written_and_delivered_during_a_stop_and_outside_the_window(mongo_db, stop):
    db = mongo_db
    await world(db, window=False)
    await add(db, "w1", os_name="windows", tokens=NO_TOKEN, ids=("KB5034441",))
    await add(db, "l1")
    if stop == "platform":
        await seed_platform_stop(db)
    else:
        await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"stop": {
            "active": True, "scope": "tenant", "pressedBy": {"username": "ann"}, "pressedAt": datetime.now(timezone.utc)}}})
    await halt(db)
    pending = [i async for i in db.agent_instructions.find({"tenantId": T, "type": "rollback_patches"})]
    assert len(pending) == 2
    kept = await delivery.hold_back_autonomous(db, T, pending)
    assert sorted(i["agent_id"] for i in kept) == ["l1", "w1"]
    for item in kept:
        assert (await db.agent_instructions.find_one({"id": item["id"]}))["status"] == "pending"


async def test_a_partly_failed_install_reverts_only_what_succeeded_and_keeps_its_failure_for_the_breaker(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "l1", ids=("openssl", "curl", "zlib1g"), row_state="failed", host_state="failed",
              results=[{"patch_id": "openssl", "status": "success"}, {"patch_id": "curl", "status": "success"},
                       {"patch_id": "zlib1g", "status": "failed", "message": "no"}])
    await halt(db)
    got = await row(db, "l1")
    assert got["state"] == "undone" and got["undo"]["params"]["patch_ids"] == ["openssl", "curl"]
    assert got["reasonCode"] == "rollout_install_failed"            # a real failure still counts toward the breaker


async def test_the_revert_ids_come_from_the_shared_helper_and_nothing_else(mongo_db):
    from patch_core_endpoints import installed_ids_for
    job = {"agentResults": {"a_1": {"results": [{"patch_id": "openssl", "status": "success"},
                                               {"patch_id": "CVE-2026-1", "status": "success"},
                                               {"patch_id": "curl", "status": "failed"},
                                               {"patch_id": "KB5034441", "status": "success"}]}}}
    assert installed_ids_for(job, "a.1") == ["openssl", "KB5034441"]
    assert installed_ids_for({}, "a.1") == [] and installed_ids_for(None, "a.1") == []


async def test_a_second_pass_writes_no_second_revert_and_a_late_result_is_reverted_on_the_next_tick(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "l1")
    await add(db, "l3", host_state="installing", results=[])        # sent, no result yet
    await db.patch_deployment_jobs.update_one({"id": "job-l3"}, {"$set": {"agentResults": {}}})
    await db.autonomy_actions.update_one({"id": "AO-l3"}, {"$set": {"state": "dispatching"}})
    await halt(db)
    assert [i["agent_id"] for i in await undo_instructions(db)] == ["l1"]
    rollout = store.normalise(await db.patch_rollouts.find_one({"id": "r1"}))
    assert (await revert.start_ring_revert(db, T, rollout, 1, NOW))["decided"] == 0
    assert len(await undo_instructions(db)) == 1

    assert await post_result(db, "job-l3", "l3", success_result(["openssl"]))        # the install result lands after the halt
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    assert sorted(i["agent_id"] for i in await undo_instructions(db)) == ["l1", "l3"]
    assert (await row(db, "l3"))["state"] == "undone"


# ---------------------------------------------------------------- Task 2: results, restarts, the summary

async def settled(db, answers):
    """Revert two computers, let the agents answer as ``answers`` says and tick once."""
    await world(db)
    for agent, spec in answers.items():
        await add(db, agent, os_name=spec.get("os", "linux"), ids=(spec["id"],))
    await halt(db)
    for agent, spec in answers.items():
        if spec.get("body") is not None:
            await answer(db, agent, spec["body"])
    await controller.tick(db, now=NOW + timedelta(minutes=1))


async def test_each_result_settles_its_computer_and_only_a_success_reads_reverted(mongo_db):
    db = mongo_db
    changed = example("revert_not_changed", "openssl")
    changed["results"].append({"patch_id": "zlib1g", "status": "success", "reboot_required": False, "code": "reverted"})
    await settled(db, {"ok": {"id": "openssl", "body": example("revert_ok")},
                       "kb": {"id": "KB5034441", "os": "windows", "body": example("revert_not_uninstallable")},
                       "ver": {"id": "openssl", "body": example("revert_version_not_offered")},
                       "na": {"id": "openssl", "body": {"status": "failed", "results": [
                           {"patch_id": "openssl", "status": "failed", "code": "not_applicable", "message": "no record"}]}},
                       "wait": {"id": "openssl", "body": None}})
    states = {a: await host_doc(db, a) for a in ("ok", "kb", "ver", "na", "wait")}
    assert states["ok"]["state"] == "reverted" and states["ok"]["revertedAt"] is not None
    assert (states["kb"]["state"], states["kb"]["notRevertedReason"]) == ("not_reverted", "not_uninstallable")
    assert (states["ver"]["state"], states["ver"]["notRevertedReason"]) == ("not_reverted", "version_not_offered")
    assert (states["na"]["state"], states["na"]["notRevertedReason"]) == ("not_reverted", "not_applicable")
    assert states["wait"]["state"] == "reverting"
    rows = {r["agentId"]: r for r in views.host_rows([store.normalise(dict(s)) for s in states.values()])[0]}
    assert rows["kb"]["result"] == rm.NOT_REVERTED["not_uninstallable"]
    assert rows["na"]["result"] == rm.NOT_REVERTED_OTHER and rows["wait"]["state"] == "reverting"     # an unknown code never raises


async def test_a_skipped_patch_beside_a_success_is_reverted_and_a_job_that_changed_nothing_is_not(mongo_db):
    mixed = {"status": "completed", "results": [
        {"patch_id": "openssl", "status": "success", "code": "reverted"},
        {"patch_id": "curl", "status": "skipped", "code": "not_changed_by_job"}]}
    only = example("revert_not_changed")
    db = mongo_db
    await world(db)
    await add(db, "m1", ids=("openssl", "curl"))
    await add(db, "m2", ids=("curl",))
    await halt(db)
    await answer(db, "m1", mixed)
    await answer(db, "m2", only)
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    assert (await host_doc(db, "m1"))["state"] == "reverted"
    got = await host_doc(db, "m2")
    assert (got["state"], got["notRevertedReason"]) == ("not_reverted", "not_changed_by_job")


async def test_the_halt_summary_counts_the_results_recorded_and_never_the_instructions_sent(mongo_db):
    db = mongo_db
    await settled(db, {"a": {"id": "openssl", "body": example("revert_ok")},
                       "b": {"id": "KB5034441", "os": "windows", "body": example("revert_not_uninstallable")},
                       "c": {"id": "openssl", "body": None}})
    assert len(await undo_instructions(db)) == 3
    rollout = store.normalise(await db.patch_rollouts.find_one({"id": "r1"}))
    block = views.halt_block(rollout, await store.host_docs(db, T, "r1"))
    assert "Reverted on 1 computer." in block["reverts"] and "Reverting 1 computer now." in block["reverts"]
    assert any(l.startswith("1 computer could not be reverted: Windows doesn't allow this update to be uninstalled.")
              and l.endswith("The patch is still installed on it.") for l in block["reverts"])
    assert not any("3 computers" in l for l in block["reverts"])
    caller = type("Who", (), {"can_manage_patches": True, "can_open_decisions": True, "interactive": True,
                              "platform_tenant": False})()
    card = await views.rollout_card(db, T, store.normalise(await db.patch_rollouts.find_one({"id": "r1"})), caller, NOW)
    assert card["revertRunning"] is True and card["canResume"] is False


async def test_a_revert_the_agent_never_received_reads_not_reverted_not_reverting_forever(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "l1")
    await halt(db)
    await db.agent_instructions.update_one({"agent_id": "l1", "type": "rollback_patches"}, {"$set": {"status": "refused"}})
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    got = await host_doc(db, "l1")
    assert (got["state"], got["notRevertedReason"]) == ("not_reverted", "not_delivered")


async def test_a_revert_that_needs_a_restart_raises_the_line_which_a_stop_freezes_but_a_denial_still_works(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "l1")
    await halt(db)
    await answer(db, "l1", example("revert_ok", reboot=True))
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    got = await host_doc(db, "l1")
    assert got["state"] == "reverted" and got["revertRebootNeeded"] is True
    found = await lines.line_rows(db, T, "r1", 1, "revert_reboot")
    assert [(r["command"], r["targets"], r["state"]) for r in found] == [("reboot_host", ["l1"], "awaiting_approval")]
    block = views.halt_block(store.normalise(await db.patch_rollouts.find_one({"id": "r1"})),
                             await store.host_docs(db, T, "r1"))
    assert "A restart is needed on 1 computer to finish the revert. See Needs your decision." in block["reverts"]

    await seed_platform_stop(db)
    frozen = await lines.approve_line(db, T, "r1", 1, "revert_reboot", approver=APPROVER, now=NOW)
    assert frozen["status"] == "stopped"
    assert [i async for i in db.agent_instructions.find({"type": "reboot_host"})] == []
    denied = await lines.deny_line(db, T, "r1", 1, "revert_reboot", approver=APPROVER)
    assert denied["status"] == "denied"


async def test_no_restart_line_is_raised_during_a_stop_and_it_is_raised_when_the_stop_ends(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "l1")
    await halt(db)
    await answer(db, "l1", example("revert_ok", reboot=True))
    await seed_platform_stop(db)
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    assert (await host_doc(db, "l1"))["revertRebootNeeded"] is True            # settled and remembered
    assert await lines.line_rows(db, T, "r1", 1, "revert_reboot") == []        # but nothing asked for during the stop
    await seed_platform_stop(db, active=False)
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    assert len(await lines.line_rows(db, T, "r1", 1, "revert_reboot")) == 1


async def test_an_approved_revert_restart_is_sent_on_the_halted_rollout_and_ends_on_a_new_boot(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "l1")
    await halt(db)
    await answer(db, "l1", example("revert_ok", reboot=True))
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    # The approval dispatcher sends on the wall clock, not on NOW (fixed at import): late in a long run the
    # computer would read offline.
    await db.agents.update_one({"id": "l1"}, {"$set": {"lastSeen": datetime.now(timezone.utc).isoformat()}})
    done = await lines.approve_line(db, T, "r1", 1, "revert_reboot", approver=APPROVER, now=NOW)
    assert done["status"] == "approved" and done["when"] == "now"
    sent = [i async for i in db.agent_instructions.find({"type": "reboot_host"}, {"_id": 0})]
    assert len(sent) == 1 and sent[0]["agent_id"] == "l1"
    host = await host_doc(db, "l1")
    assert host["state"] == "reverted" and host["revertRestart"]["baselineBootTime"] == BOOT      # still Reverted, never Healthy
    due = store.aware(host["revertRestart"]["scheduledAt"])
    await db.agents.update_one({"id": "l1"}, {"$set": {"lastSeen": (due + timedelta(minutes=1)).isoformat(),
                                                       "meta.response_state.boot_time": int(due.timestamp()) + 5}})
    await controller.tick(db, now=due + timedelta(minutes=2))
    host = await host_doc(db, "l1")
    assert host["revertRebootNeeded"] is False and host["state"] == "reverted"
    ended = await db.autonomy_actions.find_one({"reason.inputs.line": "revert_reboot"})
    assert ended["state"] == "executed"


# ---------------------------------------------------------------- Task 3: the breaker and the no-undo rule

async def breaker_row(db, n, state, code):
    when = NOW - timedelta(minutes=n)
    await db.autonomy_actions.insert_one({
        "id": f"AO-br{n}", "tenantId": T, "kind": "patching", "state": state, "autoDispatched": True, "reasonCode": code,
        "createdAt": when - timedelta(seconds=30), "updatedAt": when, "finishedAt": when, "command": "install_patches",
        "targets": ["a1"], "params": {}, "dispatcher": "patch_rollout", "reason": {"ruleId": "t", "inputs": {}}})


async def test_three_reverted_rows_do_not_trip_the_breaker_but_three_real_install_failures_do(mongo_db):
    db = mongo_db
    await ledger.ensure_indexes(db)
    await seed_rollout_tenant(db, T, shadow=False)
    for n in range(3):
        await breaker_row(db, n, "undone", "ring_reverted")
    assert await breaker.evaluate(db, T, now=NOW) is False
    await db.autonomy_actions.delete_many({})
    for n in range(3):
        await breaker_row(db, n, "failed", "rollout_halted")
    assert await breaker.evaluate(db, T, now=NOW) is False
    await db.autonomy_actions.delete_many({})
    for n in range(3):
        await breaker_row(db, n, "failed", "rollout_install_failed")
    assert await breaker.evaluate(db, T, now=NOW) is True
    assert {"ring_reverted", "rollout_halted"} <= set(ledger.BREAKER_IGNORED)
    assert "rollout_install_failed" not in ledger.BREAKER_IGNORED


async def test_a_rollout_install_row_offers_no_undo_and_the_undo_route_refuses_it(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "l1")
    got = await row(db, "l1")
    assert response_views.row_extras(got, can_act=True)["canUndo"] is False
    assert response_views.row_extras({**got, "dispatcher": "security_response"}, can_act=True)["canUndo"] is True
    refused = await approvals.undo(db, T, "AO-l1", actor=APPROVER)
    assert refused == {"status": "refused", "reason": "not_undoable"}
    assert (await row(db, "l1"))["state"] == "executed" and await undo_instructions(db) == []
