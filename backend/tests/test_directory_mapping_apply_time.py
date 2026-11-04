"""Apply-time checks on LDAP/SAML group-to-role mappings (Phase 75 WR-04).

The mapping endpoints hold the role ceiling when a mapping is written or deleted. These
tests pin what happens when a mapping is *applied* (LDAP sync/login, SAML login):

- a mapping never replaces the role of an existing account that holds permissions the
  mapping's role lacks, unless that role came from the directory in the first place;
- a mapping records who wrote it, and a mapping whose writer can no longer assign its
  role is skipped (logged and audited); a legacy mapping with no writer keeps working.

Both providers share the logic, so every test runs for LDAP and SAML.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

import ldap_service
import saml_mapping
from tests.conftest import make_token_data


def _match(doc, query):
    for key, want in (query or {}).items():
        if isinstance(want, dict) and "$in" in want:
            if doc.get(key) not in want["$in"]:
                return False
        elif doc.get(key) != want:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, key, direction=1):
        self._docs.sort(key=lambda d: d.get(key, 0), reverse=direction == -1)
        return self

    async def to_list(self, length=None):
        return self._docs[:length] if length else self._docs


class _Collection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query=None, projection=None):
        return next((dict(d) for d in self.docs if _match(d, query)), None)

    def find(self, query=None, projection=None):
        return _Cursor([dict(d) for d in self.docs if _match(d, query)])

    async def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return type("R", (), {"inserted_id": doc["_id"]})()

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set", {}))
                return type("R", (), {"matched_count": 1, "upserted_id": None})()
        if upsert:
            doc = dict(query, **update.get("$set", {}), _id=ObjectId())
            self.docs.append(doc)
            return type("R", (), {"matched_count": 0, "upserted_id": doc["_id"]})()
        return type("R", (), {"matched_count": 0, "upserted_id": None})()


class _DB:
    """One in-memory store behind both the tenant wrapper and the raw handle."""

    def __init__(self):
        self.users = _Collection()
        self.roles = _Collection()
        self.ldap_group_mappings = _Collection()
        self.saml_group_mappings = _Collection()
        self._db = self


_LDAP_CONFIG = ldap_service.LDAPConfig(uri="ldap://x", bind_dn="cn=svc", bind_password="pw", user_base_dn="dc=x")


class _LDAP:
    name, module, source = "ldap", ldap_service, "ldap"
    collection, key = "ldap_group_mappings", "group_dn"

    @staticmethod
    def mapped(email):
        return {"ldap_dn": f"cn={email}", "ldap_user_id": email, "email": email,
                "full_name": email, "groups": ["cn=g1", "cn=g2"]}

    @staticmethod
    async def apply(mapped, tenant_id, role):
        return await ldap_service.LDAPUserSyncer(_LDAP_CONFIG).sync_user(
            mapped, tenant_id, role=role)

    @staticmethod
    async def resolve(groups, tenant_id):
        return await ldap_service.LDAPGroupMapper(_LDAP_CONFIG).resolve_role(
            groups, tenant_id)

    @staticmethod
    async def upsert(value, role, tenant_id, writer):
        return await ldap_service.LDAPGroupMapper.upsert_mapping(value, role, tenant_id=tenant_id, writer=writer)


class _SAML:
    name, module, source = "saml", saml_mapping, "saml"
    collection, key = "saml_group_mappings", "group_value"

    @staticmethod
    def mapped(email):
        return {"email": email, "full_name": email, "nameid": email, "groups": ["cn=g1", "cn=g2"]}

    @staticmethod
    async def apply(mapped, tenant_id, role):
        return await saml_mapping.SAMLUserProvisioner(None).provision_user(mapped, tenant_id, role=role)

    @staticmethod
    async def resolve(groups, tenant_id):
        return await saml_mapping.SAMLGroupMapper().resolve_role(groups, tenant_id)

    @staticmethod
    async def upsert(value, role, tenant_id, writer):
        return await saml_mapping.SAMLGroupMapper.upsert_mapping(value, role, tenant_id=tenant_id, writer=writer)


@pytest.fixture(params=[_LDAP, _SAML], ids=lambda p: p.name)
def provider(request):
    return request.param


@pytest.fixture
def db(provider, monkeypatch):
    store = _DB()
    monkeypatch.setattr(provider.module, "get_database", lambda: store)
    return store


@pytest.fixture
def revoke(monkeypatch):
    import authentication_service
    mock = AsyncMock()
    monkeypatch.setattr(authentication_service, "revoke_user_sessions", mock)
    return mock


@pytest.fixture
def audit(monkeypatch):
    import audit_ledger
    mock = AsyncMock(return_value={})
    monkeypatch.setattr(audit_ledger, "event", mock)
    return mock


async def _user(db, email, role, **extra):
    await db.users.insert_one({"email": email, "tenantId": "t1", "role": role, "status": "Active", **extra})


# ------------------------------------------------------------- existing accounts

async def test_mapping_never_demotes_a_local_account_that_holds_more(provider, db, revoke):
    """A local tenant admin who shares an email with a directory entry keeps their role."""
    await _user(db, "boss@x.com", "Tenant Admin")
    doc = await provider.apply(provider.mapped("boss@x.com"), "t1", "itam_viewer")
    assert doc["role"] == "Tenant Admin"
    assert (await db.users.find_one({"email": "boss@x.com"}))["role"] == "Tenant Admin"
    revoke.assert_not_awaited()


async def test_a_protected_local_account_stays_protected_on_the_next_sign_in(provider, db, revoke):
    """The first directory sign-in links the account (source becomes the provider); the
    second one must not treat that link as the directory owning the role."""
    await _user(db, "boss@x.com", "Tenant Admin")
    await provider.apply(provider.mapped("boss@x.com"), "t1", "itam_viewer")
    doc = await provider.apply(provider.mapped("boss@x.com"), "t1", "itam_viewer")
    assert doc["role"] == "Tenant Admin"
    revoke.assert_not_awaited()


async def test_a_local_account_linked_without_a_mapping_stays_protected(provider, db, revoke):
    await _user(db, "boss@x.com", "Tenant Admin")
    await provider.apply(provider.mapped("boss@x.com"), "t1", None)
    doc = await provider.apply(provider.mapped("boss@x.com"), "t1", "itam_viewer")
    assert doc["role"] == "Tenant Admin"
    revoke.assert_not_awaited()


async def test_mapping_still_upgrades_a_local_account(provider, db, revoke):
    await _user(db, "u@x.com", "itam_viewer")
    doc = await provider.apply(provider.mapped("u@x.com"), "t1", "itam_admin")
    assert doc["role"] == "itam_admin"
    revoke.assert_awaited_once()


async def test_mapping_still_demotes_a_role_the_directory_gave(provider, db, revoke):
    """Moving a user to a lower directory group still demotes them."""
    await db.users.insert_one({"email": "new@x.com", "tenantId": "t1", "role": "itam_admin",
                               "status": "Active", "source": provider.source, "directoryRole": "itam_admin"})
    doc = await provider.apply(provider.mapped("new@x.com"), "t1", "itam_viewer")
    assert doc["role"] == "itam_viewer"
    stored = await db.users.find_one({"email": "new@x.com"})
    assert stored["role"] == "itam_viewer" and stored["directoryRole"] == "itam_viewer"
    revoke.assert_awaited_once()


async def test_a_new_directory_account_records_its_directory_role(provider, db, revoke):
    await provider.apply(provider.mapped("fresh@x.com"), "t1", "itam_admin")
    stored = await db.users.find_one({"email": "fresh@x.com"})
    assert stored["role"] == "itam_admin" and stored["directoryRole"] == "itam_admin"
    doc = await provider.apply(provider.mapped("fresh@x.com"), "t1", "itam_user")
    assert doc["role"] == "itam_user"


async def test_an_admin_elevated_directory_account_is_not_demoted(provider, db, revoke):
    """An admin raised a directory user above what the directory gives: the directory no
    longer owns that role, so the next sign-in keeps it."""
    await db.users.insert_one({"email": "e@x.com", "tenantId": "t1", "role": "itam_admin", "status": "Active",
                               "source": provider.source, "directoryRole": "itam_user"})
    doc = await provider.apply(provider.mapped("e@x.com"), "t1", "itam_user")
    assert doc["role"] == "itam_admin"
    revoke.assert_not_awaited()


async def test_a_legacy_directory_account_keeps_following_the_directory(provider, db, revoke):
    """Accounts synced before directoryRole was recorded: the directory created them, so a
    mapping still applies to them as it always did."""
    await db.users.insert_one({"email": "old@x.com", "tenantId": "t1", "role": "itam_admin",
                               "status": "Active", "source": provider.source})
    doc = await provider.apply(provider.mapped("old@x.com"), "t1", "itam_viewer")
    assert doc["role"] == "itam_viewer"


async def test_an_unreadable_role_store_keeps_the_existing_role(provider, db, revoke, monkeypatch):
    async def down(*_a, **_k):
        raise RuntimeError("role store down")

    db.roles.find_one = down
    await _user(db, "u@x.com", "itam_user")
    doc = await provider.apply(provider.mapped("u@x.com"), "t1", "itam_admin")
    assert doc["role"] == "itam_user"
    revoke.assert_not_awaited()


# ------------------------------------------------------------- mapping writers

async def test_upsert_records_the_writer(provider, db):
    await provider.upsert("cn=g1", "itam_user", "t1",
                          writer=make_token_data(username="ia@x.com", role="itam_admin", tenant_id="t1"))
    stored = getattr(db, provider.collection).docs[0]
    assert stored["writtenBy"] == "ia@x.com"
    assert stored["writtenByRole"] == "itam_admin"
    assert stored["writtenByTenantId"] == "t1"
    assert stored["writtenAt"]


async def _mapping(db, provider, value, role, priority, writer=None):
    doc = {provider.key: value, "role": role, "tenant_id": "t1", "priority": priority}
    if writer:
        doc.update({"writtenBy": writer, "writtenByRole": "Tenant Admin", "writtenByTenantId": "t1"})
    await getattr(db, provider.collection).insert_one(doc)


async def test_a_mapping_whose_writer_was_demoted_is_skipped(provider, db, audit):
    await _user(db, "was-admin@x.com", "itam_viewer")
    await _mapping(db, provider, "cn=g1", "Tenant Admin", 1, writer="was-admin@x.com")
    await _mapping(db, provider, "cn=g2", "itam_viewer", 2)
    assert await provider.resolve(["cn=g1", "cn=g2"], "t1") == "itam_viewer"
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "directory_mapping.skipped"
    assert audit.await_args.kwargs["outcome"] == "denied"


@pytest.mark.parametrize("writer_doc", [
    None,
    {"email": "gone@x.com", "tenantId": "t1", "role": "Tenant Admin", "status": "Disabled"},
    {"email": "gone@x.com", "tenantId": "t2", "role": "Tenant Admin", "status": "Active"},
], ids=["deleted", "disabled", "moved"])
async def test_a_mapping_whose_writer_left_is_skipped(provider, db, audit, writer_doc):
    if writer_doc:
        await db.users.insert_one(writer_doc)
    await _mapping(db, provider, "cn=g1", "itam_admin", 1, writer="gone@x.com")
    assert await provider.resolve(["cn=g1"], "t1") is None
    audit.assert_awaited_once()


async def test_a_mapping_whose_writer_still_holds_the_role_applies(provider, db, audit):
    await _user(db, "admin@x.com", "Tenant Admin")
    await _mapping(db, provider, "cn=g1", "itam_admin", 1, writer="admin@x.com")
    assert await provider.resolve(["cn=g1"], "t1") == "itam_admin"
    audit.assert_not_awaited()


async def test_a_legacy_mapping_with_no_writer_still_applies(provider, db, audit):
    await _mapping(db, provider, "cn=g1", "Tenant Admin", 1)
    assert await provider.resolve(["cn=g1"], "t1") == "Tenant Admin"
    audit.assert_not_awaited()
