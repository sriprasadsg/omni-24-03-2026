"""Phase 87 plan 02: the partner roles are fenced (D-04, D-20) and live only in partner organizations.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Role resolution runs over the in-memory role store;
the tenant type lookup of assignment runs on real MongoDB.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import auth_roles
import authentication_service as auth_svc
import user_endpoints as ue
import rbac_defaults as d
import rbac_utils
import role_assignment
from auth_types import TokenData
from rbac_service import effective_permissions
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rbac_test_support import role_store, shared_role_docs

PARTNER_SPELLINGS = ["partner_admin", "Partner Admin", "partner-admin", "partner_viewer", "Partner Viewer"]
PARTNER_PERMS = {"partner_admin": ["manage:partner_customers", "view:partner_portal"],
                 "partner_viewer": ["view:partner_portal"]}


def _doc(name, tenant, permissions):
    return {"id": f"doc-{tenant}-{name}", "name": name, "tenantId": tenant, "description": name,
            "permissions": permissions, "isEditable": True}


def _store(extra=()):
    db, raw = role_store(roles=shared_role_docs() + list(extra), tenants=[], users=[])
    return db


@pytest.fixture(autouse=True)
def _clean_cache():
    auth_svc._clear_mfa_role_cache()
    yield
    auth_svc._clear_mfa_role_cache()


# -- the platform checks never pass a partner role ------------------------------------------

@pytest.mark.parametrize("tenant", ["partner-a", d.PLATFORM_TENANT_ID, "tenant-a"])
@pytest.mark.parametrize("role", PARTNER_SPELLINGS)
async def test_a_partner_role_passes_no_platform_check(role, tenant):
    """protects=partner staff are never platform staff, even inside the platform tenant;
    fails_when=can_read_all_tenants or has_platform_permission is True for a partner role;
    no_claim=the HTTP stack (called with a TokenData)."""
    user = TokenData(username="p@partner.example", role=role, tenant_id=tenant, mfa_verified=True)
    assert rbac_utils.can_read_all_tenants(user) is False
    assert await rbac_utils.has_platform_permission(user, "view:tenants") is False
    assert await rbac_utils.has_platform_permission(user, "view:partner_portal") is False


@pytest.mark.parametrize("role", PARTNER_SPELLINGS)
def test_partner_roles_are_in_no_role_set(role):
    """protects=SUPER_ROLES and the RoleSet factories never contain a partner spelling;
    fails_when=a partner role is added to a super or platform or tenant-admin set;
    no_claim=sets built with explicit extras."""
    assert role not in auth_roles.SUPER_ROLES
    assert role not in auth_roles.platform_scope_roles()
    assert role not in auth_roles.platform_owner_roles()
    assert role not in auth_roles.tenant_admin_roles()
    assert not d.is_platform_role(role) and not d.is_tenant_admin(role)


# -- effective permissions ----------------------------------------------------------------

@pytest.mark.parametrize("role,key", [("partner_admin", "partner_admin"), ("Partner Admin", "partner_admin"),
                                      ("partner_viewer", "partner_viewer"), ("Partner Viewer", "partner_viewer")])
async def test_a_partner_role_holds_only_its_table_row(role, key):
    """protects=a role document under any spelling cannot widen a partner role (T-87-04);
    fails_when=manage:users or view:tenants reaches a partner role from a document in the platform
    or own tenant catalogue; no_claim=feature switches (granted_permissions)."""
    wide = ["manage:users", "view:tenants", "manage:partners", "*", "view:partner_portal", "manage:partner_customers"]
    db = _store([_doc("Partner Admin", "platform", wide), _doc("Partner Admin", "partner-a", wide),
                 _doc("partner_admin", "partner-a", wide), _doc("Partner Viewer", "partner-a", wide),
                 _doc("partner_viewer", "all", wide)])
    got = await effective_permissions(db, role, "partner-a")
    assert sorted(got) == sorted(PARTNER_PERMS[key])
    assert sorted(got) == sorted(d.defaults_for(key))


@pytest.mark.parametrize("role", ["Tenant Admin", "admin", "viewer", "Platform Support", "Platform Billing", "user"])
async def test_partner_permissions_are_dropped_from_every_other_role(role):
    """protects=a document of a non-partner role cannot carry the two partner permissions;
    fails_when=view:partner_portal or manage:partner_customers survives effective_permissions;
    no_claim=the other permissions of those documents (they are unchanged)."""
    tenant = "tenant-a"
    db = _store([_doc(role, tenant, ["view:partner_portal", "manage:partner_customers", "view:agents"]),
                 _doc(role, "platform", ["view:partner_portal"]), _doc(role, "all", ["manage:partner_customers"])])
    got = await effective_permissions(db, role, tenant)
    assert "view:partner_portal" not in got and "manage:partner_customers" not in got
    assert "view:agents" in got


async def test_a_custom_role_cannot_carry_a_partner_permission():
    """protects=a custom tenant role stays out of the partner portal; fails_when=a custom role
    document lists view:partner_portal and keeps it; no_claim=assignment of that role."""
    db = _store([_doc("Helpdesk", "tenant-a", ["view:partner_portal", "view:agents"])])
    assert await effective_permissions(db, "Helpdesk", "tenant-a") == ["view:agents"]


def test_partner_only_permissions_are_exactly_the_two_partner_permissions():
    """protects=the banned set matches the partner table rows; fails_when=a partner permission is
    added to a role row without joining the banned set; no_claim=none beyond protects."""
    assert d.PARTNER_ONLY_PERMISSIONS == frozenset({"manage:partner_customers", "view:partner_portal"})
    held = set().union(*(set(d.defaults_for(k)) for k in d.PARTNER_ROLE_KEYS))
    assert held == set(d.PARTNER_ONLY_PERMISSIONS)
    for key, perms in d.ROLE_DEFAULTS.items():
        if key not in d.PARTNER_ROLE_KEYS:
            assert not (set(perms) & d.PARTNER_ONLY_PERMISSIONS), key


# -- MFA (D-20) ---------------------------------------------------------------------------

def test_partner_admin_is_admin_tier_and_the_viewer_is_not():
    """protects=D-20: partner admins enroll MFA, viewers do not; fails_when=the admin tier drops
    manage:partner_customers or the viewer joins it; no_claim=enrollment flow itself."""
    assert d.requires_mfa(d.defaults_for("partner_admin")) is True
    assert d.requires_mfa(d.defaults_for("partner_viewer")) is False
    assert auth_svc.mfa_required_for("Partner Admin", "partner-a") is True
    assert auth_svc.mfa_required_for("partner_viewer", "partner-a") is False


async def test_resolve_mfa_required_follows_the_partner_rows():
    """protects=the first session of an invited partner admin gets mfa_action enroll and a viewer none;
    fails_when=resolve_mfa_required answers False for partner_admin or True for partner_viewer;
    no_claim=login endpoint wiring."""
    with patch("database.get_database", return_value=_store()):
        assert await auth_svc.resolve_mfa_required("partner_admin", "partner-a") is True
        assert await auth_svc.resolve_mfa_required("Partner Viewer", "partner-a") is False
    assert auth_svc.mfa_action_for("partner_admin", False, False, required=True) == "enroll"


# -- assignment: a partner role lives only in a partner organization (D-04) --------------------

SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id=d.PLATFORM_TENANT_ID, mfa_verified=True)
TENANT_ADMIN = TokenData(username="admin@cust.example", role="Tenant Admin", tenant_id="cust-1", mfa_verified=True)


@pytest.fixture
async def orgs(mongo_db):
    await mongo_db.tenants.insert_many([
        {"id": "partner-1", "name": "Retailer", "type": "partner"},
        {"id": "cust-1", "name": "Cafe", "type": "customer", "partnerId": "partner-1"},
        {"id": "direct-1", "name": "Direct"},
    ])
    return mongo_db


async def test_a_partner_role_fits_only_a_partner_organization(orgs):
    """protects=T-87-05 on the tenant side: partner roles only in a type partner tenant, and no other role there;
    fails_when=partner_admin is accepted in a customer or untyped tenant, or Tenant Admin in a partner org,
    or a viewer in a customer is refused; no_claim=the HTTP stack (the helper is called directly)."""
    fits = role_assignment.assert_role_fits_tenant_type
    for role in ("partner_admin", "Partner Admin", "partner_viewer"):
        for tenant in ("cust-1", "direct-1"):
            with pytest.raises(HTTPException) as exc:
                await fits(orgs, role, tenant)
            assert exc.value.status_code == 400 and "partner role" in exc.value.detail
        await fits(orgs, role, "partner-1")
    for role in ("Tenant Admin", "viewer", "user", "itam_admin"):
        with pytest.raises(HTTPException) as exc:
            await fits(orgs, role, "partner-1")
        assert exc.value.status_code == 400 and "must hold a partner role" in exc.value.detail
        await fits(orgs, role, "cust-1")
    await fits(orgs, "viewer", "no-such-tenant")
    await fits(orgs, "partner_viewer", None)


@pytest.mark.parametrize("role", ["partner_admin", "Partner Admin", "partner_viewer"])
async def test_only_the_super_admin_assigns_a_partner_role(orgs, role):
    """protects=T-87-05: a tenant admin gets 403 with the super-admin message, the Super Admin passes;
    fails_when=rule 1 of assert_can_assign_role does not name partner roles; no_claim=the ceiling matrix."""
    with pytest.raises(HTTPException) as exc:
        await role_assignment.assert_can_assign_role(_store(), TENANT_ADMIN, role, target_tenant_id="cust-1")
    assert exc.value.status_code == 403 and "Only a platform super-admin" in exc.value.detail
    await role_assignment.assert_can_assign_role(_store(), SUPER, role, target_tenant_id="partner-1")


async def test_a_tenant_admin_cannot_manage_a_partner_account():
    """protects=T-87-05: partner accounts are managed by the Super Admin only;
    fails_when=a tenant admin passes assert_can_manage_account for a partner_admin account;
    no_claim=accounts of other roles."""
    with pytest.raises(HTTPException) as exc:
        await role_assignment.assert_can_manage_account(_store(), TENANT_ADMIN, "partner_admin",
                                                        target_tenant_id="cust-1")
    assert exc.value.status_code == 403 and "platform super-admin" in exc.value.detail
    await role_assignment.assert_can_manage_account(_store(), SUPER, "partner_admin", target_tenant_id="partner-1")


@pytest.mark.parametrize("role", ["partner_admin", "Partner Viewer", "partner-viewer"])
def test_a_directory_mapping_to_a_partner_role_is_refused(role):
    """protects=T-87-06: LDAP and SAML mappings cannot create partner staff;
    fails_when=refuse_directory_platform_role lets a partner role through; no_claim=the mapping endpoints (unchanged)."""
    with pytest.raises(HTTPException) as exc:
        role_assignment.refuse_directory_platform_role(role)
    assert exc.value.status_code == 400 and "partner role" in exc.value.detail
    role_assignment.refuse_directory_platform_role("viewer")


@pytest.fixture
def users_api(orgs):
    handle = SimpleNamespace(users=orgs.users, tenants=orgs.tenants, _db=orgs)
    with patch.object(ue, "get_database", return_value=handle), patch.object(ue, "_audit", new=AsyncMock()):
        yield orgs


async def test_create_user_refuses_a_partner_role_in_a_customer_and_stores_nothing(users_api):
    """protects=T-87-05 on the create path: the Super Admin cannot put partner_admin in a customer org nor
    a customer role in a partner org, and nothing is stored; fails_when=create_user skips the tenant type check;
    no_claim=password policy and the router dependency chain."""
    body = dict(password="Str0ng!Passw0rd#1", full_name="P One", status="active")
    with pytest.raises(HTTPException) as exc:
        await ue.create_user(ue.UserCreate(email="p@x.test", role="partner_admin", tenantId="cust-1", **body),
                             current_user=SUPER)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await ue.create_user(ue.UserCreate(email="v@x.test", role="viewer", tenantId="partner-1", **body),
                             current_user=SUPER)
    assert exc.value.status_code == 400
    assert await users_api.users.count_documents({}) == 0
    out = await ue.create_user(ue.UserCreate(email="ok@x.test", role="partner_admin", tenantId="partner-1", **body),
                               current_user=SUPER)
    assert out["role"] == "partner_admin"
    assert await users_api.users.count_documents({}) == 1


async def test_update_user_refuses_moving_a_role_across_organization_types(users_api):
    """protects=T-87-05 on the update path: changing a role or tenant cannot leave a partner role outside a
    partner org or a customer role inside one; fails_when=update_user skips the tenant type check;
    no_claim=other update fields."""
    from bson import ObjectId
    partner_user = (await users_api.users.insert_one(
        {"email": "pa@x.test", "role": "partner_admin", "tenantId": "partner-1", "status": "Active"})).inserted_id
    customer_user = (await users_api.users.insert_one(
        {"email": "cu@x.test", "role": "viewer", "tenantId": "cust-1", "status": "Active"})).inserted_id
    for user_id, update in ((partner_user, ue.UserUpdate(tenantId="cust-1")),
                            (partner_user, ue.UserUpdate(role="viewer")),
                            (customer_user, ue.UserUpdate(tenantId="partner-1")),
                            (customer_user, ue.UserUpdate(role="partner_viewer"))):
        with pytest.raises(HTTPException) as exc:
            await ue.update_user(str(user_id), update, current_user=SUPER)
        assert exc.value.status_code == 400, update
    stored = await users_api.users.find_one({"_id": ObjectId(str(partner_user))})
    assert stored["role"] == "partner_admin" and stored["tenantId"] == "partner-1"
