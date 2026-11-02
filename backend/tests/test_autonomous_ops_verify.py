"""An undo that failed never reads as undone, and a failed verify compensates nothing (Phase 83, plan 83-16,
RESP-06 / RESP-03 / ACTV-02). Real MongoDB (skips without one) through the throwaway database of
tests/_mongo_test_db.py.

A stand-in agent posts the answers through the REAL result route; the sweep, the approvals (undo), the reconciler
and the verify step are the real ones.

Value: protects=what the screen says about an undo matches what the host reported: a restore the host could not
do puts the row back to Done with the failure recorded and Undo offered again; a restore that worked stays Undone;
a restore with no answer stays Undone until the no-result bound; RESP-06 - a failed verify compensates nothing;
fails_when=a row says Undone while the file is still in quarantine, a failed undo sends a second instruction on its
own, or a failed verify writes a compensating row or instruction; no_claim=a real agent or file system.
"""
import copy
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent_tasks_endpoints
from autonomous_ops import approvals, breaker, ledger, protected, reconciler, response_views, signals, sweep, verify
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_feed_ioc, seed_native_verdict, seed_response_agent, seed_tenant

SHA = "e" * 64
PATH = "/tmp/evil2.bin"
APPROVER = {"username": "alice", "display": "Alice", "tier": "tenant"}
RESTORED = {"status": "success", "outcome": "restored", "verify": {"ok": True, "check": "restored_to_path"}}
NOT_FOUND = {"status": "error", "outcome": "not_found", "error": "No such quarantined file."}
REFUSED = {"status": "error", "outcome": "refused", "error": "The original place is not writable."}
VERIFY_FAILED = {"status": "success", "outcome": "quarantined", "verify": {"ok": False, "check": "in_quarantine"}}
MOVED = {"status": "success", "outcome": "quarantined", "verify": {"ok": True, "check": "in_quarantine"}}
UNDO_FAILED_TEXT = "The host did not confirm the undo, so the action may still be in place."


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    monkeypatch.delenv("AUTONOMOUS_OPS_STUCK_DISPATCH_MIN", raising=False)
    monkeypatch.delenv("AUTONOMOUS_OPS_NO_RESULT_MIN", raising=False)
    protected.cache_clear()


@pytest.fixture
async def world(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await signals.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_response_agent(mongo_db, "t1", "a1", hostname="host-a1", tokens=["quarantine_file", "unquarantine_file"])
    await seed_native_verdict(mongo_db, "t1", "host-a1", kind="file", target=PATH, sha256=SHA)
    await seed_feed_ioc(mongo_db, ioc_type="hash", value=SHA, feed="malwarebazaar")
    return mongo_db


async def post_result(db, task_id, body, *, action):
    body = copy.deepcopy(body)
    payload = {"task_id": task_id, "action": action, "type": action, "status": body["status"], "result": body}
    with patch.object(agent_tasks_endpoints, "get_database", return_value=db):
        return await agent_tasks_endpoints.report_instruction_result("a1", payload, _tenant={"id": "t1"})


async def rows(db):
    return [r async for r in db.autonomy_actions.find({"tenantId": "t1", "kind": {"$ne": "control"}}, {"_id": 0})]


async def instructions(db):
    return [d async for d in db.agent_instructions.find({"tenantId": "t1"}, {"_id": 0}).sort("created_at", 1)]


async def done_quarantine(db):
    """A quarantine the agent confirmed (verified)."""
    await sweep.tick(db)
    (q,) = await rows(db)
    await post_result(db, q["instructionIds"][0], MOVED, action="quarantine_file")
    await reconciler.tick(db)
    q = await ledger.get(db, "t1", q["id"])
    assert q["state"] == "verified"
    return q


async def undone(db, answer):
    """A person undoes the quarantine; the agent answers ``answer`` (None: no answer yet). Returns the row."""
    q = await done_quarantine(db)
    out = await approvals.undo(db, "t1", q["id"], actor=APPROVER)
    assert out["status"] == "undone", out
    if answer is not None:
        await post_result(db, out["dispatch"]["task_id"], answer, action="unquarantine_file")
    return await ledger.get(db, "t1", q["id"])


# ------------------------------------------------------------------ a failed undo returns the row

@pytest.mark.parametrize("answer, reason", [(NOT_FOUND, "agent_failed"), (REFUSED, "agent_refused")])
async def test_an_undo_the_host_could_not_do_returns_the_row_to_done_with_the_failure(world, answer, reason):
    q = await undone(world, answer)
    assert q["state"] == "undone"                                      # until the reconciler reads the answer
    await reconciler.tick(world)
    back = await ledger.get(world, "t1", q["id"])
    assert back["state"] == "verified" and back["undoFailed"]["reason"] == reason
    assert isinstance(back["undoFailed"]["at"], datetime)
    assert back["undo"]["available"] is True and back["undo"]["action"] == "unquarantine_file"
    assert back["undo"]["undoneAt"] is None and back["undo"]["undoneBy"] is None
    assert back["undo"]["params"] == {"quarantine_id": q["instructionIds"][0]}
    extras = response_views.row_extras(back, can_act=True)
    assert extras["canUndo"] is True and extras["resultText"].startswith(UNDO_FAILED_TEXT)
    assert "Moved " in extras["resultText"]                            # what the row is still true about stays


async def test_a_failed_undo_sends_nothing_more_and_compensates_nothing(world):
    """RESP-06: the quarantine, the undo, and no third instruction; the pass writes no other row."""
    q = await undone(world, NOT_FOUND)
    await reconciler.tick(world)
    await reconciler.tick(world)
    assert [d["type"] for d in await instructions(world)] == ["quarantine_file", "unquarantine_file"]
    assert [r["id"] for r in await rows(world)] == [q["id"]]


async def test_undo_is_offered_again_and_a_second_try_works(world):
    q = await undone(world, NOT_FOUND)
    await reconciler.tick(world)
    out = await approvals.undo(world, "t1", q["id"], actor=APPROVER)
    assert out["status"] == "undone"
    await post_result(world, out["dispatch"]["task_id"], RESTORED, action="unquarantine_file")
    await reconciler.tick(world)
    final = await ledger.get(world, "t1", q["id"])
    assert final["state"] == "undone" and len(final["instructionIds"]) == 3
    assert "undoFailed" in final and response_views.row_extras(final, can_act=True)["canUndo"] is False


async def test_the_breaker_does_not_count_an_undo_that_never_took_effect(world):
    await undone(world, NOT_FOUND)
    await reconciler.tick(world)
    assert await ledger.recent_finished_auto(world, "t1", 3) and await breaker.evaluate(world, "t1") is False


# ------------------------------------------------------------------ a good undo and a silent one

async def test_an_undo_the_host_confirmed_stays_undone(world):
    q = await undone(world, RESTORED)
    await reconciler.tick(world)
    assert (await ledger.get(world, "t1", q["id"]))["state"] == "undone"
    assert "undoFailed" not in await ledger.get(world, "t1", q["id"])


async def test_an_undo_with_no_answer_stays_undone_until_the_no_result_bound(world, monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_OPS_NO_RESULT_MIN", "60")
    q = await undone(world, None)
    now = datetime.now(timezone.utc)
    await reconciler.tick(world, now=now + timedelta(minutes=10))
    assert (await ledger.get(world, "t1", q["id"]))["state"] == "undone"
    await reconciler.tick(world, now=now + timedelta(minutes=61))
    back = await ledger.get(world, "t1", q["id"])
    assert back["state"] == "verified" and back["undoFailed"]["reason"] == "no_result"


async def test_a_late_answer_after_the_bound_still_settles_by_what_it_says(world, monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_OPS_NO_RESULT_MIN", "60")
    q = await undone(world, None)
    await post_result(world, (await ledger.get(world, "t1", q["id"]))["instructionIds"][-1], RESTORED,
                      action="unquarantine_file")
    await reconciler.tick(world, now=datetime.now(timezone.utc) + timedelta(minutes=90))
    assert (await ledger.get(world, "t1", q["id"]))["state"] == "undone"


async def test_other_dispatchers_and_old_undos_are_left_alone(world):
    base = {"tenantId": "t1", "kind": "security", "state": "undone", "command": "block_ip", "targets": ["a1"],
            "instructionIds": ["i-1", "i-2"], "createdAt": datetime.now(timezone.utc), "reason": {"inputs": {}}}
    recent = {"available": True, "action": "unblock_ip", "params": {}, "undoneAt": datetime.now(timezone.utc)}
    await world.autonomy_actions.insert_many([
        {**base, "id": "AO-other", "dispatcher": "remediation", "undo": recent},
        {**base, "id": "AO-old", "dispatcher": "security_response",
         "undo": {**recent, "undoneAt": datetime.now(timezone.utc) - timedelta(days=3)}}])
    await world.agent_instructions.insert_many([
        {"id": "i-2", "tenantId": "t1", "status": "FAILURE", "result": {"outcome": "not_found"}}])
    await reconciler.tick(world)
    assert {r["id"]: r["state"] for r in await rows(world)} == {"AO-other": "undone", "AO-old": "undone"}


# ------------------------------------------------------------------ RESP-06: a failed verify compensates nothing

async def test_resp_06_a_failed_verify_writes_no_compensation_row_or_instruction(world):
    await sweep.tick(world)
    (q,) = await rows(world)
    await post_result(world, q["instructionIds"][0], VERIFY_FAILED, action="quarantine_file")
    await reconciler.tick(world)
    failed = await ledger.get(world, "t1", q["id"])
    assert (failed["state"], failed["reasonCode"]) == ("failed", "verify_failed")
    assert [d["type"] for d in await instructions(world)] == ["quarantine_file"]
    assert [r["id"] for r in await rows(world)] == [q["id"]]
    assert failed["rollback"] == [] and "undoFailed" not in failed
    assert verify.process_entries([{"pid": 1, "name": "x", "start_time": 5}, "junk"]) == []


async def test_a_confirmed_quarantine_is_verified_and_lists_no_process(world):
    q = await done_quarantine(world)
    assert q["verifiedAt"] is not None and q.get("stillRunning") in (None, [])
