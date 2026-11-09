"""The gate's side of the service desk (Phase 85, plan 85-04, DESK-01 / DESK-05).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the D-03 outcome matrix (only Undoable-auto, shadow off, no stop, no force_suggest and
under 20 an hour posts), the desk's own hourly pool (the 21st answer is a draft, nobody is paged, security
actions are untouched), drafts that never expire, approve and deny closed to desk rows, a pluggable undo
that fails closed, no ticket command ever written to an agent queue, a reconciler that leaves desk rows
alone, and Activity rows that link to their ticket; fails_when=Suggest or a forced suggestion posts, the
21st answer becomes an approval card or a page, a draft expires, a draft can be approved from Activity,
a desk undo runs without a registered handler, a ticket command reaches an agent, or an Activity row loses
its ticket link or shows Undo when it cannot work; no_claim=the desk's own undo handler and breaker
(plan 85-18, test_service_desk_withdraw.py).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import approvals, desk_gate, dispatch_check, gate, ledger, messages, reconciler, views
from tests._autonomous_ops_http import api  # noqa: F401  (fixture: both routers on one app; also sets the autouse env)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_platform_stop, seed_tenant

DESK = {"ticketId": "k1", "ticketNumber": "TKT-0001", "title": "VPN drops", "phase": "drafted"}


@pytest.fixture
async def world(mongo_db):  # noqa: F811
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_tenant(mongo_db, "t2", shadow=False)
    await mongo_db.tickets.insert_many([
        {"id": f"k{i}", "tenantId": "t1", "ticket_number": f"TKT-{i:04d}", "title": f"Ticket {i}"} for i in range(1, 30)
    ] + [{"id": "other", "tenantId": "t2", "ticket_number": "TKT-9000", "title": "Other tenant"}])
    return mongo_db


def desk_request(tenant, ticket_id, *, force_suggest=False, **extra):
    """The ActionRequest the desk pipeline sends (kind servicedesk, dispatcher service_desk, no targets)."""
    desk = {**DESK, "ticketId": ticket_id, "ticketNumber": f"TKT-{ticket_id}"}
    return gate.ActionRequest(
        tenant_id=tenant, kind="servicedesk", origin="service_desk", actions=["ticket_answer"], targets=[],
        params={"ticketId": ticket_id}, dedupe_key=f"{tenant}|service_desk|{ticket_id}",
        reason={"ruleId": "service_desk:answer", "inputs": {"suggestionOnly": True}}, dispatcher="service_desk",
        desk=desk, force_suggest=force_suggest, **extra)


async def _decide(db, req, *, master_shadow=False):
    return await gate.decide(db, req, master_shadow=master_shadow)


async def _rows(db, tenant="t1", **flt):
    return await db.autonomy_actions.find({"tenantId": tenant, **flt}, {"_id": 0}).to_list(100)


async def _set(db, tenant, **fields):
    await db.autonomy_settings.update_one({"tenantId": tenant}, {"$set": fields})


# ---------------------------------------------------------------- Task 1: the D-03 matrix

async def test_undoable_auto_with_everything_clear_posts(world):
    """protects=D-03: the one case that posts."""
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.state, d.shadow) == ("allow_auto", "dispatching", False)
    (row,) = await _rows(world)
    assert row["state"] == "dispatching" and row["autoDispatched"] is True


async def test_suggest_level_gives_a_draft(world):
    await _set(world, "t1", level="suggest")
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.state, d.reason) == ("suggest", "suggested", "level_suggest")


async def test_force_suggest_gives_a_draft_even_at_undoable_auto(world):
    """protects=PROH-85-10: a tenant at Undoable-auto whose desk switch is Drafts only never posts."""
    d = await _decide(world, desk_request("t1", "k1", force_suggest=True))
    assert (d.outcome, d.state, d.reason) == ("suggest", "suggested", "suggest_requested")
    assert await _rows(world, state="dispatching") == []
    assert await _rows(world, autoDispatched=True) == []


async def test_shadow_records_what_would_have_happened(world):
    await _set(world, "t1", shadow=True)
    d = await _decide(world, desk_request("t1", "k1"))
    assert d.state == "shadow" and d.would_have == "allow_auto" and d.shadow is True
    (row,) = await _rows(world)
    assert row["state"] == "shadow" and row["wouldHave"] == "allow_auto"


async def test_the_deployment_master_shadow_also_wins(world):
    d = await _decide(world, desk_request("t1", "k1"), master_shadow=True)
    assert d.state == "shadow" and d.would_have == "allow_auto"


async def test_a_tenant_stop_is_a_recorded_refusal(world):
    await _set(world, "t1", stop={"active": True, "by": "admin", "at": datetime.now(timezone.utc)})
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.reason, d.recorded) == ("refuse", "tenant_stop", True)
    (row,) = await _rows(world)
    assert row["state"] == "refused"


async def test_a_platform_stop_is_a_recorded_refusal(world):
    await seed_platform_stop(world)
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.reason) == ("refuse", "platform_stop")


async def test_level_off_records_nothing(world):
    await _set(world, "t1", level="off")
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.reason, d.recorded) == ("refuse", "level_off", False)
    assert await _rows(world) == []


async def test_an_unticked_tenant_records_nothing(world):
    await seed_tenant(world, "t3", shadow=False, ticked=False)
    d = await _decide(world, desk_request("t3", "k1"))
    assert (d.outcome, d.reason, d.recorded) == ("refuse", "not_enabled", False)
    assert await _rows(world, tenant="t3") == []


async def test_a_ticket_of_another_tenant_or_no_ticket_is_refused(world):
    d = await _decide(world, desk_request("t1", "other"))
    assert (d.outcome, d.reason) == ("refuse", "cross_tenant_target")
    d = await _decide(world, desk_request("t1", "missing"))
    assert (d.outcome, d.reason) == ("refuse", "cross_tenant_target")
    assert await _rows(world, state={"$in": ["dispatching", "suggested", "executed"]}) == []


async def test_an_agent_target_on_a_desk_request_is_refused(world):
    req = desk_request("t1", "k1")
    req.targets = ["agent-1"]
    d = await _decide(world, req)
    assert (d.outcome, d.reason) == ("refuse", "invalid_target")


# ---------------------------------------------------------------- Task 1: the desk's own hourly pool

async def _seed_rows(db, n, *, kind, tenant="t1", minutes=10, tag="s"):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    docs = []
    for i in range(n):
        created = now - timedelta(minutes=minutes, seconds=i)
        docs.append({"id": f"AO-{tag}-{kind}-{i}", "tenantId": tenant, "kind": kind, "state": "executed",
                     "autoDispatched": True, "createdAt": created, "updatedAt": created, "finishedAt": created,
                     "command": "ticket_answer" if kind == ledger.DESK_KIND else "block_ip", "targets": [],
                     "reason": {"ruleId": "t", "inputs": {}}})
    if docs:
        await db.autonomy_actions.insert_many(docs)


async def test_the_limit_is_twenty_and_is_the_desk_constant():
    from service_desk import DESK_RATE_LIMIT
    assert desk_gate.DESK_RATE_LIMIT == DESK_RATE_LIMIT == 20


async def test_the_21st_answer_in_an_hour_is_a_draft_and_nobody_is_told(world):
    """protects=D-30 / D-22 / PROH-85-07: a draft with the desk's own code, never an approval card, no
    notification and no on-call document."""
    await _seed_rows(world, 20, kind=ledger.DESK_KIND)
    d = await _decide(world, desk_request("t1", "k21"))
    assert (d.outcome, d.state, d.reason) == ("suggest", "suggested", "desk_rate_limit")
    (row,) = await _rows(world, state="suggested")
    assert row["reasonCode"] == "desk_rate_limit" and row["reasonText"] == messages.REASON_TEXT["desk_rate_limit"]
    assert row["approval"]["requiredBy"] == "desk_rate_limit"
    assert await _rows(world, state="awaiting_approval") == []
    assert await world.notifications.count_documents({}) == 0
    for name in await world.list_collection_names():
        if "oncall" in name.lower() or "on_call" in name.lower():
            assert await world[name].count_documents({}) == 0, name
    marker = await world.autonomy_settings.find_one({"tenantId": "t1"})
    assert marker.get("rateLimitNotifiedAt") is None


async def test_nineteen_answers_still_post(world):
    await _seed_rows(world, 19, kind=ledger.DESK_KIND)
    d = await _decide(world, desk_request("t1", "k20"))
    assert (d.outcome, d.state) == ("allow_auto", "dispatching")


async def test_rows_older_than_an_hour_do_not_count(world):
    await _seed_rows(world, 20, kind=ledger.DESK_KIND, minutes=90)
    d = await _decide(world, desk_request("t1", "k21"))
    assert d.state == "dispatching"


async def test_twenty_desk_rows_leave_the_security_limit_untouched(world):
    """protects=D-30: a ticket flood never pushes a security action to approval."""
    await _seed_rows(world, 20, kind=ledger.DESK_KIND)
    await world.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "h1", "ipAddress": "10.1.1.5"})
    req = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["block_ip"], targets=["a1"],
                             params={"ip_address": "203.0.113.7"}, dedupe_key="t1|block_ip|203.0.113.7")
    d = await _decide(world, req)
    assert (d.outcome, d.state) == ("allow_auto", "dispatching")


async def test_twenty_security_rows_do_not_limit_the_desk(world):
    await _seed_rows(world, 20, kind="security")
    d = await _decide(world, desk_request("t1", "k21"))
    assert d.state == "dispatching"


async def test_an_unreadable_pool_count_drafts_instead(world, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(ledger, "count_auto_since", boom)
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.reason) == ("suggest", "desk_rate_limit")


# ---------------------------------------------------------------- Task 1: drafts never expire

async def test_a_draft_has_no_expiry_and_expire_due_leaves_it(world):
    """protects=research default: a draft waits on the ticket until a person sends, edits or discards it."""
    await _decide(world, desk_request("t1", "k1", force_suggest=True))
    (row,) = await _rows(world)
    assert row["state"] == "suggested" and row["approval"]["expiresAt"] is None
    assert await approvals.expire_due(world, now=datetime.now(timezone.utc) + timedelta(hours=25)) == 0
    (row,) = await _rows(world)
    assert row["state"] == "suggested"


async def test_another_dispatchers_suggestion_still_expires(world):
    """No behaviour change for every other row: a card keeps its 24 hour expiry."""
    await world.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "h1", "ipAddress": "10.1.1.5"})
    req = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["block_ip"], targets=["a1"],
                             params={"ip_address": "203.0.113.7"}, dedupe_key="t1|block_ip|203.0.113.7",
                             force_suggest=True)
    await _decide(world, req)
    (row,) = await _rows(world)
    assert isinstance(row["approval"]["expiresAt"], datetime)


# ---------------------------------------------------------------- Task 2: approve, deny, undo, agent queue, reconciler

APPROVER = {"username": "alice", "display": "Alice", "tier": "tenant"}


async def _desk_row(db, ticket, *, state="suggested", phase="posted", undoable=True, tenant="t1"):
    """One recorded desk row: a draft (suggested) or an answer that was posted (executed)."""
    if state == "suggested":
        d = await _decide(db, desk_request(tenant, ticket, force_suggest=True))
    else:
        d = await _decide(db, desk_request(tenant, ticket))
        assert d.state == "dispatching"
        await ledger.transition(db, tenant, d.action_id, ("dispatching",), state,
                                **{"desk.phase": phase, "desk.undoable": undoable})
    return d.action_id


@pytest.mark.parametrize("what", ["approve", "deny"])
async def test_approve_and_deny_refuse_a_desk_draft(world, what):
    """protects=T-85-12 / D-10: a draft is sent, edited or discarded on the ticket only."""
    action_id = await _desk_row(world, "k1")
    if what == "approve":
        out = await approvals.approve(world, "t1", action_id, approver=APPROVER)
    else:
        out = await approvals.deny(world, "t1", action_id, approver=APPROVER, reason="no")
    assert out == {"status": "refused", "reason": "desk_draft"}
    (row,) = await _rows(world)
    assert row["state"] == "suggested" and row["approval"]["approver"] is None
    assert await world.agent_instructions.count_documents({}) == 0


async def test_approve_still_reports_not_found_for_an_unknown_row(world):
    assert (await approvals.approve(world, "t1", "AO-none", approver=APPROVER))["status"] == "not_found"
    assert (await approvals.deny(world, "t1", "AO-none", approver=APPROVER))["status"] == "not_found"


async def test_undo_calls_the_handler_registered_for_the_desk(world, monkeypatch):
    """protects=D-12: the desk's own withdraw is plugged in by registration (85-18 owns it)."""
    calls = []

    async def fake(db, tenant_id, row, *, actor):
        calls.append((tenant_id, row["id"], actor))
        return {"status": "undone", "desk_breaker_tripped": False}

    monkeypatch.setitem(approvals._UNDO_HANDLERS, "service_desk", fake)
    action_id = await _desk_row(world, "k1", state="executed")
    out = await approvals.undo(world, "t1", action_id, actor=APPROVER)
    assert out == {"status": "undone", "desk_breaker_tripped": False}
    assert calls == [("t1", action_id, APPROVER)]


async def test_undo_with_no_desk_handler_refuses_and_writes_nothing(world, monkeypatch):
    """protects=T-85-15: fail closed. The real handler (85-18) registers when service_desk.withdraw is imported,
    so this test takes it out for its own run."""
    monkeypatch.delitem(approvals._UNDO_HANDLERS, "service_desk", raising=False)
    action_id = await _desk_row(world, "k1", state="executed")
    before = await _rows(world)
    out = await approvals.undo(world, "t1", action_id, actor=APPROVER)
    assert out == {"status": "refused", "reason": "not_undoable"}
    assert await _rows(world) == before and before[0]["state"] == "executed"
    assert await world.agent_instructions.count_documents({}) == 0


@pytest.mark.parametrize("command", ["ticket_answer", "ticket_withdraw"])
@pytest.mark.parametrize("dispatcher", ["service_desk", "instruction", "remediation"])
async def test_bind_refuses_every_ticket_command_for_every_row(world, command, dispatcher):
    """protects=T-85-13 (assumption-delta companion): no ticket command can be bound to an agent dispatch."""
    row = {"id": "AO-x", "tenantId": "t1", "dispatcher": dispatcher, "targets": ["a1"], "command": command,
           "params": {}, "actions": [command]}
    out = await dispatch_check.bind(world, "t1", row, command=command, agent_id="a1", params={}, kind="action")
    assert out == "unregistered_action"


async def test_gate_execute_never_writes_a_ticket_command_to_an_agent_queue(world):
    action_id = await _desk_row(world, "k1", state="executed")
    for command, kind in (("ticket_answer", "action"), ("ticket_withdraw", "undo")):
        out = await gate.execute(world, "t1", action_id, command=command, agent_id="a1", params={}, kind=kind)
        assert out.get("status") != "queued"
    assert await world.agent_instructions.count_documents({}) == 0


async def test_the_reconciler_leaves_a_dispatching_desk_row_untouched(world):
    d = await _decide(world, desk_request("t1", "k1"))
    assert d.state == "dispatching"
    long_ago = datetime.now(timezone.utc) - timedelta(hours=3)
    await world.autonomy_actions.update_one({"id": d.action_id}, {"$set": {"updatedAt": long_ago}})
    before = (await _rows(world))[0]
    await reconciler.tick(world, now=datetime.now(timezone.utc) + timedelta(hours=2))
    (after,) = await _rows(world)
    assert after["state"] == "dispatching" and after["updatedAt"] == before["updatedAt"]


async def test_the_reconciler_still_fails_a_stuck_security_row(world):
    """The desk skip is by dispatcher only: a stuck instruction row is still failed as before."""
    await world.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "h1", "ipAddress": "10.1.1.5"})
    req = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["block_ip"], targets=["a1"],
                             params={"ip_address": "203.0.113.7"}, dedupe_key="t1|block_ip|203.0.113.7")
    d = await _decide(world, req)
    await world.autonomy_actions.update_one({"id": d.action_id}, {"$set": {
        "updatedAt": datetime.now(timezone.utc) - timedelta(hours=3)}})
    await reconciler.tick(world, now=datetime.now(timezone.utc) + timedelta(hours=2))
    (row,) = await _rows(world)
    assert row["state"] == "failed"


async def test_the_undo_route_reports_deskBreakerTripped(api, monkeypatch):
    """protects=D-25: the undo body says whether the desk's own breaker tripped."""
    await seed_tenant(api.db, "t1", shadow=False)
    await api.db.tickets.insert_many([{"id": "k1", "tenantId": "t1", "ticket_number": "TKT-0001"},
                                      {"id": "k2", "tenantId": "t1", "ticket_number": "TKT-0002"}])
    tripped = {"value": True}

    async def fake(db, tenant_id, row, *, actor):
        await ledger.transition(db, tenant_id, row["id"], ("executed",), "undone", actor=actor)
        return {"status": "undone", "desk_breaker_tripped": tripped["value"]}

    monkeypatch.setitem(approvals._UNDO_HANDLERS, "service_desk", fake)
    first = await _desk_row(api.db, "k1", state="executed")
    done = await api.call("POST", f"/api/autonomous-ops/actions/{first}/undo", role="security_analyst")
    assert done.status_code == 200, done.text
    assert done.json()["deskBreakerTripped"] is True and done.json()["breakerTripped"] is False
    tripped["value"] = False
    second = await _desk_row(api.db, "k2", state="executed")
    done = await api.call("POST", f"/api/autonomous-ops/actions/{second}/undo", role="security_analyst")
    assert done.status_code == 200 and done.json()["deskBreakerTripped"] is False


async def test_the_approve_route_gives_the_desk_draft_words(api):
    await seed_tenant(api.db, "t1", shadow=False)
    await api.db.tickets.insert_one({"id": "k1", "tenantId": "t1", "ticket_number": "TKT-0001"})
    action_id = await _desk_row(api.db, "k1")
    done = await api.call("POST", f"/api/autonomous-ops/actions/{action_id}/approve", role="tenant_admin")
    assert done.status_code == 409 and done.json()["detail"] == messages.API_DETAIL["desk_draft"]


# ---------------------------------------------------------------- Task 3: Activity rows

def _present(row, *, can_act=True):
    return views.present_row(row, viewer_is_platform_staff=False, can_act=can_act,
                             now=datetime.now(timezone.utc))


def _row(state, *, phase="drafted", undoable=False, shadow=False, result=None, command="ticket_answer"):
    now = datetime.now(timezone.utc)
    return {"id": "AO-1", "tenantId": "t1", "kind": "servicedesk", "dispatcher": "service_desk", "command": command,
            "action": command, "actions": [command], "targets": [], "params": {"ticketId": "k1"}, "steps": [],
            "rollback": [], "state": state, "shadow": shadow, "reasonCode": "suggest_requested",
            "reasonText": "The desk is set to draft.", "reason": {"ruleId": "service_desk:answer", "inputs": {}},
            "createdAt": now, "updatedAt": now, "activityResult": result,
            "desk": {"ticketId": "k1", "ticketNumber": "TKT-0001", "title": "VPN", "phase": phase, "undoable": undoable},
            "undo": {"available": True, "action": "ticket_withdraw", "params": {}, "undoneAt": None, "undoneBy": None}}


def test_a_draft_row_links_to_its_ticket_and_reads_as_a_draft():
    shown = _present(_row("suggested", result="Waiting for a person to send it."))
    assert (shown["ticketId"], shown["ticketNumber"]) == ("k1", "TKT-0001")
    assert shown["actionLabel"] == messages.DESK_ACTION_LABELS["draft"] == "Draft ticket answer"
    assert shown["resultText"] == "Waiting for a person to send it."
    assert shown["canUndo"] is False and shown["suggestion"] is None and shown["incidentId"] is None


def test_a_simulated_draft_reads_as_a_draft_too():
    shown = _present(_row("shadow", phase="drafted"))
    assert shown["actionLabel"] == "Draft ticket answer" and shown["canUndo"] is False


def test_a_posted_answer_offers_undo_to_a_person_who_may_act():
    row = _row("executed", phase="posted", undoable=True, result="Posted on the ticket.")
    shown = _present(row)
    assert shown["canUndo"] is True and shown["undoHint"] == messages.DESK_UNDO_HINT
    assert shown["actionLabel"] == messages.ACTION_LABELS["ticket_answer"] and shown["resultText"] == "Posted on the ticket."
    assert _present({**row, "desk": {**row["desk"], "phase": "sent"}})["canUndo"] is True


@pytest.mark.parametrize("change", [{"can_act": False}, {"shadow": True}, {"undoable": False}, {"phase": "confirmed"},
                                    {"state": "undone"}, {"state": "failed"}])
def test_undo_is_not_offered_when_it_would_mean_nothing(change):
    kw = {"state": "executed", "phase": "posted", "undoable": True}
    can_act = change.pop("can_act", True)
    kw.update(change)
    assert _present(_row(**kw), can_act=can_act)["canUndo"] is False


def test_a_hand_off_row_links_to_its_ticket_and_has_no_undo():
    shown = _present(_row("executed", phase="handed_off", command="ticket_handoff", result="Sent to a person."))
    assert shown["ticketNumber"] == "TKT-0001" and shown["actionLabel"] == "Send ticket to a person"
    assert shown["canUndo"] is False and shown["resultText"] == "Sent to a person."


def test_a_security_row_has_no_ticket_fields_and_keeps_its_extras():
    row = {"id": "AO-2", "tenantId": "t1", "kind": "security", "dispatcher": "instruction", "command": "block_ip",
           "action": "block_ip", "actions": ["block_ip"], "targets": ["a1"], "params": {"ip_address": "203.0.113.7"},
           "steps": [], "rollback": [], "state": "executed", "shadow": False, "reasonCode": "class_auto",
           "reason": {"ruleId": "t", "inputs": {}}, "createdAt": datetime.now(timezone.utc),
           "undo": {"available": True, "action": "unblock_ip", "params": {"ip_address": "203.0.113.7"}}}
    shown = _present(row)
    assert shown["ticketId"] is None and shown["ticketNumber"] is None
    assert shown["actionLabel"] == messages.ACTION_LABELS["block_ip"] and shown["blockedUntil"] is None


async def test_the_activity_list_shows_a_recorded_desk_draft(world):
    action_id = await _desk_row(world, "k1")
    row = await ledger.get(world, "t1", action_id)
    shown = _present(row)
    assert shown["ticketId"] == "k1" and shown["actionLabel"] == "Draft ticket answer"
    assert shown["reasonText"] == row["reasonText"]
