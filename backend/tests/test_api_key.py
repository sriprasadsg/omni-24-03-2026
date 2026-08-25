"""API token management tests — Phase 64 Plan 05 (ITAM-USR-05).

Covers:
 - Task 1: APIKeyService lifecycle (create/list/revoke/validate/authenticate),
   bcrypt storage, prefix lookup, expiration, rate limiting.
 - Task 2: user-scoped and admin-scoped /api/api-keys endpoints.
 - Task 3: TokenData scope defaults + rbac_service scope-narrowing
   enforcement (has_permission()/require_role() intersect role permissions
   with token scopes — role is the outer bound, scopes only narrow).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from auth_types import TokenData
from tests.conftest import make_test_app, make_token_data
from authentication_service import get_current_user as real_get_current_user


def _run(coro):
    return asyncio.run(coro)


# ===========================================================================
# Fake db.users double — supports exactly the query shapes api_key_auth.py
# and api_key_endpoints.py issue: $or user lookup, $push, positional $ / $set
# updates keyed on apiKeys.id or apiKeys.keyPrefix, and a plain find() cursor
# for the admin listing route. Mirrors the hand-rolled-fake convention
# established by test_user_crud.py / test_support_admin_to_user.py.
# ===========================================================================

class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _FakeUsersCollection:
    def __init__(self, users):
        self._users = users  # list[dict], mutated in place

    @staticmethod
    def _match(doc, query):
        if not query:
            return True
        for k, v in query.items():
            if k == "$or":
                # $or is ANDed with any sibling keys in the same query dict
                # (e.g. the merged user-filter + "apiKeys.id" in revoke_key).
                if not any(_FakeUsersCollection._match(doc, sub) for sub in v):
                    return False
            elif k == "apiKeys.id":
                if not any(ak.get("id") == v for ak in doc.get("apiKeys", [])):
                    return False
            elif k == "apiKeys.keyPrefix":
                if not any(ak.get("keyPrefix") == v for ak in doc.get("apiKeys", [])):
                    return False
            elif k == "apiKeys.0":
                want = v.get("$exists", True) if isinstance(v, dict) else bool(v)
                if bool(doc.get("apiKeys")) != want:
                    return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    @staticmethod
    def _project(doc, query, projection):
        if not projection:
            return dict(doc)
        result = {}
        for key, want in projection.items():
            if want != 1:
                continue
            if key == "apiKeys.$":
                match = None
                if "apiKeys.keyPrefix" in query:
                    match = next(
                        (ak for ak in doc.get("apiKeys", []) if ak.get("keyPrefix") == query["apiKeys.keyPrefix"]),
                        None,
                    )
                elif "apiKeys.id" in query:
                    match = next(
                        (ak for ak in doc.get("apiKeys", []) if ak.get("id") == query["apiKeys.id"]),
                        None,
                    )
                result["apiKeys"] = [dict(match)] if match else []
            elif key in doc:
                result[key] = doc[key]
        return result

    async def find_one(self, query=None, projection=None):
        query = query or {}
        for doc in self._users:
            if self._match(doc, query):
                return self._project(doc, query, projection)
        return None

    def find(self, query=None, projection=None):
        query = query or {}
        docs = [self._project(d, query, projection) for d in self._users if self._match(d, query)]
        return _FakeCursor(docs)

    async def update_one(self, query, update):
        query = query or {}
        for doc in self._users:
            if self._match(doc, query):
                if "$push" in update:
                    for k, v in update["$push"].items():
                        doc.setdefault(k, []).append(v)
                if "$set" in update:
                    for k, v in update["$set"].items():
                        if k.startswith("apiKeys.$."):
                            field = k.split(".", 2)[2]
                            target_id = query.get("apiKeys.id")
                            for ak in doc.get("apiKeys", []):
                                if target_id is None or ak.get("id") == target_id:
                                    ak[field] = v
                        else:
                            doc[k] = v
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()


class _FakeDB:
    def __init__(self, users=None):
        self.users = _FakeUsersCollection(users or [])


@pytest.fixture
def fake_users_db(monkeypatch):
    from database import mongodb

    fdb = _FakeDB(users=[
        {"_id": "u1", "email": "alice@tenant-a.com", "role": "itam_admin", "tenantId": "tenant-a", "apiKeys": []},
        {"_id": "u2", "email": "bob@tenant-b.com", "role": "user", "tenantId": "tenant-b", "apiKeys": []},
    ])
    monkeypatch.setattr(mongodb, "db", fdb)
    return fdb


# ===========================================================================
# Task 1: APIKeyService lifecycle
# ===========================================================================

class TestAPIKeyServiceLifecycle:

    def test_create_key_returns_plaintext_once_and_stores_bcrypt_hash(self, fake_users_db):
        from api_key_auth import APIKeyService
        svc = APIKeyService()
        model, plaintext = _run(svc.create_key("alice@tenant-a.com", "CI token", scopes=["view:itam"], rate_limit=10))

        assert plaintext.startswith("omni_pat_")
        assert model.keyPrefix == plaintext[:12]
        assert model.keyHash != plaintext

        stored = fake_users_db.users._users[0]["apiKeys"][0]
        assert stored["keyHash"] != plaintext
        assert bcrypt.checkpw(plaintext.encode("utf-8"), stored["keyHash"].encode("utf-8"))

    def test_create_key_unknown_user_raises(self, fake_users_db):
        from api_key_auth import APIKeyService
        svc = APIKeyService()
        with pytest.raises(ValueError):
            _run(svc.create_key("nobody@nowhere.com", "x"))

    def test_list_keys_excludes_hash_in_public_dict(self, fake_users_db):
        from api_key_auth import APIKeyService
        svc = APIKeyService()
        _run(svc.create_key("alice@tenant-a.com", "Token A"))

        keys = _run(svc.list_keys("alice@tenant-a.com"))
        assert len(keys) == 1
        pub = keys[0].to_public_dict()
        assert "keyHash" not in pub
        assert pub["prefix"] == keys[0].keyPrefix

    def test_revoke_key_marks_revoked_and_then_fails_validation(self, fake_users_db):
        from api_key_auth import APIKeyService
        svc = APIKeyService()
        model, plaintext = _run(svc.create_key("alice@tenant-a.com", "To revoke"))
        assert _run(svc.validate_key(plaintext)) is not None

        revoked = _run(svc.revoke_key("alice@tenant-a.com", model.id))
        assert revoked is True
        assert _run(svc.validate_key(plaintext)) is None

    def test_revoke_unknown_key_returns_false(self, fake_users_db):
        from api_key_auth import APIKeyService
        svc = APIKeyService()
        assert _run(svc.revoke_key("alice@tenant-a.com", "nope")) is False

    def test_validate_key_prefix_lookup_wrong_key_fails(self, fake_users_db):
        from api_key_auth import APIKeyService
        svc = APIKeyService()
        _model, plaintext = _run(svc.create_key("alice@tenant-a.com", "Token"))
        tampered = plaintext[:-1] + ("x" if plaintext[-1] != "x" else "y")
        assert _run(svc.validate_key(tampered)) is None

    def test_validate_key_updates_last_used_at(self, fake_users_db):
        from api_key_auth import APIKeyService
        svc = APIKeyService()
        model, plaintext = _run(svc.create_key("alice@tenant-a.com", "Token"))
        assert model.lastUsedAt is None

        validated = _run(svc.validate_key(plaintext))
        assert validated is not None
        assert validated.lastUsedAt is not None

    def test_expired_key_fails_validation(self, fake_users_db):
        from api_key_auth import APIKeyService
        svc = APIKeyService()
        _model, plaintext = _run(svc.create_key("alice@tenant-a.com", "Expiring", expires_in_days=1))

        stored = fake_users_db.users._users[0]["apiKeys"][0]
        stored["expiresAt"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        assert _run(svc.validate_key(plaintext)) is None

    def test_rate_limit_enforced_per_key(self, fake_users_db):
        from api_key_auth import APIKeyService
        svc = APIKeyService()
        _model, plaintext = _run(svc.create_key("alice@tenant-a.com", "Limited", rate_limit=2))

        assert _run(svc.validate_key(plaintext)) is not None
        assert _run(svc.validate_key(plaintext)) is not None
        with pytest.raises(HTTPException) as exc_info:
            _run(svc.validate_key(plaintext))
        assert exc_info.value.status_code == 429

    def test_authenticate_returns_token_data_with_scopes_and_api_key_source(self, fake_users_db):
        from api_key_auth import APIKeyService
        svc = APIKeyService()
        _model, plaintext = _run(svc.create_key("alice@tenant-a.com", "Scoped", scopes=["view:itam"]))

        token = _run(svc.authenticate(plaintext))
        assert token is not None
        assert token.scopes == ["view:itam"]
        assert token.auth_source == "api_key"
        assert token.username == "alice@tenant-a.com"
        assert token.role == "itam_admin"
        assert token.tenant_id == "tenant-a"

    def test_authenticate_unknown_key_returns_none(self, fake_users_db):
        from api_key_auth import APIKeyService
        svc = APIKeyService()
        assert _run(svc.authenticate("omni_pat_totally_bogus_key_value")) is None


# ===========================================================================
# Task 2: user-scoped and admin-scoped /api/api-keys endpoints
# ===========================================================================

def _make_endpoints_app(monkeypatch):
    import api_key_endpoints
    import itam_asset_endpoints

    async def _fake_verify_permission(user, permission):
        if permission != "manage:assets":
            return False
        return getattr(user, "role", "") in (
            "itam_admin", "admin", "Admin", "Tenant Admin", "tenant_admin", "super_admin", "Super Admin",
        )

    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", _fake_verify_permission)

    app, _ = make_test_app(api_key_endpoints.router, api_key_endpoints.admin_router)
    return app


def _override_user(app, token):
    app.dependency_overrides[real_get_current_user] = lambda: token


async def _client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


class TestAPIKeyEndpoints:

    @pytest.mark.asyncio
    async def test_create_list_revoke_endpoint_flow(self, monkeypatch, fake_users_db):
        app = _make_endpoints_app(monkeypatch)
        user = make_token_data(username="alice@tenant-a.com", role="itam_admin", tenant_id="tenant-a")
        _override_user(app, user)

        async with await _client(app) as ac:
            r = await ac.post("/api/api-keys", json={"name": "CI", "scopes": ["view:itam"]})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["key"].startswith("omni_pat_")
            key_id = body["id"]

            r2 = await ac.get("/api/api-keys")
            assert r2.status_code == 200
            listed = r2.json()
            assert len(listed) == 1
            assert "key" not in listed[0]
            assert "keyHash" not in listed[0]

            r3 = await ac.delete(f"/api/api-keys/{key_id}")
            assert r3.status_code == 200
            assert r3.json()["success"] is True

    @pytest.mark.asyncio
    async def test_create_endpoint_rejects_unknown_scope(self, monkeypatch, fake_users_db):
        app = _make_endpoints_app(monkeypatch)
        user = make_token_data(username="alice@tenant-a.com", role="itam_admin", tenant_id="tenant-a")
        _override_user(app, user)

        async with await _client(app) as ac:
            r = await ac.post("/api/api-keys", json={"name": "Bad", "scopes": ["not:a_real_scope"]})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_scopes_endpoint_lists_catalog(self, monkeypatch, fake_users_db):
        app = _make_endpoints_app(monkeypatch)
        user = make_token_data(username="alice@tenant-a.com", role="itam_admin", tenant_id="tenant-a")
        _override_user(app, user)

        async with await _client(app) as ac:
            r = await ac.get("/api/api-keys/scopes")
        assert r.status_code == 200
        scopes = {s["scope"] for s in r.json()}
        assert "view:itam" in scopes

    @pytest.mark.asyncio
    async def test_revoke_missing_key_endpoint_returns_404(self, monkeypatch, fake_users_db):
        app = _make_endpoints_app(monkeypatch)
        user = make_token_data(username="alice@tenant-a.com", role="itam_admin", tenant_id="tenant-a")
        _override_user(app, user)

        async with await _client(app) as ac:
            r = await ac.delete("/api/api-keys/does-not-exist")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_list_endpoint_returns_keys_across_users(self, monkeypatch, fake_users_db):
        app = _make_endpoints_app(monkeypatch)
        alice = make_token_data(username="alice@tenant-a.com", role="itam_admin", tenant_id="tenant-a")
        bob = make_token_data(username="bob@tenant-b.com", role="user", tenant_id="tenant-b")

        async with await _client(app) as ac:
            _override_user(app, alice)
            await ac.post("/api/api-keys", json={"name": "Alice key"})

            _override_user(app, bob)
            await ac.post("/api/api-keys", json={"name": "Bob key"})

            admin = make_token_data(username="admin@platform.com", role="admin", tenant_id="tenant-a")
            _override_user(app, admin)
            r = await ac.get("/api/admin/api-keys")

        assert r.status_code == 200
        owners = {k["owner"] for k in r.json()}
        assert owners == {"alice@tenant-a.com", "bob@tenant-b.com"}

    @pytest.mark.asyncio
    async def test_admin_endpoint_denied_for_non_admin(self, monkeypatch, fake_users_db):
        app = _make_endpoints_app(monkeypatch)
        user = make_token_data(username="alice@tenant-a.com", role="user", tenant_id="tenant-a")
        _override_user(app, user)

        async with await _client(app) as ac:
            r = await ac.get("/api/admin/api-keys")
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_revoke_endpoint(self, monkeypatch, fake_users_db):
        app = _make_endpoints_app(monkeypatch)
        alice = make_token_data(username="alice@tenant-a.com", role="itam_admin", tenant_id="tenant-a")

        async with await _client(app) as ac:
            _override_user(app, alice)
            r = await ac.post("/api/api-keys", json={"name": "ToRevoke"})
            key_id = r.json()["id"]

            admin = make_token_data(username="admin@platform.com", role="admin", tenant_id="tenant-a")
            _override_user(app, admin)
            r2 = await ac.delete(f"/api/admin/api-keys/{key_id}")

        assert r2.status_code == 200
        assert r2.json()["success"] is True


# ===========================================================================
# Task 3: TokenData defaults + rbac_service scope-narrowing enforcement
# ===========================================================================

def _mock_db(role_doc=None):
    db = MagicMock()
    db.roles = MagicMock()
    db._db = db  # DB-F10: rbac_service.find_role_doc bypasses the wrapper via db._db for global-role fallback lookups
    db.roles.find_one = AsyncMock(return_value=role_doc)
    return db


class TestTokenDataDefaults:
    """Behavior test 1: TokenData() with no arguments has scopes=None and
    auth_source='session'; existing positional/keyword call sites keep
    working unchanged."""

    def test_default_tokendata_has_no_scopes_and_session_auth_source(self):
        td = TokenData()
        assert td.scopes is None
        assert td.auth_source == "session"

    def test_positional_and_keyword_construction_still_works(self):
        # Existing call sites (authentication_service.py) construct with only
        # the original 4 fields — must keep working unchanged.
        td1 = TokenData("alice", "admin", "tenant-a", True)
        assert td1.scopes is None
        assert td1.auth_source == "session"

        td2 = TokenData(username="bob", role="user", tenant_id="t1", mfa_verified=False)
        assert td2.scopes is None
        assert td2.auth_source == "session"


class TestScopeEnforcement:
    """Behavior tests 2-8: rbac_service.has_permission()/require_role()
    intersect role permissions with token scopes — role is the outer bound,
    scopes only narrow, never widen."""

    async def _call_has_permission(self, required_perm, user):
        from rbac_service import RBACService
        svc = RBACService()
        dependency = svc.has_permission(required_perm)
        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            return await dependency(user=user)

    async def _call_require_role(self, allowed_roles, user):
        from rbac_service import RBACService
        svc = RBACService()
        dependency = svc.require_role(allowed_roles)
        return await dependency(user=user)

    def test_2_has_permission_admits_matching_scope_and_role(self):
        user = TokenData(username="a@b.com", role="admin", tenant_id="t1",
                          scopes=["view:itam"], auth_source="api_key")
        result = _run(self._call_has_permission("view:itam", user))
        assert result is user

    def test_3_has_permission_denies_when_scope_narrower_than_role(self):
        user = TokenData(username="a@b.com", role="admin", tenant_id="t1",
                          scopes=["view:itam"], auth_source="api_key")
        with pytest.raises(HTTPException) as exc_info:
            _run(self._call_has_permission("manage:itam", user))
        assert exc_info.value.status_code == 403

    def test_4_has_permission_denies_when_role_lacks_permission_even_if_scope_grants_it(self):
        user = TokenData(username="a@b.com", role="itam_viewer", tenant_id="t1",
                          scopes=["manage:itam"], auth_source="api_key")
        with pytest.raises(HTTPException) as exc_info:
            _run(self._call_has_permission("manage:itam", user))
        assert exc_info.value.status_code == 403

    def test_5_super_admin_wildcard_narrowed_by_api_key_scopes_but_not_by_session(self):
        api_key_user = TokenData(username="root@platform.com", role="super_admin", tenant_id=None,
                                  scopes=["view:itam"], auth_source="api_key")
        with pytest.raises(HTTPException) as exc_info:
            _run(self._call_has_permission("manage:itam", api_key_user))
        assert exc_info.value.status_code == 403

        session_user = TokenData(username="root@platform.com", role="super_admin", tenant_id=None)
        result = _run(self._call_has_permission("manage:itam", session_user))
        assert result is session_user

    def test_6_session_tokendata_scope_check_behaves_unchanged(self):
        user = TokenData(username="a@b.com", role="admin", tenant_id="t1")
        result = _run(self._call_has_permission("manage:itam", user))
        assert result is user

        denied_user = TokenData(username="a@b.com", role="viewer", tenant_id="t1")
        with pytest.raises(HTTPException) as exc_info:
            _run(self._call_has_permission("manage:itam", denied_user))
        assert exc_info.value.status_code == 403

    def test_7_require_role_enforces_admin_gating_scope_for_api_key(self):
        missing_scope_user = TokenData(username="a@b.com", role="admin", tenant_id="t1",
                                        scopes=["view:itam"], auth_source="api_key")
        with pytest.raises(HTTPException) as exc_info:
            _run(self._call_require_role(["admin"], missing_scope_user))
        assert exc_info.value.status_code == 403

        with_scope_user = TokenData(username="a@b.com", role="admin", tenant_id="t1",
                                     scopes=["admin:itam"], auth_source="api_key")
        result = _run(self._call_require_role(["admin"], with_scope_user))
        assert result is with_scope_user

        session_user = TokenData(username="a@b.com", role="admin", tenant_id="t1")
        result2 = _run(self._call_require_role(["admin"], session_user))
        assert result2 is session_user

    def test_8_empty_scopes_list_denies_every_permission(self):
        user = TokenData(username="a@b.com", role="admin", tenant_id="t1",
                          scopes=[], auth_source="api_key")
        with pytest.raises(HTTPException) as exc_info:
            _run(self._call_has_permission("view:itam", user))
        assert exc_info.value.status_code == 403
