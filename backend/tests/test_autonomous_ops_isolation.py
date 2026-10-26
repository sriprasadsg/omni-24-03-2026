"""Two-tenant isolation proof for Autonomous Ops approvals, undo, expiry, breaker and the
reconciler (Phase 81, plan 81-04, GATE-11 adjacency). Real MongoDB (skips without one).

Value: protects=an approve, deny, undo, expiry, breaker trip or reconciler pass for one tenant
never reads or changes another tenant's settings, rows, instructions or audit events, even when
hostnames, finding ids and dedupe keys are identical; fails_when=any document of the other
tenant differs after an operation, or one tenant's open row blocks the other's identical
request; no_claim=request-level tenant resolution (plan 81-09).
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tenant_context
from autonomous_ops import APPROVAL_TTL, approvals, breaker, gate, ledger, protected, reconciler
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_tenant

APPROVER = {"username": "alice", "display": "Alice", "tier": "tenant"}
IP = "203.0.113.7"
COLLECTIONS = ("autonomy_actions", "autonomy_settings", "agent_instructions", "response_tasks", "agents",
               "tenants", "audit_logs")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("AUTONOMOUS_REMEDIATION_DRY_RUN", raising=False)
    protected.cache_clear()


@pytest.fixture
async def two(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    for tenant in ("t-a", "t-b"):
        await seed_tenant(mongo_db, tenant, shadow=False)
        await seed_agent(mongo_db, tenant, f"agent-{tenant}", hostname="host-1")
    return mongo_db


def _req(tenant, action="block_ip", ip=IP, key="finding-1|dedupe"):
    return gate.ActionRequest(tenant_id=tenant, kind="security", origin="test", actions=[action],
                              targets=[f"agent-{tenant}"], params={"ip_address": ip}, dedupe_key=key,
                              reason={"ruleId": "finding-1", "inputs": {"finding": "finding-1"}})


async def snapshot(db, tenant):
    """Every document that belongs to ``tenant`` in the collections Autonomous Ops touches."""
    out = {}
    for name in COLLECTIONS:
        flt = {"id": tenant} if name == "tenants" else {"tenantId": tenant}
        docs = [{k: v for k, v in d.items() if k != "_id"} async for d in db[name].find(flt)]
        out[name] = sorted(docs, key=repr)
    return out


class Untouched:
    """Assert that ``tenant``'s documents are identical before and after the block."""

    def __init__(self, db, tenant):
        self.db, self.tenant = db, tenant

    async def __aenter__(self):
        self.before = await snapshot(self.db, self.tenant)

    async def __aexit__(self, *exc):
        if exc[0] is None:
            assert await snapshot(self.db, self.tenant) == self.before, f"{self.tenant} was changed"


async def _executed_block(db, tenant, ip=IP, key="finding-1|dedupe"):
    d = await gate.decide(db, _req(tenant, ip=ip, key=key), master_shadow=False)
    assert d.state == "dispatching", d
    await gate.execute(db, tenant, d.action_id, command="block_ip", agent_id=f"agent-{tenant}",
                       params={"ip_address": ip})
    assert await ledger.transition(db, tenant, d.action_id, ("dispatching",), "executed")
    return d.action_id


@pytest.mark.parametrize("acting,other", [("t-a", "t-b"), ("t-b", "t-a")])
async def test_decide_approve_deny_and_undo_for_one_tenant_leave_the_other_untouched(two, acting, other):
    db = two
    async with Untouched(db, other):
        card = await gate.decide(db, _req(acting, "isolate_host", key="finding-1|card"), master_shadow=False)
        assert card.state == "awaiting_approval"
        denied = await gate.decide(db, _req(acting, "reboot_host", key="finding-1|deny"), master_shadow=False)
        assert (await approvals.approve(db, acting, card.action_id, approver=APPROVER))["status"] == "dispatched"
        assert (await approvals.deny(db, acting, denied.action_id, approver=APPROVER))["status"] == "denied"
        block = await _executed_block(db, acting)
        assert (await approvals.undo(db, acting, block, actor=APPROVER))["status"] == "undone"
        listing = await ledger.list_actions(db, acting)
        assert len(listing["items"]) == 3 and await ledger.counts(db, acting)
    assert await db.agent_instructions.count_documents({"tenantId": acting}) == 3
    assert await db.agent_instructions.count_documents({"tenantId": other}) == 0


async def test_identical_requests_in_both_tenants_do_not_block_each_other(two):
    db = two
    a = await gate.decide(db, _req("t-a", "isolate_host"), master_shadow=False)
    b = await gate.decide(db, _req("t-b", "isolate_host"), master_shadow=False)
    assert a.state == b.state == "awaiting_approval" and a.action_id != b.action_id
    again = await gate.decide(db, _req("t-a", "isolate_host"), master_shadow=False)
    assert again.reason == "duplicate"
    assert (await ledger.counts(db, "t-a"))["pending"] == 1 and (await ledger.counts(db, "t-b"))["pending"] == 1
    assert [r["id"] for r in (await ledger.list_actions(db, "t-b"))["items"]] == [b.action_id]


async def test_one_tenant_cannot_act_on_the_others_rows(two):
    db = two
    card = await gate.decide(db, _req("t-a", "isolate_host"), master_shadow=False)
    block = await _executed_block(db, "t-a", ip="203.0.113.50", key="finding-1|other")
    async with Untouched(db, "t-a"), Untouched(db, "t-b"):
        assert (await approvals.approve(db, "t-b", card.action_id, approver=APPROVER))["status"] == "not_found"
        assert (await approvals.deny(db, "t-b", card.action_id, approver=APPROVER))["status"] == "not_found"
        assert (await approvals.undo(db, "t-b", block, actor=APPROVER))["status"] == "not_found"
        assert (await ledger.list_actions(db, "t-b"))["items"] == []


async def test_expiry_and_reconciler_for_one_tenant_leave_the_other_untouched(two):
    db = two
    a = await gate.decide(db, _req("t-a", "isolate_host"), master_shadow=False)
    later = datetime.now(timezone.utc) + APPROVAL_TTL + timedelta(seconds=1)
    async with Untouched(db, "t-b"):
        assert await approvals.expire_due(db, now=later, tenant_id="t-a") == 1
        assert (await ledger.get(db, "t-a", a.action_id))["state"] == "expired"
    b = await gate.decide(db, _req("t-b", "isolate_host", key="finding-1|b"), master_shadow=False)
    async with Untouched(db, "t-b"):
        assert await approvals.expire_due(db, now=later, tenant_id="t-a") == 0
    assert (await ledger.get(db, "t-b", b.action_id))["state"] == "awaiting_approval"
    assert tenant_context.get_tenant_id() is None


async def test_breaker_trip_for_one_tenant_leaves_the_other_untouched(two):
    db = two
    for i in range(3):
        d = await gate.decide(db, _req("t-a", ip=f"203.0.113.{60 + i}", key=f"finding-1|{i}"), master_shadow=False)
        await gate.execute(db, "t-a", d.action_id, command="block_ip", agent_id="agent-t-a",
                           params={"ip_address": f"203.0.113.{60 + i}"})
        assert await ledger.transition(db, "t-a", d.action_id, ("dispatching",), "failed")
    async with Untouched(db, "t-b"):
        with patch("autonomous_ops.breaker.notify.notify", AsyncMock()) as notice:
            assert await breaker.evaluate(db, "t-b") is False
            assert await breaker.evaluate(db, "t-a") is True
        assert notice.await_args.args[1] == "t-a"
        assert (await breaker.restore(db, "t-b", actor=APPROVER))["status"] == "not_tripped"
    assert (await db.autonomy_settings.find_one({"tenantId": "t-a"}))["level"] == "suggest"
    assert (await db.autonomy_settings.find_one({"tenantId": "t-b"}))["level"] == "undoable_auto"


async def test_a_reconciler_pass_follows_each_tenants_own_instruction(two):
    """Same hostnames, finding ids and dedupe keys: a result for t-a never completes t-b's row."""
    db = two
    rows = {}
    for tenant in ("t-a", "t-b"):
        d = await gate.decide(db, _req(tenant), master_shadow=False)
        out = await gate.execute(db, tenant, d.action_id, command="block_ip", agent_id=f"agent-{tenant}",
                                 params={"ip_address": IP})
        rows[tenant] = (d.action_id, out["task_id"])
    await db.agent_instructions.update_one({"id": rows["t-a"][1]}, {"$set": {"status": "SUCCESS"}})
    async with Untouched(db, "t-b"):
        counts = await reconciler.tick(db)
    assert counts["executed"] == 1
    assert (await ledger.get(db, "t-a", rows["t-a"][0]))["state"] == "executed"
    assert (await ledger.get(db, "t-b", rows["t-b"][0]))["state"] == "dispatching"
    assert tenant_context.get_tenant_id() is None
    await db.agent_instructions.update_one({"id": rows["t-b"][1]}, {"$set": {"status": "FAILURE"}})
    async with Untouched(db, "t-a"):
        assert (await reconciler.tick(db))["failed"] == 1
    assert (await ledger.get(db, "t-b", rows["t-b"][0]))["state"] == "failed"
    assert tenant_context.get_tenant_id() is None
