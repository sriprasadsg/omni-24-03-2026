"""Devices slice (Phase 76-06): patching, deployment and device-management routers.

``MOUNTS`` guards every router whose user routes all belong to one catalogue. The named
guard ``SOFTWARE_UPDATES_GUARD`` is also imported by ``software_endpoints``, whose router
serves an agent-capable download route (D-02) and so carries the guard per route instead.

Permission strings mirror ``shared/catalogue-access.json``; ``test_catalogue_slice_devices``
fails when the two drift. ``deployment_result_endpoints`` (agent result and patch progress,
public routes) is deliberately absent.
"""
from catalogue_guards import catalogue_guard

SOFTWARE_UPDATES_GUARD = catalogue_guard(
    "softwareUpdates",
    read=("view:software_updates",),
    write=("manage:patches",),
)

PATCH_GUARD = catalogue_guard(
    "patchManagement",
    read=("view:patching",),
    write=("manage:patches",),
)

MOUNTS = {
    # Patching (patchManagement): patch_endpoints aggregates patch_core, patch_enrichment,
    # patch_integrity and patch_software (all /api/patches); repo_endpoints is /api/repo.
    ("patch_endpoints", "router"): PATCH_GUARD,
    ("repo_endpoints", "router"): PATCH_GUARD,
    # Approvals (deploymentApprovals).
    ("approval_endpoints", "router"): catalogue_guard(
        "deploymentApprovals",
        read=("view:patching",),
        write=("manage:approvals",),
    ),
    # Staged deployments and approvals under /api/deployments (softwareDeployment).
    ("deployment_endpoints", "router"): catalogue_guard(
        "softwareDeployment",
        read=("view:software_deployment",),
        write=("manage:settings", "view:software_deployment"),
    ),
    # software_endpoints is guarded per route with SOFTWARE_UPDATES_GUARD (agent-capable download).
    # Device management.
    ("mdm_endpoints", "router"): catalogue_guard(
        "mobileDeviceManagement",
        read=("view:mdm",),
        write=("manage:assets",),
    ),
}
