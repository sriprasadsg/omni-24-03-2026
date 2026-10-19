"""Custom tenant roles are assignable wherever a built-in role is (Phase 77 plan 06, D-04, D-18).

Users: POST /api/users and PUT /api/users/{id} (including Super Admin tenant moves).
Directory mappings: LDAP and SAML group-to-role writes.
A custom role is resolved inside the target tenant only, canonicalised to its stored
name before the ceiling check and storage, and never crosses tenants.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException

from authentication_service import get_current_user as real_get_current_user
from tests.conftest import make_test_app, make_token_data
from tests.test_user_crud import FakeDB, _client, _fake_verify_permission

PASSWORD = "Str0ng!Passw0rd"


def _role(name, perms, tenant):
    return {"id": f"role-{tenant}-{name}", "name": name, "tenantId": tenant, "permissions": list(perms)}


def _tenants():
    return [{"id": t, "name": t} for t in ("tenant-a", "tenant-b", "tenant-c")]


def _roles():
    return [
        _role("Helpdesk", ["view:agents"], "tenant-a"),
        _role("Security Lead", ["view:security"], "tenant-a"),
        _role("Asset Viewer", ["view:assets"], "tenant-a"),
        _role("Contractor", ["view:agents"], "tenant-b"),
        _role("Helpdesk", ["view:agents"], "tenant-c"),
    ]


@pytest.fixture
def fake_db():
    db = FakeDB(tenants=_tenants())
    db.roles.docs.extend(_roles())
    return db


@pytest.fixture
def app(fake_db, monkeypatch):
    import itam_asset_endpoints
    import user_endpoints

    monkeypatch.setattr(user_endpoints, "get_database", lambda: fake_db)
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(side_effect=_fake_verify_permission))
    monkeypatch.setattr(user_endpoints, "get_tenant_id", lambda: "tenant-a")
    app, _ = make_test_app(user_endpoints.router)
    with patch("user_endpoints.revoke_user_sessions", new_callable=AsyncMock):
        yield app


def _as(app, role, tenant="tenant-a", username=None):
    token = make_token_data(username=username or f"{role.replace(' ', '')}@{tenant}.com", role=role, tenant_id=tenant)
    app.dependency_overrides[real_get_current_user] = lambda: token


def _body(email, role, tenant="tenant-a"):
    return {"email": email, "password": PASSWORD, "full_name": "N", "role": role, "tenantId": tenant}


def _seed(fake_db, role, tenant="tenant-a", email="holder@tenant-a.com"):
    uid = ObjectId()
    fake_db.users.docs.append({"_id": uid, "email": email, "full_name": "H", "role": role,
                               "tenantId": tenant, "status": "Active", "hashed_password": "x"})
    return uid


class TestCreateWithCustomRole:
    @pytest.mark.asyncio
    async def test_tenant_admin_creates_user_with_custom_role_stored_canonically(self, app, fake_db):
        _as(app, "Tenant Admin")
        async with await _client(app) as ac:
            r = await ac.post("/api/users", json=_body("h@tenant-a.com", "helpdesk"))
        assert r.status_code == 201, r.text
        assert fake_db.users.docs[0]["role"] == "Helpdesk"

    @pytest.mark.asyncio
    async def test_delivered_permissions_come_from_the_custom_role(self, app, fake_db):
        import rbac_service
        _as(app, "Tenant Admin")
        async with await _client(app) as ac:
            r = await ac.post("/api/users", json=_body("h@tenant-a.com", "helpdesk"))
        assert r.status_code == 201, r.text
        perms = await rbac_service.session_permissions(fake_db, fake_db.users.docs[0]["role"], "tenant-a")
        assert "view:agents" in perms

    @pytest.mark.asyncio
    async def test_another_tenants_custom_role_is_400(self, app):
        _as(app, "Tenant Admin")
        async with await _client(app) as ac:
            r = await ac.post("/api/users", json=_body("c@tenant-a.com", "Contractor"))
        assert r.status_code == 400, r.text
        assert "Invalid role 'Contractor'" in r.text

    @pytest.mark.asyncio
    async def test_unknown_role_is_400(self, app):
        _as(app, "Tenant Admin")
        async with await _client(app) as ac:
            r = await ac.post("/api/users", json=_body("g@tenant-a.com", "Ghost"))
        assert r.status_code == 400, r.text

    @pytest.mark.asyncio
    async def test_ceiling_refuses_a_custom_role_above_the_callers_own(self, app, fake_db):
        _as(app, "itam_admin")
        async with await _client(app) as ac:
            r = await ac.post("/api/users", json=_body("s@tenant-a.com", "Security Lead"))
        assert r.status_code == 403, r.text
        assert fake_db.users.docs == []

    @pytest.mark.asyncio
    async def test_ceiling_allows_a_custom_role_inside_the_callers_closure(self, app, fake_db):
        _as(app, "itam_admin")
        async with await _client(app) as ac:
            r = await ac.post("/api/users", json=_body("a@tenant-a.com", "asset viewer"))
        assert r.status_code == 201, r.text
        assert fake_db.users.docs[0]["role"] == "Asset Viewer"

    @pytest.mark.asyncio
    async def test_role_store_failure_during_resolution_is_503(self, app, fake_db):
        def boom(*a, **k):
            raise RuntimeError("mongo down")
        fake_db.roles.find = boom
        _as(app, "Tenant Admin")
        async with await _client(app) as ac:
            r = await ac.post("/api/users", json=_body("h@tenant-a.com", "Helpdesk"))
        assert r.status_code == 503, r.text
        assert fake_db.users.docs == []

    @pytest.mark.asyncio
    async def test_builtin_role_keeps_its_stored_name_without_a_role_lookup(self, app, fake_db):
        def boom(*a, **k):
            raise AssertionError("built-in role must not query role documents for resolution")
        fake_db.roles.find = boom
        _as(app, "Tenant Admin")
        async with await _client(app) as ac:
            r = await ac.post("/api/users", json=_body("u@tenant-a.com", "user"))
        assert r.status_code == 201, r.text


class TestUpdateWithCustomRole:
    @pytest.mark.asyncio
    async def test_role_change_stores_canonical_custom_name(self, app, fake_db):
        uid = _seed(fake_db, "user")
        _as(app, "Tenant Admin")
        async with await _client(app) as ac:
            r = await ac.put(f"/api/users/{uid}", json={"role": "helpdesk"})
        assert r.status_code == 200, r.text
        assert fake_db.users.docs[0]["role"] == "Helpdesk"

    @pytest.mark.asyncio
    async def test_another_tenants_custom_role_is_400(self, app, fake_db):
        uid = _seed(fake_db, "user")
        _as(app, "Tenant Admin")
        async with await _client(app) as ac:
            r = await ac.put(f"/api/users/{uid}", json={"role": "Contractor"})
        assert r.status_code == 400, r.text
        assert fake_db.users.docs[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_ceiling_refuses_an_over_privileged_custom_role(self, app, fake_db):
        uid = _seed(fake_db, "user")
        _as(app, "itam_admin")
        async with await _client(app) as ac:
            r = await ac.put(f"/api/users/{uid}", json={"role": "Security Lead"})
        assert r.status_code == 403, r.text
        assert fake_db.users.docs[0]["role"] == "user"


class TestTenantMove:
    @pytest.mark.asyncio
    async def test_move_to_tenant_without_the_role_is_400_and_writes_nothing(self, app, fake_db):
        uid = _seed(fake_db, "Helpdesk")
        _as(app, "super_admin", tenant="platform")
        async with await _client(app) as ac:
            r = await ac.put(f"/api/users/{uid}", json={"tenantId": "tenant-b"})
        assert r.status_code == 400, r.text
        assert "Helpdesk" in r.text and "tenant-b" in r.text
        assert fake_db.users.docs[0]["tenantId"] == "tenant-a"
        assert fake_db.users.docs[0]["role"] == "Helpdesk"

    @pytest.mark.asyncio
    async def test_move_to_tenant_holding_its_own_copy_is_200(self, app, fake_db):
        uid = _seed(fake_db, "Helpdesk")
        _as(app, "super_admin", tenant="platform")
        async with await _client(app) as ac:
            r = await ac.put(f"/api/users/{uid}", json={"tenantId": "tenant-c"})
        assert r.status_code == 200, r.text
        assert fake_db.users.docs[0]["tenantId"] == "tenant-c"
        assert fake_db.users.docs[0]["role"] == "Helpdesk"

    @pytest.mark.asyncio
    async def test_move_with_a_new_builtin_role_in_one_request_is_200(self, app, fake_db):
        uid = _seed(fake_db, "Helpdesk")
        _as(app, "super_admin", tenant="platform")
        async with await _client(app) as ac:
            r = await ac.put(f"/api/users/{uid}", json={"tenantId": "tenant-b", "role": "viewer"})
        assert r.status_code == 200, r.text
        assert fake_db.users.docs[0]["tenantId"] == "tenant-b"
        assert fake_db.users.docs[0]["role"] == "viewer"

    @pytest.mark.asyncio
    async def test_move_with_a_custom_role_resolves_it_in_the_destination(self, app, fake_db):
        uid = _seed(fake_db, "viewer")
        _as(app, "super_admin", tenant="platform")
        async with await _client(app) as ac:
            ok = await ac.put(f"/api/users/{uid}", json={"tenantId": "tenant-b", "role": "contractor"})
            bad = await ac.put(f"/api/users/{uid}", json={"tenantId": "tenant-c", "role": "Contractor"})
        assert ok.status_code == 200, ok.text
        assert fake_db.users.docs[0]["role"] == "Contractor"
        assert bad.status_code == 400, bad.text
        assert fake_db.users.docs[0]["tenantId"] == "tenant-b"


# ── Directory group mappings (LDAP and SAML) ─────────────────────────────────

from tests import test_ldap_service as _ldap_t  # noqa: E402  (reuse its in-memory endpoint doubles)
from tests import test_sso_saml as _saml_t  # noqa: E402


def _directory_app(router, module, db, monkeypatch, *extra_modules):
    import itam_asset_endpoints
    from fastapi import FastAPI
    from rate_limiter import limiter as shared_limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    for mod in (module, *extra_modules):
        monkeypatch.setattr(mod, "get_database", lambda: db)
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(side_effect=_fake_verify_permission))
    monkeypatch.setattr(module, "get_tenant_id", lambda: "tenant-a")
    shared_limiter._storage.reset()
    app = FastAPI()
    app.state.limiter = shared_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(router)
    return app


@pytest.fixture
def ldap_db():
    db = _ldap_t._EPFakeDB()
    db.roles.docs.extend(_roles())
    return db


@pytest.fixture
def saml_db():
    db = _saml_t._EPFakeDB()
    db._db.roles.docs.extend(_roles())
    return db


@pytest.fixture
def ldap_app(ldap_db, monkeypatch):
    import ldap_endpoints
    import ldap_service
    return _directory_app(ldap_endpoints.router, ldap_endpoints, ldap_db, monkeypatch, ldap_service)


@pytest.fixture
def saml_app(saml_db, monkeypatch):
    import saml_mapping
    import saml_service
    import sso_endpoints
    return _directory_app(sso_endpoints.saml_router, sso_endpoints, saml_db, monkeypatch, saml_service, saml_mapping)


LDAP_URL = "/api/admin/ldap/group-mapping"
SAML_URL = "/api/admin/sso/saml/attribute-mapping"


def _mapping_cases(request_param):
    return {"ldap": (LDAP_URL, "group_dn", "cn=g,dc=x", "ldap_group_mappings"),
            "saml": (SAML_URL, "group_value", "Admins", "saml_group_mappings")}[request_param]


@pytest.fixture(params=["ldap", "saml"])
def directory(request, monkeypatch):
    """(app, url, group field, group value, mapping collection) for each directory kind."""
    kind = request.param
    url, field, group, coll = _mapping_cases(kind)
    app = request.getfixturevalue(f"{kind}_app")
    db = request.getfixturevalue(f"{kind}_db")
    return app, url, field, group, getattr(db, coll)


class TestDirectoryMappingEndpoints:
    @pytest.mark.asyncio
    async def test_tenant_admin_maps_custom_role_stored_canonically(self, directory):
        app, url, field, group, coll = directory
        _as(app, "Tenant Admin")
        async with await _client(app) as ac:
            r = await ac.post(url, json={field: group, "role": "helpdesk"})
        assert r.status_code == 200, r.text
        assert [d["role"] for d in coll.docs] == ["Helpdesk"]
        assert coll.docs[0]["tenant_id"] == "tenant-a"

    @pytest.mark.asyncio
    async def test_other_tenants_and_unknown_roles_are_400(self, directory):
        app, url, field, group, coll = directory
        _as(app, "Tenant Admin")
        async with await _client(app) as ac:
            other = await ac.post(url, json={field: group, "role": "Contractor"})
            ghost = await ac.post(url, json={field: group, "role": "Ghost"})
        assert other.status_code == 400, other.text
        assert ghost.status_code == 400, ghost.text
        assert coll.docs == []

    @pytest.mark.asyncio
    async def test_platform_role_is_still_400(self, directory):
        app, url, field, group, coll = directory
        _as(app, "Tenant Admin")
        async with await _client(app) as ac:
            r = await ac.post(url, json={field: group, "role": "Platform Support"})
        assert r.status_code in (400, 403), r.text
        assert coll.docs == []

    @pytest.mark.asyncio
    async def test_ceiling_applies_to_the_canonical_custom_role(self, directory):
        app, url, field, group, coll = directory
        _as(app, "itam_admin")
        async with await _client(app) as ac:
            over = await ac.post(url, json={field: group, "role": "security lead"})
            within = await ac.post(url, json={field: group, "role": "asset viewer"})
        assert over.status_code == 403, over.text
        assert within.status_code == 200, within.text
        assert [d["role"] for d in coll.docs] == ["Asset Viewer"]

    @pytest.mark.asyncio
    async def test_super_admin_platform_scope_maps_builtin_only(self, directory):
        app, url, field, group, coll = directory
        _as(app, "super_admin", tenant="platform")
        async with await _client(app) as ac:
            custom = await ac.post(url, json={field: group, "role": "Helpdesk"})
            builtin = await ac.post(url, json={field: group, "role": "itam_user"})
        assert custom.status_code == 400, custom.text
        assert builtin.status_code == 200, builtin.text
        assert [d["role"] for d in coll.docs] == ["itam_user"]


class _NoDatabase:
    def __getattr__(self, name):
        raise AssertionError(f"database touched via {name}")


class TestMapperUpsert:
    @pytest.mark.asyncio
    async def test_ldap_mapper_stores_a_tenant_custom_role(self, ldap_db):
        import ldap_service
        with patch("ldap_service.get_database", lambda: ldap_db):
            doc = await ldap_service.LDAPGroupMapper.upsert_mapping("cn=g,dc=x", "helpdesk", tenant_id="tenant-a")
        assert doc["role"] == "Helpdesk"

    @pytest.mark.asyncio
    async def test_saml_mapper_stores_a_tenant_custom_role(self, saml_db):
        import saml_mapping
        with patch("saml_mapping.get_database", lambda: saml_db):
            doc = await saml_mapping.SAMLGroupMapper.upsert_mapping("Admins", "helpdesk", tenant_id="tenant-a")
        assert doc["role"] == "Helpdesk"

    @pytest.mark.asyncio
    async def test_mappers_refuse_unknown_names_and_missing_tenants_without_the_database(self):
        import ldap_service
        import saml_mapping
        with patch("ldap_service.get_database", _NoDatabase), patch("saml_mapping.get_database", _NoDatabase):
            with pytest.raises(ldap_service.LDAPConfigError):
                await ldap_service.LDAPGroupMapper.upsert_mapping("cn=g,dc=x", "Helpdesk")
            with pytest.raises(saml_mapping.SAMLMappingError):
                await saml_mapping.SAMLGroupMapper.upsert_mapping("Admins", "Helpdesk")

    @pytest.mark.asyncio
    async def test_mappers_refuse_a_name_the_tenant_does_not_hold(self, ldap_db, saml_db):
        import ldap_service
        import saml_mapping
        with patch("ldap_service.get_database", lambda: ldap_db), patch("saml_mapping.get_database", lambda: saml_db):
            with pytest.raises(ldap_service.LDAPConfigError):
                await ldap_service.LDAPGroupMapper.upsert_mapping("cn=g,dc=x", "Contractor", tenant_id="tenant-a")
            with pytest.raises(saml_mapping.SAMLMappingError):
                await saml_mapping.SAMLGroupMapper.upsert_mapping("Admins", "Ghost", tenant_id="tenant-a")
        assert ldap_db.ldap_group_mappings.docs == [] and saml_db.saml_group_mappings.docs == []


class TestResolveAssignableRole:
    @pytest.mark.asyncio
    async def test_resolver_contract(self, fake_db):
        from role_assignment import resolve_assignable_role
        assert await resolve_assignable_role(fake_db, "helpdesk", "tenant-a") == "Helpdesk"
        assert await resolve_assignable_role(fake_db, "Tenant Admin", "tenant-a") == "Tenant Admin"
        for typed, tenant in (("Contractor", "tenant-a"), ("Helpdesk", None), ("Helpdesk", "platform"),
                              ("Helpdesk", "all"), ("", "tenant-a")):
            with pytest.raises(HTTPException) as exc:
                await resolve_assignable_role(fake_db, typed, tenant)
            assert exc.value.status_code == 400
