"""Agents slice (Phase 76-05): agent console routes carry the manifest guard, agent traffic does not.

slice_modules("agents") is split by module name: the data-plane routers that host the
agent ingest routes belong to 76-12, route_aliases to the 76-11 alias sweep. Everything
else in the slice is checked for parity here. The exclusion test covers the whole slice,
76-12's modules included: agent-key, agent-capable and reviewed public routes must stay
free of catalogue guards so enrollment, heartbeat and downloads keep their auth (D-02).
"""
from tests._catalogue_parity import SLICES, load_manifest, owner_of, parity_offenders, slice_modules
from tests._route_walk import probe_real_app, run_real_app_walk
from tests.test_route_auth_baseline import REVIEWED_UNAUTHENTICATED

TENANT = "tenant-a"

# Guarded by 76-12 (same wave): they host the verify_agent_key ingest routes.
DATA_PLANE_MODULES = frozenset({
    "agent_security_endpoints", "agent_tasks_endpoints", "agent_telemetry_endpoints",
    "agentic_tasks_endpoints", "agent_uninstall_endpoints",
})
# route_aliases straddles six catalogues; 76-11 gives each alias its canonical path's guard.
LEFTOVER_MODULES = frozenset({"route_aliases"})


def _case(path, role, *, method="GET"):
    return {"method": method, "path": path, "role": role, "tenant_id": TENANT, "auth": "session"}


def test_agents_slice_parity():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    modules = set(slice_modules("agents", records, manifest))
    assert {"agent_core_endpoints", "support_endpoints", "platform_endpoints"} <= modules
    offenders = parity_offenders(records, manifest, modules - DATA_PLANE_MODULES - LEFTOVER_MODULES)
    assert offenders == [], "unguarded or mis-guarded agents-slice routes:\n" + "\n".join(offenders)


def test_agent_routes_untouched():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    agents_views = set(SLICES["agents"])
    tagged = []
    for record in records:
        owner = owner_of(record["path"], manifest)
        if owner is None or owner["view"] not in agents_views:
            continue
        reviewed_public = any((m, record["path"]) in REVIEWED_UNAUTHENTICATED for m in record["methods"])
        if (record["auth"] in ("agent", "agent_capable", "public") or reviewed_public) and record["tags"]:
            tagged.append(f"{','.join(record['methods'])} {record['path']} ({record['module']}, {record['auth']})")
    assert tagged == [], "agent or public routes must not carry a catalogue guard (D-02):\n" + "\n".join(tagged)


def test_agents_real_app_enforced():
    (viewer_agents, analyst_agents, admin_jobs, super_jobs, viewer_remote,
     viewer_support, viewer_unread, nobody_version) = probe_real_app([
        _case("/api/agents", "viewer"),            # view:dashboard only
        _case("/api/agents", "analyst"),           # holds view:agents
        _case("/api/jobs", "tenant_admin"),        # view:jobs is super-admin only (D-11)
        _case("/api/jobs", "super_admin"),
        _case("/api/remote/sessions", "viewer"),
        _case("/api/support/conversations", "viewer"),
        _case("/api/support/unread-count", "viewer"),
        _case("/api/agents/version", "nobody"),    # reviewed public route
    ])
    assert viewer_agents == 403, "a role without view:agents must be refused on GET /api/agents"
    assert analyst_agents != 403, "a role holding view:agents must not be refused by the catalogue guard"
    assert admin_jobs == 403, "jobs reads stay super-admin only"
    assert super_jobs != 403
    assert viewer_remote == 403
    assert viewer_support != 403, "support chat is self-service for every signed-in user"
    assert viewer_unread != 403
    assert nobody_version != 403, "public agent routes carry no guard"
