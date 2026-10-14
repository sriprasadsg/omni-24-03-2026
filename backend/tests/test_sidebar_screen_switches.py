"""Spec C6: every sidebar item a tenant role reaches can be switched on or off on its own.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. In-memory fakes stand in for the tenants collection
unless a test takes the mongo_db fixture.
"""
import collections
import json
import os
import sys
from types import SimpleNamespace

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rbac_defaults
import tenant_features as tf
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.real_tenant_features

MANIFEST = json.load(open(tf._MANIFEST_PATH))
NAV = [c for c in MANIFEST["catalogues"] if c.get("nav")]
TENANT_PERMS = {p for key, perms in rbac_defaults.ROLE_DEFAULTS.items()
                if key not in rbac_defaults.PLATFORM_ROLE_KEYS and key != rbac_defaults.SUPER_ADMIN_KEY for p in perms}


class _Tenants:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, query, projection=None):
        return next((dict(d) for d in self.docs if d["id"] == query.get("id")), None)


def _db(features):
    raw = SimpleNamespace(tenants=_Tenants([{"id": "tenant-a", "enabledFeatures": features}]))
    return SimpleNamespace(_db=raw, tenants=raw.tenants)


def test_every_sidebar_item_a_tenant_role_reaches_has_its_own_switch():
    """protects=the Super Admin can switch each tenant-reachable sidebar item alone: by its permission's
    switch when no other item shares the permission, else by a screen switch; fails_when=a sidebar item
    can only be switched together with others, or has no switch at all; no_claim=the Manage Tenant screen."""
    sharing = collections.Counter(c["permission"] for c in NAV)
    unswitchable = [c["view"] for c in NAV if c["permission"] in TENANT_PERMS
                    and f"screen:{c['view']}" not in tf.SWITCHABLE
                    and not (c["permission"] in tf.SWITCHABLE and sharing[c["permission"]] == 1)]
    assert unswitchable == []
    # Platform administration never reaches a tenant, so it is never offered.
    assert not {"screen:tenantManagement", "screen:servicePricing", "screen:bundleManagement"} & tf.SWITCHABLE


def test_a_screen_needs_its_manifest_permission_and_its_parent():
    """protects=Chat needs manage:agents and View Agents on; Overview (no parent) hangs only on its own
    switch; a switched-off screen is marked for the UI only when the user would otherwise reach it;
    fails_when=Chat survives View Agents off, or Overview is marked for a user without view:dashboard;
    no_claim=MongoDB."""
    assert tf.SCREEN_SWITCHES["chat"] == "manage:agents" and tf.SWITCH_PARENTS["screen:chat"] == "view:agents"
    assert tf.screen_permissions(["manage:agents"], ["view:agents", "screen:chat"]) == ["screen:chat"]
    assert tf.screen_permissions(["manage:agents"], ["screen:chat"]) == []
    assert tf.SWITCH_PARENTS["screen:dashboard"] is None
    assert "screen-off:dashboard" in tf.hidden_screens(["view:dashboard"], [])
    assert "screen-off:dashboard" not in tf.hidden_screens(["view:dashboard"], ["screen:dashboard"])
    assert "screen-off:dashboard" not in tf.hidden_screens(["view:agents"], [])


def _app():
    from tenant_middleware import ScreenSwitchMiddleware, TenantMiddleware
    app = FastAPI()
    app.add_middleware(ScreenSwitchMiddleware)
    app.add_middleware(TenantMiddleware)
    for path in ("/api/tickets", "/api/agents", "/api/agents/approvals"):
        app.add_api_route(path, lambda: {}, methods=["GET"])
    return TestClient(app)


def _bearer(role):
    import authentication_service as auth
    claims = {"sub": "u@x", "role": role, "tenant_id": "tenant-a"}
    return {"Authorization": f"Bearer {jwt.encode(claims, auth.SECRET_KEY, algorithm=auth.ALGORITHM)}"}


@pytest.mark.parametrize("features,role,path,expected", [
    (["view:dashboard"], "Tenant Admin", "/api/tickets", 403),            # Tickets off
    (["screen:internalTickets"], "Tenant Admin", "/api/tickets", 200),    # Tickets on
    (["view:agents"], "Tenant Admin", "/api/agents", 200),                # Agents off, but hide-only
    (["view:agents"], "Tenant Admin", "/api/agents/approvals", 403),      # Agent Approvals off
    (["view:dashboard"], "agent", "/api/tickets", 200),                   # agents answer to capabilities
])
def test_a_switched_off_sidebar_screen_refuses_its_routes(monkeypatch, features, role, path, expected):
    """protects=a switched-off screen's own routes refuse tenant users, the fleet API (Agents is hide-only)
    keeps serving every other screen, and an endpoint agent's token is never refused by a screen switch;
    fails_when=Tickets' API answers with Tickets off, Remote Access loses the agent list because the Agents
    screen is off, or an agent's ticket report is refused; no_claim=API-key callers."""
    import database
    monkeypatch.setattr(database, "get_database", lambda: _db(features))
    assert _app().get(path, headers=_bearer(role)).status_code == expected


def test_new_tenants_start_with_every_screen_they_can_reach():
    """protects=a new tenant gets every parentless screen and every screen of the features it starts with;
    fails_when=a new tenant starts without Overview or Tickets; no_claim=the signup handlers themselves."""
    start = set(tf.with_all_screens(["view:reporting"]))
    assert {"screen:dashboard", "screen:internalTickets", "screen:reporting", "screen:executiveSummary"} <= start
    assert "screen:chat" not in start


async def test_migration_019_adds_only_the_new_screens(mongo_db):
    """protects=on deploy a tenant keeps every newly switchable item it reaches, gains none for a feature
    it lacks, and a Security screen switched off earlier stays off; fails_when=Overview vanishes on deploy
    or the migration re-enables EDR; no_claim=the runner bookkeeping."""
    import importlib
    await mongo_db.tenants.insert_one({"id": "t", "enabledFeatures": ["view:security", "view:agents", "screen:siem"]})
    migration = importlib.import_module("migrations.019_all_sidebar_screen_switches")
    await migration.up(mongo_db)
    await migration.up(mongo_db)
    features = (await mongo_db.tenants.find_one({"id": "t"}))["enabledFeatures"]
    assert {"screen:dashboard", "screen:internalTickets", "screen:agents", "screen:chat"} <= set(features)
    assert "screen:edr" not in features and "screen:reporting" not in features
    assert len(features) == len(set(features))


async def test_sast_is_a_devsecops_screen(mongo_db):
    """protects=the SAST item needs view:devsecops, the permission every SAST route checks, and sits
    under DevSecOps; migration 021 switches SAST on for tenants with DevSecOps and nobody else;
    fails_when=a tenant with Security on and DevSecOps off sees SAST again (every request 403s) or a
    DevSecOps tenant loses SAST on deploy; no_claim=the SAST handlers themselves."""
    import importlib
    assert tf.SCREEN_SWITCHES["sast"] == "view:devsecops" and tf.SWITCH_PARENTS["screen:sast"] == "view:devsecops"
    assert tf.screen_permissions(["view:devsecops"], ["view:security", "screen:sast"]) == []
    await mongo_db.tenants.insert_many([{"id": "dev", "enabledFeatures": ["view:devsecops"]},
                                        {"id": "sec", "enabledFeatures": ["view:security", "screen:sast"]}])
    migration = importlib.import_module("migrations.021_sast_screen_under_devsecops")
    await migration.up(mongo_db)
    await migration.up(mongo_db)
    features = {t["id"]: t["enabledFeatures"] async for t in mongo_db.tenants.find({}, {"_id": 0})}
    assert features == {"dev": ["view:devsecops", "screen:sast"], "sec": ["view:security", "screen:sast"]}
