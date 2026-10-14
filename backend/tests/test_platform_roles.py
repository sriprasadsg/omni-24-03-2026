"""Spec C1: platform roles (owner, support, billing) and the platform/tenant boundary.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Unless a test says otherwise, no_claim=the real
HTTP stack and MongoDB (functions are called directly, fakes stand in for the DB).
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import auth_roles
import rbac_defaults as d
import rbac_utils
import role_assignment
import tenant_middleware
from auth_types import TokenData
from authentication_service import mfa_required_for
from rbac_service import RBACService, effective_permissions

OWNER = TokenData(username="owner@platform", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)
SUPPORT = TokenData(username="support@platform", role="Platform Support", tenant_id="platform-admin", mfa_verified=True)
BILLING = TokenData(username="billing@platform", role="Platform Billing", tenant_id="platform-admin", mfa_verified=True)
ADMIN_A = TokenData(username="admin@a", role="Tenant Admin", tenant_id="tenant-a", mfa_verified=True)

OWNER_SPELLINGS = ["Super Admin", "super_admin", "superadmin", "platform-admin", "Platform Owner", "platform_owner"]
TENANT_ADMIN_SPELLINGS = ["admin", "Admin", "Tenant Admin", "tenant_admin"]


# ── Tiers and normalization ───────────────────────────────────────────────────

@pytest.mark.parametrize("role", OWNER_SPELLINGS)
def test_every_owner_spelling_is_the_owner_tier(role):
    """protects=existing Super Admin accounts keep working as Platform Owner (AC6);
    fails_when=a spelling such as "Platform Owner" resolves to an unknown role; no_claim=none beyond protects."""
    assert d.normalize_role(role) == d.SUPER_ADMIN_KEY
    assert d.platform_tier(role) == "owner"
    assert rbac_utils.is_super_admin(role)
    assert d.defaults_for(d.normalize_role(role)) == ("*",)


@pytest.mark.parametrize("role,tier", [("Platform Support", "support"), ("platform_support", "support"),
                                       ("Platform Billing", "billing"), ("platform-billing", "billing")])
def test_support_and_billing_tiers(role, tier):
    """protects=support/billing are platform roles but never the owner; fails_when=support passes
    is_super_admin; no_claim=none beyond protects."""
    assert d.platform_tier(role) == tier and d.is_platform_role(role)
    assert not rbac_utils.is_super_admin(role)


@pytest.mark.parametrize("role", TENANT_ADMIN_SPELLINGS + ["user", "viewer", "itam_admin", "", None])
def test_tenant_roles_have_no_platform_tier(role):
    """protects=a tenant role is never platform staff; fails_when="admin" gets a tier; no_claim=none beyond protects."""
    assert d.platform_tier(role) is None and not d.is_platform_role(role)


@pytest.mark.parametrize("role", TENANT_ADMIN_SPELLINGS)
def test_tenant_admin_spellings(role):
    """protects=one predicate for the tenant admin; fails_when=a spelling is missed; no_claim=none beyond protects."""
    assert d.is_tenant_admin(role)
    assert not d.is_tenant_admin("Super Admin") and not d.is_tenant_admin("Platform Support")


# ── Role sets used at the 67 former literal sites ─────────────────────────────

@pytest.mark.parametrize("role", TENANT_ADMIN_SPELLINGS + ["user", "viewer", "security_analyst"])
def test_platform_scope_roles_exclude_every_tenant_role(role):
    """protects=a tenant admin never skips the tenant filter (spec C1 core fix);
    fails_when="admin" is in the cross-tenant set; no_claim=per-site behaviour (see test_platform_role_isolation)."""
    assert role not in auth_roles.platform_scope_roles()


@pytest.mark.parametrize("role", OWNER_SPELLINGS + ["Platform Support", "Platform Billing"])
def test_platform_scope_roles_include_every_platform_role(role):
    """protects=platform staff read across tenants; fails_when=support is filtered to its own tenant;
    no_claim=none beyond protects."""
    assert role in auth_roles.platform_scope_roles()


def test_tenant_admin_roles_hold_admin_and_owner_only():
    """protects="403 unless admin" sites keep tenant admins and the owner and nobody else;
    fails_when=support/billing or a plain user pass; no_claim=none beyond protects."""
    roles = auth_roles.tenant_admin_roles("security_analyst")
    for role in TENANT_ADMIN_SPELLINGS + OWNER_SPELLINGS + ["security_analyst", "Security Analyst"]:
        assert role in roles, role
    for role in ("Platform Support", "Platform Billing", "user", "viewer", "", None, 42):
        assert role not in roles, role


def test_owner_roles_and_tenant_admin_names():
    """protects=owner-only set and the tenant-admin recipient names hold no platform role;
    fails_when=a recipient query matches a super admin; no_claim=none beyond protects."""
    assert "Super Admin" in auth_roles.platform_owner_roles()
    assert "Platform Support" not in auth_roles.platform_owner_roles()
    assert not any(d.is_platform_role(n) for n in auth_roles.TENANT_ADMIN_ROLE_NAMES)


# ── Permissions ───────────────────────────────────────────────────────────────

def test_platform_only_permissions_belong_to_platform_roles_only():
    """protects=license/pending/tenant-list permissions never reach a tenant role (spec C1);
    fails_when=tenant_admin holds manage:tenant_license; no_claim=none beyond protects."""
    for key, perms in d.ROLE_DEFAULTS.items():
        held = d.PLATFORM_ONLY_PERMISSIONS & set(perms)
        assert not held or key in d.PLATFORM_ROLE_KEYS, (key, held)
    assert {"manage:tenant_license", "manage:pending_agents"} <= set(d.defaults_for("platform_billing"))


def test_support_holds_only_view_permissions():
    """protects=Platform Support changes nothing by permission; fails_when=a manage:/control: string
    is added to it; no_claim=routes guarded by a view: permission (the read-only middleware covers those)."""
    assert all(p.startswith("view:") for p in d.defaults_for("platform_support"))
    assert "view:remote_access" not in d.defaults_for("platform_support")


class _Roles:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, flt, *a, **k):
        return next((x for x in self.docs if all(x.get(f) == v for f, v in flt.items())), None)


async def test_a_role_document_cannot_hand_a_tenant_role_platform_permissions():
    """protects=a tenant's custom role document cannot grant view:tenants or manage:tenant_license;
    fails_when=effective_permissions returns them for admin; no_claim=Mongo (a fake roles store)."""
    docs = [{"name": "admin", "tenantId": "tenant-a",
             "permissions": ["view:tenants", "manage:tenant_license", "manage:pending_agents", "view:tickets"]}]
    db = SimpleNamespace(_db=SimpleNamespace(roles=_Roles(docs)))
    perms = await effective_permissions(db, "admin", "tenant-a")
    assert "view:tickets" in perms
    assert not d.PLATFORM_ONLY_PERMISSIONS & set(perms)
    assert "manage:tenant_license" in await effective_permissions(db, "Platform Billing", "platform-admin")


async def test_has_platform_permission():
    """protects=platform routes accept owner always, billing for its permissions, never a tenant user;
    fails_when=a tenant admin or a billing account outside the platform tenant passes;
    no_claim=role documents (built-in defaults decide here)."""
    assert await rbac_utils.has_platform_permission(OWNER, "manage:tenant_license")
    assert await rbac_utils.has_platform_permission(BILLING, "manage:tenant_license")
    assert not await rbac_utils.has_platform_permission(SUPPORT, "manage:tenant_license")
    assert await rbac_utils.has_platform_permission(SUPPORT, "view:tenants")
    assert not await rbac_utils.has_platform_permission(ADMIN_A, "view:tenants")
    stray = TokenData(username="b@a", role="Platform Billing", tenant_id="tenant-a")
    assert not await rbac_utils.has_platform_permission(stray, "manage:tenant_license")
    assert not rbac_utils.can_read_all_tenants(stray) and rbac_utils.can_read_all_tenants(SUPPORT)


@pytest.mark.parametrize("role", ["Super Admin", "Platform Support", "Platform Billing", "admin", "itam_admin"])
def test_platform_roles_require_mfa(role):
    """protects=a platform_support login without MFA gets MFA_REQUIRED_DETAIL (AC5);
    fails_when=support or billing skip MFA; no_claim=the login flow itself (test_admin_mfa_required)."""
    assert mfa_required_for(role)


# ── Assignment rules ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("target", ["Platform Support", "Platform Billing", "Super Admin", "platform_owner"])
async def test_only_the_owner_assigns_platform_roles(target):
    """protects=a tenant admin cannot create platform staff; fails_when=the ceiling lets admin hand out
    platform_billing; no_claim=role documents (none exist here)."""
    with pytest.raises(HTTPException) as exc:
        await role_assignment.assert_can_assign_role(None, ADMIN_A, target, target_tenant_id="tenant-a")
    assert exc.value.status_code == 403
    assert not RBACService().can_assign_role("Tenant Admin", target)
    assert RBACService().can_assign_role("Super Admin", target)


async def test_only_the_owner_manages_platform_accounts():
    """protects=support/billing accounts are changed by the owner only; fails_when=billing edits support;
    no_claim=none beyond protects."""
    with pytest.raises(HTTPException) as exc:
        await role_assignment.assert_can_manage_account(None, BILLING, "Platform Support",
                                                        target_tenant_id="platform-admin")
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role,tenant,ok", [
    ("Platform Support", "platform-admin", True), ("Super Admin", "platform-admin", True),
    ("Platform Billing", "tenant-a", False), ("Super Admin", "tenant-a", False),
    ("admin", "platform-admin", False), ("user", "platform-admin", False), ("admin", "tenant-a", True),
])
def test_role_must_fit_its_tenant(role, tenant, ok):
    """protects=platform roles live only in the Platform tenant and tenant roles never do;
    fails_when=an "admin" lands in platform-admin (whose context skips tenant scoping);
    no_claim=accounts created before C1 are not re-checked."""
    if ok:
        role_assignment.assert_role_fits_tenant(role, tenant)
    else:
        with pytest.raises(HTTPException) as exc:
            role_assignment.assert_role_fits_tenant(role, tenant)
        assert exc.value.status_code == 400


def test_platform_roles_are_stored_under_their_builtin_name():
    """protects=raw role-name checks elsewhere still recognise new owners; fails_when="platform_owner"
    is stored verbatim; no_claim=none beyond protects."""
    assert role_assignment.stored_role_name("platform_owner") == "Super Admin"
    assert role_assignment.stored_role_name("platform-support") == "Platform Support"
    assert role_assignment.stored_role_name("viewer") == "viewer"


def test_directory_mappings_cannot_grant_platform_roles():
    """protects=LDAP/SAML sync never writes a platform role into a customer tenant;
    fails_when=a mapping to Platform Support is accepted; no_claim=none beyond protects."""
    with pytest.raises(HTTPException):
        role_assignment.refuse_directory_platform_role("Platform Support")
    role_assignment.refuse_directory_platform_role("analyst")


# ── Read-only guard (second wall for support and billing) ─────────────────────

@pytest.mark.parametrize("role,method,path", [
    ("Platform Support", "PATCH", "/api/tenants/tenant-a"),
    ("Platform Support", "DELETE", "/api/tenants/tenant-a"),
    ("Platform Support", "PATCH", "/api/tenants/tenant-a/license"),
    ("Platform Support", "POST", "/api/agents/pending/agent-1/approve"),
    ("Platform Support", "POST", "/api/users"),
    ("Platform Billing", "DELETE", "/api/tenants/tenant-a"),
    ("Platform Billing", "POST", "/api/users"),
    ("Platform Billing", "PATCH", "/api/tenants/tenant-a"),
    ("Platform Billing", "PUT", "/api/audit-logs/retention"),
])
def test_read_only_tiers_are_refused_writes(role, method, path):
    """protects=support changes nothing and billing only licenses/Pending (AC1/AC2);
    fails_when=one of these writes reaches its route; no_claim=routes are not executed."""
    assert tenant_middleware.platform_write_refusal(role, method, path)


@pytest.mark.parametrize("role,method,path", [
    ("Platform Support", "GET", "/api/tenants"),
    ("Platform Support", "POST", "/api/auth/logout"),
    ("Platform Support", "POST", "/api/mfa/verify"),
    ("Platform Support", "PUT", "/api/users/me/notification-preferences"),
    ("Platform Billing", "PATCH", "/api/tenants/tenant-a/license"),
    ("Platform Billing", "POST", "/api/agents/pending/agent-1/approve"),
    ("Platform Billing", "POST", "/api/agents/pending/bulk"),
    ("Platform Billing", "POST", "/api/tenants/tenant-a/allowlist"),
    ("Platform Billing", "POST", "/api/tenants/tenant-a/enrollment-keys/k1/revoke"),
    ("Super Admin", "DELETE", "/api/tenants/tenant-a"),
    ("Tenant Admin", "POST", "/api/users"),
])
def test_permitted_requests_pass_the_guard(role, method, path):
    """protects=sign-in/MFA/own profile and billing's own writes still work; owner and tenant roles are
    untouched; fails_when=the guard blocks them; no_claim=the route's own permission check."""
    assert tenant_middleware.platform_write_refusal(role, method, path) is None


def _token(role):
    # The live module at call time: other tests may re-import authentication_service with a new key.
    auth = sys.modules["authentication_service"]
    return jwt.encode({"sub": "x@platform", "role": role, "tenant_id": "platform-admin"}, auth.SECRET_KEY,
                      algorithm=auth.ALGORITHM)


def test_middleware_answers_403_before_the_route():
    """protects=a support write never reaches the handler; fails_when=the handler runs;
    no_claim=the rest of the production middleware stack (see the next test for its placement)."""
    app = FastAPI()
    hits = []

    @app.post("/api/tenants")
    def create():
        hits.append(1)
        return {"ok": True}

    app.add_middleware(tenant_middleware.PlatformReadOnlyMiddleware)
    client = TestClient(app)
    r = client.post("/api/tenants", headers={"Authorization": f"Bearer {_token('Platform Support')}"})
    assert r.status_code == 403 and "read-only" in r.json()["error"] and not hits
    assert client.post("/api/tenants", headers={"Authorization": f"Bearer {_token('Super Admin')}"}).status_code == 200
    assert client.post("/api/tenants", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 200


def test_middleware_is_registered_inside_the_audit_middleware():
    """protects=refused writes are still audited (C5) and the guard is live in the real app;
    fails_when=the guard is missing or sits outside AuditMiddleware; no_claim=behaviour of the other middleware."""
    import app_middleware
    app = FastAPI()
    with patch.object(app_middleware, "allowed_cors_origins", return_value=[]):
        app_middleware.register_middleware(app, SimpleNamespace())
    names = [m.cls.__name__ for m in app.user_middleware]  # outermost first
    assert "PlatformReadOnlyMiddleware" in names
    assert names.index("AuditMiddleware") < names.index("PlatformReadOnlyMiddleware")
    assert names.index("TenantMiddleware") < names.index("AuditMiddleware")


# ── Last-owner guard ──────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=None):
        return self.docs


class _Users:
    def __init__(self, docs):
        self.docs = docs

    def find(self, flt, projection=None):
        import re
        pattern = re.compile(flt["role"]["$regex"], re.I)
        return _Cursor([u for u in self.docs if pattern.search(u.get("role", ""))])


def _owner(i, status="Active", role="Super Admin"):
    return {"_id": f"u{i}", "role": role, "status": status, "tenantId": "platform-admin"}


@pytest.mark.parametrize("change", [{"deleting": True}, {"new_role": "Platform Support"},
                                    {"new_status": "Inactive"}, {"new_tenant_id": "tenant-a"}])
async def test_removing_the_last_owner_is_refused(change):
    """protects=deleting, demoting, disabling or moving the last active owner returns 409 (AC4);
    fails_when=the platform is left with no owner; no_claim=two concurrent removals (documented race)."""
    me = _owner(1)
    db = SimpleNamespace(users=_Users([me, _owner(2, status="Inactive"), {"_id": "u3", "role": "admin"}]))
    with pytest.raises(HTTPException) as exc:
        await role_assignment.assert_not_last_platform_owner(db, me, **change)
    assert exc.value.status_code == 409 and exc.value.detail == "last_platform_owner"


@pytest.mark.parametrize("change", [{"deleting": True}, {"new_role": "Platform Support"}, {"new_status": "Inactive"}])
async def test_removing_an_owner_with_a_second_owner_is_allowed(change):
    """protects=with two active owners the change goes through (AC4); fails_when=a second owner spelled
    "platform-admin" is not counted; no_claim=none beyond protects."""
    me = _owner(1)
    db = SimpleNamespace(users=_Users([me, _owner(2, role="platform-admin")]))
    await role_assignment.assert_not_last_platform_owner(db, me, **change)


async def test_harmless_changes_to_the_last_owner_pass():
    """protects=renaming or re-saving the last owner is not blocked; fails_when=every edit returns 409;
    no_claim=none beyond protects."""
    me = _owner(1)
    db = SimpleNamespace(users=_Users([me]))
    await role_assignment.assert_not_last_platform_owner(db, me, new_role="super_admin", new_status="Active")
    await role_assignment.assert_not_last_platform_owner(db, {"_id": "x", "role": "admin"}, deleting=True)


async def test_user_endpoints_apply_the_last_owner_guard():
    """protects=PUT and DELETE /api/users/{id} answer 409 for the last owner (AC4) and store nothing;
    fails_when=the endpoint deletes or demotes the account; no_claim=the HTTP layer and Mongo."""
    import user_endpoints
    from bson import ObjectId
    oid = ObjectId()
    me = {"_id": oid, "email": "only@platform", "role": "Super Admin", "status": "Active", "tenantId": "platform-admin"}
    users = _Users([me])
    users.find_one = AsyncMock(return_value=dict(me))
    users.update_one = AsyncMock()
    users.delete_one = AsyncMock()
    db = SimpleNamespace(users=users, roles=None)
    caller = TokenData(username="other@platform", role="Super Admin", tenant_id="platform-admin")
    with patch.object(user_endpoints, "get_database", return_value=db), \
            patch.object(user_endpoints, "revoke_user_sessions", AsyncMock()), \
            patch.object(user_endpoints, "_audit", AsyncMock()):
        for call in (user_endpoints.update_user(str(oid), user_endpoints.UserUpdate(status="inactive"), current_user=caller),
                     user_endpoints.update_user(str(oid), user_endpoints.UserUpdate(role="Platform Support"),
                                                current_user=caller),
                     user_endpoints.delete_user(str(oid), current_user=caller)):
            with pytest.raises(HTTPException) as exc:
                await call
            assert exc.value.status_code == 409
    users.update_one.assert_not_awaited()
    users.delete_one.assert_not_awaited()
