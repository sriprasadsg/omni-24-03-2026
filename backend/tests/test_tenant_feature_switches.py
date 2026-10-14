"""Spec C6: per-tenant feature switches are enforced for the tenant's users.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Unless a test says otherwise, no_claim=MongoDB and
the full app (in-memory fakes stand in for the tenants and roles collections).
"""
import json
import os
import sys
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rbac_defaults
import rbac_service
import rbac_utils
import tenant_features as tf
from auth_types import TokenData
from authentication_service import get_current_user
from catalogue_guards import catalogue_guard

pytestmark = pytest.mark.real_tenant_features

TENANT_ADMIN_DEFAULTS = list(rbac_defaults.defaults_for("tenant_admin"))
ALWAYS_ON = ["view:dashboard", "view:profile", "manage:users", "view:itam", "manage:itam"]


class _Collection:
    """find_one over a list of dicts with exact-match queries; ``fail`` makes every read raise."""

    def __init__(self, docs=(), fail=False):
        self.docs, self.fail, self.reads = list(docs), fail, 0

    async def find_one(self, query, projection=None):
        self.reads += 1
        if self.fail:
            raise RuntimeError("store unreachable")
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None


def _db(tenants=(), roles=(), tenants_fail=False, roles_fail=False):
    raw = SimpleNamespace(tenants=_Collection(tenants, fail=tenants_fail), roles=_Collection(roles, fail=roles_fail))
    return SimpleNamespace(_db=raw, roles=raw.roles, tenants=raw.tenants)


def _tenant(features, tenant_id="tenant-a"):
    return {"id": tenant_id, "name": "A", "enabledFeatures": features}


# ── The rule ──────────────────────────────────────────────────────────────────

def test_switched_off_features_are_removed_and_unswitched_permissions_kept():
    """protects=a tenant admin keeps only the switched-on features plus everything that has no
    switch; fails_when=an off switch survives, or manage:users/view:dashboard is removed; no_claim=none beyond protects."""
    granted = tf.narrow(TENANT_ADMIN_DEFAULTS, ["view:agents", "view:reporting"])
    assert {"view:agents", "view:reporting"} <= set(granted)
    assert set(ALWAYS_ON) <= set(granted)
    for off in ("view:security", "manage:rbac", "manage:api_keys", "view:finops", "export:reports"):
        assert off not in granted


def test_an_off_view_takes_its_resource_twins_with_it():
    """protects=hiding view:X cannot be undone by manage:X (catalogue guards accept manage:X for reads);
    fails_when=manage:agents survives with Agent Fleet Management off; no_claim=none beyond protects."""
    perms = ["view:agents", "manage:agents", "remediate:agents", "view:agent_logs", "manage:users"]
    assert tf.narrow(perms, []) == ["manage:users"]
    assert tf.narrow(perms, ["view:agents"]) == ["view:agents", "manage:agents", "manage:users"]


def test_a_feature_is_off_while_its_parent_is_off():
    """protects=Deploy Patches cannot be on while Patch Management is off; fails_when=a child switch
    stored on outlives its parent; no_claim=none beyond protects."""
    assert "manage:patches" not in tf.narrow(["manage:patches"], ["manage:patches"])
    assert tf.narrow(["manage:patches"], ["view:patching", "manage:patches"]) == ["manage:patches"]


def test_all_switches_nothing_off_and_a_missing_list_switches_everything_off():
    """protects="all" keeps the role intact; a tenant with no list fails closed but keeps the
    unswitched basics; fails_when="all" narrows, or None/[] grants a switch; no_claim=none beyond protects."""
    assert tf.narrow(TENANT_ADMIN_DEFAULTS, ["all"]) == TENANT_ADMIN_DEFAULTS
    for empty in (None, []):
        granted = tf.narrow(TENANT_ADMIN_DEFAULTS, empty)
        assert not set(granted) & tf.SWITCHABLE
        assert set(ALWAYS_ON) <= set(granted)


def test_the_switch_catalogue_is_sound():
    """protects=the shared list the Manage Tenant screen shows is the list the server enforces, every
    switch is a real tenant permission, and the basics are never switchable; fails_when=a typo'd
    permission, a dangling parent, or view:profile becomes switchable; no_claim=the screen's rendering."""
    assert tf.SWITCHABLE <= set(TENANT_ADMIN_DEFAULTS)
    assert all(parent in tf.SWITCHABLE for parent in tf.SWITCH_PARENTS.values() if parent)
    assert not set(ALWAYS_ON) & tf.SWITCHABLE
    assert not any(tf.is_switchable(p) for p in ALWAYS_ON)


@pytest.mark.parametrize("features,error", [
    ([{"permission": "view:x", "label": "X"}, {"permission": "view:x", "label": "X again"}], "duplicate"),
    ([{"permission": "manage:x", "label": "X", "parent": "view:nope"}], "unknown parent"),
])
def test_a_broken_switch_catalogue_stops_startup(tmp_path, features, error):
    """protects=a malformed shared list fails loudly at import; fails_when=duplicates or dangling
    parents load silently; no_claim=none beyond protects."""
    path = tmp_path / "switches.json"
    path.write_text(json.dumps({"groups": [{"name": "G", "features": features}]}))
    with pytest.raises(ValueError, match=error):
        tf._load_parents(path)


# ── The resolver ──────────────────────────────────────────────────────────────

async def test_granted_permissions_narrow_a_tenant_role_but_not_its_definition():
    """protects=a tenant admin is narrowed while the role's definition (role lists, assignment
    ceiling) is untouched; fails_when=the definition is narrowed or the grant is not; no_claim=none beyond protects."""
    db = _db(tenants=[_tenant(["view:agents"])])
    granted = await rbac_service.granted_permissions(db, "Tenant Admin", "tenant-a")
    assert "view:agents" in granted and "view:security" not in granted
    assert "view:security" in await rbac_service.effective_permissions(db, "Tenant Admin", "tenant-a")


async def test_a_tenant_role_document_is_narrowed_too():
    """protects=a custom role cannot re-add a switched-off feature through its role document;
    fails_when=a role doc's view:security survives the switch; no_claim=none beyond protects."""
    db = _db(tenants=[_tenant(["view:agents"])],
             roles=[{"name": "Helpdesk", "tenantId": "tenant-a", "permissions": ["view:security", "view:agents"]}])
    assert await rbac_service.granted_permissions(db, "Helpdesk", "tenant-a") == ["view:agents"]


@pytest.mark.parametrize("role,expected", [("Super Admin", ["*"]), ("Platform Support", None)])
async def test_platform_roles_are_never_narrowed(role, expected):
    """protects=platform staff keep their role whatever the Platform tenant's list says; fails_when=
    support loses view:security to the Platform tenant's two-entry list; no_claim=none beyond protects."""
    db = _db(tenants=[_tenant(["view:itam", "manage:itam"], tenant_id="platform-admin")])
    granted = await rbac_service.granted_permissions(db, role, "platform-admin")
    assert granted == (expected or await rbac_service.effective_permissions(db, role, "platform-admin"))
    if role == "Platform Support":
        assert "view:security" in granted


async def test_an_unknown_tenant_fails_closed():
    """protects=a user whose tenant record is gone gets no switchable feature; fails_when=a missing
    tenant means no narrowing; no_claim=none beyond protects."""
    granted = await rbac_service.granted_permissions(_db(), "Tenant Admin", "tenant-gone")
    assert not set(granted) & tf.SWITCHABLE and "manage:users" in granted


async def test_the_fallback_when_the_store_fails_is_narrowed(monkeypatch):
    """protects=/login, /me and has_permission never deliver a switched-off feature because the tenant
    lookup failed; fails_when=the built-in defaults are delivered whole; no_claim=none beyond protects."""
    db = _db(tenants_fail=True)
    delivered = await rbac_service.session_permissions(db, "Tenant Admin", "tenant-a")
    assert not set(delivered) & tf.SWITCHABLE and "manage:users" in delivered

    monkeypatch.setattr(rbac_service, "get_database", lambda: db)
    user = TokenData(username="a@a", role="Tenant Admin", tenant_id="tenant-a")
    assert await rbac_service.rbac_service.get_user_permissions(user) == delivered


async def test_a_role_store_failure_still_honours_the_tenant_switches():
    """protects=when only the role store fails, the built-in defaults are narrowed by the tenant's real
    list (switched-on features stay usable); fails_when=the fallback ignores the list or drops
    everything; no_claim=none beyond protects."""
    db = _db(tenants=[_tenant(["view:agents"])], roles_fail=True)
    delivered = await rbac_service.session_permissions(db, "Tenant Admin", "tenant-a")
    assert "view:agents" in delivered and "view:security" not in delivered


async def test_session_permissions_deliver_the_narrowed_list():
    """protects=/login and /me (both call session_permissions) hand the UI the narrowed list, so the
    sidebar hides switched-off features; fails_when=the UI gets the full role; no_claim=the routes themselves."""
    db = _db(tenants=[_tenant(["view:agents", "view:security"])])
    delivered = await rbac_service.session_permissions(db, "Tenant Admin", "tenant-a")
    assert {"view:agents", "view:security"} <= set(delivered)
    assert "view:compliance" not in delivered and "manage:rbac" not in delivered


# ── Enforcement ───────────────────────────────────────────────────────────────

async def test_verify_permission_no_longer_waves_through_a_switched_off_default(monkeypatch):
    """protects=the defaults shortcut in verify_permission cannot grant a switched-off feature;
    fails_when=view:security passes because it is in the Tenant Admin defaults; no_claim=none beyond protects."""
    admin = TokenData(username="a@a", role="Tenant Admin", tenant_id="tenant-a")
    monkeypatch.setattr(rbac_utils, "get_database", lambda: _db(tenants=[_tenant(["view:agents"])]))
    assert await rbac_utils.verify_permission(admin, "view:agents")
    assert not await rbac_utils.verify_permission(admin, "view:security")
    assert not await rbac_utils.verify_permission(admin, "manage:security_cases")

    store = _db(tenants_fail=True)
    monkeypatch.setattr(rbac_utils, "get_database", lambda: store)
    assert await rbac_utils.verify_permission(admin, "manage:users")  # unswitched: no lookup needed
    assert store.tenants.reads == 0
    assert not await rbac_utils.verify_permission(admin, "view:agents")  # lookup fails: closed


@pytest.mark.parametrize("features,expected", [(["view:security", "view:agents"], 200), (["view:dashboard"], 403)])
def test_routes_refuse_a_switched_off_feature(monkeypatch, features, expected):
    """protects=every guard style (require_permission, has_permission, catalogue_guard read and write)
    answers 403 for a switched-off feature and 200 when it is on; fails_when=any style still serves it;
    no_claim=which production routes carry a guard (Phase 76 gap ledger)."""
    db = _db(tenants=[_tenant(features)])
    monkeypatch.setattr(rbac_utils, "get_database", lambda: db)
    monkeypatch.setattr(rbac_service, "get_database", lambda: db)
    admin = TokenData(username="a@a", role="Tenant Admin", tenant_id="tenant-a", mfa_verified=True)

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: admin
    guard = catalogue_guard("agents", read=("view:agents",), write=("manage:agents",))

    @app.get("/require", dependencies=[Depends(rbac_utils.require_permission("view:security"))])
    def _require():
        return {}

    @app.get("/has", dependencies=[Depends(rbac_service.rbac_service.has_permission("view:security"))])
    def _has():
        return {}

    @app.get("/catalogue", dependencies=[Depends(guard)])
    def _catalogue_read():
        return {}

    @app.post("/catalogue", dependencies=[Depends(guard)])
    def _catalogue_write():
        return {}

    client = TestClient(app)
    for method, path in (("get", "/require"), ("get", "/has"), ("get", "/catalogue"), ("post", "/catalogue")):
        assert getattr(client, method)(path).status_code == expected, (method, path)


def test_the_real_app_refuses_a_switched_off_feature():
    """protects=on the real app (every router as registered, mount guards included) a Tenant Admin is
    refused a switched-off feature's routes and not refused when it is on; fails_when=a real route
    still serves Asset Management or Agent Fleet Management after the switch is off;
    no_claim=MongoDB (the child app has no database; the switch list comes from the case)."""
    from tests._route_walk import probe_real_app

    def case(path, features):
        return {"method": "GET", "path": path, "role": "Tenant Admin", "tenant_id": "tenant-a",
                "auth": "session", "tenant_features": features}

    assets_on, assets_off, agents_off, agents_on = probe_real_app([
        case("/api/assets", ["view:assets"]), case("/api/assets", ["view:agents"]),
        case("/api/agents", ["view:assets"]), case("/api/agents", ["view:agents"]),
    ])
    assert assets_off == 403 and agents_off == 403
    assert assets_on != 403 and agents_on != 403
