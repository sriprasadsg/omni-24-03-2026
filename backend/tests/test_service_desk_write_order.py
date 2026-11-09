"""What the desk leaves behind when a write fails AFTER its answer or draft is visible (Phase 85, plan 85-27,
DESK-01, DESK-05, decisions D-09, D-24, D-31, review warnings WR-102 and WR-103). Real MongoDB (skips without one)
through the throwaway database of tests/_mongo_test_db.py; the model is a stand-in and one write is made to fail.

Value: protects=an answer the requester can already read is never followed, on the same attempt, by a "service
desk busy" hand-off, a row stuck at dispatching or a draft the draft panel cannot see (WR-102, T-85-96), and a
person-sent draft becomes visible only on a ticket that really moved to pending_customer (WR-103, T-85-97);
fails_when=a failing desk write, row transition, Activity text or notice after the post hands the ticket off, the
row stays dispatching, a draft is kept without draftWaiting, a lost status move still shows the answer, or two
people sending at once move the status twice; no_claim=a database that keeps refusing the desk write for good
(the answer then stays visible and the desk phase stays queued, assumption A-85-G11) and the HTTP routes.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger
from service_desk import SYSTEM_AUTHOR, notify, outcomes, ticket_writes, worker
from service_desk.model import OllamaClient
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_worker_support import (Clock, _desk_env, add_tenant, job, kinds, queue,  # noqa: F401
                                               rows, stand_in, stored, world)


def fail_when(monkeypatch, module, name, when, *, times=1):
    """Make ``module.name`` raise for the calls ``when(args, kwargs)`` picks: ``times`` of them, or every one
    when ``times`` is None. Every other call goes to the real function."""
    original = getattr(module, name)
    left = {"n": times}

    async def wrapper(*args, **kwargs):
        if when(args, kwargs) and (left["n"] is None or left["n"] > 0):
            if left["n"] is not None:
                left["n"] -= 1
            raise RuntimeError(f"injected failure of {name}")
        return await original(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)


def _fields(args, kwargs):
    return args[3] if len(args) > 3 else kwargs.get("fields") or {}


def _to_state(args, kwargs):
    return args[4] if len(args) > 4 else kwargs.get("to_state")


async def _run(db, **stand):
    transport, _ = stand_in(**stand)
    return await worker.run_once(db, client=OllamaClient(transport=transport), clock=Clock())


async def _no_handoff(db, ticket, after):
    """No staff note, no hand-off notice, no ticket_handoff row and no lastReason: nothing contradicts the answer."""
    assert not {"staff_note", "handoff_notice"} & set(kinds(after))
    assert [r["command"] for r in await rows(db)] == ["ticket_answer"]
    assert "lastReason" not in (after.get("desk") or {})


async def _posted_cleanly(db, ticket, job_id):
    """The ticket ends posted: held for the customer, one requester-visible answer, desk phase posted, the row
    executed, the job reason posted and no hand-off anywhere."""
    after = await stored(db, ticket)
    assert after["status"] == "pending_customer"
    [answer] = [c for c in after["comments"] if c["kind"] == "ai_answer"]
    assert answer["visibility"] == "requester"
    assert after["desk"]["phase"] == "posted" and after["desk"]["draftWaiting"] is False
    [row] = await rows(db)
    assert row["state"] == "executed" and row["desk"]["phase"] == "posted"
    assert (await job(db, job_id))["reason"] == "posted"
    await _no_handoff(db, ticket, after)


# ---------------------------------------------------------------- post: a failure after the answer is visible

async def test_a_failed_desk_write_after_the_answer_is_repaired_and_never_handed_off(world, monkeypatch):
    """protects=WR-102 the desk phase write is tried again once; fails_when=the first failure hands the ticket
    to a person after the requester can already read the answer."""
    ticket, job_id = await queue(world, 1)
    fail_when(monkeypatch, ticket_writes, "set_desk", lambda a, k: _fields(a, k).get("phase") == "posted")
    await _run(world)
    await _posted_cleanly(world, ticket, job_id)


async def test_a_failed_executed_transition_is_repaired_and_never_handed_off(world, monkeypatch):
    """protects=WR-102 the row leaves dispatching (Undo and the breaker read it); fails_when=the row stays
    dispatching or the ticket is handed off."""
    ticket, job_id = await queue(world, 1)
    fail_when(monkeypatch, ledger, "transition", lambda a, k: _to_state(a, k) == "executed")
    await _run(world)
    await _posted_cleanly(world, ticket, job_id)


async def test_failed_activity_words_and_notice_never_hand_the_ticket_off(world, monkeypatch, caplog):
    """protects=WR-102 the Activity words and the notice are guarded and logged; fails_when=either failure
    reaches the worker's error path."""
    ticket, job_id = await queue(world, 1)
    fail_when(monkeypatch, ledger, "set_display", lambda a, k: True, times=None)
    fail_when(monkeypatch, notify, "requester_notice", lambda a, k: True, times=None)
    with caplog.at_level(logging.ERROR):
        await _run(world)
    await _posted_cleanly(world, ticket, job_id)
    assert any(ticket["id"] in record.getMessage() for record in caplog.records)


async def test_a_desk_write_that_keeps_failing_leaves_the_visible_answer_and_no_hand_off(world, monkeypatch, caplog):
    """protects=A-85-G11 the answer stays, the phase stays queued and the log names the ticket; fails_when=a
    visible answer is followed by a contradicting hand-off."""
    ticket, job_id = await queue(world, 1)
    fail_when(monkeypatch, ticket_writes, "set_desk", lambda a, k: _fields(a, k).get("phase") == "posted",
              times=None)
    with caplog.at_level(logging.ERROR):
        await _run(world)
    after = await stored(world, ticket)
    assert after["status"] == "pending_customer" and "ai_answer" in kinds(after)
    assert after["desk"]["phase"] == "queued"
    await _no_handoff(world, ticket, after)
    assert any(ticket["id"] in record.getMessage() for record in caplog.records)


async def test_a_crash_after_the_comment_is_never_followed_by_a_hand_off(world, monkeypatch):
    """protects=WR-102 belt: _fail and the stale-job recovery treat a desk answer on the ticket as answered even
    while desk.phase is still queued; fails_when=a ticket holding an ai_answer gets a busy hand-off."""
    ticket, job_id = await queue(world, 1)

    async def post_then_crash(db, tenant, tkt, *, action_id, text, cited, matched, title, now):
        await ticket_writes.move_status(db, tenant, tkt["id"], ("open",), "pending_customer", actor=SYSTEM_AUTHOR,
                                        now=now)
        await ticket_writes.add_comment(db, tenant, tkt["id"], comment_id="sd-" + action_id, kind="ai_answer",
                                        visibility="requester", text=text, author=SYSTEM_AUTHOR, now=now,
                                        ai={"actionId": action_id, "state": "posted"})
        raise RuntimeError("the process failed after the comment")

    monkeypatch.setattr(outcomes, "post", post_then_crash)
    await _run(world)
    after = await stored(world, ticket)
    assert (await job(world, job_id))["reason"] == "error"
    assert after["status"] == "pending_customer" and kinds(after) == ["ai_answer"]
    assert after["desk"]["phase"] == "queued"
    await _no_handoff(world, ticket, after)
    assert await worker._to_a_person(world, await job(world, job_id), Clock()(), only_if_unanswered=True) \
        == "already_handled"
