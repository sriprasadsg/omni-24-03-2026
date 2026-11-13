"""Autonomous Ops two-tenant contracts (Phase 86, plan 86-03, GATE-11 / D-17): one test per automatic loop.
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; the local model
is a stand-in (httpx.MockTransport), so nothing reaches Ollama or the live database.

Value: protects=no automatic loop (security response sweep, patch rollout controller, service desk worker,
scheduled retention) writes or reads across tenants: each runs its real entry point once over two
same-shaped tenants and every row, instruction, notice and count stays with the tenant that owns the agent,
ticket or data; fails_when=any row, instruction, notice or counter of one tenant carries the other tenant's
id, agent, host, address, ticket or article, one tenant's window, rings or retention days govern the other,
or one tenant's rule deletes the other tenant's rows; no_claim=the reporting surfaces (86-09 adds their own
two-tenant cases) and the live database.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-two-tenant-contracts")

import audit_ledger
import retention_gate as gate
import retention_job
from autonomous_ops import ledger, protected, signals, sweep
from autonomous_ops.rollout import loop as rollout_loop, start, store as rollout_store
from service_desk import worker
from service_desk.model import OllamaClient
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_feed_ioc, seed_native_verdict, seed_response_agent, seed_tenant
from tests.rollout_support import seed_group, seed_rings, seed_rollout_agent, seed_window
from tests.service_desk_support import desk_indexes_without_ttl, seed_article, seed_desk_tenant
from tests.service_desk_worker_support import Clock, _desk_env, job, kinds, queue, stand_in, stored  # noqa: F401

A, B = "tenant-alpha", "tenant-bravo"
NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
# Two public addresses outside every documentation range: the agent may block them.
IPS = {A: "45.33.32.156", B: "45.33.32.10"}
TOKENS = ("reboot_host", "patch_reversible_check")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()
    with patch.object(audit_ledger, "event", AsyncMock()), \
            patch("autonomous_ops.notify.notify", new=AsyncMock()) as notices:
        yield notices


# ------------------------------------------------------------------ the crossing helper

def _marks(world):
    """The strings that identify one tenant in any stored document."""
    return {m for m in world.values() if isinstance(m, str) and m}


def _names(text, marks):
    return {m for m in marks if re.search(rf"(?<![\w.]){re.escape(m)}(?!\w|\.\d)", text)}


async def assert_no_crossing(db, collections, worlds, notices=()):
    """Every document of ``collections`` (and every notice call in ``notices``) names only the tenant that owns
    it: the stamped tenant when it has one, otherwise a single tenant. Returns how many documents each tenant
    owns per collection, so a case can also prove it was not vacuous."""
    owned = {t: {} for t in worlds}

    def check(where, tenant, text):
        named = {t for t in worlds if _names(text, _marks(worlds[t]))}
        assert named <= {tenant} if tenant in worlds else len(named) <= 1, (where, tenant, named, text)
        if tenant in worlds:
            owned[tenant][where] = owned[tenant].get(where, 0) + 1

    for coll in collections:
        async for doc in db[coll].find({}, {"_id": 0}):
            check(coll, doc.get("tenantId") or doc.get("tenant_id"), json.dumps(doc, default=str))
    for call in notices:
        check("notice", call.args[1] if len(call.args) > 1 else call.kwargs.get("tenant_id"),
              json.dumps([call.args[2:], call.kwargs], default=str))
    return owned


# ------------------------------------------------------------------ security response sweep

async def _sweep_world(db, tenant):
    host = f"host-{tenant}"
    await seed_tenant(db, tenant, shadow=False)
    await seed_response_agent(db, tenant, f"a-{tenant}", hostname=host, tokens=["block_ip_ttl"], last_seen=NOW)
    await seed_native_verdict(db, tenant, host, kind="ip", target=IPS[tenant], created_at=NOW)
    await seed_feed_ioc(db, ioc_type="url", value=f"http://{IPS[tenant]}/x", source_ip=IPS[tenant],
                        feed="urlhaus", updated_at=NOW)
    return {"tenant": tenant, "agent": f"a-{tenant}", "host": host, "ip": IPS[tenant]}


async def test_one_sweep_pass_decides_for_each_tenants_own_agent_and_address(mongo_db, _env):
    await ledger.ensure_indexes(mongo_db)
    await signals.ensure_indexes(mongo_db)
    worlds = {t: await _sweep_world(mongo_db, t) for t in (A, B)}

    counts = await sweep.tick(mongo_db, now=NOW)

    assert counts["tenants"] == 2 and counts["blocked"] == 2, counts
    for t, other in ((A, B), (B, A)):
        rows = [r async for r in mongo_db.autonomy_actions.find({"tenantId": t}, {"_id": 0})]
        assert len(rows) == 1 and rows[0]["command"] == "block_ip", rows
        assert rows[0]["targets"] == [worlds[t]["agent"]] and rows[0]["params"]["ip_address"] == IPS[t], rows
        sent = [i async for i in mongo_db.agent_instructions.find({"tenantId": t}, {"_id": 0})]
        assert len(sent) == 1 and sent[0]["agent_id"] == worlds[t]["agent"], sent
        assert IPS[other] not in json.dumps(sent, default=str) + json.dumps(rows, default=str)
    owned = await assert_no_crossing(
        mongo_db, ("autonomy_actions", "agent_instructions", "autonomy_signals", "autonomy_incidents"), worlds,
        _env.call_args_list)
    for t in (A, B):
        assert owned[t]["autonomy_actions"] == 1 and owned[t]["agent_instructions"] == 1, owned


# ------------------------------------------------------------------ patch rollout loop

async def _online(db, at):
    await db.agents.update_many({}, {"$set": {"lastSeen": at.isoformat(), "status": "Online"}})


async def _rollout_world(db, tenant, *, window):
    canary, rest = f"c-{tenant}", f"r-{tenant}"
    for name in (canary, rest):
        await seed_rollout_agent(db, tenant, name, hostname=f"host-{name}", platform="Linux", tokens=TOKENS,
                                 pending=["openssl"], boot_time=1_700_000_000, last_seen=NOW)
    await seed_group(db, tenant, f"G-{tenant}", [canary])
    await seed_rings(db, tenant, [{"key": "canary", "name": "Canary", "groupIds": [f"G-{tenant}"], "soakHours": 1},
                                  {"key": "rest", "name": "Everyone else", "groupIds": [], "soakHours": 1}])
    await seed_window(db, tenant, start=window[0], end=window[1], name=f"window-{tenant}")
    out = await start.start_rollout(db, tenant, name=f"Nov-{tenant}", patch_ids=["openssl"],
                                    actor={"id": f"u-{tenant}", "name": "Ann"}, now=NOW)
    assert out["status"] == "started", out
    return {"tenant": tenant, "canary": canary, "rest": rest, "group": f"G-{tenant}", "rollout": out["rolloutId"],
            "host_canary": f"host-{canary}", "host_rest": f"host-{rest}"}


async def test_one_rollout_pass_keeps_each_tenants_window_hosts_and_instructions_apart(mongo_db, _env):
    await ledger.ensure_indexes(mongo_db)
    await rollout_store.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, A, shadow=False)
    await seed_tenant(mongo_db, B, shadow=False)
    await mongo_db.tenants.update_many({"id": {"$in": [A, B]}}, {"$set": {"agentCapabilities": ["all"]}})
    worlds = {A: await _rollout_world(mongo_db, A, window=("00:00", "23:59")),          # open at NOW
              B: await _rollout_world(mongo_db, B, window=("03:00", "04:00"))}          # closed at NOW

    await rollout_loop.run_once(mongo_db, now=NOW)

    sent_a = [i async for i in mongo_db.agent_instructions.find({"tenantId": A}, {"_id": 0})]
    assert [i["agent_id"] for i in sent_a] == [worlds[A]["canary"]], sent_a                 # A advanced
    assert await mongo_db.agent_instructions.count_documents({"tenantId": B}) == 0           # B waited
    ring_b = (await mongo_db.patch_rollouts.find_one({"id": worlds[B]["rollout"]}))["rings"][0]
    assert ring_b["state"] == "waiting_for_window", ring_b
    ring_a = (await mongo_db.patch_rollouts.find_one({"id": worlds[A]["rollout"]}))["rings"][0]
    assert ring_a["state"] != "waiting_for_window", ring_a

    # B's window opens the next day: B's own canary host is sent its install; A's hosts stay A's own.
    later = NOW + timedelta(hours=15, minutes=30)
    await _online(mongo_db, later)
    await rollout_loop.run_once(mongo_db, now=later)
    sent_b = [i async for i in mongo_db.agent_instructions.find({"tenantId": B}, {"_id": 0})]
    assert [i["agent_id"] for i in sent_b] == [worlds[B]["canary"]], sent_b

    owned = await assert_no_crossing(
        mongo_db, ("autonomy_actions", "agent_instructions", "patch_rollouts", "patch_rollout_hosts",
                   "patch_deployment_jobs"), worlds, _env.call_args_list)
    for t in (A, B):
        assert owned[t]["patch_rollouts"] == 1 and owned[t]["patch_rollout_hosts"] == 2, owned
    assert {i["agent_id"] async for i in mongo_db.agent_instructions.find({"tenantId": A})} == {worlds[A]["canary"]}
    assert owned[B]["agent_instructions"] == 1 and owned[A]["agent_instructions"] >= 1, owned
