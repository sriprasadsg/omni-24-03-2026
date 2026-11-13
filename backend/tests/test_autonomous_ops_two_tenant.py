"""Autonomous Ops two-tenant contracts (Phase 86, plan 86-03, GATE-11 / D-17): one test per automatic loop.
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; the local model
is a stand-in (httpx.MockTransport), so nothing reaches Ollama or the live database.

Value: protects=no automatic loop (security response sweep, patch rollout controller, service desk worker,
scheduled retention) writes or reads across tenants: each runs its real entry point once over two
same-shaped tenants and every row, instruction, notice and count stays with the tenant that owns the agent,
ticket or data; fails_when=any row, instruction, notice or counter of one tenant carries the other tenant's
id, agent, host, address, ticket or article, one tenant's window, rings or retention days govern the other,
or one tenant's rule deletes the other tenant's rows; the reporting surfaces (86-09: statistics, export, the
daily digest) count, list or name another tenant's rows; no_claim=the live database and the HTTP layer.
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
import rbac_utils
import retention_gate as gate
import retention_job
from auth_types import TokenData
from autonomous_ops import ledger, protected, signals, sweep, views
from autonomous_ops.reporting import digest, export, stats
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


# ------------------------------------------------------------------ service desk worker

DESK_NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)      # the clock of service_desk_worker_support
PW_CONTENT = ("If you forgot your password, open the sign-in page and choose Forgot password. Enter your work "
              "email and follow the steps to reset your password. You can sign in again once the reset is finished.")
CHAIR_CONTENT = "To order an ergonomic office chair, ask your manager to approve it and file the order with facilities."
ANSWER = "Open the sign-in page and choose Forgot password."


@pytest.fixture
async def desk(mongo_db, monkeypatch):
    """What the worker tests' ``world`` fixture sets up, minus its starter articles (they would blur the leak check)."""
    import ticket_notifications
    import tickets_config_mixin
    import tickets_service
    for module in (tickets_service, tickets_config_mixin):
        monkeypatch.setattr(module, "get_database", lambda: mongo_db)
    monkeypatch.setattr(ticket_notifications, "notify_assigned", AsyncMock())
    monkeypatch.setattr(ticket_notifications, "notify_status_changed", AsyncMock())
    await ledger.ensure_indexes(mongo_db)
    await desk_indexes_without_ttl(mongo_db)
    return mongo_db


async def test_one_desk_pass_answers_from_the_tenants_own_article_and_hands_off_the_other(desk, _env):
    for t in (A, B):                                   # Post mode: with nothing stored the desk only drafts
        await seed_desk_tenant(desk, t, mode="post", shadow=False)
    await seed_article(desk, A, "kb-chair-alpha", title="Order an office chair", content=CHAIR_CONTENT)
    await seed_article(desk, B, "kb-pw-bravo", title="Reset your own password", content=PW_CONTENT)
    ticket_a, job_a = await queue(desk, 1, tenant=A, arrived=DESK_NOW)    # the same question twice:
    ticket_b, job_b = await queue(desk, 2, tenant=B, arrived=DESK_NOW)    # only bravo's article answers it

    transport, calls = stand_in(answer=ANSWER, cited=(1,))
    for _ in range(4):                                 # the worker generates for one ticket per pass
        await worker.run_once(desk, client=OllamaClient(transport=transport), clock=Clock())
        if not await desk.service_desk_jobs.count_documents({"state": {"$in": ["pending", "ready", "running"]}}):
            break

    done_a, done_b = await job(desk, job_a), await job(desk, job_b)
    assert (done_a["state"], done_a["reason"]) == ("done", "no_article"), done_a      # handed to a person
    assert (done_b["state"], done_b["reason"]) == ("done", "posted"), done_b          # answered, not drafted
    assert not {"ai_answer", "ai_draft"} & set(kinds(await stored(desk, ticket_a)))
    assert "ai_answer" in kinds(await stored(desk, ticket_b))
    assert "Forgot password" not in json.dumps((await stored(desk, ticket_a))["comments"], default=str)
    assert [c for c in calls if c["path"] == "/api/generate"], calls
    prompts = json.dumps([c["body"] for c in calls if c["path"] == "/api/generate"])
    assert "ergonomic" not in prompts                  # alpha's article never reached the model

    worlds = {A: {"tenant": A, "ticket": ticket_a["id"], "article": "kb-chair-alpha", "job": job_a},
              B: {"tenant": B, "ticket": ticket_b["id"], "article": "kb-pw-bravo", "job": job_b}}
    owned = await assert_no_crossing(
        desk, ("service_desk_jobs", "service_desk_gaps", "autonomy_actions", "tickets", "notifications"), worlds,
        _env.call_args_list)
    for t in (A, B):
        assert owned[t]["service_desk_jobs"] == 1 and owned[t]["tickets"] == 1, owned
    for t in (A, B):
        for row in [r async for r in desk.autonomy_actions.find({"tenantId": t, "kind": "servicedesk"})]:
            assert worlds[A if t == B else B]["ticket"] not in json.dumps(row, default=str), row


# ------------------------------------------------------------------ scheduled retention

RET_NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)
DAYS = {A: 20, B: 60}                                  # each tenant's own confirmed period for the same types
AGES = (10, 30, 70)                                    # days old: kept by both, A deletes 2, B deletes 1
TYPES = ("agent_metrics", "logs")                      # an ObjectId-aged type with each tenant field spelling
FIELD = {"agent_metrics": "tenant_id", "logs": "tenantId"}


def _oid(days_ago):
    return ObjectId(ObjectId.from_datetime(RET_NOW - timedelta(days=days_ago)).binary[:4] + os.urandom(8))


async def _keys(db, collection, tenant):
    return sorted([d["age"] async for d in db[collection].find({FIELD[collection]: tenant})])


async def test_retention_deletes_each_tenants_own_rows_past_its_own_cutoff_and_counts_per_tenant(mongo_db, monkeypatch):
    monkeypatch.setattr(retention_job, "_sleep", AsyncMock())
    for t in (A, B):
        await seed_tenant(mongo_db, t)
        for rtype in TYPES:
            await mongo_db[rtype].insert_many([{"_id": _oid(age), FIELD[rtype]: t, "age": age}
                                               for age in AGES])
        for rtype in TYPES:
            await mongo_db.retention_policies.insert_one(
                {"tenantId": t, "collection": rtype, "retention_days": DAYS[t]})
    # the first run only counts; the Super Admin's review then confirms every counted period
    await retention_job.run_all(mongo_db, now=RET_NOW)
    for t in (A, B):
        for rtype in TYPES:
            row = await mongo_db.retention_counts.find_one({"tenantId": t, "type": rtype}, {"_id": 0})
            assert (row["days"], row["count"]) == (DAYS[t], sum(1 for a in AGES if a > DAYS[t])), (t, rtype, row)
            assert await _keys(mongo_db, rtype, t) == list(AGES)                 # counting deletes nothing
    rows = await gate.review_rows(mongo_db)
    await gate.confirm(mongo_db, gate.review_token(rows), "Super Admin", RET_NOW)

    summary = await retention_job.run_all(mongo_db, now=RET_NOW + timedelta(minutes=1))

    for rtype in TYPES:
        assert await _keys(mongo_db, rtype, A) == [10], rtype                    # past A's 20 days: 30 and 70 gone
        assert await _keys(mongo_db, rtype, B) == [10, 30], rtype                # past B's 60 days: only 70 gone
    assert summary["deleted"] == len(TYPES) * (2 + 1) and summary["tenants"] == 2, summary
    for t in (A, B):                                   # each tenant's own period is what its gate row now records
        for rtype in TYPES:
            row = await mongo_db.retention_gate.find_one({"tenantId": t, "type": rtype}, {"_id": 0})
            assert row["confirmedDays"] == DAYS[t], (t, rtype, row)


# ------------------------------------------------------------------ reporting surfaces (86-09)

REPORT_DAY = "2026-11-12"
STOP_RULE = "control:platform-stop"
# Distinct, public-looking targets per tenant; the same decision shapes in both.
REPORT_TARGETS = {A: ("45.33.32.156", "45.33.32.157", "45.33.32.158"), B: ("45.33.32.10", "45.33.32.11", "45.33.32.12")}
REPORT_RULES = {A: "sweep:block_ip", B: "playbook:bravo-only"}


def _report_doc(tenant, n, state, target, *, finished=None, kind="action", scope=None, rule=None, expires=None):
    doc = {"id": f"AO-{tenant}-{n}", "tenantId": tenant, "kind": kind, "origin": "playbook",
           "dispatcher": "instruction", "command": "block_ip", "actions": ["block_ip"], "targets": [],
           "target": target, "params": {}, "state": state, "level": "undoable_auto", "shadow": state == "shadow",
           "reason": {"ruleId": rule or REPORT_RULES.get(tenant, STOP_RULE), "inputs": {}},
           "reasonCode": "class_auto", "reasonText": "This action is allowed to run on its own.",
           "approval": {"requiredBy": None, "expiresAt": expires, "approver": None, "decidedAt": None},
           "undo": {"available": False, "action": None, "params": {}, "undoneAt": None, "undoneBy": None},
           "createdAt": NOW - timedelta(hours=8, minutes=n), "updatedAt": NOW, "finishedAt": finished}
    if scope:
        doc["scope"] = scope
        doc["controlEvent"] = "stop_pressed"
    return doc


async def _report_world(db):
    """Per tenant: two executed rows (one finished in the digest window), one undone, one shadow, one waiting for
    approval; plus ONE platform-scope stop row the Activity list shows to every organization."""
    await ledger.ensure_indexes(db)
    await digest.ensure_indexes(db)
    rows = []
    for tenant in (A, B):
        await seed_tenant(db, tenant, shadow=False)
        t0, t1, t2 = REPORT_TARGETS[tenant]
        finished = datetime(2026, 11, 12, 5, 0, tzinfo=timezone.utc)
        rows += [_report_doc(tenant, 1, "executed", t0, finished=finished),
                 _report_doc(tenant, 2, "executed", t1, finished=finished),
                 _report_doc(tenant, 3, "undone", t2, finished=finished),
                 _report_doc(tenant, 4, "shadow", t0 + ".shadow"),
                 _report_doc(tenant, 5, "awaiting_approval", t1 + ".wait", expires=NOW + timedelta(hours=1))]
        if tenant == B:                                     # B has an extra row so the counts differ
            rows.append(_report_doc(tenant, 6, "executed", t0 + ".extra", finished=finished))
    rows.append(_report_doc("platform-admin", 1, "executed", "stop-all", finished=NOW, kind="control",
                            scope="platform", rule=STOP_RULE))
    await db.autonomy_actions.insert_many(rows)
    return {tenant: {"tenant": tenant, **{f"ip{i}": ip for i, ip in enumerate(REPORT_TARGETS[tenant])}}
            for tenant in (A, B)}


async def test_statistics_for_each_tenant_total_only_its_own_rows(mongo_db, monkeypatch):
    monkeypatch.setattr(rbac_utils, "get_database", lambda: mongo_db)
    await _report_world(mongo_db)
    totals = {}
    for tenant in (A, B):
        caller = await views.build_caller(TokenData(username="admin@example.test", role="tenant_admin",
                                                    tenant_id=tenant, scopes=None, auth_source="session"))
        payload = await stats.statistics_payload(mongo_db, caller, tenant, 30, now=NOW)
        assert payload["tenantId"] == tenant
        assert {r["id"] for r in payload["rules"]} == {REPORT_RULES[tenant]}, payload["rules"]   # no other tenant's rule, no stop row
        totals[tenant] = payload["totals"]
    # A: 2 executed + 1 undone fired and 1 waiting; B has the same plus one more executed row.
    assert (totals[A]["fired"], totals[A]["done"], totals[A]["undone"], totals[A]["wouldHaveDone"]) == (4, 2, 1, 1)
    assert (totals[B]["fired"], totals[B]["done"], totals[B]["undone"], totals[B]["wouldHaveDone"]) == (5, 3, 1, 1)


async def test_the_export_of_each_tenant_holds_its_own_targets_and_shares_only_the_platform_stop_row(mongo_db):
    worlds = await _report_world(mongo_db)
    files = {}
    for tenant in (A, B):
        result = await export.build(mongo_db, tenant, bucket="all", days="all", fmt="csv",
                                    viewer_is_platform_staff=False, now=NOW)
        text = result.content.decode("utf-8")
        mine = [ip for key, ip in worlds[tenant].items() if key.startswith("ip")]
        other = [ip for key, ip in worlds[B if tenant == A else A].items() if key.startswith("ip")]
        assert all(ip in text for ip in mine), (tenant, mine)                 # not vacuous: every own target is there
        assert not any(ip in text for ip in other), (tenant, other)
        files[tenant] = {tuple(row) for row in result.rows}
        assert result.total == len(result.rows) == (6 if tenant == A else 7), (tenant, result.total)
    shared = files[A] & files[B]
    assert len(shared) == 1 and next(iter(shared))[6] == STOP_RULE, shared   # only the platform stop row (rule id column)


async def test_the_digest_stores_one_notice_and_one_claim_per_tenant_each_naming_only_its_own_items(mongo_db,
                                                                                                   monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)                         # no mail is attempted
    worlds = await _report_world(mongo_db)
    for tenant in (A, B):
        assert await digest.send_for_tenant(mongo_db, tenant, REPORT_DAY, NOW) == "sent"
    notices = {t: [n async for n in mongo_db.notifications.find({"tenantId": t}, {"_id": 0})] for t in (A, B)}
    assert [len(notices[t]) for t in (A, B)] == [1, 1]
    for tenant in (A, B):
        message = notices[tenant][0]["message"]
        assert worlds[tenant]["ip0"] in message and worlds[tenant]["ip1"] in message, message   # its own items are named
        assert notices[tenant][0]["metadata"]["day"] == REPORT_DAY
    assert notices[A][0]["metadata"]["counts"] == {"ran": 2, "undone": 1, "waiting": 1, "simulation": 1}
    assert notices[B][0]["metadata"]["counts"] == {"ran": 3, "undone": 1, "waiting": 1, "simulation": 1}
    owned = await assert_no_crossing(mongo_db, ["notifications", digest.DIGESTS], worlds)
    assert owned[A] == {"notifications": 1, digest.DIGESTS: 1} and owned[B] == {"notifications": 1, digest.DIGESTS: 1}
    assert "stop-all" not in notices[A][0]["message"] + notices[B][0]["message"]
