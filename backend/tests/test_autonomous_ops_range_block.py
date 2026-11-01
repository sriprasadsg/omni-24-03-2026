"""Blocking a range of addresses always waits for a person (Phase 83, plan 83-08, RESP-02).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=a request that names a network (a ``cidr``) is never dispatched on its own, whoever asks and
whatever the caller set; it can never touch a network that overlaps the never-touch list; the sweep turns a
corroborated range into one approval card; approving sends the block with the network, and undoing it names
the same network and the block's own id; fails_when=a range reaches an agent without a person, an overlap
with a never-touch entry passes, a malformed network passes, a host with only the single-address token is
sent a range, the sweep writes an instruction for a range, or an undo sends ip_address together with cidr;
no_claim=the agent's own refusal of a wide network (Rust tests, plan 83-04), the card's wording in the UI.
"""
from datetime import datetime, timezone

import pytest

from autonomous_ops import (agent_support, approvals, dispatch_check, gate, ledger, protected, registry,
                            response_dispatch, signals, sweep)  # noqa: F401  (response_dispatch registers the dispatcher)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import (seed_feed_ioc, seed_response_agent, seed_telemetry, seed_tenant)

NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
OFF = {"master_shadow": False}
NET = "45.33.32.0/24"
APPROVER = {"username": "carol", "display": "Carol", "tier": "tenant"}
BOTH = ["block_ip_ttl", "block_ip_range"]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()
    yield
    protected.cache_clear()


@pytest.fixture
async def world(mongo_db):  # noqa: F811
    await ledger.ensure_indexes(mongo_db)
    await protected.ensure_indexes(mongo_db)
    await signals.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_response_agent(mongo_db, "t1", "a1", hostname="h1", tokens=BOTH, last_seen=datetime.now(timezone.utc))
    return mongo_db


def _req(cidr=NET, *, dispatcher="security_response", origin="test", key=None, **extra):
    params = {"cidr": cidr, "ttl_seconds": 86400} if cidr is not None else {"ttl_seconds": 86400}
    return gate.ActionRequest(
        tenant_id="t1", kind="security", origin=origin, actions=["block_ip"], targets=["a1"], params=params,
        dedupe_key=key or f"t1|{dispatcher}|{origin}|{cidr}", reason={"ruleId": "test", "inputs": {}},
        dispatcher=dispatcher, **extra)


async def _decide(db, req):
    return await gate.decide(db, req, now=datetime.now(timezone.utc), **OFF)


# ---------------------------------------------------------------- the registry and the never-touch check

def test_block_and_unblock_name_their_network_parameter():
    assert registry.resolve("block_ip").cidr_params == ("cidr",)
    assert registry.resolve("unblock_ip").cidr_params == ("cidr",)
    assert registry.resolve("quarantine_file").cidr_params == ()
    assert registry.resolve("restart_service").cidr_params == ()


async def test_check_network_refuses_malformed_text(world):
    for bad in ("45.33.32.0/99", "not-a-network", "", "45.33.32.0/", None, 4533, ["45.33.32.0/24"], "45.33.32.300/24"):
        assert await protected.check_network(world, "t1", bad) == "invalid_target", bad


async def test_check_network_passes_a_clear_network_and_normalises_host_bits(world):
    assert await protected.check_network(world, "t1", NET) is None
    assert await protected.check_network(world, "t1", "45.33.32.77/24") is None
    assert await protected.check_network(world, "t1", "2606:4700::/32") is None


@pytest.mark.parametrize("entry_kind,entry,cidr", [
    ("cidr", "45.33.0.0/16", NET),                   # the entry contains the network
    ("cidr", "45.33.32.128/25", NET),                # the network contains the entry
    ("cidr", NET, NET),                              # identical
    ("ip", "45.33.32.9", NET),                       # a never-touch address inside the network
    ("ip", "45.33.32.9", "45.33.32.9/32"),
])
async def test_a_network_overlapping_a_never_touch_entry_is_protected(world, entry_kind, entry, cidr):
    await protected.add_entry(world, scope="tenant", tenant_id="t1", kind=entry_kind, value=entry)
    protected.cache_clear()
    assert await protected.check_network(world, "t1", cidr) == "protected_target"


async def test_a_network_beside_a_never_touch_entry_passes(world):
    await protected.add_entry(world, scope="tenant", tenant_id="t1", kind="cidr", value="45.33.33.0/24")
    await protected.add_entry(world, scope="tenant", tenant_id="t1", kind="ip", value="2606:4700::1")
    protected.cache_clear()
    assert await protected.check_network(world, "t1", NET) is None          # a neighbour; an IPv6 entry is another family


async def test_a_network_wide_enough_to_cover_a_built_in_entry_is_protected(world):
    assert await protected.check_network(world, "t1", "0.0.0.0/0") == "protected_target"      # loopback, link-local...
    assert await protected.check_network(world, "t1", "127.0.0.0/8") == "protected_target"


async def test_another_tenants_entry_does_not_protect_this_network(world):
    await seed_tenant(world, "t2", shadow=False)
    await protected.add_entry(world, scope="tenant", tenant_id="t2", kind="cidr", value=NET)
    protected.cache_clear()
    assert await protected.check_network(world, "t1", NET) is None


# ---------------------------------------------------------------- the gate

@pytest.mark.parametrize("origin", ["test", "sweep", "xdr-auto", "ai-selector", "operator"])
async def test_a_range_needs_approval_from_any_origin_and_nothing_is_sent(world, origin):
    """RESP-02: the gate escalates a cidr request by itself; the caller did not set playbook_raise."""
    req = _req(origin=origin)
    assert req.playbook_raise is False
    decision = await _decide(world, req)
    assert (decision.outcome, decision.state, decision.reason, decision.recorded) == (
        "needs_approval", "awaiting_approval", "range_block", True), origin
    assert await world.agent_instructions.count_documents({}) == 0
    row = await ledger.get(world, "t1", decision.action_id)
    assert row["approval"]["requiredBy"] == "range_block" and row["autoDispatched"] is False
    assert row["params"]["cidr"] == NET


async def test_a_phase_81_instruction_request_for_a_range_needs_a_person_too(world):
    decision = await _decide(world, _req(dispatcher="instruction", key="old"))
    assert (decision.outcome, decision.reason) == ("needs_approval", "range_block")


async def test_a_single_address_is_still_automatic(world):
    req = _req(None, key="single")
    req.params = {"ip_address": "45.33.32.156", "ttl_seconds": 86400}
    decision = await _decide(world, req)
    assert (decision.outcome, decision.reason) == ("allow_auto", "class_auto")


async def test_range_block_is_in_the_reason_codes_and_has_words(world):
    from autonomous_ops import messages
    assert "range_block" in gate.REASON_CODES and messages.REASON_TEXT["range_block"]


async def test_a_range_over_a_never_touch_network_is_refused_and_a_bad_one_is_invalid(world):
    await protected.add_entry(world, scope="tenant", tenant_id="t1", kind="cidr", value="45.33.0.0/16")
    protected.cache_clear()
    over = await _decide(world, _req())
    assert (over.outcome, over.reason) == ("refuse", "protected_target")
    bad = await _decide(world, _req("45.33.32.0/99", key="bad"))
    assert (bad.outcome, bad.reason) == ("refuse", "invalid_target")
    assert await world.agent_instructions.count_documents({}) == 0


async def test_a_host_with_only_the_single_address_token_is_dormant_for_a_range(world):
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=["block_ip_ttl"], last_seen=datetime.now(timezone.utc))
    ranged = await _decide(world, _req())
    assert (ranged.outcome, ranged.reason, ranged.recorded) == ("refuse", "agent_unsupported", False)
    single = _req(None, key="single")
    single.params = {"ip_address": "45.33.32.156", "ttl_seconds": 86400}
    assert (await _decide(world, single)).outcome == "allow_auto"


def test_the_token_for_a_range_is_the_range_token():
    assert agent_support.token_for("block_ip", {"cidr": NET}) == "block_ip_range"
    assert agent_support.token_for("unblock_ip", {"cidr": NET, "block_id": "x"}) == "block_ip_range"
    assert agent_support.token_for("block_ip", {"ip_address": "45.33.32.156"}) == "block_ip_ttl"
    assert agent_support.token_for("block_ip", None) == "block_ip_ttl"
    assert agent_support.token_for("block_ip", {"cidr": ""}) == "block_ip_ttl"
    assert agent_support.token_for("quarantine_file", {"cidr": NET}) == "quarantine_file"


def test_has_range_reads_every_step():
    req = _req()
    specs = dispatch_check.classify(req)[0]
    assert dispatch_check.has_range(req, specs) is True
    req.params = {"ip_address": "45.33.32.156"}
    assert dispatch_check.has_range(req, specs) is False


# ---------------------------------------------------------------- approve, then undo

async def test_approving_sends_block_ip_with_the_network_and_undo_names_the_same_network_and_block(world):
    decision = await _decide(world, _req())
    approved = await approvals.approve(world, "t1", decision.action_id, approver=APPROVER)
    assert approved["status"] == "dispatched", approved
    sent = await world.agent_instructions.find_one({"type": "block_ip"})
    assert sent["parameters"] == {"cidr": NET, "ttl_seconds": 86400} and "ip_address" not in sent["parameters"]
    row = await ledger.get(world, "t1", decision.action_id)
    assert row["blockedUntil"] is not None
    await ledger.transition(world, "t1", decision.action_id, ("dispatching",), "executed")
    undone = await approvals.undo(world, "t1", decision.action_id, actor=APPROVER)
    assert undone["status"] == "undone", undone
    lifted = await world.agent_instructions.find_one({"type": "unblock_ip"})
    assert lifted["parameters"] == {"cidr": NET, "block_id": sent["id"]}


async def test_a_day_old_range_card_is_refused_when_the_host_lost_the_range_token(world):
    decision = await _decide(world, _req())
    await world.agents.update_one({"id": "a1"}, {"$set": {"meta.response_actions.tokens": ["block_ip_ttl"]}})
    out = await approvals.approve(world, "t1", decision.action_id, approver=APPROVER)
    assert out == {"status": "refused", "reason": "agent_unsupported"}
    assert await world.agent_instructions.count_documents({}) == 0


async def test_a_card_is_refused_if_a_never_touch_entry_now_covers_the_network(world):
    decision = await _decide(world, _req())
    await protected.add_entry(world, scope="tenant", tenant_id="t1", kind="cidr", value="45.33.0.0/16")
    protected.cache_clear()
    out = await approvals.approve(world, "t1", decision.action_id, approver=APPROVER)
    assert out == {"status": "refused", "reason": "protected_target"}
    assert await world.agent_instructions.count_documents({}) == 0


# ---------------------------------------------------------------- the sweep

async def _feed_world(db, feeds):
    """A host connected to 45.33.32.156, which a feed lists as the network 45.33.32.0/24."""
    await seed_telemetry(db, "a1", connections=[{"remote_address": "45.33.32.156:443"}])
    await seed_feed_ioc(db, ioc_type="ip", value=NET, source_ip=NET, feed=feeds[0], source_feeds=list(feeds))


async def test_one_tick_turns_a_corroborated_range_into_one_card_and_sends_nothing(world):
    await _feed_world(world, ["urlhaus", "malwarebazaar"])
    first = await sweep.tick(world)
    assert first["cards"] == 1 and first["blocked"] == 0, first
    rows = [r async for r in world.autonomy_actions.find({"kind": "security"}, {"_id": 0})]
    assert len(rows) == 1
    row = rows[0]
    assert (row["state"], row["reasonCode"], row["command"]) == ("awaiting_approval", "range_block", "block_ip")
    assert row["params"] == {"cidr": NET, "ttl_seconds": 86400} and row["dispatcher"] == "security_response"
    assert row["dedupeKey"] == f"t1|sweep|block_ip|a1|{NET}"
    assert row["target"] == NET
    assert sorted(row["reason"]["inputs"]["origins"]) == ["feed:malwarebazaar", "feed:urlhaus"]
    assert await world.agent_instructions.count_documents({}) == 0
    await sweep.tick(world)
    assert await world.autonomy_actions.count_documents({"kind": "security"}) == 1       # nothing repeats


async def test_a_single_origin_range_is_only_a_suggestion(world):
    await _feed_world(world, ["urlhaus"])
    counts = await sweep.tick(world)
    assert counts["suggested"] == 1 and counts["cards"] == 0, counts
    (row,) = [r async for r in world.autonomy_actions.find({"kind": "security"}, {"_id": 0})]
    assert row["state"] == "suggested" and row["reason"]["inputs"]["suggestionOnly"] is True
    assert row["dedupeKey"] == f"t1|sweep-suggest|block_ip|a1|{NET}"
    assert row["params"]["cidr"] == NET and await world.agent_instructions.count_documents({}) == 0


async def test_the_sweep_leaves_no_row_for_a_range_on_a_host_without_the_range_token(world):
    await seed_response_agent(world, "t1", "a1", hostname="h1", tokens=["block_ip_ttl"], last_seen=datetime.now(timezone.utc))
    await _feed_world(world, ["urlhaus", "malwarebazaar"])
    await sweep.tick(world)
    assert await world.autonomy_actions.count_documents({"kind": "security"}) == 0


async def test_the_sweep_leaves_no_row_for_a_range_over_a_never_touch_network(world):
    await protected.add_entry(world, scope="tenant", tenant_id="t1", kind="cidr", value="45.33.0.0/16")
    protected.cache_clear()
    await _feed_world(world, ["urlhaus", "malwarebazaar"])
    await sweep.tick(world)
    assert await world.agent_instructions.count_documents({}) == 0
    rows = [r async for r in world.autonomy_actions.find({"kind": "security"}, {"_id": 0})]
    assert all(r["state"] == "refused" for r in rows)
