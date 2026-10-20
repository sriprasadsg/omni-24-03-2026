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
import jwt
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
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.real_tenant_features

TENANT_ADMIN_DEFAULTS = list(rbac_defaults.defaults_for("tenant_admin"))
ALWAYS_ON = ["view:dashboard", "view:profile", "manage:users"]


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
    assert {p for p in tf.SWITCHABLE if not p.startswith(tf.SCREEN_PREFIX)} <= set(TENANT_ADMIN_DEFAULTS)
    manifest = {c["view"]: c["permission"] for c in json.load(open(tf._CATALOGUE_PATH.parent / "catalogue-access.json"))["catalogues"]}
    assert all(manifest.get(view) == parent for view, parent in tf.SCREEN_SWITCHES.items())
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
        tf._load_switches(path)


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
    granted = await rbac_service.granted_permissions(db, "Helpdesk", "tenant-a")
    assert [p for p in granted if not p.startswith(tf.SCREEN_OFF_PREFIX)] == ["view:agents"]


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


async def test_the_itam_backfill_runs_once_as_a_migration(mongo_db):
    """protects=migration 016 gives pre-ITAM tenants ITAM once, skips the platform tenant and tenants
    already carrying it, and seeding no longer re-adds it (so a Super Admin can switch ITAM off);
    fails_when=the platform tenant or an untouched tenant is changed; no_claim=the runner bookkeeping."""
    import importlib
    await mongo_db.tenants.insert_many([
        {"id": "old", "enabledFeatures": ["view:agents"]},
        {"id": "has", "enabledFeatures": ["view:itam", "manage:itam"]},
        {"id": "platform-admin", "enabledFeatures": []}])
    await importlib.import_module("migrations.016_itam_feature_backfill_once").up(mongo_db)
    features = {t["id"]: t["enabledFeatures"] async for t in mongo_db.tenants.find({}, {"_id": 0})}
    assert set(features["old"]) == {"view:agents", "view:itam", "manage:itam"}
    assert features["has"] == ["view:itam", "manage:itam"] and features["platform-admin"] == []


# ── Per-screen switches (Security / Compliance screens share one permission) ──

def test_screen_switch_rule():
    """protects=a screen is on only when its switch and its parent switch are on, "all" turns on every
    screen of a held parent, route ownership is the longest manifest prefix, and new tenants get every
    screen of the features they start with; fails_when=a screen survives its parent or a non-screen
    route is claimed; no_claim=MongoDB (pure functions)."""
    assert tf.screen_permissions(["view:security"], ["view:security", "screen:edr"]) == ["screen:edr"]
    assert tf.screen_permissions(["view:security"], ["screen:edr"]) == []          # parent off
    assert tf.screen_permissions([], ["view:security", "screen:edr"]) == []        # role lacks the parent
    assert "screen:edr" in tf.screen_permissions(["view:security"], ["all"])
    assert (tf.screen_of("/api/edr/hosts"), tf.screen_of("/api/edr"), tf.screen_of("/api/agents")) == ("edr", "edr", None)
    # Security and Compliance screens are ticked by a Super Admin, never added with their feature.
    assert not set(tf.with_all_screens(["view:security"])) & {"screen:edr", "screen:alertManagement"}
    fleet = set(tf.with_all_screens(["view:agents"]))
    assert {"screen:agents", "screen:chat", "screen:dashboard", "screen:internalTickets"} <= fleet
    assert not fleet & {"screen:edr", "screen:reporting"}                         # their parents are absent


async def test_granted_permissions_mark_the_switched_off_screens():
    """protects=/login and /me mark each switched-off Security screen (screen-off:<view>) so the UI hides
    it, mark nothing for a tenant with every screen on (its list stays the role's permissions), and mark
    nothing for a feature the user lacks; fails_when=EDR is marked off while on, or Alert Management is not
    marked while off; no_claim=none beyond protects."""
    db = _db(tenants=[_tenant(["view:security", "screen:edr"])])
    granted = await rbac_service.granted_permissions(db, "Tenant Admin", "tenant-a")
    assert "screen-off:alertManagement" in granted and "screen-off:edr" not in granted
    # D-16 (Phase 77): view:compliance is switched off, so its nav screen carries a marker too.
    assert "screen-off:compliance" in granted and "view:compliance" not in granted
    assert not any(p.startswith("screen:") for p in granted)
    everything = _db(tenants=[_tenant(["all"])])
    assert await rbac_service.granted_permissions(everything, "Tenant Admin", "tenant-a") == \
        await rbac_service.effective_permissions(everything, "Tenant Admin", "tenant-a")


def _screen_app():
    from fastapi.testclient import TestClient
    from tenant_middleware import ScreenSwitchMiddleware, TenantMiddleware
    app = FastAPI()
    app.add_middleware(ScreenSwitchMiddleware)
    app.add_middleware(TenantMiddleware)
    for path in ("/api/edr/hosts", "/api/alerts", "/api/agents"):
        app.add_api_route(path, lambda: {}, methods=["GET"])
    return TestClient(app)


def _bearer(role, tenant):
    import authentication_service as auth
    token = jwt.encode({"sub": "u@x", "role": role, "tenant_id": tenant}, auth.SECRET_KEY, algorithm=auth.ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("features,role,path,expected", [
    (["view:security"], "Tenant Admin", "/api/edr/hosts", 403),
    (["view:security", "screen:edr"], "Tenant Admin", "/api/edr/hosts", 200),
    (["view:security", "screen:edr"], "Tenant Admin", "/api/alerts", 403),
    (["view:security"], "Tenant Admin", "/api/agents", 200),
    (["view:security"], "Platform Support", "/api/edr/hosts", 200),
])
def test_a_switched_off_screen_is_refused_on_its_routes(monkeypatch, features, role, path, expected):
    """protects=the server refuses a tenant user the routes a switched-off screen owns, serves a
    switched-on screen, ignores routes no switched screen owns, and never limits platform roles;
    fails_when=EDR's API answers with the EDR screen off; no_claim=API-key callers (no bearer JWT pass
    through to the route's own guard)."""
    import database
    tenant = "platform-admin" if role == "Platform Support" else "tenant-a"
    monkeypatch.setattr(database, "get_database", lambda: _db(tenants=[_tenant(features)]))
    assert _screen_app().get(path, headers=_bearer(role, tenant)).status_code == expected


def test_a_failed_screen_lookup_refuses(monkeypatch):
    """protects=when the tenant's switches cannot be read a screen route is refused, not served;
    fails_when=an error falls through to the route; no_claim=none beyond protects."""
    import database
    monkeypatch.setattr(database, "get_database", lambda: _db(tenants_fail=True))
    assert _screen_app().get("/api/edr/hosts", headers=_bearer("Tenant Admin", "tenant-a")).status_code == 403


async def test_migration_017_keeps_every_screen_a_tenant_already_had(mongo_db):
    """protects=on deploy every tenant keeps all Security/Compliance screens of the features it has, and
    gains none for features it lacks; fails_when=security screens vanish for an existing tenant;
    no_claim=the runner bookkeeping."""
    import importlib
    await mongo_db.tenants.insert_many([{"id": "sec", "enabledFeatures": ["view:security"]},
                                        {"id": "none", "enabledFeatures": ["view:agents"]}])
    migration = importlib.import_module("migrations.017_screen_switches")
    await migration.up(mongo_db)
    await migration.up(mongo_db)
    features = {t["id"]: t["enabledFeatures"] async for t in mongo_db.tenants.find({}, {"_id": 0})}
    # Since 2026-10-15 Security screens are explicit (migration 022), so 017 adds none of them.
    assert not {"screen:edr", "screen:alertManagement"} & set(features["sec"])
    assert not {"screen:edr", "screen:alertManagement"} & set(features["none"])


def test_settings_screens_are_switched_one_by_one():
    """protects=each System Settings screen (they share manage:settings) has its own switch, nested
    route prefixes go to the most specific screen (API Status inside System Health, Invoices inside
    Subscription Plan), and a settings screen is on only with System Settings on; fails_when=switching
    off System Health also blocks API Status, or a settings screen survives its parent; no_claim=MongoDB."""
    assert (tf.screen_of("/api/system/routes"), tf.screen_of("/api/system/info")) == ("apiStatus", "systemHealth")
    assert (tf.screen_of("/api/payments/invoices/1"), tf.screen_of("/api/payments/plans")) == ("invoices", "subscriptionManagement")
    assert tf.screen_permissions(["manage:settings"], ["manage:settings", "screen:pam"]) == ["screen:pam"]
    assert tf.screen_permissions(["manage:settings"], ["screen:pam"]) == []
    assert "screen-off:systemHealth" in tf.hidden_screens(["manage:settings"], ["manage:settings", "screen:pam"])


async def test_migration_018_keeps_every_settings_screen(mongo_db):
    """protects=on deploy a tenant with System Settings keeps all its settings screens (on top of the
    Security/Compliance screens migration 017 gave it); fails_when=settings screens vanish; no_claim=the
    runner bookkeeping."""
    import importlib
    await mongo_db.tenants.insert_many([{"id": "s", "enabledFeatures": ["manage:settings", "view:security", "screen:edr"]},
                                        {"id": "n", "enabledFeatures": ["view:agents"]}])
    await importlib.import_module("migrations.018_settings_screen_switches").up(mongo_db)
    features = {t["id"]: set(t["enabledFeatures"]) async for t in mongo_db.tenants.find({}, {"_id": 0})}
    assert {"screen:settings", "screen:invoices"} <= features["s"]
    assert "screen:pam" not in features["s"]                                      # a Security screen: explicit
    assert not {"screen:pam", "screen:settings", "screen:invoices"} & features["n"]


async def test_migration_023_drops_the_hadr_switch_from_every_tenant(mongo_db):
    """protects=HA/DR (platform backups and restores) leaves every tenant's list on deploy and is no
    longer a tenant switch; fails_when=a tenant keeps screen:hadr or loses another entry; no_claim=the
    runner bookkeeping."""
    import importlib
    await mongo_db.tenants.insert_many([{"id": "h", "enabledFeatures": ["manage:settings", "screen:hadr", "screen:settings"]},
                                        {"id": "n", "enabledFeatures": ["view:agents"]}])
    migration = importlib.import_module("migrations.023_hadr_platform_only")
    for _ in range(2):  # running it twice changes nothing more
        await migration.up(mongo_db)
        features = {t["id"]: t["enabledFeatures"] async for t in mongo_db.tenants.find({}, {"_id": 0})}
        assert features == {"h": ["manage:settings", "screen:settings"], "n": ["view:agents"]}
    assert "screen:hadr" not in tf.SWITCHABLE and "hadr" not in tf.SCREEN_SWITCHES
