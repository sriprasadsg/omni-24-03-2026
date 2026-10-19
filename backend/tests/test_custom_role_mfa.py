"""Phase 77 plan 04 (D-14, ACC-09): MFA follows permissions, not role names.

A session whose role's effective permissions hold "*" or an admin-tier permission
(rbac_defaults.ADMIN_TIER_PERMISSIONS) must pass MFA. Built-in roles keep exactly the
behaviour they had when the rule keyed on six role names. Hermetic: one in-memory role
store stands in for the live database.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import authentication_service as auth_svc
import rbac_defaults
from tests.rbac_test_support import (
    StoreCollection, make_auth_client, make_user, me, role_store, shared_role_docs, login, reset_shared_limiter,
)

EMAIL = "who@mfa.test"
BUILTIN_ADMIN_TIER = {"super_admin", "tenant_admin", "admin", "itam_admin", "platform_support", "platform_billing"}


def _token(role, tenant="tenant-a", **claims):
    return auth_svc.create_access_token({"sub": EMAIL, "role": role, "tenant_id": tenant, **claims})


def _doc(name, tenant, permissions):
    return {"id": f"custom-{tenant}-{name}", "name": name, "tenantId": tenant,
            "description": name, "permissions": permissions, "isEditable": True}


def _store(extra=()):
    docs = shared_role_docs()
    docs += [
        _doc("Deskadmin", "tenant-a", ["manage:rbac", "view:agents"]),
        _doc("Helpdesk", "tenant-a", ["view:agents"]),
        _doc("viewer", "tenant-a", ["manage:users"]),  # legacy document extending a built-in
    ]
    docs += list(extra)
    db, raw = role_store(roles=docs, tenants=[], users=[], ldap_group_mappings=[], saml_group_mappings=[])
    db.raw = raw
    return db


@pytest.fixture(autouse=True)
def _clean_cache():
    auth_svc._clear_mfa_role_cache()
    yield
    auth_svc._clear_mfa_role_cache()


@pytest.fixture
def db():
    store = _store()
    # revoked_tokens lookups fail open when the raw handle cannot answer; keep them quiet.
    store.raw.revoked_tokens.find_one = AsyncMock(return_value=None)
    with patch("database.get_database", return_value=store):
        yield store


def _mfa_refused(exc):
    return exc.value.status_code == 403 and exc.value.headers.get("X-MFA-Required") == "1"


# --- the one admin-tier definition ---------------------------------------------

def test_admin_tier_selects_exactly_the_builtin_admin_roles():
    got = {k for k in rbac_defaults.builtin_role_keys() if rbac_defaults.requires_mfa(rbac_defaults.defaults_for(k))}
    assert got == BUILTIN_ADMIN_TIER
    for k in ("user", "analyst", "security_analyst", "incident_responder", "viewer", "itam_user", "itam_viewer"):
        assert not rbac_defaults.requires_mfa(rbac_defaults.defaults_for(k)), k


def test_admin_tier_definition():
    assert {"manage:users", "manage:rbac", "manage:settings", "manage:api_keys", "control:remote_access"} \
        <= rbac_defaults.ADMIN_TIER_PERMISSIONS
    assert rbac_defaults.PLATFORM_ONLY_PERMISSIONS <= rbac_defaults.ADMIN_TIER_PERMISSIONS
    assert rbac_defaults.requires_mfa(["*"])
    assert not rbac_defaults.requires_mfa([])


def test_the_name_keyed_role_set_is_gone():
    assert not hasattr(auth_svc, "_MFA_REQUIRED_ROLE_KEYS")


# --- custom roles over the async path -------------------------------------------

async def test_custom_role_with_admin_tier_permission_is_held_to_mfa(db):
    with pytest.raises(HTTPException) as exc:
        await auth_svc.get_current_user(_token("Deskadmin"))
    assert _mfa_refused(exc)


async def test_custom_admin_tier_role_with_mfa_verified_passes(db):
    user = await auth_svc.get_current_user(_token("Deskadmin", mfa_verified=True))
    assert user.role == "Deskadmin"


async def test_custom_role_without_admin_tier_permission_passes(db):
    assert (await auth_svc.get_current_user(_token("Helpdesk"))).role == "Helpdesk"


async def test_legacy_document_on_a_builtin_name_is_tenant_scoped(db):
    with pytest.raises(HTTPException) as exc:
        await auth_svc.get_current_user(_token("viewer", tenant="tenant-a"))
    assert _mfa_refused(exc)
    assert (await auth_svc.get_current_user(_token("viewer", tenant="tenant-b"))).role == "viewer"


@pytest.mark.parametrize("role", ["Super Admin", "Tenant Admin", "admin", "itam_admin"])
async def test_builtin_admin_roles_still_need_mfa(db, role):
    with pytest.raises(HTTPException) as exc:
        await auth_svc.get_current_user(_token(role))
    assert _mfa_refused(exc)


@pytest.mark.parametrize("role", ["user", "analyst", "security_analyst", "itam_viewer"])
async def test_other_builtin_roles_still_do_not(db, role):
    assert (await auth_svc.get_current_user(_token(role, tenant="tenant-b"))).role == role


async def test_mfa_pending_routes_accept_the_unverified_custom_admin(db):
    user = await auth_svc.get_current_user_mfa_pending(_token("Deskadmin"))
    assert user.mfa_verified is False


# --- fail closed -------------------------------------------------------------------

@pytest.fixture
def broken_store():
    broken = MagicMock()
    broken._db.revoked_tokens.find_one = AsyncMock(return_value=None)
    cursor = MagicMock()
    cursor.limit.return_value.__aiter__ = lambda self: iter([])
    broken._db.revoked_tokens.find.return_value = cursor
    broken._db.roles.find_one = AsyncMock(side_effect=RuntimeError("store down"))
    with patch("database.get_database", return_value=broken):
        yield broken


@pytest.mark.parametrize("role", ["Deskadmin", "Helpdesk"])
async def test_store_error_requires_mfa_for_custom_names(broken_store, role):
    with pytest.raises(HTTPException) as exc:
        await auth_svc.get_current_user(_token(role))
    assert _mfa_refused(exc)


async def test_store_error_uses_the_table_answer_for_builtin_names(broken_store):
    assert (await auth_svc.get_current_user(_token("Viewer"))).role == "Viewer"
    with pytest.raises(HTTPException):
        await auth_svc.get_current_user(_token("Tenant Admin"))


async def test_store_error_is_not_cached(broken_store):
    assert await auth_svc.resolve_mfa_required("Helpdesk", "tenant-a") is True
    assert auth_svc._mfa_role_cache == {}


# --- synchronous (WebSocket) path ----------------------------------------------------

async def test_sync_path_cold_cache_requires_mfa_for_custom_names(db):
    for role in ("Deskadmin", "Helpdesk"):
        with pytest.raises(HTTPException) as exc:
            auth_svc.verify_token(_token(role))
        assert _mfa_refused(exc)


async def test_sync_path_uses_the_cached_answer(db):
    await auth_svc.get_current_user(_token("Helpdesk"))
    assert auth_svc.verify_token(_token("Helpdesk")).role == "Helpdesk"
    with pytest.raises(HTTPException):
        await auth_svc.get_current_user(_token("Deskadmin"))
    with pytest.raises(HTTPException):
        auth_svc.verify_token(_token("Deskadmin"))


async def test_sync_path_builtin_names_use_the_table_answer(db):
    assert auth_svc.verify_token(_token("Viewer")).role == "Viewer"
    with pytest.raises(HTTPException):
        auth_svc.verify_token(_token("Tenant Admin"))


# --- cache -------------------------------------------------------------------------------

async def test_a_role_edit_is_enforced_after_the_cache_expires(db):
    assert await auth_svc.resolve_mfa_required("Helpdesk", "tenant-a") is False
    for doc in db.raw.roles.docs:
        if doc["name"] == "Helpdesk":
            doc["permissions"] = ["view:agents", "manage:users"]
    assert await auth_svc.resolve_mfa_required("Helpdesk", "tenant-a") is False  # cached
    auth_svc._clear_mfa_role_cache()
    assert await auth_svc.resolve_mfa_required("Helpdesk", "tenant-a") is True


async def test_cache_entries_expire_after_sixty_seconds(db):
    assert auth_svc.MFA_ROLE_CACHE_SECONDS == 60
    assert await auth_svc.resolve_mfa_required("Helpdesk", "tenant-a") is False
    key = next(iter(auth_svc._mfa_role_cache))
    auth_svc._mfa_role_cache[key] = (0.0, False)  # long expired
    for doc in db.raw.roles.docs:
        if doc["name"] == "Helpdesk":
            doc["permissions"] = ["manage:rbac"]
    assert await auth_svc.resolve_mfa_required("Helpdesk", "tenant-a") is True


async def test_cache_is_per_tenant(db):
    assert await auth_svc.resolve_mfa_required("viewer", "tenant-a") is True
    assert await auth_svc.resolve_mfa_required("viewer", "tenant-b") is False


async def test_verified_sessions_trigger_no_lookup(db):
    with patch("rbac_service.effective_permissions", new_callable=AsyncMock) as eff:
        await auth_svc.get_current_user(_token("Deskadmin", mfa_verified=True))
    eff.assert_not_awaited()


async def test_invalidation_drops_only_the_named_tenant(db):
    """77 WR-03: a role write clears its tenant's cached answers, so the edit applies at once."""
    assert await auth_svc.resolve_mfa_required("Helpdesk", "tenant-a") is False
    assert await auth_svc.resolve_mfa_required("viewer", "tenant-b") is False
    for doc in db.raw.roles.docs:
        if doc["name"] == "Helpdesk":
            doc["permissions"] = ["view:agents", "manage:users"]
    auth_svc.invalidate_mfa_role_cache("tenant-a")
    assert await auth_svc.resolve_mfa_required("Helpdesk", "tenant-a") is True
    assert ("tenant-b", "viewer") in auth_svc._mfa_role_cache


async def test_a_lookup_overtaken_by_a_role_write_is_not_cached(db, monkeypatch):
    """77 IN-12: a lookup that read the role before an edit landed must not store that answer."""
    import rbac_service
    real = rbac_service.effective_permissions

    async def overtaken(store, role, tenant):
        perms = await real(store, role, tenant)
        auth_svc.invalidate_mfa_role_cache(tenant)  # the edit lands while the lookup is in flight
        return perms

    monkeypatch.setattr(rbac_service, "effective_permissions", overtaken)
    assert await auth_svc.resolve_mfa_required("Helpdesk", "tenant-a") is False
    assert ("tenant-a", "helpdesk") not in auth_svc._mfa_role_cache
    monkeypatch.setattr(rbac_service, "effective_permissions", real)
    assert await auth_svc.resolve_mfa_required("Helpdesk", "tenant-a") is False
    assert ("tenant-a", "helpdesk") in auth_svc._mfa_role_cache


async def test_store_error_never_answers_less_strictly_than_the_last_answer(db, monkeypatch):
    """77 WR-03: a built-in name whose tenant document adds an admin-tier permission stays
    held to MFA while the store is down, instead of falling back to the table's False."""
    assert await auth_svc.resolve_mfa_required("viewer", "tenant-a") is True
    key = ("tenant-a", "viewer")
    auth_svc._mfa_role_cache[key] = (0.0, True)  # expired
    monkeypatch.setattr(db.raw.roles, "find_one", AsyncMock(side_effect=RuntimeError("store down")))
    assert await auth_svc.resolve_mfa_required("viewer", "tenant-a") is True
    assert auth_svc._mfa_role_cache[key] == (0.0, True)  # the error answer itself is not cached
    # A custom name still fails closed whatever it answered before.
    auth_svc._mfa_role_cache[("tenant-a", "helpdesk")] = (0.0, False)
    assert await auth_svc.resolve_mfa_required("Helpdesk", "tenant-a") is True


# --- WebSocket connect (77 WR-02) -------------------------------------------------------------

@pytest.fixture
def ws(monkeypatch):
    import websocket_manager as wsm
    wsm._connect_attempts_by_ip.clear()
    monkeypatch.setattr(wsm.sio, "emit", AsyncMock())
    sids = []

    async def connect(role):
        sid = f"sid-{role}-{len(sids)}"
        sids.append(sid)
        return await wsm.connect(sid, {"REMOTE_ADDR": f"192.0.2.{len(sids)}"},
                                 {"tenant_id": "tenant-a", "token": _token(role)})
    yield connect
    for sid in sids:
        for clients in wsm.connected_clients.values():
            clients.discard(sid)
    wsm.user_sessions.pop(EMAIL, None)
    wsm.user_roles.pop(EMAIL, None)
    wsm.user_tenants.pop(EMAIL, None)
    wsm._connect_attempts_by_ip.clear()


async def test_websocket_connect_resolves_mfa_from_the_role_store(db, ws):
    """On a cold cache the socket asks the role store, like every HTTP route: a non-admin
    custom role connects, an admin-tier custom role without MFA does not."""
    assert await ws("Helpdesk") is True
    assert await ws("Deskadmin") is False


async def test_websocket_connect_holds_an_extended_builtin_to_mfa(db, ws):
    """A built-in name whose tenant document adds manage:users needs MFA on the socket too."""
    assert await ws("viewer") is False
    assert await ws("Viewer") is False


# --- mfa_action_for ------------------------------------------------------------------------

def test_mfa_action_for_uses_an_explicit_requirement():
    assert auth_svc.mfa_action_for("Deskadmin", False, False, required=True) == "enroll"
    assert auth_svc.mfa_action_for("Deskadmin", False, True, required=True) == "verify"
    assert auth_svc.mfa_action_for("Deskadmin", True, True, required=True) is None
    assert auth_svc.mfa_action_for("Helpdesk", False, False, required=False) is None



# --- login and /me ----------------------------------------------------------------------------

def _client(db, monkeypatch, users):
    db.raw.users.docs.extend(users)
    reset_shared_limiter()
    return make_auth_client(db, monkeypatch)


def test_password_login_of_a_custom_admin_says_enroll(monkeypatch):
    store = _store()
    store.raw.login_attempts = StoreCollection([])
    client = _client(store, monkeypatch, [make_user("desk@mfa.test", "Deskadmin", "tenant-a"),
                                         make_user("help@mfa.test", "Helpdesk", "tenant-a")])
    with patch("database.get_database", return_value=store):
        desk = login(client, "desk@mfa.test")
        reset_shared_limiter()
        helpdesk = login(client, "help@mfa.test")
    assert desk.status_code == 200, desk.text
    assert desk.json()["user"]["mfa_action"] == "enroll"
    assert helpdesk.status_code == 200, helpdesk.text
    assert helpdesk.json()["user"]["mfa_action"] is None


def test_me_for_an_unverified_custom_admin_says_enroll_or_verify(monkeypatch):
    store = _store()
    enrolled = make_user("on@mfa.test", "Deskadmin", "tenant-a", mfa={"enabled": True})
    plain = make_user("off@mfa.test", "Deskadmin", "tenant-a")
    client = _client(store, monkeypatch, [enrolled, plain])
    with patch("database.get_database", return_value=store):
        assert me(client, "off@mfa.test", "Deskadmin", "tenant-a").json()["mfa_action"] == "enroll"
        assert me(client, "on@mfa.test", "Deskadmin", "tenant-a").json()["mfa_action"] == "verify"


def test_me_for_a_verified_custom_admin_and_a_plain_custom_role_says_nothing(monkeypatch):
    from auth_types import TokenData
    from authentication_service import get_current_user_mfa_pending
    store = _store()
    client = _client(store, monkeypatch, [make_user("on@mfa.test", "Deskadmin", "tenant-a", mfa={"enabled": True}),
                                         make_user("help@mfa.test", "Helpdesk", "tenant-a")])
    with patch("database.get_database", return_value=store):
        client.app.dependency_overrides[get_current_user_mfa_pending] = lambda: TokenData(
            username="on@mfa.test", role="Deskadmin", tenant_id="tenant-a", mfa_verified=True)
        verified = client.get("/api/auth/me", headers={"X-Test-Tenant": "tenant-a"})
        client.app.dependency_overrides.pop(get_current_user_mfa_pending, None)
        assert verified.json()["mfa_action"] is None
        assert me(client, "help@mfa.test", "Helpdesk", "tenant-a").json()["mfa_action"] is None
