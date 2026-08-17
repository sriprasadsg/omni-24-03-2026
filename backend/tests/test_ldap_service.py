"""
Unit tests for ldap_service.py (ITAM-USR-03).

Covers: LDAPConfig resolution, connection pooling, authentication (bind),
user sync/mapping, group-to-role mapping, and the full authenticate_ldap
flow. LDAP wire operations are mocked via unittest.mock (no real LDAP
server required) — see plan 64-03 Task 1.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ldap3.core.exceptions import LDAPBindError, LDAPSocketOpenError

from ldap_service import (
    LDAPConfig,
    LDAPConfigError,
    LDAPConnectionError,
    LDAPAuthError,
    LDAPSyncError,
    LDAPConnectionManager,
    LDAPAuthenticator,
    LDAPUserSyncer,
    LDAPGroupMapper,
    get_ldap_config,
    authenticate_ldap,
    is_ldap_sourced_user,
)


def _run(coro):
    return asyncio.run(coro)


def _config(**overrides) -> LDAPConfig:
    base = dict(
        uri="ldap://ldap.example.com:389",
        bind_dn="cn=svc,dc=example,dc=com",
        bind_password="svc-pass",
        user_base_dn="ou=users,dc=example,dc=com",
        group_base_dn="ou=groups,dc=example,dc=com",
    )
    base.update(overrides)
    return LDAPConfig(**base)


class _FakeEntry:
    def __init__(self, dn, attrs):
        self.entry_dn = dn
        self.entry_attributes_as_dict = attrs


def _make_conn(bind_ok=True, entries=None):
    conn = MagicMock()
    conn.open.return_value = None
    conn.bind.return_value = bind_ok
    conn.bound = bind_ok
    conn.result = {"description": "success" if bind_ok else "invalidCredentials"}
    conn.entries = entries or []
    conn.start_tls.return_value = True
    conn.search = MagicMock(return_value=True)
    conn.unbind = MagicMock()
    return conn


def _patch_ldap3(server_ssl=False, connections=None):
    """Patch ldap_service.Server/Connection. `connections` is a list of
    pre-built fake Connection objects returned in order across successive
    Connection(...) calls; the last one repeats if the list is exhausted."""
    server = MagicMock()
    server.ssl = server_ssl
    conns = list(connections or [_make_conn()])

    def _connection_factory(*args, **kwargs):
        if len(conns) > 1:
            return conns.pop(0)
        return conns[0]

    server_patch = patch("ldap_service.Server", return_value=server)
    conn_patch = patch("ldap_service.Connection", side_effect=_connection_factory)
    return server_patch, conn_patch


# ===========================================================================
# LDAPConfig
# ===========================================================================

class TestLDAPConfig:

    def test_from_env_requires_core_vars(self, monkeypatch):
        monkeypatch.delenv("LDAP_URI", raising=False)
        monkeypatch.delenv("LDAP_BIND_DN", raising=False)
        monkeypatch.delenv("LDAP_USER_BASE_DN", raising=False)
        with pytest.raises(LDAPConfigError):
            LDAPConfig.from_env()

    def test_from_env_builds_config_with_defaults(self, monkeypatch):
        monkeypatch.setenv("LDAP_URI", "ldaps://ad.example.com:636")
        monkeypatch.setenv("LDAP_BIND_DN", "cn=svc,dc=example,dc=com")
        monkeypatch.setenv("LDAP_BIND_PASSWORD", "secret")
        monkeypatch.setenv("LDAP_USER_BASE_DN", "ou=users,dc=example,dc=com")
        cfg = LDAPConfig.from_env()
        assert cfg.uri == "ldaps://ad.example.com:636"
        assert cfg.user_id_attr == "sAMAccountName"
        assert cfg.user_filter == "(objectClass=user)"

    def test_from_dict_applies_defaults_for_missing_optional_fields(self):
        cfg = LDAPConfig.from_dict({
            "uri": "ldap://x:389", "bind_dn": "cn=a", "bind_password": "p",
            "user_base_dn": "ou=u,dc=x",
        })
        assert cfg.user_filter == "(objectClass=user)"
        assert cfg.group_member_attr == "member"


class TestGetLdapConfig:

    def test_falls_back_to_env_when_no_db_doc(self, monkeypatch):
        monkeypatch.setenv("LDAP_URI", "ldap://env:389")
        monkeypatch.setenv("LDAP_BIND_DN", "cn=svc")
        monkeypatch.setenv("LDAP_USER_BASE_DN", "ou=users")
        db = MagicMock()
        db.ldap_configs.find_one = AsyncMock(return_value=None)
        with patch("ldap_service.get_database", return_value=db):
            cfg = _run(get_ldap_config(tenant_id="t1"))
        assert cfg.uri == "ldap://env:389"

    def test_uses_db_doc_and_decrypts_password(self):
        db = MagicMock()
        db.ldap_configs.find_one = AsyncMock(return_value={
            "uri": "ldap://db:389", "bind_dn": "cn=svc,dc=x",
            "bind_password_encrypted": "enc(secret)", "user_base_dn": "ou=users,dc=x",
            "tenant_id": "t1",
        })
        enc_svc = MagicMock()
        enc_svc.decrypt.return_value = "plaintext-secret"
        with patch("ldap_service.get_database", return_value=db), \
             patch("encryption_service.get_encryption_service", return_value=enc_svc):
            cfg = _run(get_ldap_config(tenant_id="t1"))
        assert cfg.uri == "ldap://db:389"
        assert cfg.bind_password == "plaintext-secret"

    def test_tenant_scoped_falls_back_to_platform_default(self):
        db = MagicMock()
        platform_doc = {
            "uri": "ldap://platform:389", "bind_dn": "cn=svc,dc=x",
            "bind_password": "p", "user_base_dn": "ou=users,dc=x", "tenant_id": None,
        }
        db.ldap_configs.find_one = AsyncMock(side_effect=[None, platform_doc])
        with patch("ldap_service.get_database", return_value=db):
            cfg = _run(get_ldap_config(tenant_id="t1"))
        assert cfg.uri == "ldap://platform:389"


# ===========================================================================
# LDAPConnectionManager
# ===========================================================================

class TestLDAPConnectionManager:

    def test_service_connection_pools_and_reuses(self):
        conn = _make_conn(bind_ok=True)
        server_patch, conn_patch = _patch_ldap3(connections=[conn])
        with server_patch, conn_patch:
            mgr = LDAPConnectionManager(_config(), pool_size=3)
            with mgr.service_connection() as c1:
                assert c1 is conn
            with mgr.service_connection() as c2:
                assert c2 is conn  # reused from pool, not a fresh bind
            assert conn.bind.call_count == 1

    def test_user_connection_never_pooled_and_unbinds(self):
        conn = _make_conn(bind_ok=True)
        server_patch, conn_patch = _patch_ldap3(connections=[conn])
        with server_patch, conn_patch:
            mgr = LDAPConnectionManager(_config())
            with mgr.user_connection("cn=u,dc=x", "pw") as c:
                assert c is conn
            conn.unbind.assert_called_once()
            assert mgr._pool == []

    def test_connection_retries_then_raises_ldapconnectionerror(self):
        server = MagicMock()
        server.ssl = False

        def _always_fails(*a, **k):
            raise LDAPSocketOpenError("no route to host")

        with patch("ldap_service.Server", return_value=server), \
             patch("ldap_service.Connection", side_effect=_always_fails):
            mgr = LDAPConnectionManager(_config(), retries=1)
            with pytest.raises(LDAPConnectionError):
                with mgr.service_connection():
                    pass

    def test_bind_failure_raises_ldapbinderror(self):
        conn = _make_conn(bind_ok=False)
        server_patch, conn_patch = _patch_ldap3(connections=[conn])
        with server_patch, conn_patch:
            mgr = LDAPConnectionManager(_config())
            with pytest.raises(LDAPBindError):
                with mgr.service_connection():
                    pass


# ===========================================================================
# LDAPAuthenticator (auth)
# ===========================================================================

class TestLDAPAuthenticatorAuth:

    def test_authenticate_success(self):
        search_conn = _make_conn(bind_ok=True, entries=[
            _FakeEntry("cn=jdoe,ou=users,dc=x", {"sAMAccountName": ["jdoe"]}),
        ])
        user_conn = _make_conn(bind_ok=True)
        server_patch, conn_patch = _patch_ldap3(connections=[search_conn, user_conn])
        with server_patch, conn_patch:
            auth = LDAPAuthenticator(_config())
            result = auth.authenticate("jdoe", "correct-password")
        assert result["dn"] == "cn=jdoe,ou=users,dc=x"

    def test_authenticate_no_user_found_raises_ldapautherror(self):
        search_conn = _make_conn(bind_ok=True, entries=[])
        server_patch, conn_patch = _patch_ldap3(connections=[search_conn])
        with server_patch, conn_patch:
            auth = LDAPAuthenticator(_config())
            with pytest.raises(LDAPAuthError):
                auth.authenticate("ghost", "pw")

    def test_authenticate_bad_credentials_raises_ldapautherror(self):
        search_conn = _make_conn(bind_ok=True, entries=[
            _FakeEntry("cn=jdoe,ou=users,dc=x", {"sAMAccountName": ["jdoe"]}),
        ])
        bad_user_conn = _make_conn(bind_ok=False)
        server_patch, conn_patch = _patch_ldap3(connections=[search_conn, bad_user_conn])
        with server_patch, conn_patch:
            auth = LDAPAuthenticator(_config())
            with pytest.raises(LDAPAuthError):
                auth.authenticate("jdoe", "wrong-password")

    def test_authenticate_empty_password_rejected(self):
        auth = LDAPAuthenticator(_config())
        with pytest.raises(LDAPAuthError):
            auth.authenticate("jdoe", "")


# ===========================================================================
# LDAPUserSyncer
# ===========================================================================

class TestLDAPUserSyncer:

    def test_map_entry_extracts_fields(self):
        syncer = LDAPUserSyncer(_config())
        entry = _FakeEntry("cn=jdoe,ou=users,dc=x", {
            "sAMAccountName": ["jdoe"], "mail": ["jdoe@example.com"],
            "displayName": ["Jane Doe"], "memberOf": ["cn=itam-admins,ou=groups,dc=x"],
        })
        mapped = syncer._map_entry(entry)
        assert mapped == {
            "ldap_dn": "cn=jdoe,ou=users,dc=x", "ldap_user_id": "jdoe",
            "email": "jdoe@example.com", "full_name": "Jane Doe",
            "groups": ["cn=itam-admins,ou=groups,dc=x"],
        }

    def test_map_entry_skips_when_email_missing(self):
        syncer = LDAPUserSyncer(_config())
        entry = _FakeEntry("cn=jdoe,ou=users,dc=x", {"sAMAccountName": ["jdoe"]})
        assert syncer._map_entry(entry) is None

    def test_sync_user_creates_new_with_source_ldap(self):
        db = MagicMock()
        db.users.find_one = AsyncMock(return_value=None)
        inserted = MagicMock()
        inserted.inserted_id = "new-id"
        db.users.insert_one = AsyncMock(return_value=inserted)
        with patch("ldap_service.get_database", return_value=db):
            syncer = LDAPUserSyncer(_config())
            mapped = {"ldap_dn": "cn=jdoe", "ldap_user_id": "jdoe",
                      "email": "jdoe@example.com", "full_name": "Jane Doe", "groups": []}
            doc = _run(syncer.sync_user(mapped, tenant_id="t1"))
        assert doc["source"] == "ldap"
        assert doc["role"] == "itam_viewer"  # default_role applied on create
        db.users.insert_one.assert_awaited_once()

    def test_sync_user_update_preserves_existing_role_when_no_mapping(self):
        """Re-syncing a user with no resolved group mapping must NOT reset
        an admin-assigned elevated role back to the default (regression
        guard for an 'every re-sync clobbers role' bug)."""
        db = MagicMock()
        existing = {"_id": "abc123", "email": "jdoe@example.com", "role": "itam_admin"}
        db.users.find_one = AsyncMock(return_value=existing)
        db.users.update_one = AsyncMock()
        with patch("ldap_service.get_database", return_value=db):
            syncer = LDAPUserSyncer(_config())
            mapped = {"ldap_dn": "cn=jdoe", "ldap_user_id": "jdoe",
                      "email": "jdoe@example.com", "full_name": "Jane Doe", "groups": []}
            doc = _run(syncer.sync_user(mapped, tenant_id="t1", role=None))
        assert doc["role"] == "itam_admin"

    def test_sync_user_update_applies_resolved_role(self):
        db = MagicMock()
        existing = {"_id": "abc123", "email": "jdoe@example.com", "role": "itam_viewer"}
        db.users.find_one = AsyncMock(return_value=existing)
        db.users.update_one = AsyncMock()
        with patch("ldap_service.get_database", return_value=db):
            syncer = LDAPUserSyncer(_config())
            mapped = {"ldap_dn": "cn=jdoe", "ldap_user_id": "jdoe",
                      "email": "jdoe@example.com", "full_name": "Jane Doe", "groups": []}
            doc = _run(syncer.sync_user(mapped, tenant_id="t1", role="itam_admin"))
        assert doc["role"] == "itam_admin"

    def test_sync_all_summarizes_results(self):
        syncer = LDAPUserSyncer(_config())
        mapped_users = [
            {"ldap_dn": "cn=a", "ldap_user_id": "a", "email": "a@x.com", "full_name": "A", "groups": []},
            {"ldap_dn": "cn=b", "ldap_user_id": "b", "email": "b@x.com", "full_name": "B", "groups": []},
        ]
        with patch.object(syncer, "search_users", return_value=mapped_users), \
             patch.object(syncer, "sync_user", new=AsyncMock(return_value={})):
            result = _run(syncer.sync_all(tenant_id="t1"))
        assert result["total_found"] == 2
        assert result["synced"] == 2
        assert result["errors"] == []

    def test_sync_all_records_errors_without_aborting(self):
        syncer = LDAPUserSyncer(_config())
        mapped_users = [
            {"ldap_dn": "cn=a", "ldap_user_id": "a", "email": "a@x.com", "full_name": "A", "groups": []},
        ]

        async def _boom(*a, **k):
            raise RuntimeError("db down")

        with patch.object(syncer, "search_users", return_value=mapped_users), \
             patch.object(syncer, "sync_user", new=_boom):
            result = _run(syncer.sync_all(tenant_id="t1"))
        assert result["synced"] == 0
        assert len(result["errors"]) == 1


# ===========================================================================
# LDAPGroupMapper
# ===========================================================================

class TestLDAPGroupMapper:

    def test_resolve_role_returns_highest_priority_match(self):
        db = MagicMock()
        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.to_list = AsyncMock(return_value=[{"role": "itam_admin", "priority": 1}])
        db.ldap_group_mappings.find.return_value = cursor
        with patch("ldap_service.get_database", return_value=db):
            role = _run(LDAPGroupMapper(_config()).resolve_role(["cn=itam-admins,ou=groups,dc=x"], "t1"))
        assert role == "itam_admin"

    def test_resolve_role_returns_none_when_no_groups(self):
        role = _run(LDAPGroupMapper(_config()).resolve_role([], "t1"))
        assert role is None

    def test_upsert_mapping_rejects_invalid_role(self):
        with pytest.raises(LDAPConfigError):
            _run(LDAPGroupMapper.upsert_mapping("cn=g,dc=x", "not_a_real_role"))

    def test_upsert_mapping_accepts_valid_role(self):
        db = MagicMock()
        result = MagicMock()
        result.upserted_id = "new-map-id"
        db.ldap_group_mappings.update_one = AsyncMock(return_value=result)
        with patch("ldap_service.get_database", return_value=db):
            doc = _run(LDAPGroupMapper.upsert_mapping("cn=g,dc=x", "itam_admin", tenant_id="t1"))
        assert doc["role"] == "itam_admin"
        assert doc["_id"] == "new-map-id"

    def test_delete_mapping(self):
        db = MagicMock()
        del_result = MagicMock()
        del_result.deleted_count = 1
        db.ldap_group_mappings.delete_one = AsyncMock(return_value=del_result)
        with patch("ldap_service.get_database", return_value=db), \
             patch("bson.ObjectId", side_effect=lambda x: x):
            deleted = _run(LDAPGroupMapper.delete_mapping("507f1f77bcf86cd799439011"))
        assert deleted is True


# ===========================================================================
# is_ldap_sourced_user
# ===========================================================================

class TestIsLdapSourcedUser:

    def test_true_for_ldap_source(self):
        db = MagicMock()
        db.users.find_one = AsyncMock(return_value={"source": "ldap"})
        with patch("ldap_service.get_database", return_value=db):
            assert _run(is_ldap_sourced_user("jdoe@example.com")) is True

    def test_false_for_local_source(self):
        db = MagicMock()
        db.users.find_one = AsyncMock(return_value={"source": "local"})
        with patch("ldap_service.get_database", return_value=db):
            assert _run(is_ldap_sourced_user("jdoe@example.com")) is False

    def test_false_when_user_not_found(self):
        db = MagicMock()
        db.users.find_one = AsyncMock(return_value=None)
        with patch("ldap_service.get_database", return_value=db):
            assert _run(is_ldap_sourced_user("ghost@example.com")) is False


# ===========================================================================
# authenticate_ldap — full flow (auth)
# ===========================================================================

class TestAuthenticateLdapFlowAuth:

    def _patched_db(self, existing_user=None, resolved_role=None):
        db = MagicMock()
        db.users.find_one = AsyncMock(return_value=existing_user)
        db.users.update_one = AsyncMock()
        inserted = MagicMock()
        inserted.inserted_id = "new-id"
        db.users.insert_one = AsyncMock(return_value=inserted)
        db.ldap_configs.find_one = AsyncMock(return_value=None)
        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.to_list = AsyncMock(
            return_value=[{"role": resolved_role}] if resolved_role else []
        )
        db.ldap_group_mappings.find.return_value = cursor
        return db

    def test_full_flow_mints_tokens_for_new_user(self, monkeypatch):
        monkeypatch.setenv("LDAP_URI", "ldap://x:389")
        monkeypatch.setenv("LDAP_BIND_DN", "cn=svc,dc=x")
        monkeypatch.setenv("LDAP_USER_BASE_DN", "ou=users,dc=x")
        monkeypatch.setenv("LDAP_DEFAULT_TENANT_ID", "tenant-default")
        db = self._patched_db(existing_user=None)
        mapped = {"ldap_dn": "cn=jdoe,ou=users,dc=x", "ldap_user_id": "jdoe",
                  "email": "jdoe@example.com", "full_name": "Jane Doe", "groups": []}
        with patch("ldap_service.get_database", return_value=db), \
             patch.object(LDAPAuthenticator, "authenticate", return_value={"dn": mapped["ldap_dn"], "bound": True}), \
             patch.object(LDAPUserSyncer, "search_single_user", return_value=mapped):
            result = _run(authenticate_ldap("jdoe", "correct-password"))
        assert result["success"] is True
        assert result["email"] == "jdoe@example.com"
        assert result["tenant_id"] == "tenant-default"
        assert result.get("access_token")
        assert result.get("refresh_token")

    def test_full_flow_bad_credentials_raises(self, monkeypatch):
        monkeypatch.setenv("LDAP_URI", "ldap://x:389")
        monkeypatch.setenv("LDAP_BIND_DN", "cn=svc,dc=x")
        monkeypatch.setenv("LDAP_USER_BASE_DN", "ou=users,dc=x")
        db = self._patched_db()
        with patch("ldap_service.get_database", return_value=db), \
             patch.object(LDAPAuthenticator, "authenticate", side_effect=LDAPAuthError("bad creds")):
            with pytest.raises(LDAPAuthError):
                _run(authenticate_ldap("jdoe", "wrong"))

    def test_full_flow_no_tenant_determinable_raises_sync_error(self, monkeypatch):
        monkeypatch.setenv("LDAP_URI", "ldap://x:389")
        monkeypatch.setenv("LDAP_BIND_DN", "cn=svc,dc=x")
        monkeypatch.setenv("LDAP_USER_BASE_DN", "ou=users,dc=x")
        monkeypatch.delenv("LDAP_DEFAULT_TENANT_ID", raising=False)
        db = self._patched_db(existing_user=None)
        mapped = {"ldap_dn": "cn=jdoe,ou=users,dc=x", "ldap_user_id": "jdoe",
                  "email": "jdoe@example.com", "full_name": "Jane Doe", "groups": []}
        with patch("ldap_service.get_database", return_value=db), \
             patch.object(LDAPAuthenticator, "authenticate", return_value={"dn": mapped["ldap_dn"], "bound": True}), \
             patch.object(LDAPUserSyncer, "search_single_user", return_value=mapped):
            with pytest.raises(LDAPSyncError):
                _run(authenticate_ldap("jdoe", "correct-password"))

    def test_full_flow_existing_user_inherits_tenant_and_role(self, monkeypatch):
        monkeypatch.setenv("LDAP_URI", "ldap://x:389")
        monkeypatch.setenv("LDAP_BIND_DN", "cn=svc,dc=x")
        monkeypatch.setenv("LDAP_USER_BASE_DN", "ou=users,dc=x")
        existing = {"_id": "abc", "email": "jdoe@example.com", "tenantId": "tenant-a", "role": "itam_admin"}
        db = self._patched_db(existing_user=existing)
        mapped = {"ldap_dn": "cn=jdoe,ou=users,dc=x", "ldap_user_id": "jdoe",
                  "email": "jdoe@example.com", "full_name": "Jane Doe", "groups": []}
        with patch("ldap_service.get_database", return_value=db), \
             patch.object(LDAPAuthenticator, "authenticate", return_value={"dn": mapped["ldap_dn"], "bound": True}), \
             patch.object(LDAPUserSyncer, "search_single_user", return_value=mapped):
            result = _run(authenticate_ldap("jdoe", "correct-password"))
        assert result["tenant_id"] == "tenant-a"
        assert result["role"] == "itam_admin"


# ===========================================================================
# ldap_endpoints.py — admin config/sync/mapping endpoints + login route
# (endpoint, auth)
# ===========================================================================

from bson import ObjectId
from httpx import AsyncClient, ASGITransport

import ldap_endpoints
import ldap_service
from tests.conftest import make_token_data
from authentication_service import get_current_user as real_get_current_user


def _ep_match(doc, query):
    for k, v in (query or {}).items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _EPCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **k):
        return self

    async def to_list(self, length=None):
        return self._docs[:length] if length else list(self._docs)


class _EPCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query=None, projection=None):
        for d in self.docs:
            if _ep_match(d, query or {}):
                return dict(d)
        return None

    def find(self, query=None, projection=None):
        return _EPCursor([dict(d) for d in self.docs if _ep_match(d, query or {})])

    async def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return type("R", (), {"inserted_id": doc["_id"]})()

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _ep_match(d, query):
                d.update(update.get("$set", {}))
                return type("R", (), {"matched_count": 1, "upserted_id": None})()
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", {}))
            new_doc.setdefault("_id", ObjectId())
            self.docs.append(new_doc)
            return type("R", (), {"matched_count": 0, "upserted_id": new_doc["_id"]})()
        return type("R", (), {"matched_count": 0, "upserted_id": None})()

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _ep_match(d, query):
                del self.docs[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()


class _EPFakeDB:
    def __init__(self):
        self.ldap_configs = _EPCollection([])
        self.ldap_group_mappings = _EPCollection([])
        self.users = _EPCollection([])


_ADMIN_ROLES = {"admin", "Admin", "Tenant Admin", "tenant_admin"}


async def _fake_verify_permission(user, permission):
    from rbac_utils import is_super_admin
    if permission != "manage:assets":
        return False
    return is_super_admin(user.role) or user.role in _ADMIN_ROLES


@pytest.fixture
def ep_db():
    return _EPFakeDB()


@pytest.fixture
def ep_app(ep_db, monkeypatch):
    import itam_asset_endpoints

    # Both modules call get_database() from their own namespace — patch both
    # so every code path (endpoint handlers AND ldap_service internals like
    # get_ldap_config/sync_user/resolve_role) sees the same fake DB.
    monkeypatch.setattr(ldap_endpoints, "get_database", lambda: ep_db)
    monkeypatch.setattr(ldap_service, "get_database", lambda: ep_db)
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(side_effect=_fake_verify_permission))
    monkeypatch.setattr(ldap_endpoints, "get_tenant_id", lambda: "tenant-a")

    from fastapi import FastAPI
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from rate_limiter import limiter as shared_limiter

    app = FastAPI()
    app.state.limiter = shared_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(ldap_endpoints.router)
    return app


@pytest.fixture(autouse=True)
def _reset_ldap_rate_limit():
    from rate_limiter import limiter as shared_limiter
    shared_limiter._storage.reset()
    yield
    shared_limiter._storage.reset()


def _override_user(app, token):
    app.dependency_overrides[real_get_current_user] = lambda: token


async def _ep_client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


class TestLDAPConfigEndpoint:

    @pytest.mark.asyncio
    async def test_save_and_read_config_masks_password(self, ep_app, monkeypatch):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        enc = MagicMock()
        enc.encrypt.return_value = "enc(secret)"
        monkeypatch.setattr("encryption_service.get_encryption_service", lambda: enc)

        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/ldap/config", json={
                "uri": "ldap://ad.example.com:389", "bind_dn": "cn=svc,dc=x",
                "bind_password": "super-secret", "user_base_dn": "ou=users,dc=x",
            })
            assert resp.status_code == 200, resp.text
            assert resp.json()["success"] is True

            resp2 = await client.get("/api/admin/ldap/config")
            assert resp2.status_code == 200
            body = resp2.json()
            assert body["bind_password"] == "***masked***"
            assert "bind_password_encrypted" not in body

    @pytest.mark.asyncio
    async def test_config_requires_admin(self, ep_app):
        viewer = make_token_data(username="viewer@tenant-a.com", role="itam_viewer", tenant_id="tenant-a")
        _override_user(ep_app, viewer)
        async with await _ep_client(ep_app) as client:
            resp = await client.get("/api/admin/ldap/config")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_read_config_404_when_unset(self, ep_app):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        async with await _ep_client(ep_app) as client:
            resp = await client.get("/api/admin/ldap/config")
        assert resp.status_code == 404


class TestLDAPTestConnectionEndpoint:

    @pytest.mark.asyncio
    async def test_connection_success(self, ep_app, monkeypatch):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        monkeypatch.setenv("LDAP_URI", "ldap://x:389")
        monkeypatch.setenv("LDAP_BIND_DN", "cn=svc,dc=x")
        monkeypatch.setenv("LDAP_USER_BASE_DN", "ou=users,dc=x")

        class _OkMgr:
            def __init__(self, config):
                pass

            def service_connection(self):
                cm = MagicMock()
                cm.__enter__ = MagicMock(return_value=MagicMock())
                cm.__exit__ = MagicMock(return_value=False)
                return cm

        monkeypatch.setattr(ldap_endpoints, "LDAPConnectionManager", _OkMgr)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/ldap/test-connection")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_connection_not_configured_returns_400(self, ep_app, monkeypatch):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        monkeypatch.delenv("LDAP_URI", raising=False)
        monkeypatch.delenv("LDAP_BIND_DN", raising=False)
        monkeypatch.delenv("LDAP_USER_BASE_DN", raising=False)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/ldap/test-connection")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_connection_failure_returns_502(self, ep_app, monkeypatch):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        monkeypatch.setenv("LDAP_URI", "ldap://x:389")
        monkeypatch.setenv("LDAP_BIND_DN", "cn=svc,dc=x")
        monkeypatch.setenv("LDAP_USER_BASE_DN", "ou=users,dc=x")

        class _FailingCtx:
            def __enter__(self):
                raise LDAPConnectionError("down")

            def __exit__(self, *a):
                return False

        class _FailMgr:
            def __init__(self, config):
                pass

            def service_connection(self):
                return _FailingCtx()

        monkeypatch.setattr(ldap_endpoints, "LDAPConnectionManager", _FailMgr)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/ldap/test-connection")
        assert resp.status_code == 502


class TestLDAPSyncEndpoint:

    @pytest.mark.asyncio
    async def test_trigger_sync_returns_summary(self, ep_app, monkeypatch):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        monkeypatch.setenv("LDAP_URI", "ldap://x:389")
        monkeypatch.setenv("LDAP_BIND_DN", "cn=svc,dc=x")
        monkeypatch.setenv("LDAP_USER_BASE_DN", "ou=users,dc=x")

        async def _fake_sync_all(self, tenant_id, group_mapper=None, default_role="itam_viewer"):
            return {"total_found": 3, "synced": 3, "errors": []}

        monkeypatch.setattr(ldap_service.LDAPUserSyncer, "sync_all", _fake_sync_all)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/ldap/sync")
        assert resp.status_code == 200
        body = resp.json()
        assert body["synced"] == 3

    @pytest.mark.asyncio
    async def test_trigger_sync_requires_admin(self, ep_app):
        viewer = make_token_data(username="viewer@tenant-a.com", role="itam_viewer", tenant_id="tenant-a")
        _override_user(ep_app, viewer)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/ldap/sync")
        assert resp.status_code == 403


class TestLDAPGroupMappingEndpoint:

    @pytest.mark.asyncio
    async def test_create_list_delete_mapping(self, ep_app):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/ldap/group-mapping", json={
                "group_dn": "cn=itam-admins,ou=groups,dc=x", "role": "itam_admin", "priority": 1,
            })
            assert resp.status_code == 200, resp.text
            mapping_id = resp.json()["_id"]

            resp2 = await client.get("/api/admin/ldap/group-mapping")
            assert resp2.status_code == 200
            assert len(resp2.json()) == 1

            resp3 = await client.delete(f"/api/admin/ldap/group-mapping/{mapping_id}")
            assert resp3.status_code == 200
            assert resp3.json()["success"] is True

    @pytest.mark.asyncio
    async def test_create_mapping_rejects_invalid_role(self, ep_app):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/ldap/group-mapping", json={
                "group_dn": "cn=g,dc=x", "role": "not_a_role",
            })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_missing_mapping_returns_404(self, ep_app):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        async with await _ep_client(ep_app) as client:
            resp = await client.delete(f"/api/admin/ldap/group-mapping/{ObjectId()}")
        assert resp.status_code == 404


class TestLDAPLoginEndpointAuth:

    @pytest.mark.asyncio
    async def test_login_success(self, ep_app, monkeypatch):
        async def _fake_authenticate_ldap(username, password, tenant_id=None):
            return {"access_token": "tok", "refresh_token": "rtok", "token_type": "bearer",
                    "success": True, "email": "jdoe@example.com", "role": "itam_viewer",
                    "tenant_id": "tenant-a"}

        monkeypatch.setattr(ldap_endpoints, "authenticate_ldap", _fake_authenticate_ldap)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/auth/ldap/login", json={"username": "jdoe", "password": "correct"})
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "tok"

    @pytest.mark.asyncio
    async def test_login_bad_credentials_returns_401(self, ep_app, monkeypatch):
        async def _fake_authenticate_ldap(username, password, tenant_id=None):
            raise LDAPAuthError("invalid")

        monkeypatch.setattr(ldap_endpoints, "authenticate_ldap", _fake_authenticate_ldap)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/auth/ldap/login", json={"username": "jdoe", "password": "wrong"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_not_configured_returns_503(self, ep_app, monkeypatch):
        async def _fake_authenticate_ldap(username, password, tenant_id=None):
            raise LDAPConfigError("not configured")

        monkeypatch.setattr(ldap_endpoints, "authenticate_ldap", _fake_authenticate_ldap)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/auth/ldap/login", json={"username": "jdoe", "password": "x"})
        assert resp.status_code == 503
