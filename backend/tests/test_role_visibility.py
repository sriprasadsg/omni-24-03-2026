"""Phase 77 plan 07: GET /api/roles/{role_id}/visibility (D-09, D-10, D-17, SC3).

A bare FastAPI app over ``role_endpoints.router`` and one in-memory role store; the live
database is never touched. The view must equal what delivery (/login, /me) hands the role.
"""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import rbac_defaults
import rbac_service
import rbac_utils
import catalogue_guards
import role_visibility
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


# ── Task 2: switches, platform roles, Super Admin tenants, equality with enforcement ──

SWITCH_CONFIGS = {"all_on": ["all"], "agents_only": ["view:agents"],
                  "security_edr": ["view:security", "screen:edr"]}


def set_features(store, features, tenant="tenant-a"):
    for doc in store.raw.tenants.docs:
        if doc["id"] == tenant:
            doc["enabledFeatures"] = list(features)


def switched(body):
    return {s["view"] for g in body["groups"] for s in g["switchedOff"]}


@pytest.mark.real_tenant_features
def test_a_tenant_that_switched_a_feature_off_lists_its_screens_apart(client, store):
    set_features(store, ["view:agents", "screen:agents"])
    body = visibility(client, "role-tenant-admin").json()
    assert "compliance" in switched(body) and "compliance" not in visible_views(body)
    assert "agents" in visible_views(body)
    assert body["visibleCount"] == len(visible_views(body))
    # agents shares view:agents with Agent Approvals, so it also has its own screen switch:
    # the feature alone does not show it (the pipeline, not the permission string, decides).
    set_features(store, ["view:agents"])
    assert "agents" in switched(visibility(client, "role-tenant-admin").json())


@pytest.mark.real_tenant_features
def test_a_per_screen_switch_lists_the_screen_apart(client, store):
    set_features(store, ["view:security", "screen:edr"])
    body = visibility(client, "role-tenant-admin").json()
    assert "alertManagement" in switched(body) and "alertManagement" not in visible_views(body)
    assert "edr" in visible_views(body)


@pytest.mark.real_tenant_features
@pytest.mark.parametrize("config", list(SWITCH_CONFIGS))
@pytest.mark.parametrize("key", TENANT_ROLE_KEYS)
def test_no_screen_is_both_visible_and_switched_off(client, store, key, config):
    set_features(store, SWITCH_CONFIGS[config])
    body = visibility(client, BUILTIN_ID[key]).json()
    for group in body["groups"]:
        shown = {s["view"] for s in group["screens"]}
        assert not shown & {s["view"] for s in group["switchedOff"]}
        assert group["visibleCount"] == len(group["screens"])


def test_super_admin_sees_everything_as_manage_on_a_platform_basis(client):
    body = visibility(client, "role-super-admin", caller="super_admin", tenant=None).json()
    assert body["basis"]["kind"] == "platform_role"
    assert body["visibleCount"] == body["totalCount"]
    assert all(s["access"] == "manage" for g in body["groups"] for s in g["screens"])


def test_platform_support_is_a_platform_role_and_never_narrowed(client, store):
    set_features(store, [])
    body = visibility(client, "role-platform-support", caller="super_admin", tenant=None).json()
    assert body["basis"]["kind"] == "platform_role"
    assert all(g["switchedOff"] == [] for g in body["groups"])


@pytest.mark.parametrize("caller", ["tenant_admin", "itam_admin"])
def test_platform_roles_are_404_for_a_tenant_caller(client, caller):
    assert visibility(client, "role-platform-support", caller=caller).status_code == 404
    assert visibility(client, "role-super-admin", caller=caller).status_code == 404


@pytest.mark.real_tenant_features
def test_super_admin_with_a_tenant_is_narrowed_by_that_tenant(client, store):
    set_features(store, ["view:agents"])
    body = visibility(client, "role-tenant-admin", caller="super_admin", tenant=None, tenantId="tenant-a").json()
    assert body["basis"] == {"kind": "tenant", "tenantId": "tenant-a", "tenantName": "Tenant A"}
    assert "compliance" in switched(body)


def test_super_admin_without_a_tenant_sees_a_built_in_unnarrowed(client):
    body = visibility(client, "role-viewer", caller="super_admin", tenant=None).json()
    assert body["basis"] == {"kind": "no_tenant", "tenantId": None, "tenantName": None}
    assert all(g["switchedOff"] == [] for g in body["groups"])


def test_super_admin_without_a_tenant_cannot_see_a_custom_role(client):
    res = visibility(client, "custom-tenant-a-Helpdesk", caller="super_admin", tenant=None)
    assert res.status_code == 400 and "Select a tenant" in res.json()["detail"]


def test_super_admin_with_a_tenant_sees_its_custom_role(client):
    res = visibility(client, "custom-tenant-a-Helpdesk", caller="super_admin", tenant=None, tenantId="tenant-a")
    assert res.status_code == 200 and "agents" in visible_views(res.json())


def test_a_foreign_tenant_id_is_403_and_a_foreign_custom_role_is_404(client):
    assert visibility(client, "role-viewer", tenantId="tenant-b").status_code == 403
    assert visibility(client, "custom-tenant-b-Contractor").status_code == 404


def test_authorization_follows_manage_users_or_manage_rbac(client):
    assert visibility(client, "role-viewer", caller="viewer").status_code == 403
    assert visibility(client, "role-viewer", caller="itam_admin").status_code == 200


def test_unknown_role_is_404(client):
    assert visibility(client, "role-does-not-exist").status_code == 404


def test_store_failure_is_503(client, store, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(role_endpoints, "effective_permissions", boom)
    assert visibility(client, "role-viewer").status_code == 503


# SC3: the three enforce:true groups agree with the backend guard.
_MANIFEST = json.loads((Path(tenant_features.__file__).resolve().parent.parent / "shared" / "catalogue-access.json").read_text())
_ENFORCED = {g["id"] for g in _MANIFEST["groups"] if g.get("enforce")}
CHECKED = [e for e in _MANIFEST["catalogues"]
           if e.get("nav") and e["group"] in _ENFORCED and e.get("routes") and not e.get("read")
           and e["view"] not in tenant_features.HIDE_ONLY_SCREENS]


def test_the_property_covers_the_three_enforced_groups():
    assert _ENFORCED == {"infra", "security", "mgmt"} and len(CHECKED) > 30
    assert len(TENANT_ROLE_KEYS) >= 9


@pytest.mark.asyncio
@pytest.mark.real_tenant_features
@pytest.mark.parametrize("config", list(SWITCH_CONFIGS))
@pytest.mark.parametrize("key", TENANT_ROLE_KEYS)
async def test_visible_equals_the_backend_guard_for_enforced_groups(store, key, config):
    set_features(store, SWITCH_CONFIGS[config])
    effective = await rbac_service.effective_permissions(store, BUILTIN_NAME[key], "tenant-a")
    enabled = SWITCH_CONFIGS[config]
    body = role_visibility.build_visibility(
        role_id=BUILTIN_ID[key], role_name=BUILTIN_NAME[key], built_in=True, effective=effective,
        enabled=enabled, narrowed=True, basis={"kind": "tenant", "tenantId": "tenant-a", "tenantName": "A"})
    shown = visible_views(body)
    user = TokenData(username="u@x.test", role=BUILTIN_NAME[key], tenant_id="tenant-a")
    held = role_visibility.delivered_for(effective, enabled, narrowed=True)
    on = set(tenant_features.screen_permissions(held, enabled))
    for entry in CHECKED:
        perm = entry["permission"]
        try:
            await catalogue_guards.check_catalogue_access(user, "GET", read=(perm,), write=(perm,))
            allowed = True
        except Exception:
            allowed = False
        owner = tenant_features.screen_of(entry["routes"][0])
        if allowed and owner == entry["view"]:
            allowed = f"screen:{owner}" in on
        assert (entry["view"] in shown) == allowed, (key, config, entry["view"])
