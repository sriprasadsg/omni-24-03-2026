"""
Unit tests for TenantIsolatedCollection and get_database().

These tests verify that:
 - Tenant context is correctly injected into every DB query
 - Platform-admin bypasses tenant isolation (super admin path)
 - Missing tenant context uses the emergency fallback to prevent data leakage
 - get_database() raises RuntimeError when the database isn't connected (our fix)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_col():
    col = MagicMock()
    col.find_one      = AsyncMock(return_value=None)
    col.find          = MagicMock(return_value=MagicMock())
    col.count_documents = AsyncMock(return_value=0)
    col.update_one    = AsyncMock(return_value=MagicMock(matched_count=1))
    col.aggregate     = MagicMock(return_value=MagicMock())
    return col


# ===========================================================================
# TenantIsolatedCollection — _inject_tenant_id
# ===========================================================================

class TestTenantInjection:

    def test_injects_tenant_id_for_scoped_user(self):
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("tenant-xyz")
        col = TenantIsolatedCollection(_make_col())
        result = col._inject_tenant_id({"status": "open"})

        assert result["tenantId"] == "tenant-xyz"
        assert result["status"] == "open"

    def test_platform_admin_bypasses_injection(self):
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("platform-admin")
        col = TenantIsolatedCollection(_make_col())
        result = col._inject_tenant_id({"status": "open"})

        assert "tenantId" not in result

    def test_empty_filter_gets_tenant_added(self):
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("t-abc")
        col = TenantIsolatedCollection(_make_col())
        result = col._inject_tenant_id({})

        assert result == {"tenantId": "t-abc"}

    def test_no_tenant_context_uses_emergency_string(self):
        """Fail-closed: missing context must never return another tenant's data."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id(None)
        col = TenantIsolatedCollection(_make_col())
        result = col._inject_tenant_id({})

        assert result["tenantId"] == "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"

    def test_tenant_id_overwrites_caller_supplied_value(self):
        """Context-var tenant always wins — callers cannot self-escalate."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("real-tenant")
        col = TenantIsolatedCollection(_make_col())
        result = col._inject_tenant_id({"tenantId": "evil-attempt"})

        assert result["tenantId"] == "real-tenant"


# ===========================================================================
# TenantIsolatedCollection — find / count_documents pass-through
# ===========================================================================

class TestCollectionPassThrough:

    def test_find_injects_tenant_into_underlying_call(self):
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("t1")
        inner = _make_col()
        col = TenantIsolatedCollection(inner)
        col.find({"status": "open"})

        inner.find.assert_called_once()
        call_filter = inner.find.call_args[0][0]
        assert call_filter["tenantId"] == "t1"
        assert call_filter["status"] == "open"

    def test_find_one_injects_tenant_into_underlying_call(self):
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("t2")
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        import asyncio
        asyncio.run(col.find_one({"id": "abc"}))

        inner.find_one.assert_called_once()
        call_filter = inner.find_one.call_args[0][0]
        assert call_filter["tenantId"] == "t2"
        assert call_filter["id"] == "abc"


# ===========================================================================
# TenantIsolatedDatabase — collection routing
# ===========================================================================

class TestDatabaseRouting:

    def test_exempt_collections_bypass_isolation(self):
        """Global reference data (roles, tenants) must NOT be tenant-scoped."""
        from database import TenantIsolatedCollection, TenantIsolatedDatabase

        raw_db = MagicMock()
        raw_db.roles = _make_col()
        raw_db.tenants = _make_col()

        db = TenantIsolatedDatabase(raw_db)

        assert db["roles"] is raw_db["roles"] or not isinstance(db["roles"], TenantIsolatedCollection)
        # Access via attribute (the other access path)
        assert not isinstance(db.roles, TenantIsolatedCollection)
        assert not isinstance(db.tenants, TenantIsolatedCollection)

    def test_regular_collections_are_wrapped(self):
        from database import TenantIsolatedCollection, TenantIsolatedDatabase

        raw_db = MagicMock()
        db = TenantIsolatedDatabase(raw_db)

        assert isinstance(db["tickets"], TenantIsolatedCollection)
        assert isinstance(db["security_events"], TenantIsolatedCollection)


# ===========================================================================
# get_database() — RuntimeError when db is None (our fix)
# ===========================================================================

class TestGetDatabase:

    def test_raises_runtime_error_when_not_connected(self):
        """Before the fix, get_database() returned None causing confusing TypeErrors."""
        from database import get_database, mongodb

        original = mongodb.db
        mongodb.db = None
        try:
            with pytest.raises(RuntimeError, match="Database not connected"):
                get_database()
        finally:
            mongodb.db = original

    def test_returns_isolated_database_when_connected(self):
        from database import get_database, mongodb, TenantIsolatedDatabase

        if mongodb.db is None:
            pytest.skip("MongoDB not running in this environment")

        result = get_database()
        assert isinstance(result, TenantIsolatedDatabase)
