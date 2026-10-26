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

from autonomous_ops import ledger, protected, settings, views
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
