"""The return to a person after three working days of silence (Phase 85, plan 85-17, D-08, D-31). Real MongoDB
(skips without one) through the throwaway database of tests/_mongo_test_db.py; the model is a stand-in and every
time is seeded by the test.

Value: protects=a requester who never answers is not forgotten, and the desk never decides for them;
fails_when=a ticket is returned a minute early or a day late, a confirmed, helped, withdrawn or reopened ticket
is returned, a return resolves or closes the ticket, Undo changes, a second sweep adds a second hand-off or
notice, one broken ticket stops the others, or the zone of the tenant is ignored; no_claim=holidays (the desk
counts Monday to Friday only, a decision of 85-CONTEXT).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger
from service_desk import returns, ticket_writes, worker
from service_desk.model import OllamaClient
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_worker_support import (Clock, _desk_env, add_tenant, kinds, queue, rows, stand_in,  # noqa: F401
                                               stored, world)

FRIDAY = datetime(2026, 11, 6, 16, 0, tzinfo=timezone.utc)          # the answer is posted Friday 16:00 UTC
DUE = datetime(2026, 11, 11, 16, 0, tzinfo=timezone.utc)            # Wednesday 16:00 UTC: three working days later
ONE_MINUTE = timedelta(minutes=1)


async def posted_by_the_desk(db, n=1, at=FRIDAY, tenant="t1"):
    """A real attempt: the ticket arrives and the worker posts its answer at ``at``."""
    ticket, job_id = await queue(db, n, arrived=at, tenant=tenant)
    stand_up, _ = stand_in()
    await worker.run_once(db, client=OllamaClient(transport=stand_up), clock=Clock(at))
    after = await stored(db, ticket)
    assert after["desk"]["phase"] == "posted" and after["status"] == "pending_customer", after["desk"]
    return after


async def answered(db, n, *, at=FRIDAY, tenant="t1", phase="posted", status="pending_customer"):
    """A ticket in the state an answer leaves it in, written directly (no model, no row)."""
    ticket = {"id": f"k{n}", "tenantId": tenant, "ticket_number": f"TKT-{n:04d}", "title": "t", "description": "d",
              "type": "task", "priority": "medium", "status": status, "reporter": "alice", "assignee": None,
              "raised_via": "portal", "comments": [], "history": [], "requester_channel": {"portal": True},
              "desk": {"phase": phase, "postedAt": at, "undoable": True}}
    await db.tickets.insert_one(dict(ticket))
    return ticket


def handoffs(found):
    return [r for r in found if r["command"] == "ticket_handoff" and r["reasonCode"] == "no_reply_to_ai_answer"]


# ---------------------------------------------------------------- the boundary

async def test_a_ticket_is_returned_at_the_due_time_and_not_a_minute_before(world):
    ticket = await posted_by_the_desk(world)
    before_rows = await rows(world)
    assert await returns.sweep_due(world, now=DUE - ONE_MINUTE) == {"returned": 0, "failed": 0}
    early = await stored(world, ticket)
    assert early["status"] == "pending_customer" and early["desk"]["phase"] == "posted"
    assert await rows(world) == before_rows

    assert await returns.sweep_due(world, now=DUE) == {"returned": 1, "failed": 0}
    after = await stored(world, ticket)
    assert after["status"] == "open" and after["desk"]["phase"] == "returned"
    assert after["desk"]["lastReason"] == "no_reply_to_ai_answer" and after["desk"]["returnedAt"] is not None
    assert len(handoffs(await rows(world))) == 1
    assert kinds(after).count("handoff_notice") == 1 and kinds(after).count("staff_note") == 1
    notice = [c for c in after["comments"] if c["kind"] == "handoff_notice"][0]
    assert notice["visibility"] == "requester"

    again = await returns.sweep_due(world, now=DUE + timedelta(hours=1))
    assert again == {"returned": 0, "failed": 0}
    assert len(handoffs(await rows(world))) == 1 and len(kinds(await stored(world, ticket))) == len(kinds(after))


async def test_the_tenants_own_time_zone_decides_the_hour_across_a_daylight_saving_change(world):
    """Friday 16:00 in New York before the clocks change is due Wednesday 16:00 after it (20:00 UTC, not 21:00)."""
    await world.maintenance_settings.insert_one({"tenantId": "t1", "timeZone": "America/New_York"})
    posted = datetime(2026, 3, 6, 21, 0, tzinfo=timezone.utc)                    # Friday 16:00 EST
    ticket = await answered(world, 1, at=posted)
    due = datetime(2026, 3, 11, 20, 0, tzinfo=timezone.utc)                      # Wednesday 16:00 EDT
    assert (await returns.sweep_due(world, now=due - ONE_MINUTE))["returned"] == 0
    assert (await returns.sweep_due(world, now=due))["returned"] == 1
    assert (await stored(world, ticket))["status"] == "open"


async def test_a_sent_draft_is_returned_like_a_post(world):
    ticket = await answered(world, 1, phase="sent")
    assert (await returns.sweep_due(world, now=DUE))["returned"] == 1
    assert (await stored(world, ticket))["desk"]["phase"] == "returned"


# ---------------------------------------------------------------- who is never returned

async def test_a_ticket_the_requester_or_a_person_already_dealt_with_is_never_returned(world):
    confirmed = await answered(world, 1, phase="confirmed", status="resolved")
    helped = await answered(world, 2, phase="helped", status="open")
    withdrawn = await answered(world, 3, phase="withdrawn")
    reopened = await answered(world, 4, status="open")
    on_hold = await answered(world, 5, status="on_hold")
    drafted = await answered(world, 6, phase="drafted")
    waiting = await answered(world, 7)
    assert await returns.sweep_due(world, now=DUE) == {"returned": 1, "failed": 0}
    for ticket in (confirmed, helped, withdrawn, reopened, on_hold, drafted):
        after = await stored(world, ticket)
        assert after["status"] == ticket["status"] and after["desk"]["phase"] == ticket["desk"]["phase"]
        assert after["comments"] == [] and after["history"] == []
    assert (await stored(world, waiting))["desk"]["phase"] == "returned"
    assert len(handoffs(await rows(world))) == 1


async def test_a_return_never_resolves_or_closes_a_ticket_and_leaves_undo_alone(world):
    ticket = await posted_by_the_desk(world)
    action_id = ticket["desk"]["actionId"]
    row_before = await ledger.get(world, "t1", action_id)
    await returns.sweep_due(world, now=DUE)
    after = await stored(world, ticket)
    assert after["status"] == "open" and "resolved_at" not in after and "closed_at" not in after
    assert after["desk"]["undoable"] is True
    row = await ledger.get(world, "t1", action_id)
    assert row["state"] == row_before["state"] and row["desk"]["undoable"] == row_before["desk"]["undoable"]
    assert row["desk"]["phase"] == "returned" and row["desk"]["returnedAt"] is not None


async def test_one_broken_ticket_does_not_stop_the_others_and_each_tenant_keeps_its_own(world, monkeypatch):
    await add_tenant(world, "t2")
    first = await answered(world, 1)
    other_tenant = await answered(world, 2, tenant="t2")
    last = await answered(world, 3)
    real = ticket_writes.move_status

    async def broken(db, tenant, ticket_id, *args, **kwargs):
        if ticket_id == "k1":
            raise RuntimeError("boom")
        return await real(db, tenant, ticket_id, *args, **kwargs)
    monkeypatch.setattr(ticket_writes, "move_status", broken)
    assert await returns.sweep_due(world, now=DUE) == {"returned": 2, "failed": 1}
    assert (await stored(world, first))["status"] == "pending_customer"
    for ticket in (other_tenant, last):
        assert (await stored(world, ticket))["desk"]["phase"] == "returned"
    t2_rows = handoffs(await rows(world, "t2"))
    assert len(t2_rows) == 1 and t2_rows[0]["tenantId"] == "t2"


# ---------------------------------------------------------------- the loop

async def test_the_loop_runs_a_pass_every_turn_and_the_return_sweep_once_an_hour(world, monkeypatch):
    passes, sweeps, clock = [], [], {"t": 0.0}

    async def fake_pass(db, **kwargs):
        passes.append(db)
        return {"jobs": []}

    async def fake_sweep(db, *, now):
        sweeps.append(now)
        return {"returned": 0, "failed": 0}

    async def sleep(seconds):
        clock["t"] += 1900 if len(passes) < 4 else 0
        if len(passes) >= 5:
            raise asyncio.CancelledError
    monkeypatch.setattr(worker, "run_once", fake_pass)
    monkeypatch.setattr(returns, "sweep_due", fake_sweep)
    with pytest.raises(asyncio.CancelledError):
        await worker.desk_loop(lambda: world, sleep=sleep, monotonic=lambda: clock["t"])
    # turns at 0, 1900, 3800, 5700 and 5700 seconds (monotonic): the sweep runs at 0 and 3800 only
    assert len(passes) == 5 and len(sweeps) == 2


async def test_a_pass_that_fails_does_not_end_the_loop(world, monkeypatch):
    turns = []

    async def broken_pass(db, **kwargs):
        turns.append(1)
        raise RuntimeError("database away")

    async def sleep(seconds):
        if len(turns) >= 3:
            raise asyncio.CancelledError
    monkeypatch.setattr(worker, "run_once", broken_pass)
    with pytest.raises(asyncio.CancelledError):
        await worker.desk_loop(lambda: world, sleep=sleep)
    assert len(turns) == 3
