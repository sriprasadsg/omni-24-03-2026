"""Phase 77 plan 07: GET /api/roles/{role_id}/visibility (D-09, D-10, D-17, SC3).

A bare FastAPI app over ``role_endpoints.router`` and one in-memory role store; the live
database is never touched. The view must equal what delivery (/login, /me) hands the role.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import rbac_defaults
import rbac_service
import rbac_utils
import role_endpoints
import tenant_features
from auth_types import TokenData
from authentication_service import get_current_user
from tests.rbac_test_support import role_store, shared_role_docs

TENANT_ROLE_KEYS = [b.key for b in rbac_defaults.BUILTIN_ROLES if b.key not in rbac_defaults.PLATFORM_ROLE_KEYS]
BUILTIN_ID = {b.key: b.role_id for b in rbac_defaults.BUILTIN_ROLES}
BUILTIN_NAME = {b.key: b.name for b in rbac_defaults.BUILTIN_ROLES}


def _custom(name, tenant, permissions):
    return {"id": f"custom-{tenant}-{name}", "name": name, "tenantId": tenant,
            "description": f"{name} role", "permissions": permissions, "isEditable": True}


@pytest.fixture
def store(monkeypatch):
    docs = shared_role_docs()
    docs += [_custom("Helpdesk", "tenant-a", ["view:agents"]),
             _custom("Empty", "tenant-a", []),
             _custom("Contractor", "tenant-b", ["view:agents"])]
    tenants = [{"id": "tenant-a", "name": "Tenant A", "enabledFeatures": ["all"]},
               {"id": "tenant-b", "name": "Tenant B", "enabledFeatures": ["all"]}]
    db, raw = role_store(roles=docs, tenants=tenants, users=[], ldap_group_mappings=[], saml_group_mappings=[])
    for module in (role_endpoints, rbac_utils, rbac_service):
        monkeypatch.setattr(module, "get_database", lambda: db, raising=False)
    db.raw = raw
    return db


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(role_endpoints.router)
    return TestClient(app)


def visibility(client, role_id, caller="tenant_admin", tenant="tenant-a", **params):
    client.app.dependency_overrides[get_current_user] = (
        lambda: TokenData(username=f"{caller}@x.test", role=caller, tenant_id=tenant))
    try:
        return client.get(f"/api/roles/{role_id}/visibility", params=params)
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def visible_views(body):
    return {s["view"] for g in body["groups"] for s in g["screens"]}


def screens(body):
    return {s["view"]: s for g in body["groups"] for s in g["screens"]}


async def delivered(store, role, tenant):
    return await rbac_service.session_permissions(store, role, tenant)


def expected_views(perms):
    return {view for view, _l, _g, need in tenant_features.NAV_SCREENS
            if need in perms and f"screen-off:{view}" not in perms}


def test_payload_shape_groups_in_manifest_order_and_totals(client):
    res = visibility(client, "role-viewer")
    assert res.status_code == 200
    body = res.json()
    assert [g["id"] for g in body["groups"]] == [g[0] for g in tenant_features.NAV_GROUPS]
    assert sum(g["total"] for g in body["groups"]) == body["totalCount"] == len(tenant_features.NAV_SCREENS) == 188
    assert body["roleId"] == "role-viewer" and body["builtIn"] is True
    assert body["basis"] == {"kind": "tenant", "tenantId": "tenant-a", "tenantName": "Tenant A"}
    assert body["visibleCount"] == sum(g["visibleCount"] for g in body["groups"])
    order = [v for v, *_ in tenant_features.NAV_SCREENS]
    for group in body["groups"]:
        views = [s["view"] for s in group["screens"]]
        assert views == sorted(views, key=order.index)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", TENANT_ROLE_KEYS)
async def test_visible_equals_delivered_permissions_for_every_builtin(client, store, key):
    res = visibility(client, BUILTIN_ID[key])
    assert res.status_code == 200, res.text
    body = res.json()
    perms = await delivered(store, BUILTIN_NAME[key], "tenant-a")
    assert visible_views(body) == expected_views(perms)
    assert body["visibleCount"] == len(expected_views(perms))


def test_itam_admin_sees_assets_and_certificates_as_manage_itam_viewer_as_view(client):
    admin = screens(visibility(client, "role-itam-admin").json())
    assert "assetManagement" in admin and "certificates" in admin
    assert admin["assetManagement"]["access"] == "manage"
    viewer = screens(visibility(client, "role-itam-viewer").json())
    assert viewer["assetManagement"]["access"] == "view"


def test_custom_role_by_id(client):
    body = visibility(client, "custom-tenant-a-Helpdesk").json()
    assert body["builtIn"] is False and body["roleName"] == "Helpdesk"
    assert screens(body)["agents"]["access"] == "view"


def test_empty_custom_role_returns_all_groups_with_zero(client):
    body = visibility(client, "custom-tenant-a-Empty").json()
    assert body["visibleCount"] == 0 and len(body["groups"]) == 8
    assert all(g["visibleCount"] == 0 and g["total"] > 0 and g["screens"] == [] for g in body["groups"])
