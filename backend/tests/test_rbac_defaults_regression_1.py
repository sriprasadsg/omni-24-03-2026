"""
Regression: ISSUE-005 — tenant admins see the platform-wide Service Pricing screen
Found by /qa on 2026-10-13
Report: .gstack/qa-reports/run-20261013T151919Z/qa-report-127.0.0.1-2026-10-13.md

Live repro: a tenant admin's sidebar showed "Service Pricing Configuration (applies to
all tenants)" with an Add button, because tenant_admin held manage:pricing; the pricing
API refuses tenant admins. Service pricing is platform-wide (user decision D6, QA run),
so manage:pricing is a platform-only permission.

Value: protects=no built-in tenant role holds manage:pricing and a tenant role document
cannot add it back; fails_when=manage:pricing returns to a tenant role's defaults or is
dropped from the super-admin-only set; why_new=test_rbac_defaults pins the full golden
sets but does not state pricing's platform-only rule; seam=none; no_claim=role documents
in Mongo (rbac_service._role_docs is patched to return one document).
"""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rbac_defaults
import rbac_service


@pytest.mark.parametrize("key", sorted(rbac_defaults.ROLE_DEFAULTS))
def test_no_builtin_tenant_role_grants_pricing(key):
    assert "manage:pricing" not in rbac_defaults.defaults_for(key)


def test_pricing_is_super_admin_only():
    assert "manage:pricing" in rbac_defaults.SUPER_ADMIN_ONLY_PERMISSIONS


async def test_tenant_role_document_cannot_add_pricing_back():
    doc = {"permissions": ["manage:pricing", "view:dashboard"]}
    with patch.object(rbac_service, "_role_docs", AsyncMock(return_value=[doc])):
        perms = await rbac_service.effective_permissions(None, "Tenant Admin", "tenant-a")
    assert "manage:pricing" not in perms
    assert "view:dashboard" in perms
