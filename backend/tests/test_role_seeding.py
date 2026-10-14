"""SC4 (ACC-02): startup mirrors rbac_defaults into the 13 shared role documents (11 + spec C1's two platform roles).

Runs the real seed_database() over the real TenantIsolatedDatabase wrapper (in-memory
collections) inside the platform-admin tenant context, exactly as the app lifespan does.
"""
import contextvars
import copy
from unittest.mock import AsyncMock

import pytest

import app_startup
import rbac_defaults
import tenant_context
from tests.rbac_test_support import StoreCollection, make_user, role_store

SHARED_NAMES = {
    "Super Admin", "Tenant Admin", "admin", "analyst", "security_analyst",
    "incident_responder", "user", "viewer", "itam_admin", "itam_user", "itam_viewer",
    "Platform Support", "Platform Billing",
}
SHARED_TENANTS = {"platform", "all"}

TENANT_VIEWER = {
    "id": "role-tenant-x-viewer", "name": "viewer", "tenantId": "tenant_x",
    "permissions": ["custom:only"], "description": "tenant's own", "isEditable": True,
}


def _seed_store(roles=None):
    super_admin = make_user("super@omni.ai", "Super Admin", "platform-admin")
    db, raw = role_store(users=[super_admin], roles=list(roles or []), tenants=[{"id": "platform-admin"}])
    return db, raw


def _run_seed(monkeypatch, db, *, tenant="platform-admin"):
    monkeypatch.setattr(app_startup, "get_database", lambda: db)
    monkeypatch.setattr(app_startup, "run_migrations", AsyncMock())

    async def _go():
        if tenant:
            tenant_context.set_tenant_id(tenant)
        await app_startup.seed_database()

    import asyncio
    contextvars.Context().run(lambda: asyncio.run(_go()))


def _shared(raw):
    return [d for d in raw.roles.docs if d.get("tenantId") in SHARED_TENANTS]


def _by_name(raw):
    return {d["name"]: d for d in _shared(raw)}


def test_seeds_thirteen_shared_documents_and_leaves_tenant_document_untouched(monkeypatch):
    db, raw = _seed_store([copy.deepcopy(TENANT_VIEWER)])
    _run_seed(monkeypatch, db)
    shared = _shared(raw)
    assert len(shared) == 13
    assert {d["name"] for d in shared} == SHARED_NAMES
    tenant_docs = [d for d in raw.roles.docs if d.get("tenantId") == "tenant_x"]
    assert tenant_docs == [TENANT_VIEWER]
    by_name = _by_name(raw)
    platform_names = {"Super Admin", "Platform Support", "Platform Billing"}
    for name in platform_names:  # spec C1: platform roles live in the "platform" catalogue
        assert by_name[name]["tenantId"] == "platform"
    assert by_name["Super Admin"]["permissions"] == ["*"]
    for name in SHARED_NAMES - platform_names:
        assert by_name[name]["tenantId"] == "all"


def test_each_shared_document_equals_the_table(monkeypatch):
    db, raw = _seed_store()
    _run_seed(monkeypatch, db)
    by_name = _by_name(raw)
    for role in rbac_defaults.BUILTIN_ROLES:
        doc = by_name[role.name]
        assert doc["permissions"] == list(rbac_defaults.defaults_for(role.key))
        assert doc["id"] == role.role_id
        assert doc["isEditable"] is role.is_editable


def test_seeding_twice_is_idempotent(monkeypatch):
    db, raw = _seed_store()
    _run_seed(monkeypatch, db)
    _run_seed(monkeypatch, db)
    assert len(_shared(raw)) == 13
    assert len(raw.roles.docs) == 13


def test_live_shaped_super_admin_updated_in_place(monkeypatch):
    live = {"id": "role-super-admin", "name": "Super Admin", "tenantId": "platform",
            "permissions": [f"view:x{i}" for i in range(95)] + ["admin:*"], "isEditable": False}
    db, raw = _seed_store([live])
    _run_seed(monkeypatch, db)
    supers = [d for d in raw.roles.docs if d["name"] == "Super Admin"]
    assert len(supers) == 1
    assert supers[0]["tenantId"] == "platform"
    assert supers[0]["permissions"] == ["*"]


def test_manual_edit_of_shared_document_is_reverted(monkeypatch):
    stale = {"id": "role-tenant-admin", "name": "Tenant Admin", "tenantId": "all",
             "permissions": ["view:dashboard", "manage:tenants"], "isEditable": False}
    db, raw = _seed_store([stale])
    _run_seed(monkeypatch, db)
    doc = _by_name(raw)["Tenant Admin"]
    assert "manage:tenants" not in doc["permissions"]
    assert doc["permissions"] == list(rbac_defaults.defaults_for("tenant_admin"))


def test_seeding_without_tenant_context_still_writes_all_documents(monkeypatch):
    db, raw = _seed_store([copy.deepcopy(TENANT_VIEWER)])
    _run_seed(monkeypatch, db, tenant=None)
    assert len(_shared(raw)) == 13
    assert [d for d in raw.roles.docs if d.get("tenantId") == "tenant_x"] == [TENANT_VIEWER]


def test_one_failed_document_does_not_stop_others_and_seed_never_re_adds_itam(monkeypatch, caplog):
    # ITAM is a per-tenant feature switch (spec C6); its one-time backfill is migration 016,
    # so seeding must not re-enable it on every startup.
    db, raw = _seed_store()
    real = raw.roles.update_one

    async def flaky(flt, update, **kw):
        if flt.get("name") == "Super Admin":
            raise RuntimeError("simulated write failure")
        return await real(flt, update, **kw)

    raw.roles.update_one = flaky
    calls = []
    real_many = raw.tenants.update_many

    async def spy_many(flt, update, **kw):
        calls.append(flt)
        return await real_many(flt, update, **kw)

    raw.tenants.update_many = spy_many
    with caplog.at_level("ERROR"):
        _run_seed(monkeypatch, db)
    assert {d["name"] for d in _shared(raw)} == SHARED_NAMES - {"Super Admin"}
    assert any("Super Admin" in r.getMessage() for r in caplog.records)
    assert not [f for f in calls if "enabledFeatures" in str(f)], "seeding must not re-add ITAM features"
