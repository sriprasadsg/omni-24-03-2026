"""
Regression tests for DB-F10 (2026-08-25 audit): rbac_service.find_role_doc.

roles used to be exempt from tenant isolation, so any tenant could read
every other tenant's custom role definitions (live-verified: 2 role docs
belonging to one specific tenant were readable by all tenants). Now that
roles is wrapped like any other collection, a plain db.roles.find_one with
no explicit tenantId (or one that gets overwritten by the wrapper) can
never match a genuinely global role (real tenantId "all"/"platform") —
find_role_doc is the one place allowed to bypass the wrapper for exactly
those two sentinel values.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock

from rbac_service import find_role_doc


@pytest.mark.asyncio
async def test_finds_own_tenant_role_first():
    own_role = {"name": "Custom Role", "tenantId": "tenant-a", "permissions": ["view:custom"]}
    db = MagicMock()
    db.roles.find_one = AsyncMock(return_value=own_role)
    db._db = db

    result = await find_role_doc(db, "Custom Role", "tenant-a")
    assert result == own_role
    db.roles.find_one.assert_awaited_with({"name": "Custom Role", "tenantId": "tenant-a"})


@pytest.mark.asyncio
async def test_falls_back_to_global_all_role_via_raw_db():
    global_role = {"name": "viewer", "tenantId": "all", "permissions": ["view:dashboard"]}

    async def own_tenant_find_one(query, *a, **kw):
        return None  # no tenant-specific override

    async def raw_find_one(query, *a, **kw):
        if query.get("tenantId") == "all":
            return global_role
        return None

    db = MagicMock()
    db.roles.find_one = own_tenant_find_one
    raw_db = MagicMock()
    raw_db.roles.find_one = raw_find_one
    db._db = raw_db

    result = await find_role_doc(db, "viewer", "tenant-a")
    assert result == global_role


@pytest.mark.asyncio
async def test_returns_none_when_no_role_matches_anywhere():
    db = MagicMock()
    db.roles.find_one = AsyncMock(return_value=None)
    raw_db = MagicMock()
    raw_db.roles.find_one = AsyncMock(return_value=None)
    db._db = raw_db

    result = await find_role_doc(db, "nonexistent_role", "tenant-a")
    assert result is None


@pytest.mark.asyncio
async def test_no_tenant_id_skips_own_tenant_lookup_but_still_checks_global():
    global_role = {"name": "viewer", "tenantId": "all"}
    db = MagicMock()
    db.roles.find_one = AsyncMock(side_effect=AssertionError("must not query own-tenant with no tenant_id"))
    raw_db = MagicMock()

    async def raw_find_one(query, *a, **kw):
        return global_role if query.get("tenantId") == "all" else None

    raw_db.roles.find_one = raw_find_one
    db._db = raw_db

    result = await find_role_doc(db, "viewer", None)
    assert result == global_role


@pytest.mark.asyncio
async def test_cross_tenant_role_not_visible_via_own_tenant_lookup():
    """The exact scenario DB-F10 found live: tenant-b's custom role must
    never be returned when tenant-a looks up a role by the same name."""
    db = MagicMock()

    async def own_tenant_find_one(query, *a, **kw):
        # Simulates the real wrapper: only matches docs whose tenantId
        # equals the queried tenantId.
        if query.get("tenantId") == "tenant-a":
            return None  # tenant-a has no "itam_admin" role of its own
        return None

    db.roles.find_one = own_tenant_find_one
    raw_db = MagicMock()
    raw_db.roles.find_one = AsyncMock(return_value=None)  # no global "itam_admin" either
    db._db = raw_db

    # tenant-b owns a real "itam_admin" role doc, but tenant-a's lookup
    # must never see it.
    result = await find_role_doc(db, "itam_admin", "tenant-a")
    assert result is None
