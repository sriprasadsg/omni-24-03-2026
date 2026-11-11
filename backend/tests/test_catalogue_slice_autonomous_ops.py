"""Autonomous Ops catalogue slice (Phase 81, plan 81-09): the tenant router is mounted through
catalogue_mounts_autonomous_ops with the manifest's autonomousOps read and write strings.

The automation group is not an enforced catalogue group, so the shared slice partition does not
list this module; this file checks the same parity directly for the routes of this module.

Value: protects=the Autonomous Ops routes carry exactly the manifest's permissions and the guard
authenticates through get_current_user_or_api_key; fails_when=the guard drifts from the manifest, a
route is mounted unguarded, or a router disappears from the app;
no_claim=the per-role behaviour of each route (test_autonomous_ops_endpoints).
"""
import catalogue_mounts_autonomous_ops as autonomous_ops
from catalogue_mounts import MOUNT_GUARDS
from tests._catalogue_parity import load_manifest, owner_of, resolved_read, resolved_write
from tests._route_walk import run_real_app_walk


def _entry():
    manifest = load_manifest()
    return next(c for c in manifest["catalogues"] if c["view"] == "autonomousOps")


def test_guard_matches_manifest_and_is_the_mount():
    entry = _entry()
    meta = autonomous_ops.AUTONOMOUS_OPS_GUARD.__catalogue_guard__
    assert meta["catalogue"] == "autonomousOps"
    assert sorted(meta["read"]) == sorted(resolved_read(entry)) == ["view:autonomous_ops"]
    assert sorted(meta["write"]) == sorted(resolved_write(entry))
    assert MOUNT_GUARDS[("autonomous_ops_endpoints", "router")] is autonomous_ops.AUTONOMOUS_OPS_GUARD
    assert MOUNT_GUARDS[("autonomous_ops_response_endpoints", "router")] is autonomous_ops.AUTONOMOUS_OPS_GUARD
    assert MOUNT_GUARDS[("autonomous_ops_service_desk_endpoints", "router")] is autonomous_ops.AUTONOMOUS_OPS_GUARD
    assert MOUNT_GUARDS[("autonomous_ops_reporting_endpoints", "router")] is autonomous_ops.AUTONOMOUS_OPS_GUARD
    assert autonomous_ops.MOUNTS == {("autonomous_ops_endpoints", "router"): autonomous_ops.AUTONOMOUS_OPS_GUARD,
                                     ("autonomous_ops_response_endpoints", "router"): autonomous_ops.AUTONOMOUS_OPS_GUARD,
                                     ("autonomous_ops_service_desk_endpoints", "router"): autonomous_ops.AUTONOMOUS_OPS_GUARD,
                                     ("autonomous_ops_reporting_endpoints", "router"): autonomous_ops.AUTONOMOUS_OPS_GUARD}


def test_every_tenant_route_carries_the_manifest_guard():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    entry = _entry()
    mine = [r for r in records if r["module"] in ("autonomous_ops_endpoints", "autonomous_ops_response_endpoints",
                                                  "autonomous_ops_service_desk_endpoints",
                                                  "autonomous_ops_reporting_endpoints")]
    assert {"/api/autonomous-ops/status", "/api/autonomous-ops/actions",
            "/api/autonomous-ops/response-settings", "/api/autonomous-ops/service-desk",
            "/api/autonomous-ops/service-desk/restore", "/api/autonomous-ops/statistics"} <= {r["path"] for r in mine}
    offenders = []
    for record in mine:
        assert owner_of(record["path"], manifest)["view"] == "autonomousOps"
        assert record["auth"] == "user", record
        matched = any(t["catalogue"] == "autonomousOps"
                      and sorted(t["read"]) == sorted(resolved_read(entry))
                      and sorted(t["write"]) == sorted(resolved_write(entry)) for t in record["tags"])
        if not matched:
            offenders.append(f"{record['methods']} {record['path']}")
    assert offenders == [], offenders


def test_tenant_router_is_required():
    import router_registry
    assert "autonomous_ops_endpoints" in router_registry._REQUIRED_ROUTERS


def test_response_settings_routers_are_required():
    import router_registry
    assert "autonomous_ops_response_endpoints" in router_registry._REQUIRED_ROUTERS
    assert "autonomous_ops_response_platform_endpoints" in router_registry._REQUIRED_ROUTERS


def test_service_desk_settings_router_is_required_and_its_routes_are_all_guarded():
    import router_registry
    assert "autonomous_ops_service_desk_endpoints" in router_registry._REQUIRED_ROUTERS
    records = [r for r in run_real_app_walk()["routes"] if r["module"] == "autonomous_ops_service_desk_endpoints"]
    assert {(m, r["path"]) for r in records for m in r["methods"]} == {
        ("GET", "/api/autonomous-ops/service-desk"), ("PUT", "/api/autonomous-ops/service-desk"),
        ("POST", "/api/autonomous-ops/service-desk/restore")}
    for record in records:
        assert any(t["catalogue"] == "autonomousOps" for t in record["tags"]), record


def test_platform_router_is_mounted_required_and_permission_checked():
    import router_registry
    assert "autonomous_ops_platform_endpoints" in router_registry._REQUIRED_ROUTERS
    records = run_real_app_walk()["routes"]
    platform = [r for r in records if r["path"].startswith("/api/platform/autonomous-ops")]
    assert {(m, r["path"]) for r in platform for m in r["methods"]} >= {
        ("GET", "/api/platform/autonomous-ops/status"), ("GET", "/api/platform/autonomous-ops/actions"),
        ("POST", "/api/platform/autonomous-ops/stop"), ("POST", "/api/platform/autonomous-ops/resume"),
        ("PUT", "/api/platform/autonomous-ops/tenants/{tenant_id}/max-level"),
        ("PUT", "/api/platform/autonomous-ops/tenants/{tenant_id}/shadow"),
        ("GET", "/api/platform/autonomous-ops/retention/review"),
        ("POST", "/api/platform/autonomous-ops/retention/confirm"),
        ("GET", "/api/platform/autonomous-ops/response-settings"),
        ("PUT", "/api/platform/autonomous-ops/response-settings/bulk")}
    for record in platform:
        assert record["auth"] == "user", record
        assert record["known_guard"], record      # a _require_* dependency on every platform route
        assert record["module"] in ("autonomous_ops_platform_endpoints", "autonomous_ops_retention_endpoints",
                                    "autonomous_ops_response_platform_endpoints")
