"""User CRUD tests — Phase 64 Plan 01 (ITAM-USR-01).

user_endpoints.py does its own manual tenantId filtering (via
tenant_context.get_tenant_id()) rather than routing through
database.TenantIsolatedDatabase, so these tests use a small hand-rolled
in-memory Mongo-ish collection (matching the established convention in
test_support_admin_to_user.py / test_itam_audit.py) rather than the
TenantIsolatedDatabase double used by the itam_* test suites.

Admin gating goes through itam_asset_endpoints._require_itam_admin, which
calls rbac_utils.verify_permission("manage:assets"). Rather than blanket
`AsyncMock(return_value=True)` (which would defeat the admin-gating tests
this file is specifically responsible for), verify_permission is patched
with a role-aware fake mirroring the codebase's actual admin-role set.
"""
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId
from httpx import AsyncClient, ASGITransport

from tests.conftest import make_test_app, make_token_data
from authentication_service import get_current_user as real_get_current_user


# ── Minimal in-memory Mongo-ish collection ──────────────────────────────────

def _match(doc, query):
    for k, v in (query or {}).items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
        elif isinstance(v, dict) and "$regex" in v:
            flags = re.IGNORECASE if v.get("$options") == "i" else 0
            if not re.search(v["$regex"], str(doc.get(k, "")), flags):
                return False
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


def _project(doc, projection):
    if not projection:
        return dict(doc)
    exclude = {k for k, v in projection.items() if v == 0}
    return {k: v for k, v in doc.items() if k not in exclude}


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **k):
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    def limit(self, n):
        if n:
            self._docs = self._docs[:n]
        return self

    async def to_list(self, length=None):
        return self._docs[:length] if length else list(self._docs)


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query=None, projection=None):
        for d in self.docs:
            if _match(d, query or {}):
                return _project(d, projection)
        return None

    def find(self, query=None, projection=None):
        return _FakeCursor([_project(d, projection) for d in self.docs if _match(d, query or {})])

    async def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return type("R", (), {"inserted_id": doc["_id"]})()

    async def update_one(self, query, update):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                del self.docs[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    async def count_documents(self, query=None):
        return sum(1 for d in self.docs if _match(d, query or {}))


class FakeDB:
    def __init__(self, users=None, tenants=None):
        self.users = FakeCollection(users or [])
        self.tenants = FakeCollection(tenants or [])
        self.audit_logs = FakeCollection([])
        self.audit_logs.insert_one = AsyncMock(side_effect=self.audit_logs.insert_one)


# ── Fixtures ─────────────────────────────────────────────────────────────────

TENANT_A = {"id": "tenant-a", "name": "Tenant A"}
TENANT_B = {"id": "tenant-b", "name": "Tenant B"}

# Admin-gate role set mirrored from rbac_utils.DEFAULT_PERMISSIONS/manage:assets
# grantees, including the Title-Case "Admin" the /api/roles UI stub actually
# sends (see 64-01-SUMMARY.md deviation notes).
_FAKE_ADMIN_ROLES = {"admin", "Admin", "Tenant Admin", "tenant_admin"}


async def _fake_verify_permission(user, permission):
    from rbac_utils import is_super_admin
    if permission != "manage:assets":
        return False
    return is_super_admin(user.role) or user.role in _FAKE_ADMIN_ROLES


@pytest.fixture
def fake_db():
    return FakeDB(tenants=[dict(TENANT_A), dict(TENANT_B)])


@pytest.fixture
def app(fake_db, monkeypatch):
    import user_endpoints
    import itam_asset_endpoints

    monkeypatch.setattr(user_endpoints, "get_database", lambda: fake_db)
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(side_effect=_fake_verify_permission))
    monkeypatch.setattr(user_endpoints, "get_tenant_id", lambda: "tenant-a")

    app, _ = make_test_app(user_endpoints.router)
    return app


def _override_user(app, token):
    app.dependency_overrides[real_get_current_user] = lambda: token


async def _client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


# ── Task 1: Create ──────────────────────────────────────────────────────────

class TestCreateUser:
    @pytest.mark.asyncio
    async def test_create_user_with_itam_fields(self, app, fake_db):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.post("/api/users", json={
                "email": "newuser@tenant-a.com",
                "password": "Str0ng!Passw0rd",
                "full_name": "New User",
                "role": "user",
                "tenantId": "tenant-a",
            })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["email"] == "newuser@tenant-a.com"
        assert body["tenantId"] == "tenant-a"
        assert body["status"] == "Active"
        assert body["createdAt"]
        assert body["updatedAt"]
        assert "password" not in body
        assert "hashed_password" not in body

        stored = fake_db.users.docs[0]
        assert stored["status"] == "Active"
        assert stored["hashed_password"] != "Str0ng!Passw0rd"

    @pytest.mark.asyncio
    async def test_create_user_invalid_role_rejected(self, app):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.post("/api/users", json={
                "email": "x@tenant-a.com", "password": "Str0ng!Passw0rd",
                "full_name": "X", "role": "not_a_real_role", "tenantId": "tenant-a",
            })
        assert r.status_code == 400, r.text

    @pytest.mark.asyncio
    async def test_create_user_title_case_admin_role_accepted(self, app):
        """Regression: the /api/roles UI stub sends Title-Case role names
        ('Admin'), which must normalize-match rbac_service.default_roles'
        lowercase 'admin' key rather than being rejected as unknown."""
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.post("/api/users", json={
                "email": "titlecase@tenant-a.com", "password": "Str0ng!Passw0rd",
                "full_name": "Title Case", "role": "Admin", "tenantId": "tenant-a",
            })
        assert r.status_code == 201, r.text

    @pytest.mark.asyncio
    async def test_non_super_admin_cannot_assign_super_admin_role(self, app):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.post("/api/users", json={
                "email": "escalate@tenant-a.com", "password": "Str0ng!Passw0rd",
                "full_name": "Escalate", "role": "super_admin", "tenantId": "tenant-a",
            })
        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_super_admin_can_assign_super_admin_role(self, app):
        super_admin = make_token_data(username="root@platform.com", role="Super Admin", tenant_id="platform-admin")
        _override_user(app, super_admin)

        async with await _client(app) as ac:
            r = await ac.post("/api/users", json={
                "email": "newsuper@tenant-a.com", "password": "Str0ng!Passw0rd",
                "full_name": "New Super", "role": "super_admin", "tenantId": "tenant-a",
            })
        assert r.status_code == 201, r.text

    @pytest.mark.asyncio
    async def test_create_user_nonexistent_tenant_rejected(self, app):
        super_admin = make_token_data(username="root@platform.com", role="Super Admin", tenant_id="platform-admin")
        _override_user(app, super_admin)

        async with await _client(app) as ac:
            r = await ac.post("/api/users", json={
                "email": "ghost@nowhere.com", "password": "Str0ng!Passw0rd",
                "full_name": "Ghost", "role": "user", "tenantId": "tenant-ghost",
            })
        assert r.status_code == 400, r.text
        assert "does not exist" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_non_admin_cannot_create_user(self, app):
        regular_user = make_token_data(username="bob@tenant-a.com", role="user", tenant_id="tenant-a")
        _override_user(app, regular_user)

        async with await _client(app) as ac:
            r = await ac.post("/api/users", json={
                "email": "y@tenant-a.com", "password": "Str0ng!Passw0rd",
                "full_name": "Y", "role": "user", "tenantId": "tenant-a",
            })
        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_create_user_weak_password_rejected(self, app):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.post("/api/users", json={
                "email": "weak@tenant-a.com", "password": "weak", "full_name": "Weak",
                "role": "user", "tenantId": "tenant-a",
            })
        assert r.status_code == 400, r.text


# ── Task 1: Read / /me ───────────────────────────────────────────────────────

class TestUserProfile:
    @pytest.mark.asyncio
    async def test_get_my_profile_does_not_require_admin(self, app, fake_db):
        fake_db.users.docs.append({
            "_id": ObjectId(), "email": "bob@tenant-a.com", "full_name": "Bob",
            "role": "user", "tenantId": "tenant-a", "status": "Active",
            "createdAt": "2026-01-01T00:00:00Z", "hashed_password": "x",
        })
        regular_user = make_token_data(username="bob@tenant-a.com", role="user", tenant_id="tenant-a")
        _override_user(app, regular_user)

        async with await _client(app) as ac:
            r = await ac.get("/api/users/me")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["email"] == "bob@tenant-a.com"
        assert "hashed_password" not in body
        assert "password" not in body


# ── Task 1: Tenant isolation on list ─────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_tenant_admin_only_sees_own_tenant_users(self, app, fake_db):
        fake_db.users.docs.extend([
            {"_id": ObjectId(), "email": "a1@tenant-a.com", "full_name": "A1", "role": "user",
             "tenantId": "tenant-a", "status": "Active", "createdAt": "2026-01-01T00:00:00Z"},
            {"_id": ObjectId(), "email": "b1@tenant-b.com", "full_name": "B1", "role": "user",
             "tenantId": "tenant-b", "status": "Active", "createdAt": "2026-01-01T00:00:00Z"},
        ])
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.get("/api/users")
        assert r.status_code == 200, r.text
        emails = {u["email"] for u in r.json()}
        assert emails == {"a1@tenant-a.com"}

    @pytest.mark.asyncio
    async def test_list_users_requires_admin_gate(self, app, fake_db):
        fake_db.users.docs.append({
            "_id": ObjectId(), "email": "a1@tenant-a.com", "full_name": "A1", "role": "user",
            "tenantId": "tenant-a", "status": "Active", "createdAt": "2026-01-01T00:00:00Z",
        })
        regular_user = make_token_data(username="bob@tenant-a.com", role="user", tenant_id="tenant-a")
        _override_user(app, regular_user)

        async with await _client(app) as ac:
            r = await ac.get("/api/users")
        assert r.status_code == 403, r.text


# ── Task 1: Update ───────────────────────────────────────────────────────────

class TestUpdateUser:
    @pytest.mark.asyncio
    async def test_update_user_role_and_status(self, app, fake_db):
        user_id = ObjectId()
        fake_db.users.docs.append({
            "_id": user_id, "email": "carol@tenant-a.com", "full_name": "Carol",
            "role": "user", "tenantId": "tenant-a", "status": "Active",
            "createdAt": "2026-01-01T00:00:00Z",
        })
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.put(f"/api/users/{user_id}", json={"role": "analyst", "status": "inactive"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["role"] == "analyst"
        assert body["status"] == "Disabled"  # inactive collapses to the two-value display contract

        stored = fake_db.users.docs[0]
        assert stored["status"] == "Inactive"

    @pytest.mark.asyncio
    async def test_update_user_blocks_password_change_for_ldap_sourced_user(self, app, fake_db):
        """ITAM-USR-03 Pitfall 4 / T-64-12: LDAP is the source of truth for
        an LDAP-sourced user's credentials — local password changes via
        this admin endpoint must be rejected."""
        user_id = ObjectId()
        fake_db.users.docs.append({
            "_id": user_id, "email": "ldapuser@tenant-a.com", "full_name": "LDAP User",
            "role": "user", "tenantId": "tenant-a", "status": "Active", "source": "ldap",
            "createdAt": "2026-01-01T00:00:00Z",
        })
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.put(f"/api/users/{user_id}", json={"password": "NewStr0ng!Passw0rd"})
        assert r.status_code == 403, r.text

        stored = fake_db.users.docs[0]
        assert "hashed_password" not in stored

    @pytest.mark.asyncio
    async def test_update_user_cross_tenant_forbidden(self, app, fake_db):
        user_id = ObjectId()
        fake_db.users.docs.append({
            "_id": user_id, "email": "dana@tenant-b.com", "full_name": "Dana",
            "role": "user", "tenantId": "tenant-b", "status": "Active",
            "createdAt": "2026-01-01T00:00:00Z",
        })
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.put(f"/api/users/{user_id}", json={"role": "viewer"})
        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_update_user_invalid_role_rejected(self, app, fake_db):
        user_id = ObjectId()
        fake_db.users.docs.append({
            "_id": user_id, "email": "erin@tenant-a.com", "full_name": "Erin",
            "role": "user", "tenantId": "tenant-a", "status": "Active",
            "createdAt": "2026-01-01T00:00:00Z",
        })
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.put(f"/api/users/{user_id}", json={"role": "galactic_overlord"})
        assert r.status_code == 400, r.text

    @pytest.mark.asyncio
    async def test_non_super_admin_cannot_move_user_between_tenants(self, app, fake_db):
        user_id = ObjectId()
        fake_db.users.docs.append({
            "_id": user_id, "email": "frank@tenant-a.com", "full_name": "Frank",
            "role": "user", "tenantId": "tenant-a", "status": "Active",
            "createdAt": "2026-01-01T00:00:00Z",
        })
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.put(f"/api/users/{user_id}", json={"tenantId": "tenant-b"})
        assert r.status_code == 403, r.text


# ── Task 1: Delete ───────────────────────────────────────────────────────────

class TestDeleteUser:
    @pytest.mark.asyncio
    async def test_delete_user_cross_tenant_forbidden(self, app, fake_db):
        user_id = ObjectId()
        fake_db.users.docs.append({
            "_id": user_id, "email": "gina@tenant-b.com", "full_name": "Gina",
            "role": "user", "tenantId": "tenant-b", "status": "Active",
            "createdAt": "2026-01-01T00:00:00Z",
        })
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.delete(f"/api/users/{user_id}")
        assert r.status_code == 403, r.text
        assert len(fake_db.users.docs) == 1

    @pytest.mark.asyncio
    async def test_cannot_delete_own_account(self, app, fake_db):
        user_id = ObjectId()
        fake_db.users.docs.append({
            "_id": user_id, "email": "admin@tenant-a.com", "full_name": "Admin",
            "role": "admin", "tenantId": "tenant-a", "status": "Active",
            "createdAt": "2026-01-01T00:00:00Z",
        })
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.delete(f"/api/users/{user_id}")
        assert r.status_code == 400, r.text

    @pytest.mark.asyncio
    async def test_delete_user_succeeds_for_own_tenant_admin(self, app, fake_db):
        user_id = ObjectId()
        fake_db.users.docs.append({
            "_id": user_id, "email": "hank@tenant-a.com", "full_name": "Hank",
            "role": "user", "tenantId": "tenant-a", "status": "Active",
            "createdAt": "2026-01-01T00:00:00Z",
        })
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.delete(f"/api/users/{user_id}")
        assert r.status_code == 200, r.text
        assert len(fake_db.users.docs) == 0


# ── Task 2: Pagination / filtering / search ──────────────────────────────────

def _seed_many_users(fake_db, n=5, tenant_id="tenant-a"):
    for i in range(n):
        fake_db.users.docs.append({
            "_id": ObjectId(),
            "email": f"user{i}@tenant-a.com",
            "full_name": f"User {i}",
            "role": "user",
            "tenantId": tenant_id,
            "status": "Active",
            "createdAt": f"2026-01-{i + 1:02d}T00:00:00Z",
        })


@pytest.mark.asyncio
async def test_user_list_pagination(app, fake_db):
    _seed_many_users(fake_db, n=5)
    admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
    _override_user(app, admin)

    async with await _client(app) as ac:
        r = await ac.get("/api/users", params={"skip": 2, "limit": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 2
    assert r.headers.get("X-Total-Count") == "5"


class TestListUsersFilteringAndSearch:
    @pytest.mark.asyncio
    async def test_list_users_returns_bare_array_when_unpaginated(self, app, fake_db):
        """GET /api/users with no query params must stay a plain JSON array —
        services/apiService.ts fetchUsers() assigns the body straight into an
        array-typed cache (fetchWithCache('users', '/users', [], ...))."""
        _seed_many_users(fake_db, n=3)
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.get("/api/users")
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list)
        assert len(body) == 3

    @pytest.mark.asyncio
    async def test_list_users_filter_by_role(self, app, fake_db):
        fake_db.users.docs.extend([
            {"_id": ObjectId(), "email": "viewer1@tenant-a.com", "full_name": "V1", "role": "viewer",
             "tenantId": "tenant-a", "status": "Active", "createdAt": "2026-01-01T00:00:00Z"},
            {"_id": ObjectId(), "email": "user1@tenant-a.com", "full_name": "U1", "role": "user",
             "tenantId": "tenant-a", "status": "Active", "createdAt": "2026-01-01T00:00:00Z"},
        ])
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.get("/api/users", params={"role": "viewer"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["email"] == "viewer1@tenant-a.com"

    @pytest.mark.asyncio
    async def test_list_users_filter_by_status(self, app, fake_db):
        fake_db.users.docs.extend([
            {"_id": ObjectId(), "email": "active1@tenant-a.com", "full_name": "A1", "role": "user",
             "tenantId": "tenant-a", "status": "Active", "createdAt": "2026-01-01T00:00:00Z"},
            {"_id": ObjectId(), "email": "inactive1@tenant-a.com", "full_name": "I1", "role": "user",
             "tenantId": "tenant-a", "status": "Inactive", "createdAt": "2026-01-01T00:00:00Z"},
        ])
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.get("/api/users", params={"status": "inactive"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["email"] == "inactive1@tenant-a.com"

    @pytest.mark.asyncio
    async def test_list_users_search_by_email_or_name(self, app, fake_db):
        fake_db.users.docs.extend([
            {"_id": ObjectId(), "email": "zack@tenant-a.com", "full_name": "Zack Zebra", "role": "user",
             "tenantId": "tenant-a", "status": "Active", "createdAt": "2026-01-01T00:00:00Z"},
            {"_id": ObjectId(), "email": "other@tenant-a.com", "full_name": "Other Person", "role": "user",
             "tenantId": "tenant-a", "status": "Active", "createdAt": "2026-01-01T00:00:00Z"},
        ])
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.get("/api/users", params={"search": "zebra"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["email"] == "zack@tenant-a.com"

    @pytest.mark.asyncio
    async def test_list_users_tenant_filter_super_admin_only(self, app, fake_db):
        fake_db.users.docs.extend([
            {"_id": ObjectId(), "email": "a1@tenant-a.com", "full_name": "A1", "role": "user",
             "tenantId": "tenant-a", "status": "Active", "createdAt": "2026-01-01T00:00:00Z"},
            {"_id": ObjectId(), "email": "b1@tenant-b.com", "full_name": "B1", "role": "user",
             "tenantId": "tenant-b", "status": "Active", "createdAt": "2026-01-01T00:00:00Z"},
        ])
        super_admin = make_token_data(username="root@platform.com", role="Super Admin", tenant_id="platform-admin")
        _override_user(app, super_admin)

        async with await _client(app) as ac:
            r = await ac.get("/api/users", params={"tenantId": "tenant-b"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["email"] == "b1@tenant-b.com"

    @pytest.mark.asyncio
    async def test_list_users_non_super_admin_tenant_param_ignored(self, app, fake_db):
        """A tenant-scoped admin can never widen their view via the tenantId
        query param — it is silently overridden to their own tenant."""
        fake_db.users.docs.extend([
            {"_id": ObjectId(), "email": "a1@tenant-a.com", "full_name": "A1", "role": "user",
             "tenantId": "tenant-a", "status": "Active", "createdAt": "2026-01-01T00:00:00Z"},
            {"_id": ObjectId(), "email": "b1@tenant-b.com", "full_name": "B1", "role": "user",
             "tenantId": "tenant-b", "status": "Active", "createdAt": "2026-01-01T00:00:00Z"},
        ])
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(app, admin)

        async with await _client(app) as ac:
            r = await ac.get("/api/users", params={"tenantId": "tenant-b"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["email"] == "a1@tenant-a.com"
