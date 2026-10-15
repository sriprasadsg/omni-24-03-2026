"""SecOps slice (Phase 76-07): detection and response routes carry the manifest guard.

Public and agent routes of these modules (EDR event ingest, deception webhook, autonomous
response task results, agent alert ingest) stay free of catalogue guards (D-02).
"""
import catalogue_mounts_secops as secops
from catalogue_mounts import MOUNT_GUARDS
from tests._catalogue_parity import (
    SLICES, load_manifest, owner_of, parity_offenders, resolved_read, resolved_write, slice_modules,
)
from tests._route_walk import probe_real_app, run_real_app_walk
from tests.test_route_auth_baseline import REVIEWED_UNAUTHENTICATED

TENANT = "tenant-a"
PUBLIC_ROUTES = [
    ("POST", "/api/edr/events"),
    ("POST", "/api/deception/webhook/trigger/{token_id}"),
]


def _case(path, role, *, method="GET"):
    return {"method": method, "path": path, "role": role, "tenant_id": TENANT, "auth": "session"}


def test_secops_slice_parity():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    modules = slice_modules("secops", records, manifest)
    for expected in ("alert_endpoints", "siem_endpoints", "edr_telemetry_endpoints", "security_cases_endpoints"):
        assert expected in modules
    offenders = parity_offenders(records, manifest, modules)
    assert offenders == [], "unguarded or mis-guarded secops-slice routes:\n" + "\n".join(offenders)


def test_secops_guards_match_manifest():
    """Every named guard and mount entry carries exactly the manifest's resolved read/write."""
    manifest = load_manifest()
    by_view = {c["view"]: c for c in manifest["catalogues"]}
    guards = [v for k, v in secops.MOUNTS.items()]
    guards += [getattr(secops, name) for name in secops.__all__ if name.endswith("_GUARD")]
    for guard in guards:
        meta = guard.__catalogue_guard__
        entry = by_view[meta["catalogue"]]
        assert sorted(meta["read"]) == sorted(resolved_read(entry)), meta
        assert sorted(meta["write"]) == sorted(resolved_write(entry)), meta
    for key in secops.MOUNTS:
        assert MOUNT_GUARDS[key] is secops.MOUNTS[key]


def test_secops_public_routes_untouched():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    secops_views = set(SLICES["secops"])
    tagged, seen = [], set()
    for record in records:
        owner = owner_of(record["path"], manifest)
        if owner is None or owner["view"] not in secops_views:
            continue
        reviewed_public = any((m, record["path"]) in REVIEWED_UNAUTHENTICATED for m in record["methods"])
        if record["auth"] in ("agent", "agent_capable", "public") or reviewed_public:
            for method in record["methods"]:
                seen.add((method, record["path"]))
            if record["tags"]:
                tagged.append(f"{','.join(record['methods'])} {record['path']} ({record['module']}, {record['auth']})")
    assert tagged == [], "agent or public routes must not carry a catalogue guard (D-02):\n" + "\n".join(tagged)
    for route in PUBLIC_ROUTES:
        assert route in seen, f"{route} missing from the route walk"
    assert ("POST", "/api/alerts") in seen
    assert ("POST", "/api/response/tasks/{task_id}/result") in seen


def test_secops_real_app_enforced():
    nobody = ["/api/alerts", "/api/siem/events", "/api/mitre/techniques", "/api/threat-intel/stats",
              "/api/detection-rules/stats", "/api/edr/alerts", "/api/response/policies", "/api/mdr/dashboard",
              "/api/deception/summary", "/api/security-cases", "/api/xdr/automated-hunts"]
    denied = probe_real_app([_case(p, "nobody") for p in nobody])
    assert denied == [403] * len(nobody), dict(zip(nobody, denied))
    # security_analyst holds view:security; the catalogue guard must not refuse these reads
    allowed_paths = ["/api/alerts", "/api/siem/events", "/api/edr/alerts", "/api/deception/summary"]
    for role in ("security_analyst", "tenant_admin"):
        allowed = probe_real_app([_case(p, role) for p in allowed_paths])
        assert 403 not in allowed, (role, dict(zip(allowed_paths, allowed)))


def test_secops_writes_use_existing_strings():
    """A write by a role holding the route's existing guard string is not refused by the catalogue guard
    (Pitfall 2: nothing demands manage:security)."""
    statuses = probe_real_app([
        _case("/api/security-cases", "tenant_admin", method="POST"),   # investigate:security
        _case("/api/alerts/bulk", "tenant_admin", method="PATCH"),     # manage:security_cases
    ])
    assert 403 not in statuses, statuses
