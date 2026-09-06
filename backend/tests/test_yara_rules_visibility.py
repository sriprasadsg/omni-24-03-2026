"""Regression test: GET /api/analysis/yara-rules (list_yara_rules) must
show built-in rules to every tenant, not just platform-admin.

Live-verified in this environment: 30 built-in rules exist in
custom_yara_rules, all with tenantId="platform-admin" (seeded by
app_startup._seed_yara_rules, which writes via the raw unwrapped
collection). But list_yara_rules queried through the tenant-isolation-
wrapped database — TenantIsolatedCollection._inject_tenant_id forcibly
rescopes every find() to the caller's own tenantId for any non-
platform-admin caller, so a regular tenant's query could never match
those platform-admin-scoped docs. Every regular tenant's YARA Rule Editor
showed "0 built-in" regardless of how many built-in rules existed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock

from binary_analysis_endpoints import list_yara_rules
from auth_types import TokenData


def _mock_db(own_tenant_rules, builtin_rules):
    db = MagicMock()
    own_cursor = MagicMock()
    own_cursor.to_list = AsyncMock(return_value=own_tenant_rules)
    db.custom_yara_rules.find = MagicMock(return_value=own_cursor)

    raw_cursor = MagicMock()
    raw_cursor.to_list = AsyncMock(return_value=builtin_rules)
    db._db = MagicMock()
    db._db.custom_yara_rules.find = MagicMock(return_value=raw_cursor)
    return db


@pytest.mark.asyncio
async def test_regular_tenant_sees_builtin_rules_merged_with_own(monkeypatch):
    builtins = [{"id": "builtin_ransomware_x", "source": "builtin", "tenantId": "platform-admin"}]
    own = [{"id": "custom-1", "source": "custom", "tenantId": "tenant-a"}]
    db = _mock_db(own_tenant_rules=own, builtin_rules=builtins)
    monkeypatch.setattr("binary_analysis_endpoints.get_database", lambda: db)

    result = await list_yara_rules(current_user=TokenData(tenant_id="tenant-a", username="u1"))

    assert builtins[0] in result
    assert own[0] in result
    assert len(result) == 2
    # The wrapped, tenant-scoped path must never be asked to fetch built-ins
    # directly (it structurally can't return them) — the raw path is what
    # supplies them.
    db._db.custom_yara_rules.find.assert_called_once_with(
        {"source": "builtin", "tenantId": "platform-admin"}, {"_id": 0}
    )


@pytest.mark.asyncio
async def test_regular_tenant_with_no_custom_rules_still_sees_builtins(monkeypatch):
    """The exact reported scenario: a tenant with zero custom rules must
    still see the 30 seeded built-ins, not "0 built-in, 0 custom"."""
    builtins = [{"id": f"builtin_{i}", "source": "builtin", "tenantId": "platform-admin"} for i in range(30)]
    db = _mock_db(own_tenant_rules=[], builtin_rules=builtins)
    monkeypatch.setattr("binary_analysis_endpoints.get_database", lambda: db)

    result = await list_yara_rules(current_user=TokenData(tenant_id="tenant-a", username="u1"))

    assert len(result) == 30
    assert all(r["source"] == "builtin" for r in result)


@pytest.mark.asyncio
async def test_platform_admin_does_not_double_fetch_builtins(monkeypatch):
    """Platform-admin's query already bypasses tenant injection entirely
    (TenantIsolatedCollection._inject_tenant_id's Super Admin bypass), so
    db.custom_yara_rules.find({"tenantId": "platform-admin"}) alone already
    returns the built-ins — merging in the raw fetch too would double-count
    them."""
    builtins_via_wrapper = [{"id": "builtin_x", "source": "builtin", "tenantId": "platform-admin"}]
    db = _mock_db(own_tenant_rules=builtins_via_wrapper, builtin_rules=[{"id": "should-not-appear"}])
    monkeypatch.setattr("binary_analysis_endpoints.get_database", lambda: db)

    result = await list_yara_rules(current_user=TokenData(tenant_id="platform-admin", username="admin"))

    assert result == builtins_via_wrapper
    db._db.custom_yara_rules.find.assert_not_called()
