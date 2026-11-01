"""Dormancy (Phase 83, plan 83-08, RESP-10, D-19, D-20): a host that cannot carry a response action stays
silent. Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=an unticked tenant, an old agent, an agent without the feature token and an offline host
get no row from the sweep, no row from the gate and no instruction from a day-old approval, and none of
that can ever count against the circuit breaker (PROH-83-11); fails_when=a dormant host leaves a row, an
agent is judged by version number, the order of the three reasons moves, the 5 minute boundary moves, a
Phase 81 request is touched, or a suggestion can be approved through the API;
no_claim=the sweep's own decisions (test_autonomous_ops_sweep.py), the breaker filter (test_autonomous_ops_breaker.py).
"""
from datetime import datetime, timedelta, timezone

import pytest

from autonomous_ops import agent_support, approvals, gate, ledger, messages, protected, response_dispatch  # noqa: F401 (registers the dispatcher)
from tests._autonomous_ops_http import _env, api  # noqa: F401  (fixtures)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_response_agent, seed_tenant

NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
OFF = {"master_shadow": False}
IP = "45.33.32.156"
APPROVER = {"username": "carol", "display": "Carol", "tier": "tenant"}
TOKENS = ["block_ip_ttl", "block_ip_range"]


@pytest.fixture(autouse=True)
def _clear_cache():
    protected.cache_clear()
    yield
    protected.cache_clear()


@pytest.fixture
async def world(mongo_db):  # noqa: F811
    await ledger.ensure_indexes(mongo_db)
    await protected.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    return mongo_db


def _req(dispatcher="security_response", *, action="block_ip", target="a1", ip=IP, key=None, reason=None, **extra):
    return gate.ActionRequest(
        tenant_id="t1", kind="security", origin="test", actions=[action], targets=[target],
        params={"ip_address": ip, "ttl_seconds": 86400}, dedupe_key=key or f"t1|{dispatcher}|{action}|{target}|{ip}",
        reason=reason or {"ruleId": "test", "inputs": {}}, dispatcher=dispatcher, **extra)


async def _rows(db):
    return await db.autonomy_actions.count_documents({"kind": {"$ne": "control"}})


def _seen(minutes=0, seconds=0):
    return NOW - timedelta(minutes=minutes, seconds=seconds)


# ---------------------------------------------------------------- the gate: every combination, no row

@pytest.mark.real_agent_capabilities
@pytest.mark.parametrize("name,agent,code", [
    ("tick missing", {"tokens": TOKENS, "capable": False}, "capability_off"),
    ("token missing", {"tokens": ["quarantine_file"]}, "agent_unsupported"),
    ("no tokens at all", {"tokens": []}, "agent_unsupported"),
    ("offline status", {"tokens": TOKENS, "status": "Offline"}, "agent_offline"),
    ("not seen for 6 minutes", {"tokens": TOKENS, "last_seen": _seen(minutes=6)}, "agent_offline"),
])
async def test_a_dormant_host_is_refused_by_the_gate_and_leaves_nothing(world, name, agent, code):
    """RESP-10, D-19: the gate refuses a security_response request for a host that cannot carry it, with the
    plain code, and records nothing (the refusal is unrecorded, like the Off tenant)."""
    await seed_response_agent(world, "t1", "a1", hostname="h1", **agent)
    decision = await gate.decide(world, _req(), now=NOW, **OFF)
    assert (decision.outcome, decision.reason, decision.recorded) == ("refuse", code, False), name
    assert await _rows(world) == 0
    assert await world.agent_instructions.count_documents({}) == 0
    assert {"check": "agent_support", "result": "refuse", "code": code} in decision.trace


@pytest.mark.parametrize("meta", [None, {}, {"response_actions": None}, {"response_actions": {}},
                                  {"response_actions": {"tokens": None}}, {"response_actions": {"tokens": "block_ip_ttl"}},
                                  {"response_actions": {"tokens": [1, None, {"a": 1}]}},
                                  {"response_actions": "block_ip_ttl"}, "garbage"])
async def test_missing_or_malformed_tokens_read_as_no_support(world, meta):
    """Edge RESP-10 empty: a missing meta, a missing response_actions, an empty list or a malformed value is
    no support, never an error."""
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=TOKENS, last_seen=NOW)
    await world.agents.update_one({"id": "a1"}, {"$set": {"meta": meta}} if meta is not None else {"$unset": {"meta": ""}})
    decision = await gate.decide(world, _req(), now=NOW, **OFF)
    assert (decision.outcome, decision.reason, decision.recorded) == ("refuse", "agent_unsupported", False)
    assert await _rows(world) == 0


async def test_a_2_1_15_agent_stays_dormant_because_support_is_read_from_tokens_not_versions(world):
    """RESP-10: a 2.1.15 agent has block_ip in its code but no block_ip_ttl token: it would accept the
    instruction and ignore the time limit, so the rule waits."""
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=[], last_seen=NOW)
    await world.agents.update_one({"id": "a1"}, {"$set": {"version": "2.1.15", "agent_version": "2.1.15"}})
    decision = await gate.decide(world, _req(), now=NOW, **OFF)
    assert (decision.reason, decision.recorded) == ("agent_unsupported", False)
    await world.agents.update_one({"id": "a1"}, {"$set": {"version": "0.0.1",
                                                          "meta.response_actions.tokens": TOKENS}})
    again = await gate.decide(world, _req(key="after"), now=NOW, **OFF)
    assert (again.outcome, again.reason, again.recorded) == ("allow_auto", "class_auto", True)    # the token decides


async def test_a_capable_host_is_decided_as_before(world):
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=TOKENS, last_seen=NOW)
    decision = await gate.decide(world, _req(), now=NOW, **OFF)
    assert (decision.outcome, decision.state, decision.recorded) == ("allow_auto", "dispatching", True)
    assert {"check": "agent_support", "result": "pass", "code": None} in decision.trace


async def test_five_minutes_is_online_and_one_second_more_is_offline(world):
    """Edge RESP-10 adjacency: the same boundary in the gate as in agent_support.online."""
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=TOKENS, last_seen=_seen(minutes=5))
    edge = await gate.decide(world, _req(), now=NOW, **OFF)
    assert (edge.outcome, edge.recorded) == ("allow_auto", True)
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=TOKENS, last_seen=_seen(minutes=5, seconds=1))
    late = await gate.decide(world, _req(key="late"), now=NOW, **OFF)
    assert (late.outcome, late.reason, late.recorded) == ("refuse", "agent_offline", False)


@pytest.mark.real_agent_capabilities
async def test_the_reason_shown_is_stable_capability_then_online_then_token(world):
    """Edge RESP-10 ordering: a host that is unticked AND offline AND tokenless reads capability_off; ticked
    and offline and tokenless reads agent_offline; ticked and online and tokenless reads agent_unsupported."""
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=[], status="Offline", capable=False)
    assert (await gate.decide(world, _req(key="1"), now=NOW, **OFF)).reason == "capability_off"
    await world.tenants.update_one({"id": "t1"}, {"$set": {"agentCapabilities": ["all"]}})
    assert (await gate.decide(world, _req(key="2"), now=NOW, **OFF)).reason == "agent_offline"
    await world.agents.update_one({"id": "a1"}, {"$set": {"status": "Online", "lastSeen": NOW.isoformat()}})
    assert (await gate.decide(world, _req(key="3"), now=NOW, **OFF)).reason == "agent_unsupported"
    assert await _rows(world) == 0


# ---------------------------------------------------------------- other dispatchers and suggestions

async def test_a_phase_81_request_is_decided_exactly_as_before(world):
    """The step applies only to dispatcher security_response: a plain instruction request for a host with no
    tokens, no lastSeen and no capability still decides (the Phase 81 behaviour)."""
    await seed_agent(world, "t1", "a1", hostname="old-host")
    decision = await gate.decide(world, _req(dispatcher="instruction"), now=NOW, **OFF)
    assert (decision.outcome, decision.reason, decision.recorded) == ("allow_auto", "class_auto", True)
    assert not any(t["check"] == "agent_support" for t in decision.trace)


async def test_a_suggestion_skips_the_step(world):
    """Suggestions do not dispatch: gate.suggest on a dormant host records the suggestion (the sweep, not the
    gate, decides whether to ask)."""
    await seed_agent(world, "t1", "a1", hostname="old-host")
    decision = await gate.suggest(world, _req(), now=NOW, **OFF)
    assert (decision.outcome, decision.state, decision.recorded) == ("suggest", "suggested", True)
    assert not any(t["check"] == "agent_support" for t in decision.trace)


async def test_the_step_sits_right_after_the_protected_target_step():
    order = [step.__name__ for step in gate._STEPS]
    assert order[order.index("_step_protected_targets") + 1] == "gate_step"
    assert gate._STEPS[order.index("gate_step")] is agent_support.gate_step
    for code in ("agent_unsupported", "capability_off", "agent_offline"):
        assert code in gate.REASON_CODES and code in gate._UNRECORDED and code in messages.REASON_TEXT


# ---------------------------------------------------------------- approval: a day later

async def _card(db, **kw):
    """A security_response card (a range-free block that the playbook raised to a person)."""
    decision = await gate.decide(db, _req(playbook_raise=True, **kw), now=datetime.now(timezone.utc), **OFF)
    assert decision.state == "awaiting_approval", decision
    return decision.action_id


async def _refused(db, action_id, code):
    out = await approvals.approve(db, "t1", action_id, approver=APPROVER)
    assert out == {"status": "refused", "reason": code}
    row = await ledger.get(db, "t1", action_id)
    assert row["state"] == "refused" and row["reasonCode"] == code
    assert row["reasonText"] == messages.REASON_TEXT[code]
    assert await db.agent_instructions.count_documents({}) == 0


async def test_a_card_whose_agent_lost_its_token_before_approval_ends_refused(world):
    """RESP-10: approved up to 24 hours later, the same check runs in _revalidate; nothing is written."""
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=TOKENS)
    card = await _card(world)
    await world.agents.update_one({"id": "a1"}, {"$set": {"meta.response_actions.tokens": []}})
    await _refused(world, card, "agent_unsupported")
    assert (await ledger.get(world, "t1", card))["reasonText"] == "This computer's agent doesn't support this action yet."


async def test_a_card_whose_agent_went_offline_before_approval_ends_refused(world):
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=TOKENS)
    card = await _card(world)
    await world.agents.update_one({"id": "a1"}, {"$set": {"lastSeen": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}})
    await _refused(world, card, "agent_offline")


@pytest.mark.real_agent_capabilities
async def test_a_tick_removed_between_decision_and_approval_is_caught_at_approval(world):
    """Edge RESP-10 concurrency: the capability tick removed after the decision is caught by the re-check."""
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=TOKENS)
    card = await _card(world)
    await world.tenants.update_one({"id": "t1"}, {"$set": {"agentCapabilities": []}})
    await _refused(world, card, "capability_off")


async def test_a_capable_card_is_still_approved_and_dispatched(world):
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=TOKENS)
    card = await _card(world)
    out = await approvals.approve(world, "t1", card, approver=APPROVER)
    assert out["status"] == "dispatched"
    assert await world.agent_instructions.count_documents({}) == 1


# ---------------------------------------------------------------- suggestion-only rows cannot be approved

async def _suggestion(db, *, marker=True):
    inputs = {"suggestionOnly": True} if marker else {}
    req = _req(dispatcher="instruction", action="isolate_host", ip=None, key=f"sugg|{marker}",
               reason={"ruleId": "sweep:single_signal", "inputs": inputs})
    req.params = {}
    decision = await gate.suggest(db, req, now=datetime.now(timezone.utc), **OFF)
    assert decision.state == "suggested", decision
    return decision.action_id


async def test_approving_a_suggestion_only_row_is_refused_before_anything_changes(world):
    """D-07, D-25 (T-83-33): the row stays suggested, nothing is dispatched."""
    await seed_agent(world, "t1", "a1", hostname="h1")
    card = await _suggestion(world)
    out = await approvals.approve(world, "t1", card, approver=APPROVER)
    assert out == {"status": "refused", "reason": "suggestion_only"}
    row = await ledger.get(world, "t1", card)
    assert row["state"] == "suggested" and not (row.get("approval") or {}).get("approver")
    assert await world.agent_instructions.count_documents({}) == 0


async def test_a_phase_81_suggestion_without_the_marker_can_still_be_approved(world):
    await seed_agent(world, "t1", "a1", hostname="h1")
    card = await _suggestion(world, marker=False)
    assert (await approvals.approve(world, "t1", card, approver=APPROVER))["status"] == "dispatched"


async def test_the_route_answers_409_with_the_api_text_for_a_suggestion_only_row(api):
    """D-07: the approve route answers 409 with the plain sentence, and nothing is dispatched."""
    await api.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": False}})
    await seed_agent(api.db, "t1", "a1", hostname="h1")
    card = await _suggestion(api.db)
    done = await api.call("POST", f"/api/autonomous-ops/actions/{card}/approve", role="tenant_admin")
    assert done.status_code == 409
    assert done.json()["detail"] == messages.API_DETAIL["suggestion_only"]
    assert await api.db.agent_instructions.count_documents({}) == 0
    assert (await ledger.get(api.db, "t1", card))["state"] == "suggested"
