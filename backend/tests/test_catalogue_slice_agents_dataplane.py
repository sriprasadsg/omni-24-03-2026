"""Agents data-plane slice (Phase 76-12): console reads are guarded, agent ingest routes are not.

Five routers put agent ingest (instructions, results, telemetry, scan uploads, tickets,
uninstall reports) next to console reads under /api/agents. Every guard here is route-level,
and a guard on the wrong route would stop agents from reporting (D-02), so this file carries
an explicit ingest-route list in addition to the generic auth-class check.
"""
import importlib

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from tests._catalogue_parity import load_manifest, parity_offenders, slice_modules
from tests._route_walk import probe_real_app, run_real_app_walk

TENANT = "tenant-a"

DATA_PLANE_MODULES = frozenset({
    "agent_tasks_endpoints", "agent_security_endpoints", "agent_telemetry_endpoints",
    "agentic_tasks_endpoints", "agent_uninstall_endpoints",
})

# (method, mounted path) of every route an agent calls, with the auth class the route walk
# derives from its dependency tree: "agent" (verify_agent_key) or "agent_capable"
# (get_current_user_or_agent). None may carry a catalogue guard or exemption, and these are
# the only agent routes of the five modules (76 WR-06: walked, not counted in the source).
AGENT_INGEST_ROUTES = {
    ("GET", "/api/agents/{hostname}/instructions"): "agent",
    ("POST", "/api/agents/{hostname}/instructions/result"): "agent",
    ("POST", "/api/agents/{agent_id}/ticket"): "agent",
    ("POST", "/api/agents/{agent_id}/discovery/results"): "agent",
    ("POST", "/api/agents/{agent_id}/raise-ticket"): "agent_capable",
    ("POST", "/api/agents/{agent_id}/telemetry"): "agent",
    ("POST", "/api/agents/{agent_id}/logs/raw"): "agent",
    ("POST", "/api/agents/{agent_id}/fim-events"): "agent",
    ("POST", "/api/agents/{agent_id}/shadow-ai-scan"): "agent",
    ("POST", "/api/agents/{agent_id}/vulnerability-scan"): "agent",
    ("POST", "/api/agents/{agent_id}/malware-scan"): "agent",
    ("POST", "/api/agents/{agent_id}/persistence-findings"): "agent",
    ("GET", "/api/agents/{agent_id}/agentic-tasks"): "agent",
    ("POST", "/api/agents/{agent_id}/agentic-tasks/{task_id}/result"): "agent",
    ("POST", "/api/agents/{agent_id}/uninstall-report"): "agent_capable",
}


def _case(path, role, *, method="GET"):
    return {"method": method, "path": path, "role": role, "tenant_id": TENANT, "auth": "session"}


def test_dataplane_parity():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    assert DATA_PLANE_MODULES <= set(slice_modules("agents", records, manifest))
    offenders = parity_offenders(records, manifest, DATA_PLANE_MODULES)
    assert offenders == [], "unguarded or mis-guarded data-plane routes:\n" + "\n".join(offenders)


def test_dataplane_agent_routes_untouched():
    records = run_real_app_walk()["routes"]
    tagged = []
    seen = set()
    for record in records:
        if record["module"] not in DATA_PLANE_MODULES:
            continue
        for method in record["methods"]:
            seen.add((method, record["path"]))
        if record["auth"] in ("agent", "agent_capable") and (record["tags"] or record["exempt"]):
            tagged.append(f"{','.join(record['methods'])} {record['path']} ({record['module']})")
    assert tagged == [], "agent routes must not carry a catalogue guard or exemption (D-02):\n" + "\n".join(tagged)
    missing = sorted(set(AGENT_INGEST_ROUTES) - seen)
    assert missing == [], f"agent ingest routes missing from the walk (renamed?): {missing}"
    ingest_tagged = [
        f"{','.join(r['methods'])} {r['path']}" for r in records
        if r["module"] in DATA_PLANE_MODULES
        and any((m, r["path"]) in AGENT_INGEST_ROUTES for m in r["methods"])
        and (r["tags"] or r["exempt"] or r["auth"] not in ("agent", "agent_capable"))
    ]
    assert ingest_tagged == [], f"ingest routes changed auth class or gained a guard: {ingest_tagged}"


def test_dataplane_agent_auth_unchanged():
    """The walk sees exactly the ingest routes as agent routes, each with its auth class, so a
    guard change can neither drop an agent's auth nor add an agent route (76 WR-06)."""
    records = run_real_app_walk()["routes"]
    walked = {(method, r["path"]): r["auth"] for r in records if r["module"] in DATA_PLANE_MODULES
              and r["auth"] in ("agent", "agent_capable") for method in r["methods"]}
    assert walked == AGENT_INGEST_ROUTES


# (name, module, router path, mounted path) of guarded console reads.
CONSOLE_READS = (
    ("instruction history", "agent_tasks_endpoints", "/{agent_id}/instructions/history",
     "/api/agents/agent-1/instructions/history"),
    ("task status", "agent_tasks_endpoints", "/tasks/{task_id}", "/api/agents/tasks/task-1"),
    ("telemetry", "agent_telemetry_endpoints", "/{agent_id}/telemetry", "/api/agents/agent-1/telemetry"),
    ("vulnerability scans", "agent_security_endpoints", "/{agent_id}/vulnerability-scans",
     "/api/agents/agent-1/vulnerability-scans"),
    ("agentic-task decisions", "agentic_tasks_endpoints", "/{agent_id}/agentic-tasks/decisions",
     "/api/agents/agent-1/agentic-tasks/decisions"),
)


def test_dataplane_real_app_enforced():
    cases = []
    for *_route, path in CONSOLE_READS:
        cases.append(_case(path, "viewer"))    # view:dashboard only
        cases.append(_case(path, "analyst"))   # holds view:agents
    statuses = probe_real_app(cases)
    for index, (name, *_rest) in enumerate(CONSOLE_READS):
        viewer, analyst = statuses[2 * index], statuses[2 * index + 1]
        assert viewer == 403, f"a role without view:agents must be refused on {name}"
        # No database in the probe: a handler may fail (500) after the guard, a refusal never may.
        assert analyst not in (401, 403), f"a role holding view:agents must not be refused on {name}"
    # This handler needs no database, so the permitted role is answered outright.
    assert statuses[-1] == 200


def _route_dependencies(module_name, method, path):
    router = importlib.import_module(module_name).router
    route = next(r for r in router.routes if isinstance(r, APIRoute)
                 and r.path == router.prefix + path and method in r.methods)
    assert route.dependencies, f"{module_name} {method} {path} carries no route-level guard"
    return route.dependencies


def test_dataplane_guards_reach_the_handler(monkeypatch):
    """76 WR-06: each console read's own route-level guard admits a view:agents role all the way
    to a handler that answers 200, and refuses a role without it with exactly 403."""
    import rbac_defaults
    import rbac_utils
    from auth_types import TokenData
    from authentication_service import get_current_user

    async def _defaults_only(db, role, tenant_id):
        return list(rbac_defaults.defaults_for(rbac_utils._rbac_service._normalize_role(role or "")))

    monkeypatch.setattr(rbac_utils, "granted_permissions", _defaults_only)
    monkeypatch.setattr(rbac_utils, "get_database", lambda: None)
    for name, module_name, router_path, _mounted in CONSOLE_READS:
        router = APIRouter()
        router.add_api_route("/probe", lambda: {"ok": True}, methods=["GET"],
                             dependencies=_route_dependencies(module_name, "GET", router_path))
        for role, expected in (("analyst", 200), ("tenant_admin", 200), ("viewer", 403)):
            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[get_current_user] = lambda role=role: TokenData(
                username="u@example.com", role=role, tenant_id=TENANT, auth_source="session")
            status = TestClient(app, raise_server_exceptions=False).get("/probe").status_code
            assert status == expected, (name, role, status)
