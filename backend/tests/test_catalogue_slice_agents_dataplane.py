"""Agents data-plane slice (Phase 76-12): console reads are guarded, agent ingest routes are not.

Five routers put agent ingest (instructions, results, telemetry, scan uploads, tickets,
uninstall reports) next to console reads under /api/agents. Every guard here is route-level,
and a guard on the wrong route would stop agents from reporting (D-02), so this file carries
an explicit ingest-route list in addition to the generic auth-class check.
"""
import os

from tests._catalogue_parity import load_manifest, parity_offenders, slice_modules
from tests._route_walk import probe_real_app, run_real_app_walk

TENANT = "tenant-a"
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DATA_PLANE_MODULES = frozenset({
    "agent_tasks_endpoints", "agent_security_endpoints", "agent_telemetry_endpoints",
    "agentic_tasks_endpoints", "agent_uninstall_endpoints",
})

# (method, mounted path) of every route an agent calls with verify_agent_key or
# get_current_user_or_agent; none may carry a catalogue guard or exemption.
AGENT_INGEST_ROUTES = frozenset({
    ("GET", "/api/agents/{hostname}/instructions"),
    ("POST", "/api/agents/{hostname}/instructions/result"),
    ("POST", "/api/agents/{agent_id}/ticket"),
    ("POST", "/api/agents/{agent_id}/discovery/results"),
    ("POST", "/api/agents/{agent_id}/raise-ticket"),
    ("POST", "/api/agents/{agent_id}/telemetry"),
    ("POST", "/api/agents/{agent_id}/logs/raw"),
    ("POST", "/api/agents/{agent_id}/fim-events"),
    ("POST", "/api/agents/{agent_id}/shadow-ai-scan"),
    ("POST", "/api/agents/{agent_id}/vulnerability-scan"),
    ("POST", "/api/agents/{agent_id}/malware-scan"),
    ("POST", "/api/agents/{agent_id}/persistence-findings"),
    ("GET", "/api/agents/{agent_id}/agentic-tasks"),
    ("POST", "/api/agents/{agent_id}/agentic-tasks/{task_id}/result"),
    ("POST", "/api/agents/{agent_id}/uninstall-report"),
})

# Occurrences of each agent-auth dependency per module (measured 2026-10-13); a guard
# change must neither remove nor add one.
AGENT_AUTH_BASELINE = {
    "agent_tasks_endpoints": {"Depends(verify_agent_key)": 4, "Depends(get_current_user_or_agent)": 1},
    "agent_security_endpoints": {"Depends(verify_agent_key)": 5, "Depends(get_current_user_or_agent)": 0},
    "agent_telemetry_endpoints": {"Depends(verify_agent_key)": 2, "Depends(get_current_user_or_agent)": 0},
    "agentic_tasks_endpoints": {"Depends(verify_agent_key)": 2, "Depends(get_current_user_or_agent)": 0},
    "agent_uninstall_endpoints": {"Depends(verify_agent_key)": 0, "Depends(get_current_user_or_agent)": 1},
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
    missing = sorted(AGENT_INGEST_ROUTES - seen)
    assert missing == [], f"agent ingest routes missing from the walk (renamed?): {missing}"
    ingest_tagged = [
        f"{','.join(r['methods'])} {r['path']}" for r in records
        if r["module"] in DATA_PLANE_MODULES
        and any((m, r["path"]) in AGENT_INGEST_ROUTES for m in r["methods"])
        and (r["tags"] or r["exempt"] or r["auth"] not in ("agent", "agent_capable"))
    ]
    assert ingest_tagged == [], f"ingest routes changed auth class or gained a guard: {ingest_tagged}"


def test_dataplane_real_app_enforced():
    paths = (
        ("instruction history", "/api/agents/agent-1/instructions/history"),
        ("task status", "/api/agents/tasks/task-1"),
        ("telemetry", "/api/agents/agent-1/telemetry"),
        ("vulnerability scans", "/api/agents/agent-1/vulnerability-scans"),
        ("agentic-task decisions", "/api/agents/agent-1/agentic-tasks/decisions"),
    )
    cases = []
    for _name, path in paths:
        cases.append(_case(path, "viewer"))    # view:dashboard only
        cases.append(_case(path, "analyst"))   # holds view:agents
    statuses = probe_real_app(cases)
    for index, (name, _path) in enumerate(paths):
        viewer, analyst = statuses[2 * index], statuses[2 * index + 1]
        assert viewer == 403, f"a role without view:agents must be refused on {name}"
        assert analyst != 403, f"a role holding view:agents must not be refused on {name}"


def test_dataplane_agent_auth_unchanged():
    for module, expected in AGENT_AUTH_BASELINE.items():
        with open(os.path.join(BACKEND_DIR, module + ".py"), encoding="utf-8") as handle:
            source = handle.read()
        for needle, count in expected.items():
            assert source.count(needle) == count, (
                f"{module}: {needle} occurs {source.count(needle)} times, baseline {count} "
                "(agent auth must not change in the catalogue slice, D-02)"
            )
