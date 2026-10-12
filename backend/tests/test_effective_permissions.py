"""The resolver (effective_permissions) and its enforcement parity (ACC-01/ACC-02).

verify_permission, RBACService and the /login + /me delivery all answer from
rbac_service.effective_permissions over the single table in rbac_defaults.
"""
import asyncio
import contextvars
import logging

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

import rbac_defaults
import rbac_service
import rbac_utils
from auth_types import TokenData
from authentication_service import get_current_user
from tests.rbac_test_support import StoreCollection, role_store, shared_role_docs

TENANT_ADMIN_NAMES = ["Admin", "admin", "Tenant Admin", "tenant_admin"]
BUILTIN_NAMES = ["Tenant Admin", "admin", "user", "analyst", "security_analyst", "incident_responder",
                 "viewer", "itam_admin", "itam_user", "itam_viewer"]


def _token(role, tenant_id="t1", **kw):
    return TokenData(username="u@acme.test", role=role, tenant_id=tenant_id, mfa_verified=True, **kw)


def _use(monkeypatch, db):
    monkeypatch.setattr(rbac_utils, "get_database", lambda: db)
    monkeypatch.setattr(rbac_service, "get_database", lambda: db)


def _store(*role_docs):
    db, _raw = role_store(roles=list(role_docs))
    return db


class _RaisingRoles(StoreCollection):
    async def find_one(self, flt=None, projection=None, **k):
        raise RuntimeError("role store down")


def _down_store():
    db, _raw = role_store(roles=_RaisingRoles())
    return db


# --------------------------------------------------------------------------
# effective_permissions
# --------------------------------------------------------------------------

def test_defaults_come_first_then_document_extras_without_duplicates():
    db = _store({"name": "viewer", "tenantId": "t1", "permissions": ["view:dashboard", "view:extra_a", "view:extra_b"]},
                {"name": "viewer", "tenantId": "all", "permissions": ["view:extra_b", "view:reporting"]})
    perms = asyncio.run(rbac_service.effective_permissions(db, "viewer", "t1"))
    defaults = list(rbac_defaults.defaults_for("viewer"))
    assert perms == defaults + ["view:extra_a", "view:extra_b"]
    assert len(perms) == len(set(perms))


def test_repeated_calls_return_the_same_sequence():
    db = _store({"name": "viewer", "tenantId": "t1", "permissions": ["view:z", "view:a"]})
    first = asyncio.run(rbac_service.effective_permissions(db, "viewer", "t1"))
    second = asyncio.run(rbac_service.effective_permissions(db, "viewer", "t1"))
    assert first == second


@pytest.mark.parametrize("role", [None, ""])
def test_missing_role_resolves_to_empty(role):
    assert asyncio.run(rbac_service.effective_permissions(_store(), role, "t1")) == []


def test_unknown_role_without_document_resolves_to_empty():
    assert asyncio.run(rbac_service.effective_permissions(_store(), "mystery_role", "t1")) == []


def test_document_with_empty_permissions_yields_exactly_the_defaults():
    db = _store({"name": "viewer", "tenantId": "t1", "permissions": []})
    perms = asyncio.run(rbac_service.effective_permissions(db, "viewer", "t1"))
    assert perms == list(rbac_defaults.defaults_for("viewer"))


def test_super_admin_variants_resolve_to_wildcard():
    for role in ("Super Admin", "super_admin", "superadmin", "platform-admin"):
        assert asyncio.run(rbac_service.effective_permissions(_store(), role, None)) == ["*"]


def test_custom_role_unchanged():
    """A pre-existing custom role with no defaults still resolves from its document."""
    db = _store({"name": "Helpdesk", "tenantId": "tenant-a", "permissions": ["view:tickets", "manage:tickets"]})
    assert asyncio.run(rbac_service.effective_permissions(db, "Helpdesk", "tenant-a")) == ["view:tickets", "manage:tickets"]


def test_custom_role_unchanged_is_enforced(monkeypatch):
    db = _store({"name": "Helpdesk", "tenantId": "tenant-a", "permissions": ["view:tickets", "manage:tickets"]})
    _use(monkeypatch, db)
    user = _token("Helpdesk", "tenant-a")
    assert asyncio.run(rbac_utils.verify_permission(user, "manage:tickets")) is True
    assert asyncio.run(rbac_utils.verify_permission(user, "view:dashboard")) is False


def test_raw_handle_sees_tenant_document_without_tenant_context():
    db = _store({"name": "viewer", "tenantId": "t1", "permissions": ["view:custom_extra"]})

    def run():
        return asyncio.run(rbac_service.effective_permissions(db, "viewer", "t1"))

    perms = contextvars.Context().run(run)
    assert "view:custom_extra" in perms


def test_other_tenants_document_never_contributes():
    db = _store({"name": "viewer", "tenantId": "tenant-b", "permissions": ["view:secret_of_b"]})
    perms = asyncio.run(rbac_service.effective_permissions(db, "viewer", "tenant-a"))
    assert "view:secret_of_b" not in perms
    assert perms == list(rbac_defaults.defaults_for("viewer"))


# --------------------------------------------------------------------------
# One answer for every spelling of the tenant admin role
# --------------------------------------------------------------------------

@pytest.mark.parametrize("role", TENANT_ADMIN_NAMES)
def test_tenant_admin_spellings_agree_across_all_paths(monkeypatch, role):
    db = _store(*shared_role_docs())
    _use(monkeypatch, db)
    expected = list(rbac_defaults.defaults_for("tenant_admin"))
    assert asyncio.run(rbac_service.effective_permissions(db, role, "t1")) == expected
    assert asyncio.run(rbac_service.rbac_service.get_user_permissions(_token(role))) == expected
    assert asyncio.run(rbac_utils.verify_permission(_token(role), "manage:users")) is True


@pytest.mark.parametrize("role", ["Tenant Admin", "admin", "tenant_admin"])
def test_tenant_admin_roles_are_denied_manage_tenants(monkeypatch, role):
    _use(monkeypatch, _store(*shared_role_docs()))
    assert asyncio.run(rbac_utils.verify_permission(_token(role), "manage:tenants")) is False


def test_super_admin_passes_every_check(monkeypatch):
    _use(monkeypatch, _store())
    assert asyncio.run(rbac_utils.verify_permission(_token("Super Admin", None), "manage:tenants")) is True


# --------------------------------------------------------------------------
# Role-store outage
# --------------------------------------------------------------------------

def test_outage_effective_permissions_raises_but_delivery_degrades(monkeypatch, caplog):
    db = _down_store()
    with pytest.raises(RuntimeError):
        asyncio.run(rbac_service.effective_permissions(db, "viewer", "t1"))
    with caplog.at_level(logging.WARNING):
        perms = asyncio.run(rbac_service.session_permissions(db, "viewer", "t1"))
    assert perms == list(rbac_defaults.defaults_for("viewer"))
    assert any(r.levelno == logging.WARNING and "viewer" in r.getMessage() for r in caplog.records)


def test_outage_enforcement_denies_everything_outside_the_defaults(monkeypatch):
    _use(monkeypatch, _down_store())
    user = _token("viewer")
    assert asyncio.run(rbac_utils.verify_permission(user, "view:dashboard")) is True
    assert asyncio.run(rbac_utils.verify_permission(user, "manage:settings")) is False
    assert asyncio.run(rbac_utils.verify_permission(_token("mystery_role"), "view:dashboard")) is False


def test_outage_get_user_permissions_returns_defaults_only(monkeypatch):
    _use(monkeypatch, _down_store())
    perms = asyncio.run(rbac_service.rbac_service.get_user_permissions(_token("viewer")))
    assert perms == list(rbac_defaults.defaults_for("viewer"))


# --------------------------------------------------------------------------
# Enforcement parity: verify_permission grants exactly what the resolver delivers
# --------------------------------------------------------------------------

def _universe():
    every = set()
    for perms in rbac_defaults.ROLE_DEFAULTS.values():
        every.update(perms)
    every.update({"manage:tenants", "view:custom_extra", "view:not_in_any_table", "manage:not_in_any_table"})
    return sorted(every)


@pytest.mark.parametrize("role", BUILTIN_NAMES)
def test_verify_permission_matches_resolver_for_every_builtin_role(monkeypatch, role):
    key = rbac_defaults.canonical_key(rbac_service.RBACService._normalize_role(role))
    db = _store(*shared_role_docs(),
                {"name": role, "tenantId": "t1", "permissions": ["view:custom_extra"]})
    _use(monkeypatch, db)
    user = _token(role)

    async def check():
        delivered = set(await rbac_service.effective_permissions(db, role, "t1"))
        assert set(rbac_defaults.defaults_for(key)) <= delivered
        for perm in _universe():
            granted = await rbac_utils.verify_permission(user, perm)
            assert granted == (perm in delivered), f"{role}: {perm} granted={granted}"

    asyncio.run(check())


# --------------------------------------------------------------------------
# Phase 74 D-06: view and control stay independent
# --------------------------------------------------------------------------

def test_view_remote_access_document_does_not_grant_control(monkeypatch):
    db = _store({"name": "Observer", "tenantId": "t1", "permissions": ["view:remote_access"]})
    _use(monkeypatch, db)
    user = _token("Observer")
    assert asyncio.run(rbac_utils.verify_permission(user, "view:remote_access")) is True
    assert asyncio.run(rbac_utils.verify_permission(user, "control:remote_access")) is False


def test_remote_access_strings_are_independent_in_closure_and_table():
    assert "control:remote_access" not in rbac_defaults.implied_closure({"view:remote_access"})
    assert "view:remote_access" not in rbac_defaults.implied_closure({"control:remote_access"})
    admin = rbac_defaults.defaults_for("tenant_admin")
    assert "view:remote_access" in admin and "control:remote_access" in admin


# --------------------------------------------------------------------------
# has_permission keeps API-key scope narrowing
# --------------------------------------------------------------------------

def test_api_key_scopes_still_narrow_a_tenant_admin(monkeypatch):
    _use(monkeypatch, _store(*shared_role_docs()))
    user = _token("tenant_admin", scopes=["view:assets"], auth_source="api_key")
    router = APIRouter()

    @router.get("/protected")
    async def protected(u=Depends(rbac_service.rbac_service.has_permission("manage:assets"))):
        return {"ok": True}

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        resp = client.get("/protected")
    assert resp.status_code == 403
    assert "scope" in resp.json()["detail"].lower()


# --------------------------------------------------------------------------
# Derived views of the table
# --------------------------------------------------------------------------

def test_default_roles_is_a_view_of_the_table():
    roles = rbac_service.RBACService().default_roles
    for key in ("admin", "Tenant Admin", "tenant_admin", "viewer", "super_admin",
                "itam_admin", "itam_user", "itam_viewer", "user", "analyst",
                "security_analyst", "incident_responder"):
        assert key in roles, key
    assert roles["super_admin"] == ["*"]
    assert roles["admin"] == roles["Tenant Admin"] == list(rbac_defaults.defaults_for("tenant_admin"))
    assert roles["viewer"] == list(rbac_defaults.defaults_for("viewer"))


def test_get_permissions_for_role_reads_the_table():
    svc = rbac_service.RBACService()
    assert svc.get_permissions_for_role("Admin") == list(rbac_defaults.defaults_for("tenant_admin"))
    assert svc.get_permissions_for_role("Tenant Admin") == list(rbac_defaults.defaults_for("tenant_admin"))
    assert svc.get_permissions_for_role("platform-admin") == ["*"]
    assert svc.get_permissions_for_role("does_not_exist") == []
