"""A sidebar screen a tenant admin can be given must be usable by them (2026-10-20).

HA/DR & Backups was offered to tenant admins while every one of its routes required view:backups,
which no tenant role holds, so the screen only ever showed 403s; ten more screens (APM, Container
Scanning, Model Monitoring, AutoML, A/B Testing, XAI, playbook analytics, FinOps pricing, secret
reveal ...) checked permissions that no role carries. Walks the real app in a child interpreter
(tests/_route_walk) and reads each GET route's own permission checks.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._route_walk import _run_child

# Routes under a tenant screen's prefix that serve the platform itself, not the tenant.
PLATFORM_ONLY = {
    "/api/ai/own-model/status": "the platform's own model (LLMOps screen has no tenant use for it)",
}

_SCAN = r"""
import json, logging, sys
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + "/tests")
logging.disable(logging.CRITICAL)
from fastapi import FastAPI
from fastapi.routing import APIRoute
from router_registry import register_all_routers
from _route_walk import _walk_routes
import permission_vocabulary, rbac_defaults

app = FastAPI(); register_all_routers(app)
manifest = json.load(open(sys.argv[1] + "/../shared/catalogue-access.json"))
owners = sorted(((r, c) for c in manifest["catalogues"] for r in c["routes"]), key=lambda rc: -len(rc[0]))
admin = set(rbac_defaults.deliverable_closure(rbac_defaults.ROLE_DEFAULTS["tenant_admin"],
                                              permission_vocabulary.KNOWN_PERMISSIONS))

def perms_of(call):
    found = []
    for cell in getattr(call, "__closure__", None) or ():
        v = cell.cell_contents
        if isinstance(v, str) and ":" in v and " " not in v:
            found.append(v)
    return found

def deps(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from deps(d)

bad = []
for path, route, _ in _walk_routes(app.routes):
    if not isinstance(route, APIRoute) or "GET" not in route.methods:
        continue
    owner = next((c for p, c in owners if path == p or path.startswith(p + "/")), None)
    if not owner or not owner.get("nav") or owner["permission"] not in admin:
        continue
    for call in deps(route.dependant):
        if getattr(call, "__catalogue_guard__", None):
            continue
        needed = perms_of(call)
        if needed and not any(p in admin for p in needed):
            bad.append([owner["view"], path, needed])
print(json.dumps({"bad": bad, "admin_has": sorted(admin)}))
"""


def test_every_get_route_of_a_tenant_screen_accepts_a_tenant_admin():
    backend = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    result = json.loads(_run_child(_SCAN, [backend]))
    unusable = [row for row in result["bad"] if row[1] not in PLATFORM_ONLY]
    assert unusable == [], "screens a tenant admin is shown but cannot load:\n" + "\n".join(map(str, unusable))
    assert {"manage:mlops", "manage:automl", "manage:tracing"} <= set(result["admin_has"])


def test_hadr_is_a_platform_screen():
    import rbac_defaults
    manifest = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "shared", "catalogue-access.json")))
    hadr = next(c for c in manifest["catalogues"] if c["view"] == "hadr")
    assert hadr["permission"] == "view:backups" and hadr["write"] == ["manage:backups"]
    assert {"view:backups", "manage:backups"} <= rbac_defaults.SUPER_ADMIN_ONLY_PERMISSIONS
    assert not any("backups" in p for key, perms in rbac_defaults.ROLE_DEFAULTS.items() for p in perms)
