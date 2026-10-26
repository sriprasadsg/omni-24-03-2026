"""TDD suite for the Phase 53-03 remediation loop: finding sources,
playbook selection + dispatch, grounded verify, and append-only audit.

Phase 81 (81-08): remediate() is decided by the autonomy gate and every step is written by
gate.execute, so these MagicMock-database tests run under ``permissive_gate`` (the gate decides
as the test asks, in an in-memory ledger). The real-database proofs are in
test_remediation_guards.py and test_autonomous_ops_structural.py.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import autonomous_remediation_service as service_module
from autonomous_remediation_service import AutonomousRemediationService, RemediationFinding
from tests.autonomy_support import permissive_gate

pytestmark = pytest.mark.asyncio


def _mock_db():
    db = MagicMock()
    db.security_scan_results.find.return_value.to_list = AsyncMock(return_value=[])
    db.vulnerabilities.find.return_value.to_list = AsyncMock(return_value=[])
    db.fim_events.find.return_value.to_list = AsyncMock(return_value=[])
    db.remediation_audit.insert_one = AsyncMock(return_value=MagicMock(inserted_id="aud-1"))
    # remediation_playbook_service.load_playbooks() seeds+reads real vendored
    # defaults through these two calls on every remediate() invocation.
    db.remediation_playbooks.find_one = AsyncMock(return_value={"name": "already-seeded"})
    db.remediation_playbooks.find.return_value.to_list = AsyncMock(
        return_value=[dict(p, id=f"vendored-{p['name']}") for p in __import__("remediation_playbook_service").load_default_playbooks()]
    )
    db.remediation_playbooks.insert_one = AsyncMock()
    db.remediation_requests.insert_one = AsyncMock()
    db.remediation_requests.update_one = AsyncMock()
    db.remediation_inflight.count_documents = AsyncMock(return_value=0)
    db.remediation_inflight.insert_one = AsyncMock()
    db.remediation_inflight.delete_one = AsyncMock()
    db.alerts.insert_one = AsyncMock()
    db.autonomy_actions.update_one = AsyncMock()      # gate.execute links the instruction to its row
    return db


@pytest.fixture(autouse=True)
def _no_real_sleep():
    with patch("autonomous_remediation_service.asyncio.sleep", new=AsyncMock(return_value=None)):
        yield


class TestFindingSources:
    async def test_malicious_scan_surfaces_as_nscan_finding(self):
        db = _mock_db()
        db.security_scan_results.find.return_value.to_list = AsyncMock(return_value=[
            {"agentId": "agent-1", "target": "/tmp/evil.exe", "type": "file", "verdict": "Malicious", "created_at": "2026-08-01T00:00:00Z", "tenantId": "t1"}
        ])
        with patch("autonomous_remediation_service.get_database", return_value=db):
            svc = AutonomousRemediationService()
            findings = await svc.scan_for_remediable_findings("t1")
        nscan = [f for f in findings if f.finding_type == "nscan"]
        assert len(nscan) == 1
        assert nscan[0].resource_id == "/tmp/evil.exe"
        assert nscan[0].agent_id == "agent-1"

    async def test_native_vuln_surfaces_as_vuln_finding(self):
        db = _mock_db()
        db.vulnerabilities.find.return_value.to_list = AsyncMock(return_value=[
            {"id": "vuln-1", "agentId": "agent-1", "assetId": "asset-1", "severity": "Critical",
             "cveId": "CVE-2024-0001", "package": "openssl", "status": "Open", "source": "agent", "tenantId": "t1"}
        ])
        with patch("autonomous_remediation_service.get_database", return_value=db):
            svc = AutonomousRemediationService()
            findings = await svc.scan_for_remediable_findings("t1")
        vuln = [f for f in findings if f.finding_type == "vuln"]
        assert len(vuln) == 1
        assert vuln[0].finding_id == "vuln-1"

    async def test_fim_drift_surfaces_as_fim_finding(self):
        db = _mock_db()
        db.fim_events.find.return_value.to_list = AsyncMock(return_value=[
            {"agent_id": "agent-1", "path": "/etc/passwd", "change_type": "Changed", "timestamp": "2026-08-01T00:00:00Z", "tenantId": "t1"}
        ])
        with patch("autonomous_remediation_service.get_database", return_value=db):
            svc = AutonomousRemediationService()
            findings = await svc.scan_for_remediable_findings("t1")
        fim = [f for f in findings if f.finding_type == "fim"]
        assert len(fim) == 1
        assert fim[0].resource_id == "/etc/passwd"


class TestRemediateLoop:
    def _finding(self, finding_type="vuln", **overrides):
        base = dict(
            finding_id="f-1", finding_type=finding_type, severity="critical",
            tenant_id="t1", agent_id="agent-1", resource_id="asset-1",
            details={"cveId": "CVE-2024-0001", "package": "openssl"},
        )
        base.update(overrides)
        return RemediationFinding(**base)

    async def test_remediate_dispatches_steps_via_agent_instructions(self):
        db = _mock_db()
        db.agent_instructions.insert_one = AsyncMock()
        db.agent_instructions.find_one = AsyncMock(return_value={"status": "SUCCESS"})
        db.vulnerabilities.find_one = AsyncMock(return_value={"id": "f-1", "status": "Patched"})

        with permissive_gate("allow_auto") as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False), \
             patch("response_orchestrator.ResponseOrchestrator.is_duplicate_task", new=AsyncMock(return_value=False)):
            svc = AutonomousRemediationService()
            result = await svc.remediate(self._finding())

        assert db.agent_instructions.insert_one.called
        assert result["status"] == "resolved"
        # Every step is a stamped registry command written by gate.execute (GATE-05).
        written = [c.args[0] for c in db.agent_instructions.insert_one.call_args_list]
        assert written and all(d["triggered_by"] == "autonomous_ops" for d in written)
        assert all(d["autonomy"]["kind"] == "action" for d in written)
        assert all("script" not in d["payload"] and "script" not in d["parameters"] for d in written)
        # The ledger row follows the audit points: executed, then verified.
        (row,) = stack.ledger.rows.values()
        assert row["state"] == "verified"

    async def test_verify_still_present_returns_failed(self):
        db = _mock_db()
        db.agent_instructions.insert_one = AsyncMock()
        db.agent_instructions.find_one = AsyncMock(return_value={"status": "SUCCESS"})
        db.vulnerabilities.find_one = AsyncMock(return_value={"id": "f-1", "status": "Open"})

        with permissive_gate("allow_auto") as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False), \
             patch("response_orchestrator.ResponseOrchestrator.is_duplicate_task", new=AsyncMock(return_value=False)):
            svc = AutonomousRemediationService()
            result = await svc.remediate(self._finding())

        assert result["status"] == "failed"
        (row,) = stack.ledger.rows.values()
        assert row["state"] in ("failed", "rolled_back")      # patch_package has a rollback or escalates

    async def test_verify_timeout_returns_unverified_never_resolved(self):
        db = _mock_db()
        db.agent_instructions.insert_one = AsyncMock()
        db.agent_instructions.find_one = AsyncMock(return_value={"status": "SUCCESS"})
        # vulnerabilities.find_one never reflects a resolved state -> verify times out
        db.vulnerabilities.find_one = AsyncMock(return_value={"id": "f-1", "status": "Open"})

        with permissive_gate("allow_auto") as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False), \
             patch("autonomous_remediation_service.VERIFY_TIMEOUT_SEC", 0), \
             patch("response_orchestrator.ResponseOrchestrator.is_duplicate_task", new=AsyncMock(return_value=False)):
            svc = AutonomousRemediationService()
            result = await svc.remediate(self._finding())

        assert result["status"] in ("unverified", "failed")
        assert result["status"] != "resolved"

    async def test_step_poll_timeout_returns_unverified(self):
        db = _mock_db()
        db.agent_instructions.insert_one = AsyncMock()
        # Instruction never transitions out of pending -> step poll times out
        db.agent_instructions.find_one = AsyncMock(return_value={"status": "pending"})

        with permissive_gate("allow_auto") as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False), \
             patch("autonomous_remediation_service.STEP_POLL_TIMEOUT_SEC", 0), \
             patch("response_orchestrator.ResponseOrchestrator.is_duplicate_task", new=AsyncMock(return_value=False)):
            svc = AutonomousRemediationService()
            result = await svc.remediate(self._finding())

        assert result["status"] == "unverified"
        (row,) = stack.ledger.rows.values()
        assert row["state"] == "failed"                      # the host never confirmed the step

    async def test_remediate_no_matching_playbook(self):
        db = _mock_db()
        with patch("autonomous_remediation_service.get_database", return_value=db):
            svc = AutonomousRemediationService()
            result = await svc.remediate(self._finding(finding_type="compliance", details={}))
        assert result["status"] == "no_playbook"

    async def test_remediate_dry_run_does_not_dispatch(self):
        """Was status dry_run; the gate now records a simulation and returns status shadow
        (A-81-SHADOW-STATUS) with the ledger row id. Nothing reaches an agent."""
        db = _mock_db()
        db.agent_instructions.insert_one = AsyncMock()
        with permissive_gate("allow_auto", shadow=True) as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", True):
            svc = AutonomousRemediationService()
            result = await svc.remediate(self._finding())
        assert result["status"] == "shadow"
        assert result["autonomy_action_id"] in stack.ledger.rows
        db.agent_instructions.insert_one.assert_not_called()
        db.remediation_requests.insert_one.assert_not_called()

    async def test_remediate_refused_by_the_gate_writes_nothing_else(self):
        db = _mock_db()
        db.agent_instructions.insert_one = AsyncMock()
        from autonomous_ops import gate

        async def refuse(db_, req, **kw):
            return gate.Decision("refuse", "refused", "not_enabled", trace=[])

        with patch.object(gate, "decide", refuse), \
             patch("autonomous_remediation_service.get_database", return_value=db):
            result = await AutonomousRemediationService().remediate(self._finding())
        assert result["status"] == "refused" and result["reason"] == "not_enabled"
        db.remediation_requests.insert_one.assert_not_called()
        db.agent_instructions.insert_one.assert_not_called()


class TestLegacyLlmPathIsGone:
    """GATE-05: the path that let an LLM write scripts no longer exists."""

    async def test_removed_symbols_are_absent(self):
        for name in ("run_cycle", "generate_plan", "execute_plan", "verify_remediation", "_log_decision",
                     "_create_failure_ticket", "_is_tenant_enabled"):
            assert not hasattr(AutonomousRemediationService, name), name
        assert not hasattr(service_module, "RemediationPlan")
        assert not hasattr(service_module, "AUTONOMOUS_REMEDIATION_INTERVAL_SEC")

    async def test_kept_symbols_remain(self):
        for name in ("SEVERITY_ORDER", "RemediationFinding", "_render_step_params",
                     "AUTONOMOUS_REMEDIATION_DRY_RUN", "MAX_AUTO_SEVERITY"):
            assert hasattr(service_module, name), name
        assert hasattr(AutonomousRemediationService, "scan_for_remediable_findings")

    async def test_remediation_dispatcher_is_registered_with_the_ledger(self):
        from autonomous_ops import approvals
        assert approvals._DISPATCHERS["remediation"] is service_module._remediation_dispatcher


class TestAppendOnlyAudit:
    async def test_write_audit_inserts_record(self):
        from remediation_audit_service import write_audit
        db = _mock_db()
        await write_audit(db, "t1", {"remediation_id": "r1", "stage": "selected"})
        db.remediation_audit.insert_one.assert_called_once()
        inserted = db.remediation_audit.insert_one.call_args[0][0]
        assert inserted["tenantId"] == "t1"
        assert inserted["remediation_id"] == "r1"

    async def test_audit_service_exposes_no_update_or_delete(self):
        import remediation_audit_service as mod
        assert not hasattr(mod, "update_audit")
        assert not hasattr(mod, "delete_audit")

    async def test_remediate_writes_audit_at_each_stage(self):
        db = _mock_db()
        db.agent_instructions.insert_one = AsyncMock()
        db.agent_instructions.find_one = AsyncMock(return_value={"status": "SUCCESS"})
        db.vulnerabilities.find_one = AsyncMock(return_value={"id": "f-1", "status": "Patched"})

        with permissive_gate("allow_auto") as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False), \
             patch("response_orchestrator.ResponseOrchestrator.is_duplicate_task", new=AsyncMock(return_value=False)):
            svc = AutonomousRemediationService()
            await svc.remediate(self._finding())

        assert db.remediation_audit.insert_one.call_count >= 2
        stages = [c.args[0].get("stage") for c in db.remediation_audit.insert_one.call_args_list]
        assert {"selected", "requested", "dispatched", "verified"} <= set(stages)

    def _finding(self, finding_type="vuln", **overrides):
        base = dict(
            finding_id="f-1", finding_type=finding_type, severity="critical",
            tenant_id="t1", agent_id="agent-1", resource_id="asset-1",
            details={"cveId": "CVE-2024-0001", "package": "openssl"},
        )
        base.update(overrides)
        return RemediationFinding(**base)
