"""Tests for the UEBA -> autonomous_remediation_service.remediate() containment
trigger (AUT-03, D-02/D-04) — the FIRST production caller of the Phase 53
remediation engine.

Proves:
  - shadow_ai_detected + a real agent_id + a resolved tenant -> exactly one
    fire-and-forget call to remediate() (Task 2).
  - Phase 81 WR-07: the anomaly's finding id is stable per agent and rule, so the
    gate's own open-row dedupe holds a repeated anomaly to one card (Pitfall 2 /
    T-55-07); the old response_tasks lookup, which nothing ever matched, is gone.
  - a missing agent_id, a missing tenant, or a non-shadow-AI rule never
    reaches remediate() (fail-closed, T-55-09).
  - the dispatch is scheduled via background_tasks.add_task — never awaited
    inline in the request handler (T-55-08).
  - the pre-existing _AUTO_BAN_RULES block is untouched (Pitfall 4 — out of
    scope, deliberately unmodified).
  - the anomaly-triggered destructive containment path lands in
    pending_approval with NO confidence/severity-based bypass, even at max
    risk_score — the identical approval gate as every other finding_type
    (D-04, T-55-06).
  - Phase 81 (81-08): remediate() is decided by the autonomy gate before
    anything else is written. At shipped defaults an eligible tenant's
    shadow-AI anomaly produces one simulation row and nothing is dispatched;
    an unticked tenant produces nothing; the GATE-04 split holds on the
    vendored path (block_ip automatic, kill_process an approval card).
"""
import inspect
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import ueba_service
from autonomous_ops import ledger, protected
from autonomous_remediation_service import AutonomousRemediationService, RemediationFinding
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import permissive_gate, seed_agent, seed_tenant

# asyncio_mode = auto (pytest.ini) — async tests below need no explicit mark.


def _mock_db(agent_tenant="tenant-9"):
    db = MagicMock()
    db.shadow_ai_events.insert_one = AsyncMock()
    db.agents.find_one = AsyncMock(
        return_value={"tenantId": agent_tenant} if agent_tenant else None
    )
    return db


def _shadow_event(agent_id="agent-1", process="python.exe", remote_host="api.openai.com"):
    return ueba_service.ShadowAIEvent(
        agent_id=agent_id,
        process=process,
        remote_ip="1.2.3.4",
        remote_host=remote_host,
        timestamp="2026-08-03T00:00:00Z",
    )


class TestDispatchEligibility:
    """Unit-level coverage of the fail-closed eligibility gate."""

    def test_shadow_ai_with_agent_and_tenant_is_eligible(self):
        bg = MagicMock()
        dispatched = ueba_service._dispatch_anomaly_containment_if_eligible(
            bg, tenant_id="t1", agent_id="agent-1", resource_id="api.openai.com",
            anomaly_rule="shadow_ai_detected", risk_score=100,
        )
        assert dispatched is True
        bg.add_task.assert_called_once()
        assert bg.add_task.call_args.args[0] is ueba_service._dispatch_anomaly_remediation

    def test_missing_agent_id_not_eligible(self):
        bg = MagicMock()
        dispatched = ueba_service._dispatch_anomaly_containment_if_eligible(
            bg, tenant_id="t1", agent_id=None, resource_id="x", anomaly_rule="shadow_ai_detected",
        )
        assert dispatched is False
        bg.add_task.assert_not_called()

    def test_missing_tenant_not_eligible(self):
        bg = MagicMock()
        dispatched = ueba_service._dispatch_anomaly_containment_if_eligible(
            bg, tenant_id=None, agent_id="agent-1", resource_id="x", anomaly_rule="shadow_ai_detected",
        )
        assert dispatched is False
        bg.add_task.assert_not_called()

    def test_non_shadow_ai_rule_not_eligible(self):
        bg = MagicMock()
        dispatched = ueba_service._dispatch_anomaly_containment_if_eligible(
            bg, tenant_id="t1", agent_id="agent-1", resource_id="x", anomaly_rule="brute_force",
        )
        assert dispatched is False
        bg.add_task.assert_not_called()


class TestReportShadowAiCallSite:
    """Integration coverage of the actual endpoint call site."""

    async def test_report_shadow_ai_schedules_containment_fire_and_forget(self):
        db = _mock_db(agent_tenant="tenant-9")
        bg = MagicMock()  # add_task only RECORDS the callable — never executes it inline
        event = _shadow_event()

        result = await ueba_service.report_shadow_ai(event, bg, db)

        assert result == {"status": "recorded"}
        db.agents.find_one.assert_awaited_once_with({"id": "agent-1"}, {"tenantId": 1})
        scheduled = [c.args[0] for c in bg.add_task.call_args_list]
        # the pre-existing alert-persist task AND the new containment dispatch
        assert ueba_service._persist_alert in scheduled
        assert ueba_service._dispatch_anomaly_remediation in scheduled
        # the handler returned above WITHOUT the scheduled callables ever
        # running — bg is a bare MagicMock, so remediate() was never
        # invoked inline in the request/response cycle (T-55-08)

    async def test_report_shadow_ai_no_tenant_resolved_skips_dispatch(self):
        db = _mock_db(agent_tenant=None)
        bg = MagicMock()
        event = _shadow_event()

        await ueba_service.report_shadow_ai(event, bg, db)

        scheduled = [c.args[0] for c in bg.add_task.call_args_list]
        assert ueba_service._dispatch_anomaly_remediation not in scheduled


class TestDispatchAnomalyRemediation:
    """Unit-level coverage of the background-task body: the finding shape, a stable finding id
    (WR-07) and no response_tasks lookup that nothing writes."""

    async def test_no_response_task_lookup_runs_before_remediate(self):
        with patch(
            "response_orchestrator.ResponseOrchestrator.is_duplicate_task", new=AsyncMock(return_value=True),
        ) as dup, patch(
            "autonomous_remediation_service.AutonomousRemediationService.remediate",
            new=AsyncMock(return_value={"status": "shadow"}),
        ) as mock_remediate:
            await ueba_service._dispatch_anomaly_remediation(
                "t1", "agent-1", "api.openai.com", "shadow_ai_detected", 100,
            )
        dup.assert_not_called()
        mock_remediate.assert_awaited_once()

    async def test_the_finding_id_is_stable_per_agent_and_rule(self):
        ticks = iter([datetime(2026, 8, 3, 0, 0, 0, tzinfo=timezone.utc), datetime(2026, 8, 3, 0, 0, 7, tzinfo=timezone.utc)])

        class _Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return next(ticks)

        with patch.object(ueba_service, "datetime", _Clock), patch(
            "autonomous_remediation_service.AutonomousRemediationService.remediate",
            new=AsyncMock(return_value={"status": "shadow"}),
        ) as mock_remediate:
            for _ in range(2):
                await ueba_service._dispatch_anomaly_remediation(
                    "t1", "agent-1", "api.openai.com", "shadow_ai_detected", 100,
                )
        ids = [c.args[0].finding_id for c in mock_remediate.call_args_list]
        assert ids == ["UEBA-agent-1-shadow_ai_detected"] * 2

    async def test_builds_anomaly_finding_and_calls_remediate_once(self):
        with patch(
            "autonomous_remediation_service.AutonomousRemediationService.remediate",
            new=AsyncMock(return_value={"status": "dry_run"}),
        ) as mock_remediate:
            await ueba_service._dispatch_anomaly_remediation(
                "t1", "agent-1", "api.openai.com", "shadow_ai_detected", 95,
            )

        mock_remediate.assert_awaited_once()
        finding = mock_remediate.call_args.args[0]
        assert finding.finding_type == "anomaly"
        assert finding.details["anomaly_rule"] == "shadow_ai_detected"
        assert finding.agent_id == "agent-1"
        assert finding.tenant_id == "t1"
        assert finding.severity == "critical"


class TestAutoBanUntouched:
    """Pitfall 4: the pre-existing UEBA auto-ban block is out of this
    phase's scope and must remain byte-for-byte unmodified."""

    def test_auto_ban_block_still_present_and_unmodified(self):
        # analyze_login (and its auto-ban block) lives in ueba_analysis.py
        # since the CLAUDE.md 500-line-cap split of ueba_service.py — follow
        # it to its actual defining module rather than the re-exporting one.
        import ueba_analysis
        src = inspect.getsource(ueba_analysis)
        assert '_AUTO_BAN_RULES = {"brute_force", "known_malicious_ip"}' in src
        assert 'if risk_score >= 80 and _AUTO_BAN_RULES.intersection(triggered_rules):' in src


def _remediation_mock_db():
    """Mirrors test_remediation_guards.py's _mock_db() so remediate() can
    run its real select_playbook() -> kill_process path end-to-end."""
    db = MagicMock()
    db.remediation_audit.insert_one = AsyncMock(return_value=MagicMock(inserted_id="aud-1"))
    db.remediation_playbooks.find_one = AsyncMock(return_value={"name": "already-seeded"})
    db.remediation_playbooks.find.return_value.to_list = AsyncMock(
        return_value=[
            dict(p, id=f"vendored-{p['name']}")
            for p in __import__("remediation_playbook_service").load_default_playbooks()
        ]
    )
    db.remediation_playbooks.insert_one = AsyncMock()
    db.remediation_requests.insert_one = AsyncMock()
    db.remediation_requests.update_one = AsyncMock()
    db.remediation_inflight.count_documents = AsyncMock(return_value=0)
    db.remediation_inflight.insert_one = AsyncMock()
    db.remediation_inflight.delete_one = AsyncMock()
    db.alerts.insert_one = AsyncMock()
    db.agent_instructions.insert_one = AsyncMock()
    db.agent_instructions.find_one = AsyncMock(return_value={"status": "SUCCESS"})
    return db


class TestNoApprovalGateBypass:
    """Task 3 (AUT-03, D-04): the anomaly containment path must land in
    pending_approval — never auto-dispatched — for an approval-class playbook,
    with NO confidence/severity-based shortcut around the approval gate, even
    at max risk_score. The class comes from the registry (kill_process is an
    approval action), never from finding.severity/risk_score — this test proves
    the anomaly branch adds no such shortcut (D-04 / T-55-06). The gate is
    patched to decide needs_approval (what the registry says for kill_process;
    the real-database class below proves the real decision)."""

    async def test_max_risk_score_anomaly_still_pends_approval(self):
        db = _remediation_mock_db()
        finding = RemediationFinding(
            finding_id="UEBA-agent-1-shadow_ai_detected-20260803000000",
            finding_type="anomaly",
            severity="critical",  # max severity — must NOT bypass the gate
            tenant_id="t1",
            agent_id="agent-1",
            resource_id="python.exe",
            details={"anomaly_rule": "shadow_ai_detected", "risk_score": 100},
        )

        with permissive_gate(outcome="needs_approval") as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "false"}), \
             patch("response_orchestrator.ResponseOrchestrator.is_duplicate_task", new=AsyncMock(return_value=False)):
            svc = AutonomousRemediationService()
            result = await svc.remediate(finding)

        assert result["status"] == "pending_approval"
        db.remediation_requests.insert_one.assert_called_once()
        inserted = db.remediation_requests.insert_one.call_args.args[0]
        assert inserted["status"] == "pending_approval"
        assert inserted["autonomyActionId"] in stack.ledger.rows
        db.agent_instructions.insert_one.assert_not_called()


@pytest.fixture
async def live(mongo_db):  # noqa: F811
    """A real throwaway database with an eligible tenant t1 (shadow ON, the shipped default),
    its agent a1, and a ledger with its indexes. The service reads this database."""
    protected.cache_clear()
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1")
    await seed_agent(mongo_db, "t1", "a1")
    with patch("autonomous_remediation_service.get_database", return_value=mongo_db), \
         patch("soc_integration_service.push_ocsf_event", new=AsyncMock()), \
         patch("response_orchestrator.ResponseOrchestrator.is_duplicate_task", new=AsyncMock(return_value=False)):
        yield mongo_db


def _anomaly(tenant="t1", agent="a1"):
    return RemediationFinding(
        finding_id=f"UEBA-{agent}-shadow_ai_detected-20260803000000", finding_type="anomaly",
        severity="critical", tenant_id=tenant, agent_id=agent, resource_id="python.exe",
        details={"anomaly_rule": "shadow_ai_detected", "risk_score": 100})


def _ip_finding():
    return RemediationFinding(
        finding_id="scan-1", finding_type="nscan", severity="critical", tenant_id="t1", agent_id="a1",
        resource_id="203.0.113.7", details={"type": "ip", "verdict": "Malicious", "ts": "2026-08-01T00:00:00Z"})


class TestGatedAtShippedDefaults:
    """GATE-03: the one live automatic caller (ueba_service._dispatch_anomaly_remediation,
    unchanged) is decided by the gate."""

    async def test_tracer_shadow_ai_anomaly_is_a_simulation_and_nothing_is_dispatched(self, live):
        with patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "true"}):
            await ueba_service._dispatch_anomaly_remediation("t1", "a1", "api.openai.com", "shadow_ai_detected", 100)

        rows = [r async for r in live.autonomy_actions.find({"tenantId": "t1"})]
        assert len(rows) == 1
        row = rows[0]
        assert row["state"] == "shadow" and row["origin"] == "ueba" and row["dispatcher"] == "remediation"
        assert row["wouldHave"] == "needs_approval"          # kill_process is an approval-class action
        assert row["command"] == "kill_process" and row["targets"] == ["a1"]
        assert await live.agent_instructions.count_documents({}) == 0
        assert await live.remediation_requests.count_documents({}) == 0
        stages = [a["stage"] async for a in live.remediation_audit.find({"tenantId": "t1"})]
        assert "selected" in stages and "shadow" in stages

    async def test_remediate_reports_shadow_with_the_ledger_id(self, live):
        with patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "true"}):
            result = await AutonomousRemediationService().remediate(_anomaly())
        row = await live.autonomy_actions.find_one({"tenantId": "t1"})
        assert result["status"] == "shadow" and result["autonomy_action_id"] == row["id"]
        assert row["remediationId"] == result["remediation_id"]

    async def test_tenant_shadow_flag_alone_also_simulates(self, live):
        await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": True}})
        with patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "false"}):
            result = await AutonomousRemediationService().remediate(_ip_finding())
        assert result["status"] == "shadow"
        assert await live.agent_instructions.count_documents({}) == 0

    async def test_unticked_tenant_gets_nothing_recorded(self, live):
        await seed_tenant(live, "t2", ticked=False)
        await seed_agent(live, "t2", "a2")
        with patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "true"}):
            result = await AutonomousRemediationService().remediate(_anomaly("t2", "a2"))
        assert result["status"] == "refused" and result["reason"] == "not_enabled"
        assert await live.autonomy_actions.count_documents({"tenantId": "t2"}) == 0
        assert await live.remediation_requests.count_documents({}) == 0
        assert await live.agent_instructions.count_documents({}) == 0

    async def test_a_repeated_anomaly_seconds_later_keeps_one_card(self, live):
        """protects=WR-07; fails_when=each event (a new second) opens its own kill_process card."""
        await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": False}})
        ticks = iter(datetime(2026, 8, 3, 0, 0, s, tzinfo=timezone.utc) for s in range(0, 60, 3))

        class _Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return next(ticks)

        with patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "false"}), \
             patch.object(ueba_service, "datetime", _Clock):
            for _ in range(3):
                await ueba_service._dispatch_anomaly_remediation("t1", "a1", "api.openai.com", "shadow_ai_detected", 100)
        rows = [r async for r in live.autonomy_actions.find({"tenantId": "t1"})]
        assert [(r["state"], r["command"]) for r in rows] == [("awaiting_approval", "kill_process")]
        assert await live.remediation_requests.count_documents({}) == 1
        assert await live.agent_instructions.count_documents({}) == 0

    async def test_a_finding_with_no_host_is_refused_not_dispatched(self, live):
        await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": False}})
        finding = RemediationFinding(
            finding_id="scan-2", finding_type="nscan", severity="critical", tenant_id="t1", agent_id=None,
            resource_id="203.0.113.8", details={"type": "ip", "verdict": "Malicious"})
        with patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "false"}):
            result = await AutonomousRemediationService().remediate(finding)
        assert result["status"] == "refused" and result["reason"] == "no_target"
        assert await live.agent_instructions.count_documents({}) == 0


class TestGate04SplitOnTheVendoredPath:
    """GATE-04 locked split: the shipped block_ip playbook (its step carries destructive true,
    no gate_class) is decided by the registry class auto; kill_process is an approval card."""

    async def test_block_ip_playbook_is_dispatched_without_a_card(self, live):
        await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": False}})
        seen = AsyncMock(return_value={"status": "dispatching"})
        with patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "false"}), \
             patch.object(AutonomousRemediationService, "_dispatch_and_verify", new=seen):
            result = await AutonomousRemediationService().remediate(_ip_finding())

        assert result["status"] == "dispatching"
        row = await live.autonomy_actions.find_one({"tenantId": "t1"})
        assert row["state"] == "dispatching" and row["autoDispatched"] is True
        assert row["command"] == "block_ip" and row["params"] == {"ip_address": "203.0.113.7"}
        req = await live.remediation_requests.find_one({"tenantId": "t1"})
        assert req["status"] == "dispatching" and req["autonomyActionId"] == row["id"]
        assert req["id"] == row["remediationId"]
        seen.assert_awaited_once()
        assert seen.await_args.kwargs.get("action_id") == row["id"]
        assert await live.agent_instructions.count_documents({}) == 0     # the stub dispatched nothing

    async def test_kill_process_playbook_still_needs_a_card(self, live):
        await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": False}})
        with patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "false"}):
            result = await AutonomousRemediationService().remediate(_anomaly())

        assert result["status"] == "pending_approval"
        row = await live.autonomy_actions.find_one({"tenantId": "t1"})
        assert row["state"] == "awaiting_approval" and row["reasonCode"] == "class_approve"
        req = await live.remediation_requests.find_one({"tenantId": "t1"})
        assert req["status"] == "pending_approval" and req["autonomyActionId"] == row["id"]
        assert req["id"] == row["remediationId"] == result["remediation_id"]
        assert await live.agent_instructions.count_documents({}) == 0
