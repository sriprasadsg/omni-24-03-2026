"""TDD suite for the Phase 53-04 safety guards: approval gate for
destructive playbooks, rollback-on-failed-verify, DB-lease concurrency
cap, and the approve/deny/audit-read control endpoints (AUTO-03/04).

Phase 81 (81-08): the approval card now lives in the decision ledger. The MagicMock-database
tests run under ``permissive_gate``; approve and deny (GATE-10, D-24 (c)) are proven against a
real throwaway database, with a stand-in agent (``agent_that_completes``) so every instruction
the gate wrote is checked for the stamp and for being a registry command. Console permission
checks cover the approve tier (control:autonomous_ops) and the audit read tier.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autonomous_ops import ledger, protected, registry
from autonomous_remediation_service import AutonomousRemediationService, RemediationFinding
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import agent_that_completes, permissive_gate, seed_agent, seed_tenant

pytestmark = pytest.mark.asyncio

APPROVER = {"username": "alice", "display": "Alice", "tier": "tenant"}


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
    db.autonomy_actions.update_one = AsyncMock()      # gate.execute links the instruction to its row
    return db


def _finding(finding_type="nscan", **overrides):
    base = dict(
        finding_id="f-1", finding_type=finding_type, severity="critical",
        tenant_id="t1", agent_id="agent-1", resource_id="1.2.3.4",
        details={"type": "ip", "verdict": "Malicious", "ts": "2026-08-01T00:00:00Z"},
    )
    base.update(overrides)
    return RemediationFinding(**base)


def _file_finding(**overrides):
    base = dict(finding_id="f-2", agent_id="a1", resource_id="/tmp/evil.exe",
                details={"type": "file", "verdict": "Malicious", "ts": "2026-08-01T00:00:00Z"})
    base.update(overrides)
    return _finding(**base)


def _ip_finding(**overrides):
    base = dict(finding_id="f-3", agent_id="a1", resource_id="203.0.113.7")
    base.update(overrides)
    return _finding(**base)


async def _row(stack, state="dispatching"):
    """A ledger row in the in-memory ledger for the direct _dispatch_and_verify tests."""
    row = await stack.ledger.create_intent(None, {"tenantId": "t1", "kind": "security", "state": state,
                                                  "instructionIds": []})
    return row["id"]


@pytest.fixture(autouse=True)
def _no_real_sleep():
    with patch("autonomous_remediation_service.asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("response_orchestrator.ResponseOrchestrator.is_duplicate_task", new=AsyncMock(return_value=False)):
        yield


class TestApprovalGate:
    async def test_approval_class_playbook_pends_approval_without_dispatch(self):
        db = _mock_db()
        with permissive_gate("needs_approval") as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            svc = AutonomousRemediationService()
            result = await svc.remediate(_file_finding())  # nscan/file -> kill_process, an approval action
        assert result["status"] == "pending_approval"
        db.agent_instructions.insert_one.assert_not_called()
        db.remediation_requests.insert_one.assert_called_once()
        assert db.remediation_requests.insert_one.call_args.args[0]["autonomyActionId"] in stack.ledger.rows


@pytest.fixture
async def live(mongo_db):  # noqa: F811
    """Eligible tenant t1 (shadow off, so decisions are real), its agent a1, the ledger indexes, and
    the service reading the throwaway database. The master shadow flag is patched off by each test."""
    protected.cache_clear()
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1")
    with patch("autonomous_remediation_service.get_database", return_value=mongo_db), \
         patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False), \
         patch("soc_integration_service.push_ocsf_event", new=AsyncMock()):
        yield mongo_db


async def _card(live, finding=None):
    """remediate() a kill_process finding to a pending card; (service, remediation_id, ledger row)."""
    svc = AutonomousRemediationService()
    pending = await svc.remediate(finding or _file_finding())
    assert pending["status"] == "pending_approval", pending
    row = await live.autonomy_actions.find_one({"tenantId": "t1", "remediationId": pending["remediation_id"]})
    return svc, pending["remediation_id"], row


async def _instructions(live):
    return [d async for d in live.agent_instructions.find({}).sort("created_at", 1)]


class TestApprovalThroughTheLedger:
    async def test_approve_dispatches_stamped_registry_commands_only(self, live):
        svc, rid, row = await _card(live)
        assert row["state"] == "awaiting_approval"
        with agent_that_completes("Clean"):
            out = await svc.approve_remediation(rid, "t1", APPROVER)

        assert out["status"] == "resolved" and out["remediation_id"] == rid
        docs = await _instructions(live)
        assert [d["type"] for d in docs] == ["kill_process", "scan_file"]
        assert [d["autonomy"]["kind"] for d in docs] == ["action", "probe"]
        for d in docs:
            assert d["triggered_by"] == "autonomous_ops" and d["type"] in registry.commands()
            assert "script" not in d["payload"] and "script" not in d["parameters"]
        row = await live.autonomy_actions.find_one({"id": row["id"]})
        assert row["state"] == "verified" and row["approval"]["approver"] == APPROVER
        assert (await live.remediation_requests.find_one({"id": rid}))["status"] == "resolved"
        stages = [a["stage"] async for a in live.remediation_audit.find({"remediation_id": rid})]
        assert "override_approved" in stages and "dispatched" in stages and "verified" in stages

    async def test_a_second_click_dispatches_nothing(self, live):
        svc, rid, row = await _card(live)
        with agent_that_completes("Clean"):
            await svc.approve_remediation(rid, "t1", APPROVER)
            before = len(await _instructions(live))
            again = await svc.approve_remediation(rid, "t1", APPROVER)
        assert again["status"] == "already_handled"
        assert len(await _instructions(live)) == before

    async def test_the_request_compare_and_set_alone_stops_a_double_dispatch(self, live):
        svc, rid, row = await _card(live)
        approved = await live.autonomy_actions.find_one_and_update(
            {"id": row["id"]}, {"$set": {"state": "approved"}}, return_document=True)
        with agent_that_completes("Clean"):
            first = await svc.dispatch_approved_remediation(live, approved, APPROVER)
            second = await svc.dispatch_approved_remediation(live, approved, APPROVER)
        assert first["status"] == "resolved"
        assert second == {"status": "refused", "reason": "request_not_pending"}
        assert len(await _instructions(live)) == 2            # one action and one probe, not four

    async def test_a_request_without_a_ledger_card_is_refused(self, live):
        await live.remediation_requests.insert_one({"id": "REM-old", "tenantId": "t1", "status": "pending_approval"})
        out = await AutonomousRemediationService().approve_remediation("REM-old", "t1", APPROVER)
        assert out["status"] == "refused" and out["reason"] == "legacy_request"
        out = await AutonomousRemediationService().deny_remediation("REM-old", "t1", APPROVER, "no")
        assert out["status"] == "refused" and out["reason"] == "legacy_request"
        assert await live.agent_instructions.count_documents({}) == 0

    async def test_unknown_and_other_tenant_requests_are_not_found(self, live):
        svc, rid, _ = await _card(live)
        assert (await svc.approve_remediation("REM-nope", "t1", APPROVER))["status"] == "not_found"
        assert (await svc.approve_remediation(rid, "t2", APPROVER))["status"] == "not_found"
        assert (await svc.deny_remediation(rid, "t2", APPROVER))["status"] == "not_found"

    async def test_deny_cancels_and_records_the_override(self, live):
        svc, rid, row = await _card(live)
        out = await svc.deny_remediation(rid, "t1", APPROVER, "false positive")
        assert out == {"status": "denied", "remediation_id": rid}
        assert (await live.autonomy_actions.find_one({"id": row["id"]}))["state"] == "denied"
        assert (await live.remediation_requests.find_one({"id": rid}))["status"] == "denied"
        assert await live.agent_instructions.count_documents({}) == 0
        denial = await live.remediation_audit.find_one({"remediation_id": rid, "stage": "override_denied"})
        assert denial["approver"] == "alice" and denial["reason"] == "false positive"
        with agent_that_completes():
            assert (await svc.approve_remediation(rid, "t1", APPROVER))["status"] == "already_handled"
        assert await live.agent_instructions.count_documents({}) == 0

    async def test_a_stop_freezes_the_approval(self, live):
        from tests.autonomy_support import seed_platform_stop
        svc, rid, row = await _card(live)
        await seed_platform_stop(live)
        out = await svc.approve_remediation(rid, "t1", APPROVER)
        assert out["status"] == "stopped"
        assert await live.agent_instructions.count_documents({}) == 0
        assert (await live.autonomy_actions.find_one({"id": row["id"]}))["state"] == "awaiting_approval"


class TestLedgerFollowsTheAuditPoints:
    async def test_verified_failure_of_a_reversible_playbook_is_compensated_and_rolled_back(self, live):
        with agent_that_completes("Malicious"):                     # still malicious on the re-scan
            out = await AutonomousRemediationService().remediate(_ip_finding())

        assert out["status"] == "failed" and out.get("rollback_dispatched") is True
        docs = await _instructions(live)
        assert [(d["type"], d["autonomy"]["kind"]) for d in docs] == [
            ("block_ip", "action"), ("scan_ip", "probe"), ("unblock_ip", "compensate")]
        row = await live.autonomy_actions.find_one({"tenantId": "t1"})
        assert row["state"] == "rolled_back" and row["autoDispatched"] is True

    async def test_irreversible_failure_escalates_and_the_row_stays_failed(self, live):
        svc, rid, row = await _card(live)
        with agent_that_completes("Malicious"):
            out = await svc.approve_remediation(rid, "t1", APPROVER)
        assert out["status"] == "failed" and out.get("escalated") is True
        assert [d["type"] for d in await _instructions(live)] == ["kill_process", "scan_file"]
        assert (await live.autonomy_actions.find_one({"id": row["id"]}))["state"] == "failed"
        assert await live.alerts.count_documents({"type": "REMEDIATION_ESCALATION"}) == 1

    async def test_every_ledger_change_is_mirrored_to_the_audit_chain(self, live):
        with agent_that_completes("Clean"):
            await AutonomousRemediationService().remediate(_ip_finding())
        events = [e["action"] async for e in live.audit_logs.find({"tenantId": "t1"}).sort("seq", 1)]
        assert len(events) >= 3                                    # intent, executed, verified


class TestRollbackAndEscalation:
    async def test_failed_verify_reversible_dispatches_rollback(self):
        db = _mock_db()
        # nscan/ip finding -> block_ip (has rollback: unblock_ip).
        # Force verify to "failed": still Malicious on rescan.
        db.security_scan_results.find_one = AsyncMock(return_value={"verdict": "Malicious", "created_at": "2026-08-01T01:00:00Z"})

        with permissive_gate("allow_auto") as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            action_id = await _row(stack)
            svc = AutonomousRemediationService()
            result = await svc._dispatch_and_verify(
                "REM-1", _finding(),
                {"name": "block_ip", "steps": [{"action": "block_ip", "params": {"ip_address": "{{finding.resource_id}}"}, "destructive": True}],
                 "rollback": [{"action": "unblock_ip", "params": {"ip_address": "{{finding.resource_id}}"}}]},
                action_id=action_id,
            )

        written = [c.args[0] for c in db.agent_instructions.insert_one.call_args_list]
        assert "unblock_ip" in [d["type"] for d in written]
        assert [d["autonomy"]["kind"] for d in written if d["type"] == "unblock_ip"] == ["compensate"]
        assert result["status"] == "failed"
        assert result.get("rollback_dispatched") is True
        assert stack.ledger.rows[action_id]["state"] == "rolled_back"

    async def test_failed_verify_irreversible_escalates_no_rollback(self):
        db = _mock_db()
        finding = _finding(finding_type="nscan", details={"type": "file", "verdict": "Malicious", "ts": "2026-08-01T00:00:00Z"})
        # kill_process has no rollback; force verify "failed" (still malicious)
        db.security_scan_results.find_one = AsyncMock(return_value={"verdict": "Malicious", "created_at": "2026-08-01T01:00:00Z"})

        with permissive_gate("allow_auto") as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            action_id = await _row(stack)
            svc = AutonomousRemediationService()
            result = await svc._dispatch_and_verify(
                "REM-2", finding,
                {"name": "kill_process", "steps": [{"action": "kill_process", "params": {"target": "{{finding.resource_id}}"}, "destructive": True}],
                 "rollback": []},
                action_id=action_id,
            )

        dispatched_types = [c.args[0].get("type") for c in db.agent_instructions.insert_one.call_args_list]
        assert "unblock_ip" not in dispatched_types
        assert "enable_service" not in dispatched_types
        assert result["status"] == "failed"
        assert result.get("escalated") is True
        db.alerts.insert_one.assert_called_once()
        assert stack.ledger.rows[action_id]["state"] == "failed"


class TestConcurrencyCap:
    async def test_over_cap_defers_without_dispatch(self):
        db = _mock_db()
        db.remediation_inflight.count_documents = AsyncMock(return_value=99)  # over any sane cap

        with permissive_gate("allow_auto") as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            action_id = await _row(stack)
            svc = AutonomousRemediationService()
            result = await svc._dispatch_and_verify(
                "REM-3", _finding(),
                {"name": "block_ip", "steps": [{"action": "block_ip", "params": {"ip_address": "1.2.3.4"}, "destructive": True}], "rollback": []},
                action_id=action_id,
            )

        assert result["status"] == "deferred"
        db.agent_instructions.insert_one.assert_not_called()
        assert stack.ledger.rows[action_id]["state"] == "refused"      # not a bad outcome for the breaker

    async def test_lease_released_on_completion(self):
        db = _mock_db()
        db.security_scan_results.find_one = AsyncMock(return_value={"verdict": "Clean", "created_at": "2026-08-01T01:00:00Z"})

        with permissive_gate("allow_auto") as stack, \
             patch("autonomous_remediation_service.get_database", return_value=db), \
             patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False):
            action_id = await _row(stack)
            svc = AutonomousRemediationService()
            await svc._dispatch_and_verify(
                "REM-4", _finding(),
                {"name": "block_ip", "steps": [{"action": "block_ip", "params": {"ip_address": "1.2.3.4"}, "destructive": True}], "rollback": []},
                action_id=action_id,
            )

        db.remediation_inflight.insert_one.assert_called_once()
        db.remediation_inflight.delete_one.assert_called_once()

    async def test_a_step_with_no_ledger_row_is_not_dispatched(self):
        db = _mock_db()
        with patch("autonomous_remediation_service.get_database", return_value=db):
            step = await AutonomousRemediationService()._dispatch_step(
                _finding(), {"action": "block_ip", "params": {"ip_address": "1.2.3.4"}})
        assert step["status"] == "refused" and step["reason"] == "no_ledger_row"
        db.agent_instructions.insert_one.assert_not_called()


class TestControlEndpoints:
    def _app(self, db, tenant_id="t1", perms=None):
        import remediation_control_endpoints as mod
        from authentication_service import get_current_user

        app = FastAPI()
        app.include_router(mod.router)

        class User:
            def __init__(self):
                self.id = "user-1"
                self.username = "alice"
                self.tenant_id = tenant_id
                self.role = "admin"
                self.permissions = perms or ["manage:active_response"]

        app.dependency_overrides[get_current_user] = lambda: User()
        return app

    @staticmethod
    def _holds(*granted):
        return AsyncMock(side_effect=lambda user, perm: perm in granted)

    async def test_get_audit_tenant_scoped(self):
        db = _mock_db()
        db.remediation_audit.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[{"remediation_id": "r1", "tenantId": "t1"}]
        )
        with patch("remediation_control_endpoints.get_database", return_value=db), \
             patch("remediation_control_endpoints.verify_permission", new=self._holds("manage:active_response")):
            app = self._app(db)
            with TestClient(app) as client:
                resp = client.get("/api/remediation/audit")
        assert resp.status_code == 200
        assert resp.json()[0]["remediation_id"] == "r1"

    async def test_audit_does_not_accept_the_approve_tier_alone(self):
        db = _mock_db()
        with patch("remediation_control_endpoints.get_database", return_value=db), \
             patch("remediation_control_endpoints.verify_permission", new=self._holds("control:autonomous_ops")):
            with TestClient(self._app(db)) as client:
                assert client.get("/api/remediation/audit").status_code == 403

    async def test_approve_endpoint_calls_service(self):
        db = _mock_db()
        with patch("remediation_control_endpoints.get_database", return_value=db), \
             patch("remediation_control_endpoints.verify_permission", new=self._holds("control:autonomous_ops")), \
             patch("remediation_control_endpoints.AutonomousRemediationService.approve_remediation",
                   new=AsyncMock(return_value={"status": "resolved", "remediation_id": "r1"})) as mock_approve:
            app = self._app(db)
            with TestClient(app) as client:
                resp = client.post("/api/remediation/r1/approve")
        assert resp.status_code == 200
        mock_approve.assert_called_once()
        assert mock_approve.call_args.args[:2] == ("r1", "t1")
        assert mock_approve.call_args.args[2]["username"] == "alice"       # the ledger's approver shape

    async def test_deny_endpoint_calls_service(self):
        db = _mock_db()
        with patch("remediation_control_endpoints.get_database", return_value=db), \
             patch("remediation_control_endpoints.verify_permission", new=self._holds("control:autonomous_ops")), \
             patch("remediation_control_endpoints.AutonomousRemediationService.deny_remediation",
                   new=AsyncMock(return_value={"status": "denied", "remediation_id": "r1"})) as mock_deny:
            app = self._app(db)
            with TestClient(app) as client:
                resp = client.post("/api/remediation/r1/deny", json={"reason": "fp"})
        assert resp.status_code == 200
        mock_deny.assert_called_once()

    async def test_approve_and_deny_refuse_a_caller_without_the_approve_tier(self):
        db = _mock_db()
        with patch("remediation_control_endpoints.get_database", return_value=db), \
             patch("remediation_control_endpoints.verify_permission", new=self._holds("manage:active_response")), \
             patch("remediation_control_endpoints.AutonomousRemediationService.approve_remediation",
                   new=AsyncMock()) as mock_approve, \
             patch("remediation_control_endpoints.AutonomousRemediationService.deny_remediation",
                   new=AsyncMock()) as mock_deny:
            with TestClient(self._app(db)) as client:
                assert client.post("/api/remediation/r1/approve").status_code == 403
                assert client.post("/api/remediation/r1/deny", json={"reason": "x"}).status_code == 403
        mock_approve.assert_not_called()
        mock_deny.assert_not_called()

    async def test_unknown_request_is_404(self):
        db = _mock_db()
        with patch("remediation_control_endpoints.get_database", return_value=db), \
             patch("remediation_control_endpoints.verify_permission", new=self._holds("control:autonomous_ops")), \
             patch("remediation_control_endpoints.AutonomousRemediationService.approve_remediation",
                   new=AsyncMock(return_value={"status": "not_found", "remediation_id": "r9"})):
            with TestClient(self._app(db)) as client:
                assert client.post("/api/remediation/r9/approve").status_code == 404
