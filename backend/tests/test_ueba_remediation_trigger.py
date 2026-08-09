"""Tests for the UEBA -> autonomous_remediation_service.remediate() containment
trigger (AUT-03, D-02/D-04) — the FIRST production caller of the Phase 53
remediation engine.

Proves:
  - shadow_ai_detected + a real agent_id + a resolved tenant -> exactly one
    fire-and-forget, deduped call to remediate() (Task 2).
  - is_duplicate_task(...) is called BEFORE remediate() and a duplicate
    short-circuits dispatch (Pitfall 2 / T-55-07).
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
"""
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import ueba_service
from autonomous_remediation_service import AutonomousRemediationService, RemediationFinding

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
    """Unit-level coverage of the background-task body: dedup ordering,
    finding shape, and duplicate short-circuiting."""

    async def test_dedup_checked_before_remediate(self):
        order = []

        async def _dup(*a, **k):
            order.append("is_duplicate_task")
            return False

        async def _remediate(self, finding):
            order.append("remediate")
            return {"status": "dry_run"}

        with patch(
            "response_orchestrator.ResponseOrchestrator.is_duplicate_task",
            new=AsyncMock(side_effect=_dup),
        ), patch(
            "autonomous_remediation_service.AutonomousRemediationService.remediate",
            new=_remediate,
        ):
            await ueba_service._dispatch_anomaly_remediation(
                "t1", "agent-1", "api.openai.com", "shadow_ai_detected", 100,
            )

        assert order == ["is_duplicate_task", "remediate"]

    async def test_duplicate_skips_remediate(self):
        with patch(
            "response_orchestrator.ResponseOrchestrator.is_duplicate_task",
            new=AsyncMock(return_value=True),
        ), patch(
            "autonomous_remediation_service.AutonomousRemediationService.remediate",
            new=AsyncMock(),
        ) as mock_remediate:
            await ueba_service._dispatch_anomaly_remediation(
                "t1", "agent-1", "api.openai.com", "shadow_ai_detected", 100,
            )
        mock_remediate.assert_not_called()

    async def test_builds_anomaly_finding_and_calls_remediate_once(self):
        with patch(
            "response_orchestrator.ResponseOrchestrator.is_duplicate_task",
            new=AsyncMock(return_value=False),
        ), patch(
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
        src = inspect.getsource(ueba_service)
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
    pending_approval — never auto-dispatched — for a destructive playbook,
    with NO confidence/severity-based shortcut around Phase 53's approval
    gate, even at max risk_score. is_destructive is computed purely from
    the PLAYBOOK's steps (kill_process.yaml: destructive: true), never from
    finding.severity/risk_score — this test proves the anomaly branch adds
    no such shortcut (D-04 / T-55-06)."""

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

        with patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False), \
             patch("response_orchestrator.ResponseOrchestrator.is_duplicate_task", new=AsyncMock(return_value=False)):
            svc = AutonomousRemediationService()
            result = await svc.remediate(finding)

        assert result["status"] == "pending_approval"
        db.remediation_requests.insert_one.assert_called_once()
        db.agent_instructions.insert_one.assert_not_called()
