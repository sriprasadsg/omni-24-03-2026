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
    assert autonomous_ops.MOUNTS == {("autonomous_ops_endpoints", "router"): autonomous_ops.AUTONOMOUS_OPS_GUARD}


def test_every_tenant_route_carries_the_manifest_guard():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    entry = _entry()
    mine = [r for r in records if r["module"] == "autonomous_ops_endpoints"]
    assert {"/api/autonomous-ops/status", "/api/autonomous-ops/actions"} <= {r["path"] for r in mine}
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
