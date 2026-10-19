"""Phase 77 plan 10 (ACC-09, SC5, PROH-77-08): one tenant's role edit never reaches another tenant.

One in-memory role store is shared by the role write API (a bare app over ``role_endpoints.router``)
and the auth app (``/api/auth/me``). The live database, the audit ledger and shared/ files are never
touched (the audit recorder is a fake).
"""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import authentication_service as auth_svc
import permission_vocabulary as vocab
import rbac_defaults
import rbac_service
import rbac_utils
import role_endpoints
import tenant_features
from auth_types import TokenData
from authentication_service import get_current_user
from tests.rbac_test_support import make_auth_client, make_user, me, role_store, shared_role_docs

A, B = "tenant-a", "tenant-b"
HOLDER_A, HOLDER_B = "holder@a.test", "holder@b.test"
SUPER_SPELLINGS = ["Super Admin", "super_admin", "superadmin", "platform-admin", "Platform Owner"]


class _Recorder:
    async def log_action_async(self, **kwargs):
        return None


@pytest.fixture(autouse=True)
def _clean_mfa_cache():
    auth_svc._clear_mfa_role_cache()
    yield
    auth_svc._clear_mfa_role_cache()


@pytest.fixture
def store(monkeypatch):
    tenants = [{"id": A, "name": "Tenant A", "enabledFeatures": ["all"]},
               {"id": B, "name": "Tenant B", "enabledFeatures": ["all"]}]
    users = [make_user(HOLDER_A, "Helpdesk", A), make_user(HOLDER_B, "Helpdesk", B)]
    db, raw = role_store(roles=shared_role_docs(), tenants=tenants, users=users,
                         ldap_group_mappings=[], saml_group_mappings=[])
    for module in (role_endpoints, rbac_utils, rbac_service):
        monkeypatch.setattr(module, "get_database", lambda: db, raising=False)
    monkeypatch.setattr(role_endpoints, "get_audit_service", lambda: _Recorder())
    db.raw = raw
    return db


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(role_endpoints.router)
    return TestClient(app)


@pytest.fixture
def auth_client(store, monkeypatch):
    return make_auth_client(store, monkeypatch)


def call(client, method, path, role="tenant_admin", tenant=A, **kw):
    client.app.dependency_overrides[get_current_user] = (
        lambda: TokenData(username=f"{role}@x.test", role=role, tenant_id=tenant))
    try:
        return client.request(method, path, **kw)
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def make_helpdesk(client, tenant, permissions):
    res = call(client, "POST", "/api/roles", tenant=tenant,
               json={"name": "Helpdesk", "description": "Desk", "permissions": permissions})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def holder_view(auth_client, email, tenant):
    res = me(auth_client, email, "Helpdesk", tenant)
    assert res.status_code == 200, res.text
    return res


def set_features(store, tenant, features):
    for doc in store.raw.tenants.docs:
        if doc["id"] == tenant:
            doc["enabledFeatures"] = list(features)


# --- SC5: edits stay inside their tenant ---------------------------------------------------

def test_tenant_a_edit_never_changes_tenant_b(client, auth_client):
    role_a = make_helpdesk(client, A, ["view:agents"])
    make_helpdesk(client, B, ["view:logs"])
    before_a = holder_view(auth_client, HOLDER_A, A)
    before_b = holder_view(auth_client, HOLDER_B, B)
    assert "view:security" not in before_a.json()["permissions"]
    assert "view:logs" in before_b.json()["permissions"]

    edit = call(client, "PUT", f"/api/roles/{role_a}", json={"permissions": ["view:agents", "view:security"]})
    assert edit.status_code == 200, edit.text

    after_a = holder_view(auth_client, HOLDER_A, A)
    after_b = holder_view(auth_client, HOLDER_B, B)
    assert "view:security" in after_a.json()["permissions"]
    assert after_b.content == before_b.content
    assert "view:security" not in after_b.json()["permissions"]


def test_cross_tenant_role_ids_are_404(client):
    role_b = make_helpdesk(client, B, ["view:logs"])
    paths = [("GET", f"/api/roles/{role_b}/visibility"),
             ("PUT", f"/api/roles/{role_b}"),
             ("DELETE", f"/api/roles/{role_b}")]
    for method, path in paths:
        kw = {"json": {"description": "x"}} if method == "PUT" else {}
        res = call(client, method, path, **kw)
        assert res.status_code == 404, (method, path, res.status_code)
    listed = call(client, "GET", "/api/roles").json()
    assert role_b not in {r["id"] for r in listed}


def test_foreign_tenant_id_is_refused(client):
    role_a = make_helpdesk(client, A, ["view:agents"])
    body = {"name": "Other", "description": "x", "permissions": ["view:agents"], "tenantId": B}
    assert call(client, "POST", "/api/roles", json=body).status_code == 403
    assert call(client, "GET", "/api/roles", params={"tenantId": B}).status_code == 403
    assert call(client, "GET", f"/api/roles/{role_a}/visibility", params={"tenantId": B}).status_code == 403


@pytest.mark.parametrize("sentinel", ["all", "platform"])
def test_sentinel_catalogues_are_unreachable(client, store, sentinel):
    body = {"name": "Sneaky", "description": "x", "permissions": ["view:agents"], "tenantId": sentinel}
    assert call(client, "POST", "/api/roles", json=body).status_code == 403
    assert call(client, "POST", "/api/roles", json=body, role="Super Admin", tenant="platform-admin").status_code == 400
    for method in ("PUT", "DELETE"):
        kw = {"json": {"description": "x"}} if method == "PUT" else {}
        assert call(client, method, "/api/roles/role-viewer", **kw).status_code == 404
    names = {d["name"] for d in store.raw.roles.docs}
    assert "Sneaky" not in names


# --- SC5 per tenant: visibility follows each tenant's own switches -----------------------------

@pytest.mark.real_tenant_features
def test_visibility_follows_each_tenants_switches(client, store):
    role_a = make_helpdesk(client, A, ["view:agents"])  # created before A's switches narrow its admin
    edit_body = {"permissions": ["view:agents", "view:logs"]}
    set_features(store, A, ["view:agents", "view:dashboard", "view:logs", "manage:rbac"])
    set_features(store, B, ["all"])

    def seen(tenant):
        body = call(client, "GET", "/api/roles/role-viewer/visibility", tenant=tenant).json()
        visible = {s["view"] for g in body["groups"] for s in g["screens"]}
        off = {s["view"] for g in body["groups"] for s in g["switchedOff"]}
        return body, visible, off

    body_b_before, visible_b, off_b = seen(B)
    _body_a, visible_a, off_a = seen(A)
    compliance = {v for v, _l, _g, need in tenant_features.NAV_SCREENS if need == "view:compliance"}
    assert compliance and compliance <= off_a and not compliance & visible_a
    assert compliance & visible_b and not compliance & off_b

    # an edit of A's own role leaves B's payload unchanged
    assert call(client, "PUT", f"/api/roles/{role_a}", json=edit_body).status_code == 200
    body_b_after, _v, _o = seen(B)
    assert body_b_after == body_b_before


# --- SC5 super-admin handling ------------------------------------------------------------------

@pytest.mark.parametrize("spelling", SUPER_SPELLINGS)
async def test_every_super_admin_spelling_is_wildcard(client, store, spelling):
    assert await rbac_service.session_permissions(store, spelling, "platform-admin") == ["*"]
    user = TokenData(username="sa@x.test", role=spelling, tenant_id="platform-admin")
    assert await rbac_utils.verify_permission(user, "manage:tenants") is True
    assert await rbac_utils.verify_permission(user, "view:x") is True
    res = call(client, "GET", "/api/roles", role=spelling, tenant="platform-admin")
    assert res.status_code == 200, res.text
    names = {r["name"] for r in res.json()}
    assert {"Platform Support", "Platform Billing"} <= names


@pytest.mark.real_tenant_features
@pytest.mark.parametrize("key", sorted(rbac_defaults.PLATFORM_ROLE_KEYS))
async def test_platform_roles_are_never_narrowed(store, key):
    name = next(b.name for b in rbac_defaults.BUILTIN_ROLES if b.key == key)
    store.raw.tenants.docs.append(
        {"id": "platform-admin", "name": "Platform", "enabledFeatures": ["view:dashboard", "view:agents"]})
    granted = await rbac_service.granted_permissions(store, name, "platform-admin")
    effective = await rbac_service.effective_permissions(store, name, "platform-admin")
    closed = rbac_defaults.deliverable_closure(list(effective), vocab.KNOWN_PERMISSIONS)
    assert set(granted) == set(closed), key
    assert not any(p.startswith("screen-off:") for p in granted), key


# --- ACC-09 / D-14: MFA follows each tenant's own role document -----------------------------------

def test_custom_role_mfa_is_per_tenant(client, store, auth_client):
    role_a = make_helpdesk(client, A, ["view:agents"])
    make_helpdesk(client, B, ["view:logs"])
    edit = call(client, "PUT", f"/api/roles/{role_a}", json={"permissions": ["manage:rbac", "view:agents"]})
    assert edit.status_code == 200, edit.text
    with patch("database.get_database", return_value=store):
        a = holder_view(auth_client, HOLDER_A, A).json()
        b = holder_view(auth_client, HOLDER_B, B).json()
    assert a["mfa_action"] == "enroll"
    assert b["mfa_action"] is None
