"""Devices slice (Phase 76-06): patching, deployment and device-management routes carry the manifest guard.

Agent and public device routes (deployment results, patch progress, agent-capable software
downloads) stay free of catalogue guards so agents keep reporting (D-02).
"""
from tests._catalogue_parity import SLICES, load_manifest, owner_of, parity_offenders, slice_modules
from tests._route_walk import probe_real_app, run_real_app_walk
from tests.test_route_auth_baseline import REVIEWED_UNAUTHENTICATED

TENANT = "tenant-a"


def _case(path, role, *, method="GET"):
    return {"method": method, "path": path, "role": role, "tenant_id": TENANT, "auth": "session"}


def test_devices_slice_parity():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    modules = slice_modules("devices", records, manifest)
    assert "patch_core_endpoints" in modules and "mdm_endpoints" in modules and "autopilot_endpoints" in modules
    offenders = parity_offenders(records, manifest, modules)
    assert offenders == [], "unguarded or mis-guarded devices-slice routes:\n" + "\n".join(offenders)


def test_device_agent_routes_untouched():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    devices_views = set(SLICES["devices"])
    tagged, seen_public = [], set()
    for record in records:
        owner = owner_of(record["path"], manifest)
        if owner is None or owner["view"] not in devices_views:
            continue
        reviewed_public = any((m, record["path"]) in REVIEWED_UNAUTHENTICATED for m in record["methods"])
        if record["auth"] in ("agent", "agent_capable", "public") or reviewed_public:
            seen_public.add(record["path"])
            if record["tags"]:
                tagged.append(f"{','.join(record['methods'])} {record['path']} ({record['module']}, {record['auth']})")
    assert tagged == [], "agent or public routes must not carry a catalogue guard (D-02):\n" + "\n".join(tagged)
    # The two routes the plan names, plus the agent-capable download, really are in the walk.
    assert "/api/patches/deployment-jobs/{job_id}/progress" in seen_public
    assert "/api/deployments/{job_id}/result" in seen_public
    assert "/api/software/download/{filename}" in seen_public


def test_devices_real_app_enforced():
    denied_patches, allowed_patches, denied_mdm, allowed_mdm, denied_software, denied_stage = probe_real_app([
        _case("/api/patches", "nobody"),
        _case("/api/patches", "user"),             # holds view:patching
        _case("/api/mdm/summary", "viewer"),       # 76-01 tracer still holds
        _case("/api/mdm/summary", "admin"),
        _case("/api/software/inventory", "nobody"),
        _case("/api/deployments/staged", "nobody"),
    ])
    assert denied_patches == 403, "a role without view:patching must be refused on GET /api/patches"
    assert allowed_patches != 403, "a role holding view:patching must not be refused by the catalogue guard"
    assert denied_mdm == 403
    assert allowed_mdm != 403
    assert denied_software == 403
    assert denied_stage == 403



def test_device_management_real_app_enforced():
    paths = ["/api/autopilot/summary", "/api/mam/managed-apps", "/api/android-enterprise/profiles",
             "/api/branch-sites", "/api/app-catalog/apps", "/api/asset-intelligence/eol",
             "/api/device-config-profiles", "/api/firmware-drivers/inventory",
             "/api/firmware-attestation/checks"]
    denied = probe_real_app([_case(p, "nobody") for p in paths])
    assert denied == [403] * len(paths), dict(zip(paths, denied))
    # tenant_admin holds every device-management read permission and is not refused
    allowed = probe_real_app([_case(p, "tenant_admin") for p in paths])
    assert 403 not in allowed, dict(zip(paths, allowed))
