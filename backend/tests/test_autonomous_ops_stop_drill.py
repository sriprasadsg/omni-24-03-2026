"""Autonomous Ops stop drill (Phase 86, plan 86-02, GATE-06 / D-13): one world, every automatic actor.
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the stop reaches every automatic actor of Phases 82-85 at once (security sweep, agent delivery,
approvals, patch rollouts, service desk replies, self-healing restarts), for the platform scope and for one
tenant while another tenant of the same database keeps working, undo still flows, retention keeps its
documented behaviour, and a clear brings work back as new attempts with no flood and no stale card firing;
fails_when=any actor decides, delivers, approves, advances a ring or replies during a stop, a tenant stop
touches the other tenant, an unreadable stop reads as running, or a clear replays old work;
no_claim=the live agent poll, real approvals in a browser and the Ollama reply (check 5 of
docs/autonomous-ops-go-live.md covers those).
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-stop-drill")

import agent_tasks_endpoints
import audit_ledger
import retention_gate
import retention_job
from autonomous_ops import approvals, gate, ledger, protected, selfheal, settings, signals, stop, sweep
from autonomous_ops.rollout import loop as rollout_loop, start, store as rollout_store
from service_desk import intake, model, starters, store as desk_store, worker
from service_desk.model import OllamaClient
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests._watchdog_support import FakeClock, load_watchdog
from tests.autonomy_support import seed_feed_ioc, seed_native_verdict, seed_response_agent
from tests.rollout_support import (fresh_scan, post_result, seed_group, seed_rings, seed_rollout_agent, seed_window,
                                   success_result)
from tests.service_desk_support import ollama_transport, seed_desk_tenant

load_watchdog()
from omni_watchdog import restart as wd_restart, state as wd_state, sync as wd_sync  # noqa: E402

TENANTS = ("t1", "t2")
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
SWEEP_IP, QUEUED_IP = "45.33.32.156", "203.0.113.7"      # the sweep's signal; the block that is already queued
TOKENS = ("reboot_host", "patch_reversible_check")
ANSWER = "Open your company's sign-in page and choose Forgot password."
DESC = "I cannot sign in to my laptop because I forgot my password and I need to reset it"
SUPER = {"username": "root", "display": "Root", "tier": "platform"}
TENANT_ADMIN = {"username": "alice", "display": "Alice", "tier": "tenant"}
APPROVER = {"id": "u2", "name": "Bo", "username": "bo", "display": "Bo", "tier": "tenant"}
PLATFORM, TENANT_T1 = ((TENANTS, ()), (("t1",), ("t2",)))      # (stopped tenants, running tenants)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    monkeypatch.delenv("SERVICE_DESK_OLLAMA_URL", raising=False)
    monkeypatch.delenv("SERVICE_DESK_MODEL", raising=False)
    protected.cache_clear()
    model.clear_probe_cache()
    with patch.object(audit_ledger, "event", AsyncMock()), patch("autonomous_ops.notify.notify", new=AsyncMock()):
        yield


@pytest.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    import ticket_notifications
    import tickets_config_mixin
    import tickets_service
    for module in (tickets_service, tickets_config_mixin):
        monkeypatch.setattr(module, "get_database", lambda: mongo_db)
    monkeypatch.setattr(ticket_notifications, "notify_assigned", AsyncMock())
    monkeypatch.setattr(ticket_notifications, "notify_status_changed", AsyncMock())
    await ledger.ensure_indexes(mongo_db)
    await signals.ensure_indexes(mongo_db)
    await rollout_store.ensure_indexes(mongo_db)
    await desk_store.ensure_indexes(mongo_db)
    return mongo_db


# ------------------------------------------------------------------ the world

def _req(t, action, ip=None):
    return gate.ActionRequest(tenant_id=t, kind="security", origin="test", actions=[action], targets=[f"a-{t}"],
                              params={"ip_address": ip} if ip else {}, dedupe_key=f"{t}|{action}|{ip}",
                              reason={"ruleId": "test", "inputs": {}}, dispatcher="instruction")


async def _ticket(db, tenant, ticket_id, n):
    ticket = {"id": ticket_id, "tenantId": tenant, "ticket_number": f"TKT-{n:04d}", "title": "I forgot my password",
              "description": DESC, "type": "task", "priority": "medium", "status": "open", "reporter": "alice",
              "assignee": None, "raised_via": "portal", "comments": [], "history": [], "escalated": False,
              "requester_channel": {"portal": True, "tray": False, "myTickets": False}}
    await db.tickets.insert_one(dict(ticket))
    return ticket


async def _world(db, t):
    """Ticked tenant (shadow off, undoable_auto) with: sweep signals that make the sweep block an address, one
    queued stamped block and one queued stamped undo for its agent, one pending approval card, a started
    patch rollout and a ticket already waiting for the desk. Returns the ids the checks use."""
    await seed_desk_tenant(db, t, mode="post", shadow=False)
    agent = f"a-{t}"
    await seed_response_agent(db, t, agent, hostname=f"host-{t}", tokens=["block_ip_ttl"], last_seen=NOW)
    await seed_native_verdict(db, t, f"host-{t}", kind="ip", target=SWEEP_IP, created_at=NOW)
    if not await db.edr_ioc.count_documents({}):         # the threat feed is shared, like the real one
        await seed_feed_ioc(db, ioc_type="url", value=f"http://{SWEEP_IP}/x", source_ip=SWEEP_IP, feed="urlhaus",
                            updated_at=NOW)
    block = await gate.decide(db, _req(t, "block_ip", QUEUED_IP), master_shadow=False)
    assert block.outcome == "allow_auto", block
    queued = await gate.execute(db, t, block.action_id, command="block_ip", agent_id=agent,
                                params={"ip_address": QUEUED_IP})
    assert queued["status"] == "queued", queued
    undo_row = await ledger.create_intent(db, {
        "tenantId": t, "kind": "security", "state": "undone", "command": "unblock_ip", "actions": ["block_ip"],
        "targets": [agent], "params": {"ip_address": QUEUED_IP},
        "steps": [{"command": "block_ip", "params": {"ip_address": QUEUED_IP}}],
        "rollback": [{"command": "unblock_ip", "params": {"ip_address": QUEUED_IP}}],
        "undo": {"available": True, "action": "unblock_ip", "params": {"ip_address": QUEUED_IP}}})
    undo = await gate.execute(db, t, undo_row["id"], command="unblock_ip", agent_id=agent,
                              params={"ip_address": QUEUED_IP}, kind="undo")
    assert undo["status"] == "queued", undo
    card = await gate.decide(db, _req(t, "isolate_host"), master_shadow=False)
    assert card.state == "awaiting_approval", card
    canary, rest = f"c-{t}", f"r-{t}"
    for name in (canary, rest):
        await seed_rollout_agent(db, t, name, hostname=f"host-{name}", platform="Linux", tokens=TOKENS,
                                 pending=["openssl"], boot_time=1_700_000_000, last_seen=NOW)
    await seed_group(db, t, f"G-{t}", [canary])
    await seed_rings(db, t, [{"key": "canary", "name": "Canary", "groupIds": [f"G-{t}"], "soakHours": 1},
                             {"key": "rest", "name": "Everyone else", "groupIds": [], "soakHours": 1}])
    await seed_window(db, t, start="00:00", end="23:59", name=f"all-day-{t}")
    rollout = await start.start_rollout(db, t, name="Nov", patch_ids=["openssl"], actor={"id": "u1", "name": "Ann"},
                                        now=NOW)
    assert rollout["status"] == "started", rollout
    await db.knowledge_docs.insert_many(starters.copy_docs(t, {"name": "test"}, "2026-11-09T09:00:00"))
    waiting = await _ticket(db, t, f"k-{t}", 1)
    assert await intake.on_ticket_created(db, waiting, via="portal", now=NOW), "the ticket was not queued"
    return {"block": queued["task_id"], "block_row": block.action_id, "undo": undo["task_id"],
            "card": card.action_id, "rollout": rollout["rolloutId"], "canary": canary, "agent": agent}


@pytest.fixture
async def worlds(db):
    found = {t: await _world(db, t) for t in TENANTS}
    await rollout_loop.run_once(db, now=NOW)             # the canary install is sent: an attempt is in progress
    for t in TENANTS:
        assert await db.autonomy_actions.count_documents({"tenantId": t, "dispatcher": "patch_rollout",
                                                           "state": "dispatching"}) == 1
    return found


# ------------------------------------------------------------------ helpers

async def _press(db, scope, tenant="t1"):
    out = await stop.press(db, scope=scope, tenant_id=tenant if scope == "tenant" else None,
                           actor=SUPER if scope == "platform" else TENANT_ADMIN, reason="drill", now=NOW)
    assert out["status"] == "stopped", out
    return out


async def _lift(db, scope, tenant="t1"):
    """Turn a stop off through stop.clear (the only code that does), a reason typed, as the Super Admin."""
    out = await stop.clear(db, scope=scope, tenant_id=tenant if scope == "tenant" else None, actor=SUPER,
                           reason="drill over", actor_is_super_admin=True, actor_has_manage=True,
                           now=NOW + timedelta(minutes=30))
    assert out["status"] == "cleared", out


def _decisions(db, t, **extra):
    return db.autonomy_actions.count_documents({"tenantId": t, "kind": {"$ne": "control"}, **extra})


async def _poll(db, t):
    """The task ids the tenant's agent receives from its instruction poll."""
    req = MagicMock()
    req.headers = {"host": "10.0.0.1"}
    req.url.scheme = "http"
    agent = f"a-{t}"
    with patch.object(agent_tasks_endpoints, "get_database", return_value=db):
        got = await agent_tasks_endpoints.get_agent_instructions(
            agent, request=req, _tenant={"tenant_id": t, "authenticated_agent_id": agent})
    return {d.get("task_id") or d.get("id") for d in got}


async def _status(db, task_id):
    return (await db.agent_instructions.find_one({"id": task_id}, {"_id": 0}))["status"]


async def _online(db, at):
    await db.agents.update_many({}, {"$set": {"lastSeen": at.isoformat(), "status": "Online"}})


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# ------------------------------------------------------------------ one check per actor

async def _sweep_check(db, w, stopped, running):
    before = {t: await _decisions(db, t) for t in TENANTS}
    await sweep.tick(db, now=NOW)
    for t in stopped:
        assert await _decisions(db, t) == before[t], t
    for t in running:
        assert await _decisions(db, t, command="block_ip", **{"params.ip_address": SWEEP_IP}) == 1, t


async def _delivery_check(db, w, stopped, running):
    for t in stopped:
        assert await _poll(db, t) == {w[t]["undo"]}, t                 # the undo flows, the block does not
        assert await _status(db, w[t]["block"]) == "cancelled_by_stop"
        assert (await ledger.get(db, t, w[t]["block_row"]))["state"] == "cancelled_by_stop"
    for t in running:
        assert {w[t]["block"], w[t]["undo"]} <= await _poll(db, t), t
        assert (await ledger.get(db, t, w[t]["block_row"]))["state"] == "dispatching"


async def _approval_check(db, w, stopped, running):
    for t in stopped:
        out = await approvals.approve(db, t, w[t]["card"], approver=APPROVER, now=NOW)
        assert out == {"status": "stopped"}, out
        assert (await ledger.get(db, t, w[t]["card"]))["state"] == "awaiting_approval"
        assert (await approvals.deny(db, t, w[t]["card"], approver=APPROVER, reason="drill"))["status"] == "denied"
    for t in running:
        assert (await approvals.approve(db, t, w[t]["card"], approver=APPROVER, now=NOW))["status"] == "dispatched"


async def _advance(db, t, w):
    """The canary computer installs and soaks on a fresh scan: the next pass raises ring 1's approval line."""
    job = await db.patch_deployment_jobs.find_one({"rolloutId": w[t]["rollout"]})
    await post_result(db, job["id"], w[t]["canary"], success_result(["openssl"]))
    await _online(db, NOW + timedelta(minutes=2))
    await rollout_loop.run_once(db, now=NOW + timedelta(minutes=2))
    host = await db.patch_rollout_hosts.find_one({"tenantId": t, "agentId": w[t]["canary"]})
    assert host["state"] == "installed", host
    installed = _aware(host["installReportedAt"])
    await fresh_scan(db, w[t]["canary"], [], installed + timedelta(minutes=10))
    later = installed + timedelta(minutes=61)
    await _online(db, later)
    await rollout_loop.run_once(db, now=later)
    ring_one = await db.autonomy_actions.find({"tenantId": t, "dispatcher": "patch_rollout", "state": "awaiting_approval",
                                               "reason.inputs.ring": 1}).to_list(10)
    assert [r["targets"][0] for r in ring_one] == [f"r-{t}"], t


async def _rollout_check(db, w, stopped, running):
    snap = {t: (await db.autonomy_actions.count_documents({"tenantId": t}),
                await db.agent_instructions.count_documents({"tenantId": t})) for t in stopped}
    for t in running:
        await _advance(db, t, w)
    for minutes in (1, 90):                              # the frozen rollouts are looked at again and again
        await _online(db, NOW + timedelta(minutes=minutes))
        await rollout_loop.run_once(db, now=NOW + timedelta(minutes=minutes))
    for t in stopped:
        rollout = await db.patch_rollouts.find_one({"id": w[t]["rollout"]})
        assert rollout["status"] == "running" and rollout["stoppedSince"] is not None, t
        assert (await db.autonomy_actions.count_documents({"tenantId": t}),
                await db.agent_instructions.count_documents({"tenantId": t})) == snap[t], t
        assert await db.autonomy_actions.count_documents({"tenantId": t, "state": "refused"}) == 0, t
    for t in running:
        assert (await db.patch_rollouts.find_one({"id": w[t]["rollout"]})).get("stoppedSince") is None


async def _desk_check(db, w, stopped, running):
    fresh = {t: await _ticket(db, t, f"n-{t}", 2) for t in TENANTS}
    for t in TENANTS:
        queued = await intake.on_ticket_created(db, fresh[t], via="portal", now=NOW)
        assert (queued is None) == (t in stopped), t
    transport, calls = ollama_transport(ANSWER, [1])
    for _ in range(6):                                   # the worker answers one ticket per pass
        await worker.run_once(db, client=OllamaClient(transport=transport), now=NOW)
        if not await db.service_desk_jobs.count_documents({"state": {"$in": ["pending", "ready", "running"]}}):
            break
    generated = [c for c in calls if c["path"] == "/api/generate"]
    for t in stopped:
        job = await db.service_desk_jobs.find_one({"ticketId": f"k-{t}"}, {"_id": 0})
        assert (job["state"], job["reason"]) == ("done", "desk_stopped"), t
        kinds = [c["kind"] for c in (await db.tickets.find_one({"id": f"k-{t}"}))["comments"]]
        assert "staff_note" in kinds and not {"ai_answer", "ai_draft"} & set(kinds), (t, kinds)
    for t in running:
        kinds = [c["kind"] for c in (await db.tickets.find_one({"id": f"k-{t}"}))["comments"]]
        assert "ai_answer" in kinds, (t, kinds, [j async for j in db.service_desk_jobs.find({}, {"_id": 0})])
    assert (not generated) == (not running), generated


async def _all_checks(db, w, stopped, running):
    for check in (_sweep_check, _delivery_check, _approval_check, _rollout_check, _desk_check):
        await check(db, w, stopped, running)


# ------------------------------------------------------------------ control: the world acts when nothing is stopped

async def test_control_the_same_world_acts_in_every_actor_when_no_stop_is_on(db, worlds):
    await _all_checks(db, worlds, (), TENANTS)


# ------------------------------------------------------------------ Task 1: the platform stop, one test per property

async def test_platform_stop_the_sweep_records_no_new_decision_for_either_tenant(db, worlds):
    await _press(db, "platform")
    await _sweep_check(db, worlds, *PLATFORM)


async def test_platform_stop_cancels_the_queued_instruction_and_only_undo_is_delivered(db, worlds):
    pressed = await _press(db, "platform")
    assert pressed["cancelled"] >= 2
    await _delivery_check(db, worlds, *PLATFORM)
    assert await _status(db, worlds["t1"]["undo"]) == "sent"


async def test_platform_stop_approve_answers_stopped_and_deny_still_works(db, worlds):
    await _press(db, "platform")
    await _approval_check(db, worlds, *PLATFORM)


async def test_platform_stop_freezes_the_running_rollout_without_a_decision_or_a_refused_row(db, worlds):
    await _press(db, "platform")
    await _rollout_check(db, worlds, *PLATFORM)


async def test_platform_stop_the_desk_queues_nothing_and_hands_the_waiting_ticket_to_a_person(db, worlds):
    await _press(db, "platform")
    await _desk_check(db, worlds, *PLATFORM)


async def test_platform_stop_does_not_pause_retention_the_documented_exception(db, worlds, monkeypatch):
    monkeypatch.setattr(retention_job, "_sleep", AsyncMock())

    def oid(days_ago, n):
        stamp = ObjectId.from_datetime(NOW - timedelta(days=days_ago, seconds=n)).binary[:4]
        return ObjectId(stamp + os.urandom(8))

    await db.agent_metrics.insert_many([{"_id": oid(40, i), "tenant_id": "t1", "n": i} for i in range(3)]
                                       + [{"_id": oid(5, i), "tenant_id": "t1", "n": 100 + i} for i in range(2)])
    await _press(db, "platform")
    counted = await retention_job.run_all(db, now=NOW, trigger="scheduled")
    assert counted["counted"] >= 3 and counted["deleted"] == 0       # the first run only counts
    rows = await retention_gate.review_rows(db)
    await retention_gate.confirm(db, retention_gate.review_token(rows), "Super Admin", NOW)
    ran = await retention_job.run_all(db, now=NOW + timedelta(minutes=1))
    assert ran["deleted"] == 3                                       # runs and deletes, never paused by the stop
    assert [d["n"] async for d in db.agent_metrics.find({}).sort("n", 1)] == [100, 101]


async def test_platform_stop_reaches_the_watchdog_through_the_database_source_and_pauses_restarts(db, worlds, tmp_path):
    def decide(effective, source):
        calls, clock = [], FakeClock()

        def run(argv, timeout):
            calls.append(list(argv))
            return 0, "inactive\n"

        state = {"services": {"nginx": {"state": "down", "failedChecks": 2, "restarts": []}}}
        health = {sid: (True, "") for sid in ("mongod", "omni-backend", "nginx")}
        health["nginx"] = (False, "inactive")
        events = wd_restart.decide(state, health, {"effective": effective, "source": source}, clock(), {}, run=run,
                                   clock=clock, sleep=clock.advance, recheck=lambda sid: (True, ""))
        return [c for c in calls if c[1] != "is-active"], [e["kind"] for e in events]

    await _press(db, "platform")
    answer = await selfheal.sync_response(db, [], 0)                 # what the backend tells the watchdog
    effective, source = wd_sync.resolve_stop(str(tmp_path / "STOP"), answer, wd_state.empty_state(), now=1.0)
    assert (effective, source) == (True, "database")
    assert decide(effective, source) == ([], ["restart_skipped"])    # restarts pause; checks and the sync go on
    await _lift(db, "platform")
    effective, source = wd_sync.resolve_stop(str(tmp_path / "STOP"), await selfheal.sync_response(db, [], 0),
                                             wd_state.empty_state(), now=2.0)
    assert (effective, source) == (False, "database")
    restarted, kinds = decide(effective, source)
    assert restarted and "restart_skipped" not in kinds


# ------------------------------------------------------------------ Task 2: a tenant stop; the other tenant carries on

async def test_tenant_stop_the_sweep_stops_for_t1_while_t2_decides_its_block(db, worlds):
    await _press(db, "tenant")
    await _sweep_check(db, worlds, *TENANT_T1)


async def test_tenant_stop_t1_is_held_back_and_t2_is_delivered_but_undo_flows_for_both(db, worlds):
    pressed = await _press(db, "tenant")
    assert pressed["cancelled"] >= 2
    await _delivery_check(db, worlds, *TENANT_T1)
    assert await _status(db, worlds["t1"]["undo"]) == "sent" and await _status(db, worlds["t2"]["block"]) == "sent"


async def test_tenant_stop_t1_approve_answers_stopped_deny_works_and_t2_can_approve(db, worlds):
    await _press(db, "tenant")
    await _approval_check(db, worlds, *TENANT_T1)


async def test_tenant_stop_t1_rollout_is_frozen_while_t2_rollout_advances(db, worlds):
    await _press(db, "tenant")
    await _rollout_check(db, worlds, *TENANT_T1)


async def test_tenant_stop_t1_ticket_goes_to_a_person_while_t2_still_gets_its_reply(db, worlds):
    await _press(db, "tenant")
    await _desk_check(db, worlds, *TENANT_T1)


# ------------------------------------------------------------------ resume, per scope

async def _resume_check(db, w, scope, stopped):
    """Press, let every actor see the stop, clear it, and check the work comes back once and as new attempts."""
    await _press(db, scope)
    fresh = {t: await _ticket(db, t, f"n-{t}", 2) for t in stopped}
    for t in stopped:
        assert await intake.on_ticket_created(db, fresh[t], via="portal", now=NOW) is None
    await _online(db, NOW + timedelta(minutes=1))
    await rollout_loop.run_once(db, now=NOW + timedelta(minutes=1))
    cancelled = {t: {i["id"] async for i in db.agent_instructions.find(
        {"tenantId": t, "agent_id": w[t]["canary"], "status": "cancelled_by_stop"})} for t in stopped}
    assert all(len(ids) == 1 for ids in cancelled.values())
    await _lift(db, scope)

    later = NOW + timedelta(minutes=40)
    await _online(db, later)
    for _ in range(2):                                   # the next pass decides once; a second pass repeats nothing
        await sweep.tick(db, now=later)
        for t in stopped:
            assert await _decisions(db, t, command="block_ip", **{"params.ip_address": SWEEP_IP}) == 1, t
    await rollout_loop.run_once(db, now=later)
    for t in stopped:
        rollout = await db.patch_rollouts.find_one({"id": w[t]["rollout"]})
        assert rollout["status"] == "running" and rollout.get("stoppedSince") is None, t
        again = await db.autonomy_actions.find({"tenantId": t, "dispatcher": "patch_rollout",
                                                "state": "dispatching"}).to_list(10)
        assert [(r["targets"], r["reason"]["inputs"]["attempt"]) for r in again] == [([w[t]["canary"]], 2)], t
        pending = {i["id"] async for i in db.agent_instructions.find(
            {"tenantId": t, "agent_id": w[t]["canary"], "status": "pending"})}
        assert len(pending) == 1 and not pending & cancelled[t], t        # a new attempt, never the cancelled one
        card = await ledger.get(db, t, w[t]["card"])
        assert card["state"] == "awaiting_approval" and not (card.get("approval") or {}).get("approver"), t
        assert await intake.on_ticket_created(db, fresh[t], via="portal", now=later), t      # the desk queues it now


async def test_resume_after_the_platform_stop_clears_decides_again_and_offers_the_rollout_as_a_new_attempt(db, worlds):
    await _resume_check(db, worlds, "platform", TENANTS)


async def test_resume_after_a_tenant_stop_clears_t1_the_same_way_and_t2_is_unaffected(db, worlds):
    await _resume_check(db, worlds, "tenant", ("t1",))
    assert await _decisions(db, "t2", command="block_ip", **{"params.ip_address": SWEEP_IP}) == 1   # t2 never paused


async def test_a_stop_that_cannot_be_read_counts_as_stopped_for_every_gate(db, worlds):
    unreadable = AsyncMock(side_effect=RuntimeError("db down"))
    with patch.object(settings, "platform_stop", unreadable):
        assert await gate._stopped(db, "t1") is True and await gate._stopped(db, "t2") is True
        out = await approvals.approve(db, "t1", worlds["t1"]["card"], approver=APPROVER, now=NOW)
        assert out == {"status": "stopped"}
        before = await _decisions(db, "t1") + await _decisions(db, "t2")
        await sweep.tick(db, now=NOW)
        assert await _decisions(db, "t1") + await _decisions(db, "t2") == before
        assert await _poll(db, "t1") == {worlds["t1"]["undo"]}           # withheld and left as it was, undo exempt
        assert await _status(db, worlds["t1"]["block"]) == "pending"
    assert await gate._stopped(db, "t1") is False                        # readable again: nothing is stopped
