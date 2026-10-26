"""XDR / playbook fence (Phase 81, plan 81-06). Real MongoDB (skips without one) through the
throwaway database of tests/_mongo_test_db.py; no model call, nothing touches the live database.

Value: protects=GATE-03 / GATE-05 / D-21: an XDR auto-playbook step that would contain a host
(block_ip, isolate_endpoint, quarantine_file, rollback_ransomware) is a gate decision, so at
shipped defaults it is a simulation, an approve-class step becomes an approval card, and a
response task is written only for an allowed automatic action and carries the autonomy stamp;
the AI and rule-based playbook selectors only record suggestions; the 0.90 confidence
auto-approve is gone; a human-started run is unchanged;
fails_when=an automatic executor queues an unstamped response task, a selector runs a playbook,
confidence 0.99 skips the approval requirement, an unticked tenant leaves a row, or a manual
run changes shape;
no_claim=the grandfathered correlation writers (threat hunt, kill-chain pre-staging) and the
approval/dispatch of a card, which 81-04 and 81-08 cover.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger
from correlation_engine_threat import CorrelationEngineThreatMixin
from enhanced_playbook_engine import PlaybookExecutionEngine
from playbook_engine_actions import AUTOMATIC_EXECUTORS
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_tenant

IP = "198.51.100.9"
MASTER_ENV = "AUTONOMOUS_REMEDIATION_DRY_RUN"


@pytest.fixture(autouse=True)
def _default_master(monkeypatch):
    monkeypatch.delenv(MASTER_ENV, raising=False)  # unset = shadow on


def _context(executed_by, tenant_id="t1", trigger=None, execution_id="EX-1"):
    return {"variables": {"trigger": trigger if trigger is not None else {"source_ip": IP, "agent_id": "a1"}},
            "execution_id": execution_id, "tenant_id": tenant_id, "executed_by": executed_by}


async def _setup(db, *, shadow=True, tenant="t1", agent="a1", ip="10.1.1.5"):
    await ledger.ensure_indexes(db)
    await seed_tenant(db, tenant, shadow=shadow)
    await seed_agent(db, tenant, agent, hostname=f"h-{agent}", ip=ip)


async def _rows(db, tenant="t1"):
    return await db.autonomy_actions.find({"tenantId": tenant}).to_list(50)


def test_automatic_executors_are_the_three_machine_origins():
    assert AUTOMATIC_EXECUTORS == frozenset({"xdr-auto", "ai-selector", "fallback-selector"})


async def test_tracer_xdr_block_ip_at_defaults_is_a_simulation(mongo_db):
    """Tracer. protects=D-21: shadow on -> one shadow row, zero response tasks."""
    await _setup(mongo_db)
    engine = PlaybookExecutionEngine(mongo_db)

    out = await engine._action_block_ip({}, _context("xdr-auto"))

    assert await mongo_db.response_tasks.count_documents({}) == 0
    rows = await _rows(mongo_db)
    assert len(rows) == 1
    assert (rows[0]["state"], rows[0]["origin"], rows[0]["dispatcher"]) == ("shadow", "xdr-auto", "response_task")
    assert rows[0]["wouldHave"] == "allow_auto" and rows[0]["targets"] == ["a1"]
    assert "nothing was done" in out.lower()


async def test_xdr_block_ip_with_shadow_off_writes_one_stamped_task(monkeypatch, mongo_db):
    monkeypatch.setenv(MASTER_ENV, "false")
    await _setup(mongo_db, shadow=False)
    engine = PlaybookExecutionEngine(mongo_db)

    out = await engine._action_block_ip({}, _context("xdr-auto", execution_id="EX-7"))

    tasks = await mongo_db.response_tasks.find({}).to_list(10)
    assert len(tasks) == 1
    task = tasks[0]
    row = (await _rows(mongo_db))[0]
    assert (task["action"], task["params"]["ip"], task["status"], task["tenantId"]) == ("block_ip", IP, "queued", "t1")
    assert task["agent_id"] == "a1" and task["triggered_by"] == "autonomous_ops"
    assert task["autonomy"]["actionId"] == row["id"] and task["playbook_execution_id"] == "EX-7"
    assert row["state"] == "dispatching" and row["autoDispatched"] is True
    assert task["task_id"] in out


@pytest.mark.parametrize("name,method", [("isolate_host", "_action_isolate_endpoint"),
                                         ("rollback_ransomware", "_action_rollback_ransomware")])
async def test_isolate_and_rollback_from_an_automatic_executor_become_approval_cards(monkeypatch, mongo_db, name, method):
    monkeypatch.setenv(MASTER_ENV, "false")
    await _setup(mongo_db, shadow=False)
    engine = PlaybookExecutionEngine(mongo_db)

    async def _no_own_gate(*a, **k):  # the engine's own approval path must not be entered
        raise AssertionError("engine approval path entered")
    engine._gate_high_risk_action = _no_own_gate

    out = await getattr(engine, method)({}, _context("xdr-auto"))

    assert await mongo_db.response_tasks.count_documents({}) == 0
    rows = await _rows(mongo_db)
    assert len(rows) == 1
    assert (rows[0]["state"], rows[0]["command"], rows[0]["dispatcher"]) == ("awaiting_approval", name, "response_task")
    assert rows[0]["approval"]["requiredBy"] == "class_approve"
    assert "approval" in out.lower()


async def test_quarantine_file_from_an_automatic_executor_is_decided_by_the_gate(monkeypatch, mongo_db):
    monkeypatch.setenv(MASTER_ENV, "false")
    await _setup(mongo_db, shadow=False)
    engine = PlaybookExecutionEngine(mongo_db)
    trigger = {"agent_id": "a1", "process": {"path": "C:/tmp/bad.exe"}}

    await engine._action_quarantine_file({}, _context("xdr-auto", trigger=trigger))

    tasks = await mongo_db.response_tasks.find({}).to_list(10)
    assert [(t["action"], t["params"]["file_path"], t["triggered_by"]) for t in tasks] == \
        [("quarantine_file", "C:/tmp/bad.exe", "autonomous_ops")]


async def test_unticked_tenant_leaves_no_task_and_no_row(mongo_db):
    await _setup(mongo_db)
    await seed_tenant(mongo_db, "t2", ticked=False)
    await seed_agent(mongo_db, "t2", "a2", hostname="h2", ip="10.2.2.5")
    engine = PlaybookExecutionEngine(mongo_db)

    out = await engine._action_block_ip({}, _context("xdr-auto", tenant_id="t2",
                                                     trigger={"source_ip": IP, "agent_id": "a2"}))

    assert await mongo_db.response_tasks.count_documents({}) == 0
    assert await mongo_db.autonomy_actions.count_documents({}) == 0
    assert "not switched on" in out.lower() or "not enabled" in out.lower()


async def test_repeated_correlation_for_the_same_target_does_not_add_a_second_row(mongo_db):
    await _setup(mongo_db)
    engine = PlaybookExecutionEngine(mongo_db)

    await engine._action_block_ip({}, _context("xdr-auto", execution_id="EX-1"))
    out = await engine._action_block_ip({}, _context("xdr-auto", execution_id="EX-2"))

    assert len(await _rows(mongo_db)) == 1
    assert "already" in out.lower()


async def test_validation_errors_are_kept_for_automatic_executors(mongo_db):
    await _setup(mongo_db)
    engine = PlaybookExecutionEngine(mongo_db)
    with pytest.raises(ValueError, match="block_ip requires"):
        await engine._action_block_ip({}, _context("xdr-auto", trigger={}))
    with pytest.raises(ValueError, match="rollback_ransomware requires"):
        await engine._action_rollback_ransomware({}, _context("xdr-auto", trigger={}))


async def test_manual_block_ip_keeps_the_unstamped_task_shape(mongo_db):
    """Regression: a human-started run is untouched (T-81-27)."""
    await _setup(mongo_db)
    engine = PlaybookExecutionEngine(mongo_db)

    out = await engine._action_block_ip({}, _context("alice@example.com", execution_id="EX-9"))

    tasks = await mongo_db.response_tasks.find({}).to_list(10)
    assert len(tasks) == 1
    task = tasks[0]
    assert task["task_id"].startswith("PB-BLK-") and "autonomy" not in task and "triggered_by" not in task
    assert (task["action"], task["params"]["ip"], task["triggered_by_playbook"]) == ("block_ip", IP, "EX-9")
    assert await mongo_db.autonomy_actions.count_documents({}) == 0
    assert "queued" in out

    dup = await engine._action_block_ip({}, _context("alice@example.com", execution_id="EX-10"))
    assert "deduplicated" in dup and await mongo_db.response_tasks.count_documents({}) == 1


async def test_a_full_xdr_playbook_run_at_defaults_writes_no_response_task(mongo_db):
    """The path the correlation engine takes: execute_playbook with executed_by xdr-auto."""
    await _setup(mongo_db)
    await mongo_db.playbooks.insert_one({
        "_id": "pb-1", "name": "Block attacker", "tenant_id": "platform", "enabled": True,
        "steps": [{"name": "block", "type": "action", "action": "block_ip", "params": {}},
                  {"name": "note", "type": "action", "action": "log", "params": {"message": "done"}}]})
    engine = PlaybookExecutionEngine(mongo_db)

    result = await engine.execute_playbook("pb-1", {"source_ip": IP, "agent_id": "a1"}, "t1", "xdr-auto")

    assert result["status"] == "completed"
    assert await mongo_db.response_tasks.count_documents({}) == 0
    assert [r["state"] for r in await _rows(mongo_db)] == ["shadow"]


async def test_a_playbook_step_with_gate_class_approve_raises_block_ip_to_an_approval_card(monkeypatch, mongo_db):
    monkeypatch.setenv(MASTER_ENV, "false")
    await _setup(mongo_db, shadow=False)
    await mongo_db.playbooks.insert_one({
        "_id": "pb-2", "name": "Careful block", "tenant_id": "platform", "enabled": True,
        "steps": [{"name": "block", "type": "action", "action": "block_ip", "gate_class": "approve",
                   "params": {}}]})
    engine = PlaybookExecutionEngine(mongo_db)

    await engine.execute_playbook("pb-2", {"source_ip": IP, "agent_id": "a1"}, "t1", "xdr-auto")

    assert await mongo_db.response_tasks.count_documents({}) == 0
    rows = await _rows(mongo_db)
    assert [(r["state"], r["reasonCode"]) for r in rows] == [("awaiting_approval", "playbook_raised")]


# ------------------------------------------------------------------ selectors and the bypass


class _Engine(CorrelationEngineThreatMixin):
    def __init__(self, db):
        self.db = db


class _Analyzer:
    """Stands in for ai_service.IncidentAnalyzer: configured, answers with a fixed word."""
    answer = "block"
    is_configured = True

    async def initialize(self):
        return None

    async def generate_text(self, prompt, source=None):
        return self.answer


@pytest.fixture
def no_playbook_run(monkeypatch):
    """Any attempt to run a playbook from a selector fails the test."""
    calls = []

    async def boom(self, *a, **k):
        calls.append((a, k))
        raise AssertionError("a selector ran a playbook")
    monkeypatch.setattr(PlaybookExecutionEngine, "execute_playbook", boom)
    return calls


@pytest.fixture
def analyzer(monkeypatch):
    import ai_service
    monkeypatch.setattr(ai_service, "IncidentAnalyzer", _Analyzer)
    _Analyzer.answer = "block"
    return _Analyzer


CORRELATION = {"pattern_id": "p1", "pattern": "credential stuffing", "severity": "high", "type": "auth",
               "agent_id": "a1", "source_ip": IP, "confidence": 0.99}


async def test_ai_selector_records_a_suggestion_and_never_runs_the_playbook(mongo_db, analyzer, no_playbook_run):
    await _setup(mongo_db)
    await mongo_db.playbooks.insert_one({
        "_id": "pb-b", "name": "Block", "tenant_id": "platform", "enabled": True,
        "steps": [{"type": "action", "action": "send_notification", "params": {}},
                  {"type": "action", "action": "block_ip", "params": {}}]})

    await _Engine(mongo_db)._ai_select_playbook("t1", CORRELATION)

    assert no_playbook_run == []
    rows = await _rows(mongo_db)
    assert len(rows) == 1
    assert (rows[0]["origin"], rows[0]["state"], rows[0]["wouldHave"]) == ("ai-selector", "shadow", "suggest")
    assert (rows[0]["command"], rows[0]["targets"], rows[0]["dispatcher"]) == ("block_ip", ["a1"], "response_task")
    assert await mongo_db.response_tasks.count_documents({}) == 0
    assert await mongo_db.playbook_executions.count_documents({}) == 0


async def test_ai_selector_with_shadow_off_leaves_a_suggested_card_not_a_task(monkeypatch, mongo_db, analyzer,
                                                                             no_playbook_run):
    monkeypatch.setenv(MASTER_ENV, "false")
    await _setup(mongo_db, shadow=False)
    await mongo_db.playbooks.insert_one({
        "_id": "pb-b", "name": "Block", "tenant_id": "t1", "enabled": True,
        "steps": [{"type": "action", "action": "block_ip", "params": {}}]})

    await _Engine(mongo_db)._ai_select_playbook("t1", CORRELATION)

    rows = await _rows(mongo_db)
    assert [(r["origin"], r["state"]) for r in rows] == [("ai-selector", "suggested")]
    assert await mongo_db.response_tasks.count_documents({}) == 0 and no_playbook_run == []


async def test_fallback_selector_records_a_suggestion_for_an_isolate_step(monkeypatch, mongo_db, no_playbook_run):
    monkeypatch.setenv(MASTER_ENV, "false")
    await _setup(mongo_db, shadow=False)
    await mongo_db.playbooks.insert_one({
        "_id": "pb-i", "id": "pb-i", "name": "Isolate", "tenant_id": "t1", "enabled": True, "priority": 5,
        "steps": [{"type": "action", "action": "isolate_endpoint", "params": {}}]})

    await _Engine(mongo_db)._fallback_select_playbook("t1", CORRELATION)

    rows = await _rows(mongo_db)
    assert [(r["origin"], r["state"], r["command"]) for r in rows] == \
        [("fallback-selector", "suggested", "isolate_host")]
    assert await mongo_db.response_tasks.count_documents({}) == 0 and no_playbook_run == []


async def test_a_notification_only_playbook_records_nothing(mongo_db, analyzer, no_playbook_run):
    await _setup(mongo_db)
    await mongo_db.playbooks.insert_one({
        "_id": "pb-n", "id": "pb-n", "name": "Tell", "tenant_id": "t1", "enabled": True,
        "steps": [{"type": "action", "action": "send_notification", "params": {}}]})
    engine = _Engine(mongo_db)

    _Analyzer.answer = "notify"
    await engine._ai_select_playbook("t1", CORRELATION)
    await engine._fallback_select_playbook("t1", CORRELATION)

    assert await mongo_db.autonomy_actions.count_documents({}) == 0 and no_playbook_run == []


async def test_a_correlation_without_an_agent_records_nothing(mongo_db, analyzer, no_playbook_run):
    await _setup(mongo_db)
    await mongo_db.playbooks.insert_one({
        "_id": "pb-b", "name": "Block", "tenant_id": "t1", "enabled": True,
        "steps": [{"type": "action", "action": "block_ip", "params": {}}]})

    await _Engine(mongo_db)._ai_select_playbook("t1", {**CORRELATION, "agent_id": None})

    assert await mongo_db.autonomy_actions.count_documents({}) == 0


async def test_an_unticked_tenant_gets_no_suggestion_from_a_selector(mongo_db, analyzer, no_playbook_run):
    await _setup(mongo_db)
    await seed_tenant(mongo_db, "t2", ticked=False)
    await seed_agent(mongo_db, "t2", "a2", hostname="h2", ip="10.2.2.5")
    await mongo_db.playbooks.insert_one({
        "_id": "pb-b", "name": "Block", "tenant_id": "platform", "enabled": True,
        "steps": [{"type": "action", "action": "block_ip", "params": {}}]})

    await _Engine(mongo_db)._ai_select_playbook("t2", {**CORRELATION, "agent_id": "a2"})

    assert await mongo_db.autonomy_actions.count_documents({}) == 0


def test_selectors_contain_no_playbook_run_call():
    import ast
    tree = ast.parse(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "correlation_engine_threat.py")).read())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute_playbook"]
    assert calls == []


def test_the_confidence_auto_approve_is_gone():
    import backend_safety
    import playbook_engine_safety  # noqa: F401  (still imports)
    assert not hasattr(backend_safety, "AUTO_APPROVE_CONFIDENCE_THRESHOLD")
    for action in ("isolate_host", "rollback_ransomware"):
        risk = backend_safety.evaluate_action(action, confidence=0.99, auto_approved=True,
                                              asset_criticality=None, blast_radius=0)
        assert risk.allowed is True and risk.requires_approval is True
    safe = backend_safety.evaluate_action("block_ip", confidence=0.99, auto_approved=True,
                                          asset_criticality=None, blast_radius=0)
    assert safe.requires_approval is False
