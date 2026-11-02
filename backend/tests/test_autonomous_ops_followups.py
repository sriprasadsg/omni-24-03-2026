"""The two ways a quarantine ends badly: a locked file and a process that keeps running (Phase 83, plan 83-16,
RESP-03 / RESP-05 / RESP-06, D-06 / D-27, PROH-83-15). Real MongoDB (skips without one) through the throwaway
database of tests/_mongo_test_db.py.

A stand-in agent replays the example results of shared/agent-response-contract.json through the REAL result
route; the sweep, the gate, the approvals, the reconciler and the follow-ups are the real ones.

Value: protects=a file that cannot be moved because it is running reaches a person as ONE kill card; approving it
kills the named processes and tries the quarantine once more; a second failure stops; a kill reads Done only when
the agent says the processes are gone; nothing is ended without a person;
fails_when=a process is ended (or a kill instruction is written) before a person approved, a retry loops, a second
kill card appears after a failed retry, a survived kill leads to a retry, or the card names a path instead of the
pid and start time of the listed processes; no_claim=a real file system, process or agent.
"""
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent_tasks_endpoints
from autonomous_ops import approvals, followups, ledger, protected, reconciler, response_views, signals, sweep
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_feed_ioc, seed_native_verdict, seed_response_agent, seed_tenant

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
with open(os.path.join(_ROOT, "shared", "agent-response-contract.json"), encoding="utf-8") as fh:
    EXAMPLES = json.load(fh)["examples"]

SHA = "d" * 64
PATH = "/tmp/evil.bin"
APPROVER = {"username": "alice", "display": "Alice", "tier": "tenant"}
TOKENS = ["block_ip_ttl", "quarantine_file", "unquarantine_file", "kill_process_exe"]
RUNNING = EXAMPLES["quarantine_moved_still_running"]["still_running"]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    monkeypatch.delenv("AUTONOMOUS_OPS_STUCK_DISPATCH_MIN", raising=False)
    monkeypatch.delenv("AUTONOMOUS_OPS_NO_RESULT_MIN", raising=False)
    protected.cache_clear()


@pytest.fixture
async def world(mongo_db):
    """Tenant t1 (shadow off), agent a1 / host-a1 able to quarantine and kill, a file two sources flag."""
    await ledger.ensure_indexes(mongo_db)
    await signals.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_response_agent(mongo_db, "t1", "a1", hostname="host-a1", tokens=TOKENS)
    await seed_native_verdict(mongo_db, "t1", "host-a1", kind="file", target=PATH, sha256=SHA)
    await seed_feed_ioc(mongo_db, ioc_type="hash", value=SHA, feed="malwarebazaar")
    return mongo_db


def locked_with_processes():
    """The contract's locked answer plus the process list the agent reports with it (locked_body carries it)."""
    body = copy.deepcopy(EXAMPLES["quarantine_locked"])
    body["still_running"] = copy.deepcopy(RUNNING)
    return body


async def post_result(db, task_id, body, *, action):
    """What the agent posts: the example wrapped the way instructions.rs wraps it."""
    body = copy.deepcopy(EXAMPLES[body] if isinstance(body, str) else body)
    payload = {"task_id": task_id, "action": action, "type": action, "status": body["status"], "result": body}
    with patch.object(agent_tasks_endpoints, "get_database", return_value=db):
        return await agent_tasks_endpoints.report_instruction_result("a1", payload, _tenant={"id": "t1"})


async def rows(db, command=None):
    flt = {"tenantId": "t1", "kind": {"$ne": "control"}}
    if command:
        flt["command"] = command
    return [r async for r in db.autonomy_actions.find(flt, {"_id": 0}).sort("createdAt", 1)]


async def instructions(db, command=None):
    flt = {"tenantId": "t1", **({"type": command} if command else {})}
    return [d async for d in db.agent_instructions.find(flt, {"_id": 0}).sort("created_at", 1)]


async def instruction_of(db, row):
    return await db.agent_instructions.find_one({"id": row["instructionIds"][-1]}, {"_id": 0})


async def quarantine_ends(db, body):
    """One sweep tick starts the quarantine; the agent answers ``body``; one reconciler tick settles it.
    Returns the quarantine row as it is afterwards."""
    await sweep.tick(db)
    (q,) = await rows(db, "quarantine_file")
    assert q["state"] == "dispatching"
    await post_result(db, q["instructionIds"][0], body, action="quarantine_file")
    await reconciler.tick(db)
    return await ledger.get(db, "t1", q["id"])


async def kill_card(db):
    cards = await rows(db, "kill_process")
    assert len(cards) == 1, cards
    return cards[0]


async def approve_and_report(db, card, body):
    """A person approves the kill card; the agent answers ``body``; the reconciler settles it."""
    out = await approvals.approve(db, "t1", card["id"], approver=APPROVER)
    assert out["status"] == "dispatched", out
    await post_result(db, out["dispatch"]["task_id"], body, action="kill_process")
    await reconciler.tick(db)
    return await ledger.get(db, "t1", card["id"])


# ------------------------------------------------------------------ D-06: locked

async def test_a_locked_file_becomes_one_kill_card_and_nothing_is_ended(world):
    q = await quarantine_ends(world, locked_with_processes())
    assert (q["state"], q["reasonCode"]) == ("failed", "locked")
    k = await kill_card(world)
    assert k["state"] == "awaiting_approval" and k["dispatcher"] == "security_response" and k["autoDispatched"] is False
    assert k["targets"] == ["a1"] and k["dedupeKey"] == f"t1|sweep|kill_process|a1|{SHA}"
    # the card binds the approval to the listed processes: pid and start_time from the contract, unchanged
    assert k["params"] == {"target": str(RUNNING[0]["pid"]), "expected_exe": PATH,
                           "processes": [{"pid": RUNNING[0]["pid"], "start_time": RUNNING[0]["start_time"]}]}
    assert "quarantine_id" not in k["params"]
    chain = k["reason"]["inputs"]["chain"]
    assert chain["mode"] == "retry" and chain["quarantineActionId"] == q["id"]
    assert (chain["path"], chain["sha256"]) == (PATH, SHA) and chain["process"]["name"] == RUNNING[0]["name"]
    assert k["reason"]["inputs"]["incidentId"] == q["reason"]["inputs"]["incidentId"]
    assert await instructions(world, "kill_process") == []                      # PROH-83-15: nothing sent
    assert [r["command"] for r in await rows(world)] == ["quarantine_file", "kill_process"]
    await reconciler.tick(world)                                                  # nothing is repeated
    assert len(await rows(world)) == 2 and await instructions(world, "kill_process") == []


async def test_a_locked_file_with_no_listed_process_adds_no_card(world):
    q = await quarantine_ends(world, "quarantine_locked")                         # the example names no process
    assert (q["state"], q["reasonCode"]) == ("failed", "locked")
    assert await rows(world, "kill_process") == []


async def test_a_locked_file_never_counts_against_the_breaker_and_compensates_nothing(world):
    await quarantine_ends(world, locked_with_processes())
    assert await ledger.recent_finished_auto(world, "t1") == []
    assert await instructions(world, "unquarantine_file") == [] and await instructions(world, "kill_process") == []


@pytest.mark.parametrize("answer", ["kill_done", "kill_gone"])
async def test_approving_the_kill_then_retries_the_quarantine_once(world, answer):
    q = await quarantine_ends(world, locked_with_processes())
    k = await kill_card(world)
    done = await approve_and_report(world, k, answer)
    assert done["state"] == "verified"
    (kill_doc,) = await instructions(world, "kill_process")
    assert kill_doc["parameters"] == k["params"] and kill_doc["autonomy"]["actionId"] == k["id"]
    quarantines = await rows(world, "quarantine_file")
    assert len(quarantines) == 2
    r = quarantines[1]
    assert r["id"] != q["id"] and r["autoDispatched"] is True and r["state"] == "dispatching"
    assert r["reason"]["inputs"]["parentActionId"] == k["id"]
    assert r["reason"]["inputs"]["incidentId"] == q["reason"]["inputs"]["incidentId"]
    assert r["dedupeKey"] == f"t1|sweep|quarantine_file|a1|{SHA}|retry"
    assert r["params"] == {"path": PATH, "sha256": SHA}
    sent = await instructions(world, "quarantine_file")
    assert len(sent) == 2 and sent[1]["parameters"] == {"path": PATH, "sha256": SHA}
    assert r["instructionIds"] == [sent[1]["id"]]


async def test_a_retry_that_works_ends_verified_and_adds_nothing(world):
    await quarantine_ends(world, locked_with_processes())
    await approve_and_report(world, await kill_card(world), "kill_done")
    r = (await rows(world, "quarantine_file"))[1]
    await post_result(world, r["instructionIds"][0], "quarantine_moved", action="quarantine_file")
    await reconciler.tick(world)
    assert (await ledger.get(world, "t1", r["id"]))["state"] == "verified"
    assert len(await rows(world)) == 3 and len(await instructions(world)) == 3


async def test_a_retry_that_is_locked_again_stops_with_no_second_card_and_no_third_try(world):
    await quarantine_ends(world, locked_with_processes())
    k = await kill_card(world)
    await approve_and_report(world, k, "kill_done")
    r = (await rows(world, "quarantine_file"))[1]
    await post_result(world, r["instructionIds"][0], locked_with_processes(), action="quarantine_file")
    await reconciler.tick(world)
    again = await ledger.get(world, "t1", r["id"])
    assert (again["state"], again["reasonCode"]) == ("failed", "locked")
    assert len(await rows(world, "kill_process")) == 1 and len(await rows(world, "quarantine_file")) == 2
    assert len(await instructions(world)) == 3                                    # quarantine, kill, retry: no more
    await reconciler.tick(world)
    assert len(await rows(world)) == 3
    # the sweep does not start the chain again an hour later: the finding is held for a day
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    await world.agents.update_one({"id": "a1"}, {"$set": {"lastSeen": later.isoformat()}})
    await sweep.tick(world, now=later)
    assert len(await rows(world, "quarantine_file")) == 2 and len(await rows(world, "kill_process")) == 1


async def test_a_retry_that_moves_the_file_but_sees_it_running_adds_no_card(world):
    await quarantine_ends(world, locked_with_processes())
    await approve_and_report(world, await kill_card(world), "kill_done")
    r = (await rows(world, "quarantine_file"))[1]
    await post_result(world, r["instructionIds"][0], "quarantine_moved_still_running", action="quarantine_file")
    await reconciler.tick(world)
    assert (await ledger.get(world, "t1", r["id"]))["state"] == "verified"
    assert len(await rows(world, "kill_process")) == 1
    extras = response_views.row_extras(await ledger.get(world, "t1", r["id"]), can_act=True)
    assert "Needs your decision" not in (extras.get("resultText") or "")       # no card exists to point at


@pytest.mark.parametrize("answer, state, code", [("kill_survived", "failed", "verify_failed"),
                                                 ("kill_refused", "refused", "agent_refused")])
async def test_a_kill_that_did_not_end_the_process_adds_no_retry(world, answer, state, code):
    await quarantine_ends(world, locked_with_processes())
    k = await kill_card(world)
    done = await approve_and_report(world, k, answer)
    assert (done["state"], done["reasonCode"]) == (state, code)
    assert len(await rows(world, "quarantine_file")) == 1 and len(await instructions(world, "quarantine_file")) == 1
    assert not [r for r in await rows(world) if (r["reason"]["inputs"] or {}).get("parentActionId") == k["id"]]


async def test_a_denied_kill_card_adds_nothing_and_is_not_asked_again(world):
    q = await quarantine_ends(world, locked_with_processes())
    k = await kill_card(world)
    assert (await approvals.deny(world, "t1", k["id"], approver=APPROVER))["status"] == "denied"
    assert (await ledger.get(world, "t1", q["id"]))["state"] == "failed"
    assert len(await rows(world)) == 2 and await instructions(world, "kill_process") == []
    await followups.after(world, "t1", await ledger.get(world, "t1", q["id"]), await instruction_of(world, q))
    assert len(await rows(world, "kill_process")) == 1                              # a refusal is not nagged for a day


async def test_two_passes_over_one_failure_stay_one_card(world):
    q = await quarantine_ends(world, locked_with_processes())
    doc = await instruction_of(world, q)
    await followups.after(world, "t1", await ledger.get(world, "t1", q["id"]), doc)
    await followups.after(world, "t1", await ledger.get(world, "t1", q["id"]), doc)
    assert len(await rows(world, "kill_process")) == 1


async def test_a_tenant_in_shadow_gets_a_simulation_and_nothing_further(world):
    await sweep.tick(world)
    (q,) = await rows(world, "quarantine_file")
    await post_result(world, q["instructionIds"][0], locked_with_processes(), action="quarantine_file")
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": True}})
    await reconciler.tick(world)
    (k,) = await rows(world, "kill_process")
    assert k["state"] == "shadow" and k["shadow"] is True
    assert await instructions(world, "kill_process") == [] and len(await rows(world, "quarantine_file")) == 1


# ------------------------------------------------------------------ D-27: moved, still running

async def test_a_moved_file_whose_process_runs_stays_done_and_adds_a_kill_only_card(world):
    q = await quarantine_ends(world, "quarantine_moved_still_running")
    assert q["state"] == "verified" and q["stillRunning"] == RUNNING
    k = await kill_card(world)
    assert k["state"] == "awaiting_approval"
    assert k["params"] == {"target": str(RUNNING[0]["pid"]), "expected_exe": PATH,
                           "processes": [{"pid": RUNNING[0]["pid"], "start_time": RUNNING[0]["start_time"]}],
                           "quarantine_id": q["instructionIds"][0]}
    chain = k["reason"]["inputs"]["chain"]
    assert chain["mode"] == "kill_only" and chain["quarantineActionId"] == q["id"] and chain["sha256"] == SHA
    assert await instructions(world, "kill_process") == []
    text = response_views.row_extras(q, can_act=True)["resultText"]
    assert text.startswith("Moved ") and text.endswith("The process is still running. See Needs your decision.")


async def test_the_kill_only_card_ends_the_process_and_the_quarantine_row_stops_saying_it_runs(world):
    q = await quarantine_ends(world, "quarantine_moved_still_running")
    done = await approve_and_report(world, await kill_card(world), "kill_done")
    assert done["state"] == "verified"
    assert len(await rows(world, "quarantine_file")) == 1 and len(await instructions(world, "quarantine_file")) == 1
    after = await ledger.get(world, "t1", q["id"])
    assert after["state"] == "verified" and not after["stillRunning"]
    assert "still running" not in response_views.row_extras(after, can_act=True)["resultText"]


@pytest.mark.parametrize("answer", ["kill_survived", "kill_refused"])
async def test_a_kill_only_card_that_failed_leaves_the_quarantine_saying_it_runs(world, answer):
    q = await quarantine_ends(world, "quarantine_moved_still_running")
    done = await approve_and_report(world, await kill_card(world), answer)
    assert done["state"] in ("failed", "refused")
    after = await ledger.get(world, "t1", q["id"])
    assert after["stillRunning"] == RUNNING
    assert "The process is still running" in response_views.row_extras(after, can_act=True)["resultText"]
    assert len(await rows(world, "quarantine_file")) == 1


async def test_a_moved_file_with_no_process_listed_adds_no_card(world):
    q = await quarantine_ends(world, "quarantine_moved")
    assert q["state"] == "verified" and not q.get("stillRunning")
    assert await rows(world, "kill_process") == []


# ------------------------------------------------------------------ PROH-83-15 and structure

def test_the_follow_up_module_writes_no_instruction_and_never_sends_a_kill():
    with open(followups.__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert "agent_instructions" not in source and "gate.execute" not in source
    assert "gate.decide" in source and "kill_only" in source and "parentActionId" in source
    assert source.count("response_dispatch.send(") == 1                           # only the quarantine retry is sent


async def test_other_dispatchers_and_other_commands_are_left_alone(world):
    row = {"dispatcher": "remediation", "command": "quarantine_file", "state": "failed", "reasonCode": "locked",
           "tenantId": "t1", "targets": ["a1"], "params": {"path": PATH, "sha256": SHA}}
    assert await followups.after(world, "t1", row, {"result": {"still_running": RUNNING}}) is None
    row = {**row, "dispatcher": "security_response", "command": "block_ip"}
    assert await followups.after(world, "t1", row, {"result": {"still_running": RUNNING}}) is None
    assert await rows(world) == []
