"""Phase 77 plan 03: the tenant custom-role write API (D-01, D-02, D-13, D-15, D-17, D-18).

A bare FastAPI app over ``role_endpoints.router`` and one in-memory role store; the live
database and the audit ledger are never touched (the audit recorder is a fake).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import rbac_defaults
import rbac_service
import rbac_utils
import role_contents
import role_endpoints
from auth_types import TokenData
from authentication_service import get_current_user
from tests.rbac_test_support import StoreCollection, make_user, role_store, shared_role_docs

COPY_BUILTIN = 'That name matches the built-in role "{}". Choose a different name.'
COPY_RENAME = "A role's name can't be changed. To rename, create a new role and reassign its users."


def _custom(name, tenant, permissions, **extra):
    doc = {"id": f"custom-{tenant}-{name}", "name": name, "tenantId": tenant,
           "description": f"{name} role", "permissions": permissions, "isEditable": True}
    doc.update(extra)
    return doc


class _Recorder:
    def __init__(self):
        self.calls = []
        self.fail = False

    async def log_action_async(self, **kwargs):
        if self.fail:
            raise RuntimeError("ledger down")
        self.calls.append(kwargs)


@pytest.fixture
def audit(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(role_endpoints, "get_audit_service", lambda: rec)
    return rec


@pytest.fixture
def store(monkeypatch):
    docs = shared_role_docs()
    docs.append(_custom("Contractor", "tenant-b", ["view:agents"]))
    docs.append(_custom("rbacmgr", "tenant-a", ["manage:rbac", "view:agents"]))
    docs.append(_custom("viewer", "tenant-a", ["view:viewer_extra"]))  # legacy doc extending a built-in
    tenants = [{"id": "tenant-a", "name": "A"}, {"id": "tenant-b", "name": "B"}]
    db, raw = role_store(roles=docs, tenants=tenants, users=[], ldap_group_mappings=[], saml_group_mappings=[])
    for module in (role_endpoints, rbac_utils, rbac_service):
        monkeypatch.setattr(module, "get_database", lambda: db, raising=False)
    db.raw = raw
    return db


@pytest.fixture
def client(store, audit):
    app = FastAPI()
    app.include_router(role_endpoints.router)
    return TestClient(app)


def call(client, method, path, role="tenant_admin", tenant="tenant-a", **kw):
    client.app.dependency_overrides[get_current_user] = (
        lambda: TokenData(username=f"{role}@x.test", role=role, tenant_id=tenant))
    try:
        return client.request(method, path, **kw)
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def create(client, body, **kw):
    return call(client, "POST", "/api/roles", json=body, **kw)


def stored(store, tenant):
    return [d for d in store.raw.roles.docs if d.get("tenantId") == tenant]


HELPDESK = {"name": "Helpdesk", "description": "Desk", "permissions": ["view:dashboard", "view:agents"]}


# --- Task 1: create ----------------------------------------------------------------------

def test_create_returns_a_custom_role_and_stores_the_document(client, store):
    res = create(client, HELPDESK)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["builtIn"] is False and body["isEditable"] is True
    assert body["tenantId"] == "tenant-a" and body["id"].startswith("role-")
    assert body["permissions"] == ["view:agents", "view:dashboard"]
    doc = next(d for d in stored(store, "tenant-a") if d["name"] == "Helpdesk")
    assert doc["nameKey"] == "helpdesk" and doc["createdBy"] and doc["createdAt"]


def test_listing_marks_custom_and_builtin_roles(client):
    create(client, HELPDESK)
    roles = call(client, "GET", "/api/roles").json()
    by_name = {r["name"]: r for r in roles}
    assert by_name["Helpdesk"]["builtIn"] is False
    builtin_names = {b.name for b in rbac_defaults.BUILTIN_ROLES}
    for role in roles:
        if role["name"] in builtin_names:
            assert role["builtIn"] is True, role["name"]
    assert "Contractor" not in by_name


@pytest.mark.asyncio
async def test_the_holder_gets_the_permissions_from_the_shared_resolver(client, store):
    create(client, HELPDESK)
    perms = await rbac_service.session_permissions(store, "Helpdesk", "tenant-a")
    assert "view:agents" in perms


@pytest.mark.parametrize("name", ["Tenant Admin", "tenant-admin", "super admin", "SuperAdmin",
                                  "platform-admin", "Platform Owner", "itam_admin", "agent", "Agent",
                                  "viewer", "Viewer", "admin", "Platform Support"])
def test_reserved_names_are_refused_in_every_spelling(client, name):
    res = create(client, {**HELPDESK, "name": name})
    assert res.status_code == 400, (name, res.text)


def test_builtin_collision_message_uses_the_display_name(client):
    res = create(client, {**HELPDESK, "name": "viewer"})
    assert res.json()["detail"] == COPY_BUILTIN.format("Viewer")
    res = create(client, {**HELPDESK, "name": "Tenant-Admin"})
    assert res.json()["detail"] == COPY_BUILTIN.format("Tenant Admin")


def test_agent_name_has_its_own_message(client):
    assert create(client, {**HELPDESK, "name": "Agent"}).json()["detail"] == "The name 'agent' is reserved."


@pytest.mark.parametrize("name", ["  ", "<b>x</b>", "x", "a" * 65])
def test_malformed_names_are_refused(client, name):
    res = create(client, {**HELPDESK, "name": name})
    assert res.status_code in (400, 422), (name, res.text)


def test_duplicate_name_in_the_tenant_is_409_but_another_tenant_may_reuse_it(client):
    assert create(client, HELPDESK).status_code == 201
    dup = create(client, {**HELPDESK, "name": "helpdesk"})
    assert dup.status_code == 409 and dup.json()["detail"] == "A role with this name already exists."
    other = create(client, {**HELPDESK, "tenantId": "tenant-b"}, role="Super Admin", tenant="platform-admin")
    assert other.status_code == 201 and other.json()["tenantId"] == "tenant-b"


@pytest.mark.parametrize("perms", [["*"], ["manage:tenants"], ["view:tenants"], ["view:not_a_thing"]])
def test_banned_or_unknown_permissions_are_refused_by_name(client, perms):
    res = create(client, {**HELPDESK, "permissions": perms})
    assert res.status_code == 400
    assert perms[0] in res.json()["detail"]


@pytest.mark.parametrize("extra", [{"isEditable": False}, {"id": "role-x"}, {"builtIn": True}])
def test_mass_assignment_fields_are_422(client, extra):
    assert create(client, {**HELPDESK, **extra}).status_code == 422


def test_editor_ceiling_on_create(client):
    refused = create(client, {**HELPDESK, "permissions": ["view:security"]}, role="rbacmgr")
    assert refused.status_code == 403
    assert refused.json()["detail"] == "You can only grant permissions you hold yourself"
    assert create(client, {**HELPDESK, "permissions": ["view:agents"]}, role="rbacmgr").status_code == 201


def test_roles_without_manage_rbac_cannot_write(client):
    assert create(client, HELPDESK, role="viewer").status_code == 403


def test_tenant_admin_cannot_name_another_tenant(client):
    assert create(client, {**HELPDESK, "tenantId": "tenant-b"}).status_code == 403


@pytest.mark.parametrize("target", [None, "platform-admin", "all", "platform", "tenant-zzz"])
def test_super_admin_needs_an_existing_customer_tenant(client, target):
    body = dict(HELPDESK)
    if target:
        body["tenantId"] = target
    assert create(client, body, role="Super Admin", tenant="platform-admin").status_code == 400


def test_role_store_failure_on_the_ceiling_read_is_503(client, store, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("mongo down")

    monkeypatch.setattr(role_contents, "effective_permissions", boom)
    res = create(client, HELPDESK)
    assert res.status_code == 503
    assert not any(d["name"] == "Helpdesk" for d in stored(store, "tenant-a"))


def test_create_is_audited_and_an_audit_failure_does_not_fail_it(client, audit):
    assert create(client, HELPDESK).status_code == 201
    call_args = audit.calls[-1]
    assert call_args["action"] == "role.created" and call_args["resource_type"] == "role"
    assert call_args["tenant_id"] == "tenant-a"
    audit.fail = True
    assert create(client, {**HELPDESK, "name": "Helpdesk Two"}).status_code == 201


# --- Task 2: edit and delete -------------------------------------------------------------

def _make(client, name="Helpdesk", perms=("view:agents", "view:dashboard"), **kw):
    res = create(client, {"name": name, "description": "Desk", "permissions": list(perms)}, **kw)
    assert res.status_code == 201, res.text
    return res.json()


def _add_user(store, email, role, tenant="tenant-a", **extra):
    store.raw.users.docs.append(make_user(email, role, tenant, **extra))


def test_put_edits_description_and_permissions(client, store):
    role = _make(client)
    res = call(client, "PUT", f"/api/roles/{role['id']}",
               json={"description": "New", "permissions": ["view:agents", "view:logs"]})
    assert res.status_code == 200, res.text
    assert res.json()["description"] == "New" and res.json()["permissions"] == ["view:agents", "view:logs"]
    doc = next(d for d in stored(store, "tenant-a") if d["id"] == role["id"])
    assert doc["updatedBy"] and doc["updatedAt"] and doc["permissions"] == ["view:agents", "view:logs"]


def test_put_refuses_a_changed_name_and_accepts_the_same_one(client):
    role = _make(client)
    same = call(client, "PUT", f"/api/roles/{role['id']}", json={"name": "Helpdesk", "description": "x"})
    assert same.status_code == 200
    renamed = call(client, "PUT", f"/api/roles/{role['id']}", json={"name": "Help Desk"})
    assert renamed.status_code == 400 and renamed.json()["detail"] == COPY_RENAME


def test_put_ceiling_is_symmetric(client, store):
    store.raw.roles.docs.append(_custom("Seccy", "tenant-a", ["view:agents", "view:security"], id="role-seccy"))
    path = "/api/roles/role-seccy"
    desc = call(client, "PUT", path, role="rbacmgr", json={"description": "only text"})
    assert desc.status_code == 200, desc.text
    removed = call(client, "PUT", path, role="rbacmgr", json={"permissions": ["view:agents"]})
    assert removed.status_code == 403
    added = call(client, "PUT", path, role="rbacmgr", json={"permissions": ["view:agents", "view:security"]})
    assert added.status_code == 200
    # adding something the editor holds while leaving the unheld one in place is allowed
    kept = call(client, "PUT", path, role="rbacmgr", json={"permissions": ["view:agents", "view:security"]})
    assert kept.status_code == 200


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_other_tenants_builtin_and_legacy_ids_are_404(client, store, method):
    kw = {"json": {"description": "x"}} if method == "PUT" else {}
    assert call(client, method, "/api/roles/custom-tenant-b-Contractor", **kw).status_code == 404
    assert call(client, method, "/api/roles/role-viewer", **kw).status_code == 404
    assert call(client, method, "/api/roles/custom-tenant-a-viewer", **kw).status_code == 404
    assert any(d["name"] == "Contractor" for d in stored(store, "tenant-b"))


def test_an_edit_reaches_the_holder_on_the_next_me_without_a_login(client, store, monkeypatch):
    from tests.rbac_test_support import make_auth_client, me, reset_shared_limiter
    reset_shared_limiter()
    role = _make(client, perms=("view:agents",))
    _add_user(store, "u@a.test", "Helpdesk")
    auth = make_auth_client(store, monkeypatch)
    before = me(auth, "u@a.test", "Helpdesk", "tenant-a")
    assert before.status_code == 200 and "view:logs" not in before.json()["permissions"]
    assert call(client, "PUT", f"/api/roles/{role['id']}", json={"permissions": ["view:agents", "view:logs"]}).status_code == 200
    after = me(auth, "u@a.test", "Helpdesk", "tenant-a")
    assert "view:logs" in after.json()["permissions"]
    reset_shared_limiter()


def test_delete_is_refused_while_a_user_holds_the_role(client, store):
    role = _make(client)
    _add_user(store, "u@a.test", "helpdesk", full_name="Una")
    _add_user(store, "v@a.test", "Viewer")
    res = call(client, "DELETE", f"/api/roles/{role['id']}")
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["code"] == "role_in_use" and detail["holderCount"] == 1
    assert detail["holders"] == [{"name": "Una", "email": "u@a.test"}]
    assert detail["mappingCount"] == 0 and detail["mappings"] == []
    assert any(d["id"] == role["id"] for d in stored(store, "tenant-a"))


def test_holder_name_falls_back_to_the_email(client, store):
    role = _make(client)
    store.raw.users.docs.append({"_id": "z", "email": "z@a.test", "role": "Helpdesk", "tenantId": "tenant-a"})
    detail = call(client, "DELETE", f"/api/roles/{role['id']}").json()["detail"]
    assert detail["holders"] == [{"name": "z@a.test", "email": "z@a.test"}]


def test_delete_is_refused_while_a_sign_in_mapping_names_the_role(client, store):
    role = _make(client)
    store.raw.ldap_group_mappings.docs.append({"group_dn": "cn=desk", "role": "Helpdesk", "tenant_id": "tenant-a"})
    store.raw.saml_group_mappings.docs.append({"group_value": "desk", "role": "helpdesk", "tenant_id": "tenant-a"})
    store.raw.ldap_group_mappings.docs.append({"group_dn": "cn=other", "role": "Helpdesk", "tenant_id": "tenant-b"})
    res = call(client, "DELETE", f"/api/roles/{role['id']}")
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["holderCount"] == 0 and detail["mappingCount"] == 2
    assert detail["mappings"] == [{"group": "cn=desk", "source": "LDAP"}, {"group": "desk", "source": "SAML"}]


def test_delete_listing_is_capped_but_counts_are_exact(client, store):
    role = _make(client)
    for i in range(60):
        _add_user(store, f"u{i}@a.test", "Helpdesk")
    detail = call(client, "DELETE", f"/api/roles/{role['id']}").json()["detail"]
    assert detail["holderCount"] == 60 and len(detail["holders"]) == 50


def test_delete_succeeds_when_nobody_holds_the_role_and_is_audited(client, store, audit):
    role = _make(client)
    res = call(client, "DELETE", f"/api/roles/{role['id']}")
    assert res.status_code == 204
    assert not any(d["id"] == role["id"] for d in stored(store, "tenant-a"))
    entry = audit.calls[-1]
    assert entry["action"] == "role.deleted" and entry["tenant_id"] == "tenant-a"
    assert entry["previous_state"]["permissions"] == ["view:agents", "view:dashboard"]


def test_put_is_audited_with_the_previous_state(client, audit):
    role = _make(client)
    call(client, "PUT", f"/api/roles/{role['id']}", json={"permissions": ["view:agents"]})
    entry = audit.calls[-1]
    assert entry["action"] == "role.updated"
    assert entry["previous_state"]["permissions"] == ["view:agents", "view:dashboard"]
    assert entry["previous_state"]["description"] == "Desk"


def test_put_and_delete_need_manage_rbac(client):
    role = _make(client)
    assert call(client, "PUT", f"/api/roles/{role['id']}", role="viewer", json={"description": "x"}).status_code == 403
    assert call(client, "DELETE", f"/api/roles/{role['id']}", role="viewer").status_code == 403


# --- 77 WR-03: role writes reach the MFA answer at once -------------------------------------

def test_role_writes_clear_the_tenants_cached_mfa_answers(client, store, monkeypatch):
    import asyncio
    import authentication_service as auth_svc
    monkeypatch.setattr("database.get_database", lambda: store)
    auth_svc._clear_mfa_role_cache()
    try:
        other = ("tenant-b", "contractor")
        auth_svc._mfa_role_cache[("tenant-a", "helpdesk")] = (float("inf"), True)
        auth_svc._mfa_role_cache[other] = (float("inf"), False)
        role_id = create(client, HELPDESK).json()["id"]
        assert ("tenant-a", "helpdesk") not in auth_svc._mfa_role_cache
        assert other in auth_svc._mfa_role_cache

        assert asyncio.run(auth_svc.resolve_mfa_required("Helpdesk", "tenant-a")) is False
        body = {"permissions": HELPDESK["permissions"] + ["manage:rbac"]}
        assert call(client, "PUT", f"/api/roles/{role_id}", json=body).status_code == 200
        assert asyncio.run(auth_svc.resolve_mfa_required("Helpdesk", "tenant-a")) is True

        assert call(client, "DELETE", f"/api/roles/{role_id}").status_code == 204
        assert ("tenant-a", "helpdesk") not in auth_svc._mfa_role_cache
        assert other in auth_svc._mfa_role_cache
    finally:
        auth_svc._clear_mfa_role_cache()


def test_a_failed_create_after_the_insert_still_clears_the_cache(client, store, monkeypatch):
    """77 IN-12: once the insert ran, the tenant's MFA answers are dropped even if the write then fails."""
    import authentication_service as auth_svc
    real = role_contents.custom_role_docs
    calls = []

    async def fails_after_insert(db, tenant_id):
        calls.append(tenant_id)
        if len(calls) > 1:
            raise RuntimeError("store down")
        return await real(db, tenant_id)

    monkeypatch.setattr(role_contents, "custom_role_docs", fails_after_insert)
    auth_svc._clear_mfa_role_cache()
    try:
        auth_svc._mfa_role_cache[("tenant-a", "helpdesk")] = (float("inf"), False)
        assert create(client, HELPDESK).status_code == 503
        assert ("tenant-a", "helpdesk") not in auth_svc._mfa_role_cache
    finally:
        auth_svc._clear_mfa_role_cache()

