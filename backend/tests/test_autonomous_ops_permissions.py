"""Phase 81 plan 02: the Autonomous Ops permission strings (GATE-13, ACTV-01).

Each test cites the decision it pins (D-05 .. D-09, D-24 (a)). Role strings come from the real
``rbac_defaults`` table and the real shared manifest; roles are served from the in-memory role
store in ``tests/rbac_test_support`` and the live database is never touched.
"""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import rbac_defaults as d
import rbac_service
import rbac_utils
import role_endpoints
import tenant_features
from auth_types import TokenData
from authentication_service import get_current_user
from tests.rbac_test_support import role_store, shared_role_docs

VIEW, MANAGE, CONTROL = "view:autonomous_ops", "manage:autonomous_ops", "control:autonomous_ops"
PLATFORM_STOP = "control:platform_autonomous_ops"
SHARED = Path(__file__).resolve().parents[2] / "shared"
ROLE_ID = {b.key: b.role_id for b in d.BUILTIN_ROLES}


def _ops(perms):
    return {p for p in perms if p.endswith("autonomous_ops")}


# --- built-in table (D-06, D-24 (a), D-08) ------------------------------------------

@pytest.mark.parametrize("role,expected", [
    ("tenant_admin", {VIEW, MANAGE, CONTROL}),
    ("analyst", {VIEW}),
    ("security_analyst", {VIEW, CONTROL}),
    ("incident_responder", {VIEW, CONTROL}),
    ("platform_support", {VIEW}),
    ("viewer", set()),
    ("user", set()),
    ("itam_admin", set()),
    ("itam_user", set()),
    ("itam_viewer", set()),
    ("platform_billing", set()),
])
def test_role_table_grants_follow_d06_and_d24(role, expected):
    """D-06 / D-24 (a) / D-08: exactly these Autonomous Ops strings per built-in role, and no Auditor role."""
    assert _ops(d.defaults_for(role)) == expected
    assert "auditor" not in d.ROLE_DEFAULTS


def test_the_platform_stop_is_held_by_no_table_role():
    """D-05 / GATE-13: control:platform_autonomous_ops is in no table row; only '*' reaches it."""
    assert not [k for k, perms in d.ROLE_DEFAULTS.items() if PLATFORM_STOP in perms]
    assert d.defaults_for("super_admin") == ("*",)


# --- admin tier and MFA (D-07) ----------------------------------------------------------

@pytest.mark.parametrize("role,needs", [
    ("tenant_admin", True), ("security_analyst", True), ("incident_responder", True),
    ("analyst", False), ("viewer", False), ("user", False), ("itam_viewer", False),
])
def test_approve_tier_is_admin_tier(role, needs):
    """D-07: control:autonomous_ops makes its holders admin-tier; Analyst (view only) stays outside it."""
    assert d.requires_mfa(d.defaults_for(role)) is needs


def test_admin_tier_membership_of_the_new_strings():
    """D-07 / D-05: control: is admin-tier directly; the platform stop is admin-tier through the platform-only set."""
    assert CONTROL in d.ADMIN_TIER_PERMISSIONS
    assert PLATFORM_STOP in d.PLATFORM_ONLY_PERMISSIONS and PLATFORM_STOP in d.ADMIN_TIER_PERMISSIONS
    assert VIEW not in d.ADMIN_TIER_PERMISSIONS and MANAGE not in d.ADMIN_TIER_PERMISSIONS


@pytest.mark.parametrize("perms,needs", [
    ([CONTROL], True), ([VIEW], False), ([VIEW, MANAGE], False), ([MANAGE, CONTROL], True),
])
def test_custom_role_mfa_follows_the_admin_tier(perms, needs):
    """D-07 / D-09: a custom role holding control:autonomous_ops is admin-tier; view/manage alone are not."""
    assert d.requires_mfa(perms) is needs


# --- closure (PROH-81-16, D-05) ---------------------------------------------------------

def test_manage_implies_view_and_never_control():
    """PROH-81-16: implied_closure(manage) adds view and never a control: string."""
    closed = d.implied_closure([MANAGE])
    assert VIEW in closed and not {p for p in closed if p.startswith("control:")}


def test_control_alone_implies_neither_view_nor_manage():
    """PROH-81-16: control:autonomous_ops grants no screen and no manage right on its own."""
    closed = d.implied_closure([CONTROL])
    assert closed == {CONTROL}


def test_a_role_with_both_keeps_both():
    """PROH-81-16: a role holding manage and control keeps both, plus the implied view."""
    assert {VIEW, MANAGE, CONTROL} <= d.implied_closure([MANAGE, CONTROL])


def test_deliverable_closure_does_not_cross_the_adjacency():
    """PROH-81-16 over the delivered list: manage gives view, control gives neither of the other two."""
    assert VIEW in d.deliverable_closure([MANAGE], rbac_service.permission_vocabulary.KNOWN_PERMISSIONS)
    assert d.deliverable_closure([CONTROL], rbac_service.permission_vocabulary.KNOWN_PERMISSIONS) == [CONTROL]


# --- ceiling (D-09) ---------------------------------------------------------------------

@pytest.mark.parametrize("string", [VIEW, MANAGE, CONTROL])
def test_tenant_admin_may_grant_each_string_in_a_custom_role(string):
    """D-09: tenant_admin holds all three, so its ceiling allows each."""
    assert d.ceiling_allows(d.defaults_for("tenant_admin"), [string])


@pytest.mark.parametrize("caller", ["security_analyst", "incident_responder"])
def test_an_approver_cannot_grant_manage(caller):
    """D-09 / GATE-13: holding control: never lets a caller hand out manage:autonomous_ops."""
    assert d.ceiling_allows(d.defaults_for(caller), [CONTROL])
    assert not d.ceiling_allows(d.defaults_for(caller), [MANAGE])


def test_no_tenant_caller_may_grant_the_platform_stop():
    """D-05: no table role holds control:platform_autonomous_ops, so no ceiling hands it out."""
    for key in d.ROLE_DEFAULTS:
        assert not d.ceiling_allows(d.defaults_for(key), [PLATFORM_STOP]), key
    assert d.ceiling_allows(d.defaults_for("super_admin"), [PLATFORM_STOP])


# --- platform-only (D-05 / GATE-13) -------------------------------------------------------

class _Roles:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, flt, *a, **k):
        return next((x for x in self.docs if all(x.get(f) == v for f, v in flt.items())), None)


async def test_a_role_document_cannot_carry_the_platform_stop():
    """D-05: effective_permissions strips control:platform_autonomous_ops from a tenant custom role."""
    from types import SimpleNamespace
    docs = [{"name": "admin", "tenantId": "tenant-a", "permissions": [PLATFORM_STOP, CONTROL, "view:tickets"]}]
    db = SimpleNamespace(_db=SimpleNamespace(roles=_Roles(docs)))
    perms = await rbac_service.effective_permissions(db, "admin", "tenant-a")
    assert CONTROL in perms and PLATFORM_STOP not in perms


async def test_only_the_owner_passes_the_platform_stop():
    """D-05 / GATE-13: the owner passes has_platform_permission; support, billing and a tenant admin do not."""
    owner = TokenData(username="o@p", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)
    support = TokenData(username="s@p", role="Platform Support", tenant_id="platform-admin", mfa_verified=True)
    billing = TokenData(username="b@p", role="Platform Billing", tenant_id="platform-admin", mfa_verified=True)
    admin = TokenData(username="a@t", role="Tenant Admin", tenant_id="tenant-a", mfa_verified=True)
    assert await rbac_utils.has_platform_permission(owner, PLATFORM_STOP)
    for user in (support, billing, admin):
        assert not await rbac_utils.has_platform_permission(user, PLATFORM_STOP)


# --- tenant switch (GATE-02) ------------------------------------------------------------------

def test_the_catalogue_entry_and_switches_match_d05():
    """ACTV-01 / D-05 / GATE-02: the manifest entry and the two tenant switches carry the exact fields."""
    manifest = json.loads((SHARED / "catalogue-access.json").read_text())
    entry = [c for c in manifest["catalogues"] if c["view"] == "autonomousOps"]
    assert len(entry) == 1
    assert entry[0] == {"view": "autonomousOps", "label": "Autonomous Ops", "group": "automation", "nav": True,
                        "permission": VIEW, "write": [MANAGE, CONTROL], "routes": ["/api/autonomous-ops"]}
    switches = {f["permission"]: f for g in json.loads((SHARED / "tenant-feature-switches.json").read_text())["groups"]
                for f in g["features"]}
    assert switches[VIEW]["label"] == "Autonomous Ops"
    assert switches[MANAGE]["label"] == "Manage Autonomous Ops" and switches[MANAGE]["parent"] == VIEW
    assert CONTROL not in switches


def test_a_tenant_without_the_view_switch_loses_all_three_strings():
    """GATE-02: narrowing without the view switch removes view, manage and control of autonomous_ops."""
    perms = list(d.defaults_for("tenant_admin"))
    off = tenant_features.narrow(perms, ["view:dashboard"])
    assert not _ops(off)
    on = tenant_features.narrow(perms, ["view:dashboard", VIEW, MANAGE])
    assert _ops(on) == {VIEW, MANAGE, CONTROL}


def test_new_tenants_stay_overview_only():
    """GATE-02: the new switch is not part of the start set, so a new tenant is not eligible."""
    assert VIEW not in tenant_features.START_FEATURES and MANAGE not in tenant_features.START_FEATURES


# --- delivery and visibility (edge: GATE-13 empty) -----------------------------------------------

def _doc(name, tenant, permissions):
    return {"id": f"custom-{tenant}-{name}", "name": name, "tenantId": tenant,
            "description": name, "permissions": permissions, "isEditable": True}


@pytest.fixture
def store(monkeypatch):
    docs = shared_role_docs() + [_doc("Empty", "tenant-a", []), _doc("Approver", "tenant-a", [CONTROL]),
                                 _doc("Auditor", "tenant-a", [VIEW])]
    tenants = [{"id": "tenant-a", "name": "Tenant A", "enabledFeatures": ["all"]}]
    db, raw = role_store(roles=docs, tenants=tenants, users=[], ldap_group_mappings=[], saml_group_mappings=[])
    for module in (role_endpoints, rbac_utils, rbac_service):
        monkeypatch.setattr(module, "get_database", lambda: db, raising=False)
    return db


def _visible(store, role_id):
    app = FastAPI()
    app.include_router(role_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: TokenData(
        username="ta@x.test", role="tenant_admin", tenant_id="tenant-a")
    res = TestClient(app).get(f"/api/roles/{role_id}/visibility")
    assert res.status_code == 200, res.text
    return {s["view"] for g in res.json()["groups"] for s in g["screens"]}


async def test_a_custom_role_with_none_of_the_strings_has_no_autonomous_ops(store):
    """GATE-13 empty edge: no autonomous_ops string delivered and no nav entry in role visibility."""
    assert not _ops(await rbac_service.session_permissions(store, "Empty", "tenant-a"))
    assert "autonomousOps" not in _visible(store, "custom-tenant-a-Empty")


async def test_view_holders_see_the_entry_and_control_alone_does_not(store):
    """D-05 / PROH-81-16: the sidebar entry follows view:autonomous_ops; control: alone shows no screen."""
    assert "autonomousOps" in _visible(store, ROLE_ID["analyst"])
    assert "autonomousOps" in _visible(store, "custom-tenant-a-Auditor")
    assert "autonomousOps" not in _visible(store, "custom-tenant-a-Approver")
    assert "autonomousOps" not in _visible(store, ROLE_ID["viewer"])
    assert _ops(await rbac_service.session_permissions(store, "Approver", "tenant-a")) == {CONTROL}
