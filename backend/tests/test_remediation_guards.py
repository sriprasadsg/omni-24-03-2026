"""TDD suite for the Phase 53-04 safety guards: approval gate for
destructive playbooks, rollback-on-failed-verify, DB-lease concurrency
cap, and the approve/deny/audit-read control endpoints (AUTO-03/04).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autonomous_remediation_service import AutonomousRemediationService, RemediationFinding

pytestmark = pytest.mark.asyncio


def _mock_db():
    db = MagicMock()
    db.remediation_audit.insert_one = AsyncMock(return_value=MagicMock(inserted_id="aud-1"))
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
    db.agent_instructions.insert_one = AsyncMock()
    db.agent_instructions.find_one = AsyncMock(return_value={"status": "SUCCESS"})
    return db


def _finding(finding_type="nscan", **overrides):
    base = dict(
        finding_id="f-1", finding_type=finding_type, severity="critical",
        tenant_id="t1", agent_id="agent-1", resource_id="1.2.3.4",
        details={"type": "ip", "verdict": "Malicious", "ts": "2026-08-01T00:00:00Z"},
    )
    base.update(overrides)
    return RemediationFinding(**base)


@pytest.fixture(autouse=True)
def _no_real_sleep():
    with patch("autonomous_remediation_service.asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("response_orchestrator.ResponseOrchestrator.is_duplicate_task", new=AsyncMock(return_value=False)):
        yield


class TestApprovalGate:
    async def test_destructive_playbook_pends_approval_without_dispatch(self):
        db = _mock_db()
        with patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            svc = AutonomousRemediationService()
            result = await svc.remediate(_finding())  # nscan/ip -> block_ip, destructive
        assert result["status"] == "pending_approval"
        db.agent_instructions.insert_one.assert_not_called()
        db.remediation_requests.insert_one.assert_called_once()

    async def test_approve_resumes_dispatch(self):
        db = _mock_db()
        stored = {}

        async def _insert_request(doc):
            stored.update(doc)
            return MagicMock()

        db.remediation_requests.insert_one = AsyncMock(side_effect=_insert_request)
        db.remediation_requests.find_one = AsyncMock(side_effect=lambda *a, **k: dict(stored))
        db.security_scan_results.find_one = AsyncMock(return_value={"verdict": "Clean", "created_at": "2026-08-01T01:00:00Z"})

        with patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            svc = AutonomousRemediationService()
            pending = await svc.remediate(_finding())
            assert pending["status"] == "pending_approval"

            result = await svc.approve_remediation(pending["remediation_id"], "t1", "admin-1")

        assert db.agent_instructions.insert_one.called
        assert result["status"] in ("resolved", "failed", "unverified")

    async def test_deny_cancels_and_records_override(self):
        db = _mock_db()
        stored = {}

        async def _insert_request(doc):
            stored.update(doc)
            return MagicMock()

        db.remediation_requests.insert_one = AsyncMock(side_effect=_insert_request)
        db.remediation_requests.find_one = AsyncMock(side_effect=lambda *a, **k: dict(stored))

        with patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            svc = AutonomousRemediationService()
            pending = await svc.remediate(_finding())
            result = await svc.deny_remediation(pending["remediation_id"], "t1", "admin-1", "false positive")

        assert result["status"] == "denied"
        db.agent_instructions.insert_one.assert_not_called()
        audit_calls = [c.args[1] for c in db.remediation_audit.insert_one.call_args_list] if False else None
        # override recorded via write_audit -> remediation_audit.insert_one
        inserted_docs = [c.args[0] for c in db.remediation_audit.insert_one.call_args_list]
        assert any(d.get("stage") == "override_denied" for d in inserted_docs)


class TestRollbackAndEscalation:
    async def test_failed_verify_reversible_dispatches_rollback(self):
        db = _mock_db()
        # nscan/ip finding -> block_ip (destructive, has rollback: unblock_ip).
        # Force verify to "failed": still Malicious on rescan.
        db.security_scan_results.find_one = AsyncMock(return_value={"verdict": "Malicious", "created_at": "2026-08-01T01:00:00Z"})

        with patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            svc = AutonomousRemediationService()
            result = await svc._dispatch_and_verify(
                "REM-1", _finding(),
                {"name": "block_ip", "steps": [{"action": "block_ip", "params": {"ip_address": "{{finding.resource_id}}"}, "destructive": True}],
                 "rollback": [{"action": "unblock_ip", "params": {"ip_address": "{{finding.resource_id}}"}}]},
            )

        dispatched_types = [c.args[0].get("type") for c in db.agent_instructions.insert_one.call_args_list]
        assert "unblock_ip" in dispatched_types
        assert result["status"] == "failed"
        assert result.get("rollback_dispatched") is True

    async def test_failed_verify_irreversible_escalates_no_rollback(self):
        db = _mock_db()
        finding = _finding(finding_type="nscan", details={"type": "file", "verdict": "Malicious", "ts": "2026-08-01T00:00:00Z"})
        # kill_process has no rollback; force verify "failed" (still malicious)
        db.security_scan_results.find_one = AsyncMock(return_value={"verdict": "Malicious", "created_at": "2026-08-01T01:00:00Z"})

        with patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            svc = AutonomousRemediationService()
            result = await svc._dispatch_and_verify(
                "REM-2", finding,
                {"name": "kill_process", "steps": [{"action": "kill_process", "params": {"target": "{{finding.resource_id}}"}, "destructive": True}],
                 "rollback": []},
            )

        dispatched_types = [c.args[0].get("type") for c in db.agent_instructions.insert_one.call_args_list]
        assert "unblock_ip" not in dispatched_types
        assert "enable_service" not in dispatched_types
        assert result["status"] == "failed"
        assert result.get("escalated") is True
        db.alerts.insert_one.assert_called_once()


class TestConcurrencyCap:
    async def test_over_cap_defers_without_dispatch(self):
        db = _mock_db()
        db.remediation_inflight.count_documents = AsyncMock(return_value=99)  # over any sane cap

        with patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            svc = AutonomousRemediationService()
            result = await svc._dispatch_and_verify(
                "REM-3", _finding(),
                {"name": "block_ip", "steps": [{"action": "block_ip", "params": {"ip_address": "1.2.3.4"}, "destructive": True}], "rollback": []},
            )

        assert result["status"] == "deferred"
        db.agent_instructions.insert_one.assert_not_called()

    async def test_lease_released_on_completion(self):
        db = _mock_db()
        db.security_scan_results.find_one = AsyncMock(return_value={"verdict": "Clean", "created_at": "2026-08-01T01:00:00Z"})

        with patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            svc = AutonomousRemediationService()
            await svc._dispatch_and_verify(
                "REM-4", _finding(),
                {"name": "block_ip", "steps": [{"action": "block_ip", "params": {"ip_address": "1.2.3.4"}, "destructive": True}], "rollback": []},
            )

        db.remediation_inflight.insert_one.assert_called_once()
        db.remediation_inflight.delete_one.assert_called_once()


class TestControlEndpoints:
    def _app(self, db, tenant_id="t1", perms=None):
        import remediation_control_endpoints as mod
        from authentication_service import get_current_user

        app = FastAPI()
        app.include_router(mod.router)

        class User:
            def __init__(self):
                self.id = "user-1"
                self.tenant_id = tenant_id
                self.role = "admin"
                self.permissions = perms or ["manage:active_response"]

        app.dependency_overrides[get_current_user] = lambda: User()
        return app

    async def test_get_audit_tenant_scoped(self):
        db = _mock_db()
        db.remediation_audit.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[{"remediation_id": "r1", "tenantId": "t1"}]
        )
        with patch("remediation_control_endpoints.get_database", return_value=db), \
             patch("remediation_control_endpoints.verify_permission", new=AsyncMock(return_value=True)):
            app = self._app(db)
            with TestClient(app) as client:
                resp = client.get("/api/remediation/audit")
        assert resp.status_code == 200
        assert resp.json()[0]["remediation_id"] == "r1"

    async def test_approve_endpoint_calls_service(self):
        db = _mock_db()
        with patch("remediation_control_endpoints.get_database", return_value=db), \
             patch("remediation_control_endpoints.verify_permission", new=AsyncMock(return_value=True)), \
             patch("remediation_control_endpoints.AutonomousRemediationService.approve_remediation",
                   new=AsyncMock(return_value={"status": "resolved", "remediation_id": "r1"})) as mock_approve:
            app = self._app(db)
            with TestClient(app) as client:
                resp = client.post("/api/remediation/r1/approve")
        assert resp.status_code == 200
        mock_approve.assert_called_once()

    async def test_deny_endpoint_calls_service(self):
        db = _mock_db()
        with patch("remediation_control_endpoints.get_database", return_value=db), \
             patch("remediation_control_endpoints.verify_permission", new=AsyncMock(return_value=True)), \
             patch("remediation_control_endpoints.AutonomousRemediationService.deny_remediation",
                   new=AsyncMock(return_value={"status": "denied", "remediation_id": "r1"})) as mock_deny:
            app = self._app(db)
            with TestClient(app) as client:
                resp = client.post("/api/remediation/r1/deny", json={"reason": "fp"})
        assert resp.status_code == 200
        mock_deny.assert_called_once()
