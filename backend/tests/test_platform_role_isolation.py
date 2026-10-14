"""Spec C1 AC3: at the former mixed-literal scope sites a tenant admin of tenant A gets no
tenant B data, and platform staff read both.

Value: protects=the explicit tenant filter at each site now applies to a tenant admin;
fails_when="admin" is back in a cross-tenant role set (the query loses its tenant filter
and B's documents come back); no_claim=the DB wrapper: every case hands the code the RAW
database (what the platform-admin context gives), so only the site's own filter protects
tenant B. Real MongoDB (skips without one). Sites whose set is checked by membership only
are listed in test_scope_sets_by_membership.
"""
import importlib
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

ADMINS = ["admin", "Admin", "Tenant Admin", "tenant_admin"]
PLATFORM = ["Super Admin", "Platform Support", "Platform Billing"]


async def _seed(db, collection, extra=None):
    docs = [{"id": f"{t}-1", "tenantId": t, "created_at": "2026-10-14", **(extra or {})} for t in ("tenant-a", "tenant-b")]
    await db[collection].insert_many(docs)


def _tenants(rows):
    return {r.get("tenantId") for r in rows}


# (module, singleton, method, collection, extra seed fields, extra kwargs)
SERVICE_SITES = [
    ("access_review_service", "access_review_service", "list_reviews", "access_reviews", {"status": "Completed"}, {}),
    ("audit_program_service", "audit_program_service", "list_programs", "audit_programs", {}, {}),
    ("cookie_consent_service", "cookie_consent_service", "get_records", "cookie_consent_records", {}, {}),
    ("questionnaire_service", "questionnaire_service", "list_questionnaires", "questionnaires", {}, {}),
    ("risk_service", "risk_service", "get_all_risks", "risks", {}, {}),
    ("vendor_service", "vendor_service", "get_all_vendors", "vendors", {}, {}),
    ("maturity_service", "maturity_service", "list_assessments", "maturity_assessments", {}, {}),
    ("cloud_checks_service", "cloud_checks_service", "get_results", "cloud_check_results", {}, {}),
]


@pytest.mark.parametrize("module,singleton,method,collection,extra,kwargs", SERVICE_SITES,
                         ids=[s[0] for s in SERVICE_SITES])
async def test_service_site_keeps_a_tenant_admin_in_its_tenant(mongo_db, module, singleton, method, collection,
                                                               extra, kwargs):
    await _seed(mongo_db, collection, extra)
    mod = importlib.import_module(module)
    svc = getattr(mod, singleton)
    with patch("database.get_database", return_value=mongo_db), \
            patch.object(mod, "get_database", return_value=mongo_db, create=True):
        for role in ADMINS:
            rows = await getattr(svc, method)(tenant_id="tenant-a", role=role, **kwargs)
            assert _tenants(rows) == {"tenant-a"}, (module, role)
        for role in PLATFORM:
            rows = await getattr(svc, method)(tenant_id="platform-admin", role=role, **kwargs)
            assert _tenants(rows) == {"tenant-a", "tenant-b"}, (module, role)


async def test_soa_site(mongo_db):
    import soa_service
    await _seed(mongo_db, "soa_entries", {"frameworkId": "iso27001", "controlId": "A.5"})
    with patch("database.get_database", return_value=mongo_db):
        assert _tenants(await soa_service.soa_service.get_soa("iso27001", "tenant-a", "admin")) == {"tenant-a"}
        assert _tenants(await soa_service.soa_service.get_soa("iso27001", "platform-admin", "Platform Support")) == \
            {"tenant-a", "tenant-b"}


# Agent detail endpoints that filter by tenant unless the caller is platform staff.
ENDPOINT_SITES = [
    ("agent_security_endpoints", "get_shadow_ai_scans", "shadow_ai_scans"),
    ("agent_security_endpoints", "get_vulnerability_scans", "agent_vulnerability_scans"),
    ("agent_security_endpoints", "get_malware_scans", "agent_malware_scans"),
    ("agent_security_endpoints", "get_persistence_findings", "agent_persistence_findings"),
    ("agent_telemetry_endpoints", "get_telemetry", "agent_telemetry"),
    ("agent_telemetry_endpoints", "get_detections", "agent_detections"),
]


@pytest.mark.parametrize("module,func,collection", ENDPOINT_SITES, ids=[s[1] for s in ENDPOINT_SITES])
async def test_agent_endpoint_site_keeps_a_tenant_admin_in_its_tenant(mongo_db, module, func, collection):
    await _seed(mongo_db, collection, {"agent_id": "agent-1", "scanned_at": "x", "received_at": "x"})
    mod = importlib.import_module(module)
    endpoint = getattr(mod, func)
    kwargs = {"limit": 10}
    if func in ("get_telemetry", "get_detections"):
        kwargs.update({"kind": None} if func == "get_telemetry" else {"severity": None})
    with patch.object(mod, "get_database", return_value=mongo_db):
        for role in ADMINS:
            user = TokenData(username="a@a", role=role, tenant_id="tenant-a")
            assert _tenants(await endpoint("agent-1", current_user=user, **kwargs)) == {"tenant-a"}, role
        user = TokenData(username="s@p", role="Platform Support", tenant_id="platform-admin")
        assert _tenants(await endpoint("agent-1", current_user=user, **kwargs)) == {"tenant-a", "tenant-b"}


async def test_network_devices_site(mongo_db):
    import network_endpoints
    await _seed(mongo_db, "network_devices")
    with patch.object(network_endpoints, "get_database", return_value=mongo_db):
        rows = await network_endpoints.get_network_devices(current_user=TokenData(username="a", role="admin",
                                                                                  tenant_id="tenant-a"))
    assert _tenants(rows) == {"tenant-a"}


async def test_pending_approvals_site(mongo_db):
    import agent_approval_endpoints as m
    await _seed(mongo_db, m.APPROVALS_COLLECTION, {"status": "pending"})
    rows = await m.get_pending_approvals(current_user=TokenData(username="a", role="Tenant Admin", tenant_id="tenant-a"),
                                         db=mongo_db)
    assert _tenants(rows) == {"tenant-a"}


@pytest.mark.parametrize("role", ADMINS)
def test_pure_scope_helpers(role):
    """advanced_hunting._event_scope and agent_analyze._scoped_filter build the filter itself."""
    import advanced_hunting_endpoints, agent_analyze_endpoints, compliance_framework_mgmt_endpoints
    user = TokenData(username="a", role=role, tenant_id="tenant-a")
    assert advanced_hunting_endpoints._event_scope(user) == {"tenantId": "tenant-a"}
    assert agent_analyze_endpoints._scoped_filter(user, "x")["tenantId"] == "tenant-a"
    assert not compliance_framework_mgmt_endpoints._is_super(role)
    support = TokenData(username="s", role="Platform Support", tenant_id="platform-admin")
    assert advanced_hunting_endpoints._event_scope(support) == {}


# Module-level sets the cases above do not execute: membership is the whole decision there.
SCOPE_SETS = [
    ("agent_tasks_endpoints", "_TASK_SUPER_ROLES"), ("analytics_endpoints", "_ADMIN_ROLES"),
    ("cissp_oracle_endpoints", "_CISSP_SUPER_ROLES"), ("compliance_status_endpoints", "_SUPER_ROLES"),
    ("patch_core_endpoints", "_PATCH_ADMIN_ROLES"), ("platform_endpoints", "_PLATFORM_SUPER_ROLES"),
    ("powershell_evidence_endpoints", "_SUPER_ROLES"), ("agent_approval_endpoints", "_TASK_SUPER_ROLES"),
    ("skill_handlers", "_SKILL_SUPER_ROLES"),
]


@pytest.mark.parametrize("module,attr", SCOPE_SETS, ids=[f"{m}.{a}" for m, a in SCOPE_SETS])
def test_scope_sets_by_membership(module, attr):
    roles = getattr(importlib.import_module(module), attr)
    for role in ADMINS + ["user", "viewer"]:
        assert role not in roles, (module, role)
    for role in PLATFORM:
        assert role in roles, (module, role)
