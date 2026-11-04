"""Phase 81 (81-16): playbook selection is tenant-scoped, and "Undone" means every compensation
step was confirmed.

Tenant isolation (GATE-08 / GATE-11): one tenant's operator-authored playbook is never selected
for another tenant's finding. Truthful undo (ACTV-01 / GATE-07): a failed check followed by a
compensation that timed out, failed or was refused ends ``failed`` with ``rollback_incomplete``,
an escalation alert and a breaker evaluation; only a fully confirmed compensation is
``rolled_back``. Real throwaway Mongo; the "agent" is a local stand-in; no real host is touched.
"""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from autonomous_ops import ledger, messages, protected, settings, views
from autonomous_ops.scope import raw
from autonomous_remediation_service import AutonomousRemediationService, RemediationFinding
from remediation_playbook_service import (_belongs, load_default_playbooks, load_playbooks,
                                          select_playbook)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_tenant

pytestmark = pytest.mark.asyncio

KILL_A = {"name": "kill_process", "finding_class": "nscan", "source": "operator", "tenantId": "t-a",
          "steps": [{"action": "kill_process", "params": {"target": "{{finding.resource_id}}"}},
                    {"action": "block_ip", "params": {"ip_address": "203.0.113.5"}}],
          "rollback": []}


def _anomaly(tenant_id, agent_id="b1"):
    return RemediationFinding(
        finding_id=f"UEBA-{tenant_id}-1", finding_type="anomaly", severity="high", tenant_id=tenant_id,
        agent_id=agent_id, resource_id="ollama.exe", details={"anomaly_rule": "shadow_ai_detected"})


def _defaults_plus(*extra):
    return load_default_playbooks() + list(extra)


class TestSelectionIsTenantScoped:
    async def test_tenant_a_playbook_never_selected_for_tenant_b(self):
        picked = select_playbook(_anomaly("t-b"), _defaults_plus(dict(KILL_A)))
        assert picked["name"] == "kill_process" and len(picked["steps"]) == 1
        assert picked.get("tenantId") is None and picked["source"] == "vendored"

    async def test_tenant_a_still_gets_its_own_playbook(self):
        picked = select_playbook(_anomaly("t-a", "a1"), _defaults_plus(dict(KILL_A)))
        assert len(picked["steps"]) == 2 and picked["tenantId"] == "t-a"

    async def test_a_vendored_copy_stamped_and_edited_by_another_tenant_is_never_selected(self):
        edited = next(p for p in load_default_playbooks() if p["name"] == "kill_process")
        edited = dict(edited, tenantId="t-a", steps=KILL_A["steps"])
        picked = select_playbook(_anomaly("t-b"), _defaults_plus(edited))
        assert len(picked["steps"]) == 1

    async def test_a_document_without_a_tenant_that_is_not_vendored_is_never_selected(self):
        orphan = {k: v for k, v in KILL_A.items() if k != "tenantId"}
        for tenant in ("t-a", "t-b"):
            picked = select_playbook(_anomaly(tenant), _defaults_plus(orphan))
            assert len(picked["steps"]) == 1

    async def test_a_finding_without_a_tenant_selects_only_vendored_defaults(self):
        finding = _anomaly("t-a")
        finding.tenant_id = None
        assert len(select_playbook(finding, _defaults_plus(dict(KILL_A)))["steps"]) == 1

    async def test_a_tenants_own_playbook_of_the_same_name_wins_over_the_vendored_one(self):
        # the tenant's document comes after the defaults, so it overrides within that tenant
        assert select_playbook(_anomaly("t-a", "a1"), _defaults_plus(dict(KILL_A)))["source"] == "operator"
        assert select_playbook(_anomaly("t-a", "a1"))["source"] == "vendored"

    async def test_belongs(self):
        assert _belongs({"source": "vendored"}, "t-b") and _belongs({"source": "vendored", "tenantId": ""}, None)
        assert _belongs({"tenantId": "t-a"}, "t-a")
        assert not _belongs({"tenantId": "t-a"}, "t-b") and not _belongs({"tenantId": "t-a"}, None)
        assert not _belongs({"source": "operator"}, "t-a") and not _belongs({"tenantId": "t-a"}, "")
        assert not _belongs({"source": "vendored", "tenantId": "t-a"}, "t-b")


async def test_load_playbooks_returns_defaults_then_only_the_tenants_own(mongo_db):  # noqa: F811
    await mongo_db.remediation_playbooks.insert_one(dict(KILL_A, id="op-a"))
    for_b = await load_playbooks(mongo_db, "t-b")
    assert not [p for p in for_b if p.get("tenantId") == "t-a"]
    assert [p["name"] for p in for_b[:len(load_default_playbooks())]] == [p["name"] for p in load_default_playbooks()]
    for_a = await load_playbooks(mongo_db, "t-a")
    assert for_a[-1]["tenantId"] == "t-a" and for_a[-1]["name"] == "kill_process"
    assert [p for p in await load_playbooks(mongo_db, None) if p.get("tenantId")] == []


async def test_remediate_of_a_tenant_b_anomaly_never_uses_tenant_a_playbook(mongo_db):  # noqa: F811
    protected.cache_clear()
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t-b")
    await seed_agent(mongo_db, "t-b", "b1")
    await mongo_db.remediation_playbooks.insert_one(dict(KILL_A, id="op-a"))
    with patch("autonomous_remediation_service.get_database", return_value=mongo_db), \
         patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "false"}), \
         patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False, create=True), \
         patch("soc_integration_service.push_ocsf_event", new=AsyncMock()):
        await AutonomousRemediationService().remediate(_anomaly("t-b"))
    rows = [r async for r in raw(mongo_db).autonomy_actions.find({"tenantId": "t-b", "kind": "security"})]
    assert len(rows) == 1
    steps = rows[0]["steps"]
    assert len(steps) == 1 and "kill_process" in str(steps[0])
    assert "203.0.113.5" not in str(rows[0])


# ------------------------------------------------------------------ truthful undo (ACTV-01, GATE-07)

OP_BLOCK_TWO_UNDOS = {
    "name": "block_ip", "finding_class": "nscan", "source": "operator", "tenantId": "t1",
    "steps": [{"action": "block_ip", "params": {"ip_address": "{{finding.resource_id}}"}, "destructive": True}],
    "rollback": [{"action": "unblock_ip", "params": {"ip_address": "{{finding.resource_id}}"}},
                 {"action": "unblock_ip", "params": {"ip_address": "{{finding.resource_id}}"}}]}


def _ip(n=1):
    return RemediationFinding(
        finding_id=f"f-ip-{n}", finding_type="nscan", severity="critical", tenant_id="t1", agent_id="a1",
        resource_id=f"203.0.113.{6 + n}", details={"type": "ip", "verdict": "Malicious", "ts": "2026-08-01T00:00:00Z"})


def stand_in_agent(compensate=("SUCCESS",)):
    """A local stand-in agent: actions and probes complete with SUCCESS and the re-scan still reads
    Malicious (so the check fails); the n-th compensate instruction answers ``compensate[n]``
    (the last entry repeats)."""
    from autonomous_ops.scope import raw as _raw
    seen = {"n": 0}

    async def poll(self, db, task_id, timeout_sec, interval_sec, tenant_id=None):
        handle = _raw(db)
        doc = await handle.agent_instructions.find_one({"id": task_id})
        if (doc.get("autonomy") or {}).get("kind") == "compensate":
            answer = compensate[min(seen["n"], len(compensate) - 1)]
            seen["n"] += 1
            if answer != "SUCCESS":
                return answer
        await handle.agent_instructions.update_one({"id": task_id}, {"$set": {"status": "SUCCESS"}})
        if str(doc.get("type", "")).startswith("scan_"):
            params = doc.get("payload") or {}
            await handle.security_scan_results.insert_one({
                "tenantId": doc.get("tenantId"), "target": params.get("path") or params.get("target"),
                "verdict": "Malicious",
                "created_at": (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()})
        return "SUCCESS"

    return patch.object(AutonomousRemediationService, "_poll_task_status", poll)


@pytest.fixture
async def live(mongo_db):  # noqa: F811
    protected.cache_clear()
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1")
    with patch("autonomous_remediation_service.get_database", return_value=mongo_db), \
         patch.dict(os.environ, {"AUTONOMOUS_REMEDIATION_DRY_RUN": "false"}), \
         patch("autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN", False, create=True), \
         patch("soc_integration_service.push_ocsf_event", new=AsyncMock()):
        yield mongo_db


async def _row_of(live, n=1):
    return await raw(live).autonomy_actions.find_one({"tenantId": "t1", "kind": "security",
                                                      "targets": ["a1"], "dedupeKey": {"$regex": f"f-ip-{n}$"}})


class TestRolledBackMeansEveryStepWasConfirmed:
    @pytest.mark.parametrize("answer", ["TIMEOUT", "FAILURE"])
    async def test_a_compensation_that_did_not_finish_is_failed_rollback_incomplete(self, live, answer):
        with stand_in_agent((answer,)):
            out = await AutonomousRemediationService().remediate(_ip())
        assert out["status"] == "failed" and out["rollback_dispatched"] is False and out["escalated"] is True
        row = await _row_of(live)
        assert row["state"] == "failed" and row["reasonCode"] == "rollback_incomplete"
        assert row["reasonText"] == messages.REASON_TEXT["rollback_incomplete"]
        assert views.bucket_of(row) == "failed"
        assert messages.STATE_RESULT[row["state"]] == "The action did not finish."
        alerts = [a async for a in live.alerts.find({"type": "REMEDIATION_ESCALATION"})]
        assert len(alerts) == 1 and alerts[0]["tenantId"] == "t1"
        stages = {a["stage"]: a async for a in live.remediation_audit.find({})}
        assert stages["rollback_dispatched"]["complete"] is False and "escalated" in stages

    async def test_a_refused_compensation_is_failed_rollback_incomplete(self, live):
        from autonomous_ops import gate
        real = gate.execute

        async def execute(db, tenant_id, action_id, **kw):
            if kw.get("kind") == "compensate":
                return {"status": "refused", "reason": "stopped"}
            return await real(db, tenant_id, action_id, **kw)

        with stand_in_agent(), patch.object(gate, "execute", execute):
            out = await AutonomousRemediationService().remediate(_ip())
        assert out["status"] == "failed" and out["rollback_dispatched"] is False and out["escalated"] is True
        row = await _row_of(live)
        assert row["state"] == "failed" and row["reasonCode"] == "rollback_incomplete"

    async def test_every_step_confirmed_is_rolled_back_without_an_alert(self, live):
        with stand_in_agent(("SUCCESS",)):
            out = await AutonomousRemediationService().remediate(_ip())
        assert out["rollback_dispatched"] is True and "escalated" not in out
        row = await _row_of(live)
        assert row["state"] == "rolled_back" and views.bucket_of(row) != "failed"
        assert messages.STATE_RESULT[row["state"]] == "Undone."
        assert await live.alerts.count_documents({}) == 0
        audit = await live.remediation_audit.find_one({"stage": "rollback_dispatched"})
        assert audit["complete"] is True

    async def test_one_failed_step_is_enough_and_every_step_is_attempted(self, live):
        await live.remediation_playbooks.insert_one(dict(OP_BLOCK_TWO_UNDOS, id="op-t1"))
        with stand_in_agent(("SUCCESS", "TIMEOUT")):
            out = await AutonomousRemediationService().remediate(_ip())
        assert out["status"] == "failed" and out["rollback_dispatched"] is False
        compensates = [d async for d in live.agent_instructions.find({"autonomy.kind": "compensate"})]
        assert len(compensates) == 2                                 # the second was tried after the first
        audit = await live.remediation_audit.find_one({"stage": "rollback_dispatched"})
        assert [r["status"] for r in audit["rollback_steps"]] == ["SUCCESS", "TIMEOUT"]
        assert (await _row_of(live))["reasonCode"] == "rollback_incomplete"

    async def test_no_rollback_still_escalates_as_verify_failed(self, live):
        finding = RemediationFinding(
            finding_id="f-ip-9", finding_type="nscan", severity="critical", tenant_id="t1", agent_id="a1",
            resource_id="/tmp/evil.exe", details={"type": "file", "verdict": "Malicious", "ts": "2026-08-01T00:00:00Z",
                                                  "sha256": "a" * 64})
        # D-05: a malicious file is quarantined (automatic), so the tenant raises the playbook to an approval card.
        await live.remediation_playbooks.insert_one({
            "id": "op-q", "name": "quarantine_file", "finding_class": "nscan", "source": "operator", "tenantId": "t1",
            "steps": [{"action": "quarantine_file", "params": {"path": "{{finding.resource_id}}",
                                                              "sha256": "{{finding.details.sha256}}"},
                       "gate_class": "approve"}], "rollback": []})
        svc = AutonomousRemediationService()
        pending = await svc.remediate(finding)                       # quarantine_file raised: needs approval
        assert pending["status"] == "pending_approval"
        with stand_in_agent():
            out = await svc.approve_remediation(pending["remediation_id"], "t1",
                                                {"username": "alice", "display": "Alice", "tier": "tenant"})
        assert out["status"] == "failed" and out["escalated"] is True
        row = await _row_of(live, 9)
        assert row["state"] == "failed" and row["reasonCode"] == "verify_failed"

    async def test_the_failed_transition_comes_before_the_rollback_incomplete_one(self, live):
        with stand_in_agent(("TIMEOUT",)):
            await AutonomousRemediationService().remediate(_ip())
        row = await _row_of(live)
        events = [e async for e in live.audit_logs.find({"resourceId": row["id"]}).sort("seq", 1)]
        codes = [(e["action"], (e.get("details") or {}).get("reasonCode", e.get("reasonCode"))) for e in events]
        failed = [c for c in codes if c[0] == "autonomous_ops.failed"]
        assert [c[1] for c in failed] == ["verify_failed", "rollback_incomplete"], codes


class TestTheBreakerSeesRemediationOutcomes:
    async def test_three_incomplete_rollbacks_in_a_row_trip_the_breaker(self, live):
        with stand_in_agent(("TIMEOUT",)):
            for n in (1, 2, 3):
                await AutonomousRemediationService().remediate(_ip(n))
        s = await settings.load(live, "t1")
        assert s.level == "suggest" and s.breaker is not None

    async def test_a_breaker_that_raises_does_not_change_the_result(self, live):
        from autonomous_ops import breaker
        with stand_in_agent(("TIMEOUT",)), patch.object(breaker, "evaluate", AsyncMock(side_effect=RuntimeError("x"))):
            out = await AutonomousRemediationService().remediate(_ip())
        assert out["status"] == "failed" and out["rollback_dispatched"] is False and out["escalated"] is True
        assert (await _row_of(live))["reasonCode"] == "rollback_incomplete"

    async def test_a_dispatch_that_was_not_confirmed_is_also_evaluated(self, live):
        from autonomous_ops import breaker
        with stand_in_agent(), patch.object(AutonomousRemediationService, "_dispatch_step",
                                            AsyncMock(return_value={"action": "block_ip", "status": "TIMEOUT"})), \
             patch.object(breaker, "evaluate", AsyncMock(return_value=False)) as evaluate:
            out = await AutonomousRemediationService().remediate(_ip())
        assert out["status"] == "unverified"
        evaluate.assert_awaited_once()


async def test_rollback_incomplete_text_exists():
    assert messages.REASON_TEXT["rollback_incomplete"]


# ---------------------------------------------------------------- 83 T-83-27 (A-83-PATCHED)

async def test_approving_a_script_remediation_marks_nothing_patched_or_executed(mongo_db):  # noqa: F811
    """protects=no success answer for nothing sent (T-83-27); fails_when=approving marks the vulnerability
    Patched or the request Executed although the worker task sends nothing (it answers not_sent);
    no_claim=the Autonomous Ops path, which does send instructions through the gate."""
    from models import RemediationRequest
    from remediation_service import RemediationService

    await mongo_db.vulnerabilities.insert_one({"id": "v1", "tenantId": "t-a", "status": "Open"})
    req = RemediationRequest(id="r1", tenantId="t-a", assetId="a1", vulnerabilityId="v1",
                             proposedAction="update_package", scriptContent="echo hi", status="Pending",
                             createdAt="2026-11-04T00:00:00", updatedAt="2026-11-04T00:00:00")
    with patch("database.get_database", return_value=mongo_db):
        out = await RemediationService.approve_and_execute(req)
    assert out.status == "Not sent" and out.executionLog == messages_fence_worker()
    assert (await mongo_db.vulnerabilities.find_one({"id": "v1"}))["status"] == "Open"


def messages_fence_worker():
    from autonomous_ops.response_messages import FENCE
    return FENCE["worker"]
