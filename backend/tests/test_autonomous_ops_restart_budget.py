"""RESP-04, D-10 / D-11 / D-12: a listed service that fails is restarted within a budget, then a person is asked.
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; time is frozen by
passing ``now`` to the real sweep, so every boundary is exact.

Value: protects=a service on the tenant's list that an agent reports failed comes back on its own up to 3 times in
a rolling hour with waits of 1, 2 and 4 minutes, the fourth try is ONE approval card, a service off the list never
restarts, the budget is read from the ledger (a restart of the process resets nothing), and the list reaches the
tenant's agents only when the tenant holds remediation_executor; fails_when=a try is made 1 second early, a row
exactly one hour old still counts, a simulation or refused row counts, an unlisted or empty-list service restarts,
a card is raised twice or right after a person denied it, a card answered late starts a second restart, a restart
row can be undone, or a tenant without the tick sends or stores failure data;
no_claim=a real agent, a real service or the live database.
"""
import copy
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent_capabilities
import agent_tasks_endpoints
from autonomous_ops import (approvals, breaker, ledger, protected, reconciler, response_messages as rm, response_settings,
                            response_views, settings, signals, sweep, sweep_restart, sweep_security)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_response_agent, seed_tenant

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
T = "t1"
APPROVER = {"username": "carol", "display": "Carol", "tier": "tenant"}
BUDGET_TEXT = "Restarted nginx 3 times in the last hour. Further restarts need your approval."


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


def at(seconds):
    return NOW + timedelta(seconds=seconds)


async def _report(db, when, names=("nginx",), *, seen=None):
    """The agent's heartbeat at ``when``: Online, and failing the named services since two minutes before NOW."""
    since = int(NOW.timestamp()) - 120
    failures = [{"name": n, "failure_id": f"{n.lower()}-{since}", "since": since, "state": "failed", "exit_code": 3}
                for n in names]
    await db.agents.update_one({"id": "a1"}, {"$set": {"status": "Online", "lastSeen": (seen or when).isoformat(),
                                                       "meta.service_failures": failures}})


async def _world(db, *, watched=("nginx",), failing=("nginx",), tokens=("restart_service",), shadow=False,
                 capable=True):
    await ledger.ensure_indexes(db)
    await signals.ensure_indexes(db)
    await seed_tenant(db, T, shadow=shadow)
    await seed_response_agent(db, T, "a1", hostname="host-a1", tokens=tokens, last_seen=NOW, capable=capable)
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"response": {"watchedServices": list(watched)}}})
    await _report(db, NOW, failing)
    return db


async def tick(db, seconds, names=("nginx",), **kw):
    await _report(db, at(seconds), names, **kw)
    return await sweep.tick(db, now=at(seconds))


async def rows(db):
    return [r async for r in db.autonomy_actions.find({"tenantId": T, "command": "restart_service"}, {"_id": 0})
            .sort([("createdAt", 1), ("id", 1)])]


async def end_open(db, state="failed", code="verify_failed"):
    """The open automatic restarts end (the agent said the service did not come back)."""
    for row in await rows(db):
        if row["state"] == "dispatching":
            await ledger.transition(db, T, row["id"], ("dispatching",), state, reasonCode=code)


async def three_tries(db):
    """Tries at 0, 60 and 180 seconds, each of which failed."""
    for seconds in (0, 60, 180):
        await tick(db, seconds)
        await end_open(db)
    assert [r["reason"]["inputs"]["attempt"] for r in await rows(db)] == [1, 2, 3]


async def seed_row(db, state, seconds, *, key, auto=False):
    """A restart row written straight to the ledger, created ``seconds`` after NOW."""
    await ledger.create_intent(db, {
        "tenantId": T, "kind": "security", "origin": "sweep", "dispatcher": "security_response", "command": "restart_service",
        "targets": ["a1"], "target": "a1", "params": {"service_name": "nginx"}, "state": state, "dedupeKey": key,
        "autoDispatched": auto, "createdAt": at(seconds), "updatedAt": at(seconds), "reason": {"ruleId": "x", "inputs": {}}})


# ------------------------------------------------------------------ the first try

async def test_a_failed_listed_service_is_restarted_through_the_gate(mongo_db):
    await _world(mongo_db)
    counts = await tick(mongo_db, 0)
    assert counts["restarted"] == 1
    (row,) = await rows(mongo_db)
    assert row["state"] == "dispatching" and row["autoDispatched"] is True and row["params"] == {"service_name": "nginx"}
    assert row["targets"] == ["a1"] and row["reason"]["ruleId"] == "sweep:restart_service"
    inputs = row["reason"]["inputs"]
    assert inputs["service"] == "nginx" and inputs["attempt"] == 1 and inputs["failureId"].startswith("nginx-")
    assert row["reasonText"] == "nginx stopped and is on your watched list."
    assert row["undo"]["available"] is False                                   # D-12
    (doc,) = [d async for d in mongo_db.agent_instructions.find({"tenantId": T}, {"_id": 0})]
    assert doc["type"] == "restart_service" and doc["parameters"] == {"service_name": "nginx"}
    assert doc["triggered_by"] == "autonomous_ops" and doc["autonomy"]["actionId"] == row["id"]
    incident = await mongo_db.autonomy_incidents.find_one({"agentId": "a1"})
    assert inputs["incidentId"] == incident["id"] and incident["alertCount"] == 1
    assert incident["startedAt"].replace(tzinfo=timezone.utc) == NOW - timedelta(seconds=120)    # the failure's own time
    await tick(mongo_db, 30)                                                   # one open row per service and computer
    assert len(await rows(mongo_db)) == 1 and await mongo_db.agent_instructions.count_documents({}) == 1


async def test_one_failure_is_one_piece_of_evidence_however_many_tries(mongo_db):
    await _world(mongo_db)
    await tick(mongo_db, 0)
    await end_open(mongo_db)
    await tick(mongo_db, 60)
    incident = await mongo_db.autonomy_incidents.find_one({"agentId": "a1"})
    assert incident["alertCount"] == 1 and await mongo_db.autonomy_incidents.count_documents({}) == 1


# ------------------------------------------------------------------ the wait ladder and the card

async def test_the_waits_are_1_2_and_4_minutes_and_the_fourth_try_is_one_card(mongo_db):
    await _world(mongo_db)
    await tick(mongo_db, 0)
    await end_open(mongo_db)
    await tick(mongo_db, 59)
    assert len(await rows(mongo_db)) == 1                                      # 59 seconds: nothing
    await tick(mongo_db, 60)
    assert [r["reason"]["inputs"]["attempt"] for r in await rows(mongo_db)] == [1, 2]
    await end_open(mongo_db)
    await tick(mongo_db, 179)
    assert len(await rows(mongo_db)) == 2                                      # 119 seconds after the second
    await tick(mongo_db, 180)
    assert [r["reason"]["inputs"]["attempt"] for r in await rows(mongo_db)] == [1, 2, 3]
    await end_open(mongo_db)
    await tick(mongo_db, 419)
    assert len(await rows(mongo_db)) == 3                                      # 239 seconds after the third: no card yet
    counts = await tick(mongo_db, 420)
    assert counts["cards"] == 1
    card = (await rows(mongo_db))[-1]
    assert card["state"] == "awaiting_approval" and card["reasonCode"] == "playbook_raised"
    assert card["reasonText"] == BUDGET_TEXT == rm.fill(rm.WHY_TEMPLATES["restart_over_budget"], service="nginx")
    assert card["reason"]["inputs"]["overBudget"] is True and card["reason"]["inputs"]["incidentId"]
    assert "attempt" not in card["reason"]["inputs"] and card["dedupeKey"].endswith("|card")
    assert card["autoDispatched"] is False and card["approval"]["expiresAt"] is not None
    for seconds in range(480, 480 + 600, 60):                                  # ten more ticks: still the one card
        await tick(mongo_db, seconds)
    assert len(await rows(mongo_db)) == 4 and await mongo_db.agent_instructions.count_documents({}) == 3
    assert response_views.row_extras(card)["reasonText"] == BUDGET_TEXT


async def test_a_row_59m59s_old_counts_and_one_exactly_an_hour_old_does_not(mongo_db):
    await _world(mongo_db)
    await three_tries(mongo_db)
    await tick(mongo_db, 3599)                                                 # the first try is 3599 s old: still counts
    last = (await rows(mongo_db))[-1]
    assert len(await rows(mongo_db)) == 4 and last["state"] == "awaiting_approval" and last["reasonCode"] == "playbook_raised"


async def test_exactly_one_hour_old_no_longer_counts(mongo_db):
    await _world(mongo_db)
    await three_tries(mongo_db)
    await tick(mongo_db, 3600)                                                 # the first try is exactly 1 hour old
    last = (await rows(mongo_db))[-1]
    assert len(await rows(mongo_db)) == 4 and last["state"] == "dispatching" and last["reason"]["inputs"]["attempt"] == 3
    assert "overBudget" not in last["reason"]["inputs"]


async def test_the_budget_is_read_from_the_ledger_so_a_fresh_process_keeps_it(mongo_db):
    await _world(mongo_db)
    await three_tries(mongo_db)
    importlib.reload(sweep_restart)                                            # nothing is held in memory
    tenant, response = await settings.load(mongo_db, T), await response_settings.load(mongo_db, T)
    await _report(mongo_db, at(420))
    counts = await sweep_restart.run(mongo_db, T, tenant, response, at(420))
    assert counts["cards"] == 1 and (await rows(mongo_db))[-1]["state"] == "awaiting_approval"


# ------------------------------------------------------------------ who is never restarted

@pytest.mark.parametrize("watched, failing", [
    (("nginx",), ("redis",)), ((), ("nginx",)), (("nginx",), ("nginx-extra",)), (("ngin",), ("nginx",))])
async def test_a_service_off_the_list_and_an_empty_list_restart_nothing(mongo_db, watched, failing):
    await _world(mongo_db, watched=watched, failing=failing)
    await tick(mongo_db, 0, failing)
    assert await rows(mongo_db) == [] and await mongo_db.agent_instructions.count_documents({}) == 0
    assert await mongo_db.autonomy_incidents.count_documents({}) == 0


@pytest.mark.parametrize("listed, reported", [("NGINX", "nginx"), ("nginx", "NGINX"), ("Nginx", "nGiNx")])
async def test_the_list_is_compared_case_insensitively_and_the_listed_spelling_is_sent(mongo_db, listed, reported):
    await _world(mongo_db, watched=(listed,), failing=(reported,))
    await tick(mongo_db, 0, (reported,))
    (row,) = await rows(mongo_db)
    assert row["params"] == {"service_name": listed} and row["reason"]["inputs"]["service"] == listed


async def test_a_host_without_the_token_or_offline_gets_no_row_and_no_breaker_effect(mongo_db):
    await _world(mongo_db, tokens=("block_ip_ttl",))
    await tick(mongo_db, 0)
    assert await rows(mongo_db) == []
    await mongo_db.agents.update_one({"id": "a1"}, {"$set": {"meta.response_actions.tokens": ["restart_service"]}})
    await tick(mongo_db, 10, seen=at(10) - timedelta(minutes=6))               # last heard from 6 minutes ago
    assert await rows(mongo_db) == []
    assert await mongo_db.autonomy_actions.count_documents({"kind": {"$ne": "control"}}) == 0
    assert (await mongo_db.autonomy_settings.find_one({"tenantId": T}))["breaker"] is None


@pytest.mark.real_agent_capabilities
async def test_a_tenant_without_the_remediation_tick_restarts_nothing(mongo_db):
    await _world(mongo_db, capable=False)
    await tick(mongo_db, 0)
    assert await rows(mongo_db) == []


# ------------------------------------------------------------------ what counts toward the budget

async def test_simulations_and_refused_rows_count_nothing_toward_the_budget(mongo_db):
    await _world(mongo_db)
    for i in range(3):
        await seed_row(mongo_db, "shadow", -300 + i, key=f"s{i}")
    for i in range(2):
        await seed_row(mongo_db, "refused", -200 + i, key=f"r{i}")
    await tick(mongo_db, 0)
    last = (await rows(mongo_db))[-1]
    assert last["state"] == "dispatching" and last["reason"]["inputs"]["attempt"] == 1       # not a card, not attempt 4


async def test_a_tenant_in_shadow_mode_records_a_simulation_and_sends_nothing(mongo_db):
    await _world(mongo_db, shadow=True)
    counts = await tick(mongo_db, 0)
    (row,) = await rows(mongo_db)
    assert counts["shadow"] == 1 and row["state"] == "shadow" and await mongo_db.agent_instructions.count_documents({}) == 0
    await tick(mongo_db, 120)
    assert len(await rows(mongo_db)) == 1                                      # the gate holds a simulation for the cooldown


async def test_restarts_do_not_raise_the_block_cap_but_do_count_toward_the_twenty_an_hour(mongo_db):
    await _world(mongo_db)
    await three_tries(mongo_db)
    since = NOW - timedelta(hours=1)
    assert await ledger.count_host_auto_since(mongo_db, T, "a1", sweep_security._HOST_COMMANDS, since) == 0
    assert "restart_service" not in sweep_security._HOST_COMMANDS
    assert await ledger.count_auto_since(mongo_db, T, since) == 3


async def test_the_twentieth_automatic_action_of_the_hour_sends_the_restart_to_a_person(mongo_db):
    await _world(mongo_db)
    for i in range(20):
        await ledger.create_intent(mongo_db, {
            "tenantId": T, "kind": "security", "command": "block_ip", "targets": [f"x{i}"], "state": "executed",
            "dedupeKey": f"b{i}", "autoDispatched": True, "createdAt": at(-60 - i), "updatedAt": at(-60 - i)})
    await tick(mongo_db, 0)
    (row,) = await rows(mongo_db)
    assert row["state"] == "awaiting_approval" and row["reasonCode"] == "rate_limit"
    assert await mongo_db.agent_instructions.count_documents({}) == 0


# ------------------------------------------------------------------ the card

async def test_a_denied_card_is_not_raised_again_for_24_hours(mongo_db):
    await _world(mongo_db)
    await three_tries(mongo_db)
    await tick(mongo_db, 420)
    card = (await rows(mongo_db))[-1]
    await ledger.transition(mongo_db, T, card["id"], ("awaiting_approval",), "denied", finishedAt=at(480))
    for seconds in (3 * 3600, 480 + 86399):                                    # the budget rows are long gone: memory holds
        await tick(mongo_db, seconds)
        assert len(await rows(mongo_db)) == 4
    await tick(mongo_db, 480 + 86400)
    again = (await rows(mongo_db))[-1]
    assert len(await rows(mongo_db)) == 5 and again["state"] == "dispatching" and again["reason"]["inputs"]["attempt"] == 1


async def test_a_card_answered_late_cannot_start_a_second_restart_while_one_is_open(mongo_db):
    await _world(mongo_db)
    await three_tries(mongo_db)
    await tick(mongo_db, 420)
    card = (await rows(mongo_db))[-1]
    await tick(mongo_db, 3800)                                                 # the three tries are gone, the card is open
    assert len(await rows(mongo_db)) == 4 and (await rows(mongo_db))[-1]["id"] == card["id"]
    await db_seen_now(mongo_db)                                                # approvals re-check support against the real clock
    assert (await approvals.approve(mongo_db, T, card["id"], approver=APPROVER, now=at(3800)))["status"] == "dispatched"
    await tick(mongo_db, 3860)
    assert len(await rows(mongo_db)) == 4 and await mongo_db.agent_instructions.count_documents({}) == 4


async def test_a_card_for_a_service_that_has_recovered_is_refused_and_restarts_nothing(mongo_db):
    # WR-03: the service came back (by hand or on its own) after the card was raised; approving it late
    # must not restart a healthy service.
    await _world(mongo_db)
    await three_tries(mongo_db)
    await tick(mongo_db, 420)
    card = (await rows(mongo_db))[-1]
    sent = await mongo_db.agent_instructions.count_documents({})
    await mongo_db.agents.update_one({"id": "a1"}, {"$set": {"meta.service_failures": []}})
    await db_seen_now(mongo_db)
    out = await approvals.approve(mongo_db, T, card["id"], approver=APPROVER, now=at(480))
    assert out == {"status": "refused", "reason": "service_recovered"}
    row = await ledger.get(mongo_db, T, card["id"])
    assert row["state"] == "refused" and row["reasonText"] == rm.REASON_TEXT["service_recovered"]
    assert await mongo_db.agent_instructions.count_documents({}) == sent


async def test_the_sweep_ends_an_open_card_once_the_service_has_recovered(mongo_db):
    # WR-03: the next tick that no longer sees the failure ends the card; a later failure starts fresh,
    # not held quiet for 24 hours as a lapsed card would be.
    await _world(mongo_db)
    await three_tries(mongo_db)
    await tick(mongo_db, 420)
    card = (await rows(mongo_db))[-1]
    await tick(mongo_db, 480, names=())
    row = await ledger.get(mongo_db, T, card["id"])
    assert row["state"] == "expired" and row["reasonCode"] == "service_recovered"
    assert row["reasonText"] == rm.REASON_TEXT["service_recovered"]
    await tick(mongo_db, 2 * 3600)
    last = (await rows(mongo_db))[-1]
    assert len(await rows(mongo_db)) == 5 and last["state"] == "dispatching" and last["reason"]["inputs"]["attempt"] == 1


async def test_a_dead_service_spending_its_budget_does_not_trip_the_breaker(mongo_db):
    # WR-04: three failed restarts of one service are the budget working, not the tenant's automation going wrong.
    await _world(mongo_db)
    await three_tries(mongo_db)
    assert [r["reasonCode"] for r in await rows(mongo_db)] == ["verify_failed"] * 3
    with patch("autonomous_ops.breaker.notify.notify") as notice:
        assert await breaker.evaluate(mongo_db, T, now=at(240)) is False
    notice.assert_not_called()
    assert (await settings.load(mongo_db, T)).level == "undoable_auto"


async def db_seen_now(db):
    await db.agents.update_one({"id": "a1"}, {"$set": {"lastSeen": datetime.now(timezone.utc).isoformat()}})


# ------------------------------------------------------------------ what the agent reports back

async def post(db, task_id, status, body=None):
    payload = {"task_id": task_id, "type": "restart_service", "action": "restart_service", "status": status,
               "result": copy.deepcopy(body or {"status": status})}
    with patch.object(agent_tasks_endpoints, "get_database", return_value=db):
        return await agent_tasks_endpoints.report_instruction_result("a1", payload, _tenant={"id": T})


RESTARTED = {"status": "success", "outcome": "restarted", "verify": {"ok": True, "check": "service_running"},
             "healthy_after": 4}
NOT_RUNNING = {"status": "success", "outcome": "not_running", "verify": {"ok": False, "check": "service_running"}}


async def test_a_restart_the_agent_confirms_reads_restarted_with_how_long_it_took_and_has_no_undo(mongo_db):
    await _world(mongo_db)
    await tick(mongo_db, 0)
    (row,) = await rows(mongo_db)
    (doc,) = [d async for d in mongo_db.agent_instructions.find({"tenantId": T}, {"_id": 0})]
    await post(mongo_db, doc["id"], "accepted")
    await post(mongo_db, doc["id"], "success", RESTARTED)
    await reconciler.tick(mongo_db, now=at(30))
    done = await ledger.get(mongo_db, T, row["id"])
    assert done["state"] == "verified" and done["result"]["healthy_after"] == 4        # copied from the agent's body
    extras = response_views.row_extras(done, can_act=True, now=at(30))
    assert extras["resultText"] == "Restarted nginx. Healthy again after 4 s. Restart 1 of 3 this hour."
    assert extras["canUndo"] is False and done["undo"]["available"] is False


async def test_a_late_accepted_never_overwrites_the_final_answer(mongo_db):
    await _world(mongo_db)
    await tick(mongo_db, 0)
    (doc,) = [d async for d in mongo_db.agent_instructions.find({"tenantId": T}, {"_id": 0})]
    await post(mongo_db, doc["id"], "accepted")
    assert (await mongo_db.agent_instructions.find_one({"id": doc["id"]}))["status"] == "ACCEPTED"
    await post(mongo_db, doc["id"], "success", RESTARTED)
    await post(mongo_db, doc["id"], "accepted")                                # arrives late
    stored = await mongo_db.agent_instructions.find_one({"id": doc["id"]})
    assert stored["status"] == "SUCCESS" and stored["result"]["healthy_after"] == 4
    await post(mongo_db, doc["id"], "error", {"status": "error", "error": "gone"})
    await post(mongo_db, doc["id"], "accepted")
    assert (await mongo_db.agent_instructions.find_one({"id": doc["id"]}))["status"] == "FAILURE"


async def test_a_service_that_did_not_come_back_fails_the_verify_and_the_next_try_waits_a_minute(mongo_db):
    await _world(mongo_db)
    await tick(mongo_db, 0)
    (row,) = await rows(mongo_db)
    (doc,) = [d async for d in mongo_db.agent_instructions.find({"tenantId": T}, {"_id": 0})]
    await post(mongo_db, doc["id"], "success", NOT_RUNNING)
    await reconciler.tick(mongo_db, now=at(5))
    failed = await ledger.get(mongo_db, T, row["id"])
    assert failed["state"] == "failed" and failed["reasonCode"] == "verify_failed"
    await tick(mongo_db, 59)
    assert len(await rows(mongo_db)) == 1
    await tick(mongo_db, 60)
    assert len(await rows(mongo_db)) == 2


# ------------------------------------------------------------------ the list reaches the agent (Task 2)

async def _tenant_with(db, caps, names=("nginx",)):
    await db.tenants.replace_one({"id": T}, {"id": T, "name": "Acme", "agentCapabilities": caps,
                                             "license": {"maxAgents": 5, "seatsUsed": 1, "inactiveReclaimDays": 30}},
                                 upsert=True)
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"response": {"watchedServices": list(names)}}},
                                          upsert=True)


async def test_the_reply_carries_the_list_only_for_a_tenant_with_remediation_executor(mongo_db):
    await _tenant_with(mongo_db, ["remediation_executor"])
    ticked = frozenset({"remediation_executor", "agent_update"})
    assert await response_settings.heartbeat_reply(mongo_db, T, "a1", ticked) == {"watchedServices": ["nginx"]}
    assert await response_settings.heartbeat_reply(mongo_db, T, "a1", frozenset({"agent_update"})) == {}
    await mongo_db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"response.watchedServices": []}})
    assert await response_settings.heartbeat_reply(mongo_db, T, "a1", ticked) == {"watchedServices": []}   # empty stops all checks
    assert await response_settings.heartbeat_reply(mongo_db, None, "a1", ticked) == {}


async def test_a_failed_settings_read_leaves_the_key_out_and_never_raises(mongo_db, caplog):
    broken = MagicMock()
    broken.autonomy_settings.find_one.side_effect = RuntimeError("database down")
    ticked = frozenset({"remediation_executor"})
    with caplog.at_level("WARNING"):
        assert await response_settings.heartbeat_reply(broken, T, "a1", ticked) == {}
    assert "database down" in caplog.text
    await _tenant_with(mongo_db, ["remediation_executor"])
    await mongo_db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"response.watchedServices": "nginx"}})
    assert await response_settings.heartbeat_reply(mongo_db, T, "a1", ticked) == {}       # malformed: not an empty list


def test_failure_data_is_dropped_for_a_tenant_without_the_tick_and_response_actions_stays():
    assert agent_capabilities._DATA_KEYS["service_failures"] == "remediation_executor"
    for permitted, kept in ((frozenset({"fim"}), False), (frozenset({"fim", "remediation_executor"}), True)):
        payload = {"meta": {"service_failures": [{"name": "nginx"}], "response_actions": {"tokens": ["restart_service"]}}}
        dropped = agent_capabilities.strip_heartbeat(payload, permitted)
        assert ("service_failures" in payload["meta"]) is kept and "response_actions" in payload["meta"]
        assert dropped == ([] if kept else ["remediation_executor"])


def _request(path):
    return Request({"type": "http", "method": "POST", "path": path, "headers": [], "client": ("203.0.113.7", 5555)})


async def _heartbeat(db):
    import agent_heartbeat_endpoints as hb
    await db.agents.update_one({"id": "a1"}, {"$set": {"meta": {}}})
    payload = {"hostname": "pc1", "platform": "Linux", "version": "2.1.16", "ipAddress": "10.0.0.5",
               "meta": {"service_failures": [{"name": "nginx", "failure_id": "nginx-1", "since": 1, "state": "failed"}],
                        "response_actions": {"v": 1, "tokens": ["restart_service"]}}}
    tenant = await db.tenants.find_one({"id": T})
    with patch.object(hb, "get_database", return_value=db), patch.object(hb.agent_limiter, "enabled", False):
        return await hb.report_heartbeat(_request("/api/agents/a1/heartbeat"), Response(), "a1", MagicMock(), payload, tenant)


@pytest.mark.real_agent_capabilities
async def test_the_heartbeat_route_replies_with_the_list_and_stores_the_failures_for_a_ticked_tenant(mongo_db):
    await mongo_db.agents.insert_one({"id": "a1", "tenantId": T, "hostname": "pc1", "status": "Online"})
    await _tenant_with(mongo_db, ["remediation_executor"])
    body = await _heartbeat(mongo_db)
    assert body["watchedServices"] == ["nginx"] and body["success"] is True
    assert {"uninstall_protection", "enabledCapabilities"} <= set(body)
    assert body["enabledCapabilities"] == ["agent_update", "remediation_executor"]
    stored = await mongo_db.agents.find_one({"id": "a1"})
    assert stored["meta"]["service_failures"][0]["name"] == "nginx" and "response_actions" in stored["meta"]


@pytest.mark.real_agent_capabilities
async def test_the_heartbeat_route_neither_sends_nor_stores_failures_for_an_unticked_tenant(mongo_db):
    await mongo_db.agents.insert_one({"id": "a1", "tenantId": T, "hostname": "pc1", "status": "Online"})
    await _tenant_with(mongo_db, ["fim"])
    body = await _heartbeat(mongo_db)
    assert "watchedServices" not in body and {"success", "uninstall_protection", "enabledCapabilities"} <= set(body)
    stored = await mongo_db.agents.find_one({"id": "a1"})
    assert "service_failures" not in stored["meta"] and "response_actions" in stored["meta"]
