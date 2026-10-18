"""SC4 (ACC-02) / D-15 / D-16: GET /api/roles is the real, gated role list.

Built-in roles come from the single table, the caller's own tenant adds its custom
role documents, and every entry's permissions are computed by
rbac_service.effective_permissions (the resolver /me uses). The route needs
manage:users or manage:rbac.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import rbac_defaults
import rbac_service
import rbac_utils
import role_endpoints
from auth_types import TokenData
from authentication_service import get_current_user
from tests.rbac_test_support import role_store, shared_role_docs

BUILTIN_NAMES = [r.name for r in rbac_defaults.BUILTIN_ROLES if r.key not in rbac_defaults.PLATFORM_ROLE_KEYS]
PLATFORM_NAMES = [r.name for r in rbac_defaults.BUILTIN_ROLES if r.key in rbac_defaults.PLATFORM_ROLE_KEYS]


def _custom(name, tenant, permissions, **extra):
    doc = {"id": f"custom-{tenant}-{name}", "name": name, "tenantId": tenant,
           "description": f"{name} role", "permissions": permissions, "isEditable": True}
    doc.update(extra)
    return doc


def _docs():
    docs = shared_role_docs()
    docs.append(_custom("Helpdesk", "tenant-a", ["view:tickets"]))
    docs.append(_custom("Contractor", "tenant-b", ["view:contractor_only"]))
    docs.append(_custom("rbacmgr", "tenant-a", ["manage:rbac"]))
    # A tenant document sharing a built-in's name extends that built-in, it is not a second entry.
    docs.append(_custom("viewer", "tenant-a", ["view:viewer_extra"]))
    return docs


@pytest.fixture
def store(monkeypatch):
    db, _raw = role_store(roles=_docs())
    monkeypatch.setattr(role_endpoints, "get_database", lambda: db, raising=False)
    monkeypatch.setattr(rbac_utils, "get_database", lambda: db)
    return db


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(role_endpoints.router)
    return TestClient(app)


def _get(client, role, tenant="tenant-a"):
    client.app.dependency_overrides[get_current_user] = (
        lambda: TokenData(username=f"{role}@x.test", role=role, tenant_id=tenant))
    try:
        return client.get("/api/roles")
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def test_tenant_admin_lists_every_builtin_role_including_itam(client):
    res = _get(client, "Tenant Admin")
    assert res.status_code == 200, res.text
    names = [r["name"] for r in res.json()]
    for expected in BUILTIN_NAMES:
        assert expected in names
    for itam in ("itam_admin", "itam_user", "itam_viewer"):
        assert itam in names
    for platform in PLATFORM_NAMES:  # spec C1: platform roles are listed for the owner only
        assert platform not in names


@pytest.mark.asyncio
async def test_builtin_permissions_come_from_the_shared_resolver(client, store):
    res = _get(client, "Tenant Admin")
    by_name = {r["name"]: r for r in res.json()}
    for name in BUILTIN_NAMES:
        expected = await rbac_service.effective_permissions(store, name, "tenant-a")
        assert by_name[name]["permissions"] == expected, name


def test_own_tenant_custom_role_listed_and_other_tenant_hidden(client):
    names = [r["name"] for r in _get(client, "Tenant Admin").json()]
    assert "Helpdesk" in names
    assert "Contractor" not in names
    by_name = {r["name"]: r for r in _get(client, "Tenant Admin").json()}
    assert by_name["Helpdesk"]["permissions"] == ["view:tickets"]
    assert by_name["Helpdesk"]["tenantId"] == "tenant-a"
    # The other tenant sees its own document, not tenant-a's.
    other = [r["name"] for r in _get(client, "Tenant Admin", "tenant-b").json()]
    assert "Contractor" in other and "Helpdesk" not in other


def test_tenant_document_named_like_a_builtin_is_not_listed_twice(client):
    entries = [r for r in _get(client, "Tenant Admin").json() if r["name"] == "viewer"]
    assert len(entries) == 1
    assert "view:viewer_extra" in entries[0]["permissions"]


@pytest.mark.parametrize("role", ["itam_admin", "rbacmgr"])
def test_manage_users_or_manage_rbac_holders_get_200(client, role):
    assert _get(client, role).status_code == 200


@pytest.mark.parametrize("role", ["viewer", "user", "itam_viewer"])
def test_callers_without_manage_users_or_rbac_get_403(client, role):
    res = _get(client, role)
    assert res.status_code == 403
    assert "manage:users" in res.json()["detail"] and "manage:rbac" in res.json()["detail"]


def test_super_admin_sees_super_admin_entry(client):
    res = _get(client, "Super Admin")
    assert res.status_code == 200
    by_name = {r["name"]: r for r in res.json()}
    assert by_name["Super Admin"]["permissions"] == ["*"]
    assert set(PLATFORM_NAMES) <= set(by_name)


def test_every_entry_has_the_role_shape_and_no_all_permission(client):
    for caller in ("Tenant Admin", "Super Admin"):
        for entry in _get(client, caller).json():
            for field in ("id", "name", "description", "permissions", "isEditable", "tenantId"):
                assert field in entry, (entry.get("name"), field)
            assert "all" not in entry["permissions"]


def test_role_store_error_answers_503_not_a_partial_list(client, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("mongo down")

    monkeypatch.setattr(role_endpoints, "effective_permissions", boom, raising=False)
    res = _get(client, "Tenant Admin")
    assert res.status_code == 503
    assert res.json()["detail"] == "Role store unavailable"


def test_every_entry_carries_the_builtin_flag(client):
    """D-18: builtIn is true for the table roles and false for tenant documents (isEditable is unchanged)."""
    entries = _get(client, "Tenant Admin").json()
    by_name = {r["name"]: r for r in entries}
    assert by_name["Helpdesk"]["builtIn"] is False and by_name["Helpdesk"]["isEditable"] is True
    assert by_name["rbacmgr"]["builtIn"] is False
    for name in BUILTIN_NAMES:
        assert by_name[name]["builtIn"] is True, name


# --- Phase 77 plan 03, Task 3: Super Admin tenant targeting and the grantable catalogue -------

def _get_path(client, path, role, tenant="tenant-a"):
    client.app.dependency_overrides[get_current_user] = (
        lambda: TokenData(username=f"{role}@x.test", role=role, tenant_id=tenant))
    try:
        return client.get(path)
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def two_tenants(store):
    store._db.tenants.docs.extend([{"id": "tenant-a"}, {"id": "tenant-b"}])
    return store


def test_super_admin_with_tenant_id_sees_that_tenants_custom_roles(client, two_tenants):
    res = _get_path(client, "/api/roles?tenantId=tenant-b", "Super Admin", "platform-admin")
    assert res.status_code == 200, res.text
    by_name = {r["name"]: r for r in res.json()}
    assert by_name["Contractor"]["builtIn"] is False and by_name["Contractor"]["tenantId"] == "tenant-b"
    assert "Helpdesk" not in by_name
    assert set(PLATFORM_NAMES) <= set(by_name)


def test_super_admin_without_tenant_id_gets_the_builtin_roles_only(client, two_tenants):
    res = _get_path(client, "/api/roles", "Super Admin", "platform-admin")
    assert res.status_code == 200
    assert all(r["builtIn"] for r in res.json())
    assert len(res.json()) == len(rbac_defaults.BUILTIN_ROLES)


@pytest.mark.parametrize("target", ["platform-admin", "all", "platform", "tenant-zzz"])
def test_super_admin_cannot_target_a_sentinel_or_unknown_tenant(client, two_tenants, target):
    assert _get_path(client, f"/api/roles?tenantId={target}", "Super Admin", "platform-admin").status_code == 400


def test_tenant_admin_cannot_list_another_tenant(client, two_tenants):
    assert _get_path(client, "/api/roles?tenantId=tenant-b", "tenant_admin").status_code == 403
    assert _get_path(client, "/api/roles?tenantId=tenant-a", "tenant_admin").status_code == 200


def test_permission_catalogue_for_a_tenant_admin_is_its_closure_within_the_grantable_set(client, store):
    import role_contents
    res = _get_path(client, "/api/roles/permission-catalogue", "tenant_admin")
    assert res.status_code == 200, res.text
    body = res.json()
    effective = set(rbac_defaults.defaults_for("tenant_admin"))
    expected = sorted(rbac_defaults.implied_closure(effective) & role_contents.GRANTABLE_PERMISSIONS)
    assert body == {"permissions": expected, "superAdmin": False}
    banned = {"*", "manage:tenants"} | set(rbac_defaults.PLATFORM_ONLY_PERMISSIONS)
    assert not banned & set(body["permissions"])


def test_permission_catalogue_for_the_super_admin_is_every_grantable_string(client, store):
    import role_contents
    body = _get_path(client, "/api/roles/permission-catalogue", "Super Admin", "platform-admin").json()
    assert body == {"permissions": sorted(role_contents.GRANTABLE_PERMISSIONS), "superAdmin": True}


@pytest.mark.parametrize("role", ["viewer", "itam_admin"])
def test_permission_catalogue_needs_manage_rbac(client, store, role):
    assert _get_path(client, "/api/roles/permission-catalogue", role).status_code == 403
