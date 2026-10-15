---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 06
subsystem: api
tags: [rbac, catalogue-manifest, patching, deployments, device-management, d-02]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: catalogue_guard / MOUNTS convention / parity helpers (76-01), full manifest (76-02)
provides:
  - backend/catalogue_mounts_devices.py (14 MOUNTS entries across 17 device routers/modules, plus SOFTWARE_UPDATES_GUARD)
  - route-level guard on the 7 user routes of software_endpoints; its agent-capable download route is untouched
  - backend/tests/test_catalogue_slice_devices.py (parity, agent/public exclusion, real-app 403/200 probes)
affects: [76-11, 76-12, 77]

requirements-completed: [ACC-04]

actuals:
  tokens: 30000
  tasks: 2
  commits: 2
plan_head_before: a225cb5554922b80eef537bccda596ce288c26bd
plan_head_after: 43e05e6df1ba219f33bb96b4e59adc02d7d0be79

tech-stack:
  added: []
  patterns:
    - "Aggregator router: guard keyed on the module router_registry loads (patch_endpoints), not the sub-modules it includes"
    - "Mixed router (software_endpoints): per-route guard imported from the slice mount file"

key-files:
  created:
    - backend/tests/test_catalogue_slice_devices.py
  modified:
    - backend/catalogue_mounts_devices.py
    - backend/software_endpoints.py

key-decisions:
  - "patch_core/enrichment/integrity/software are included through the aggregator patch_endpoints, so the mount key is (patch_endpoints, router); keying on the sub-modules would be silently inert"
  - "software_endpoints is the only slice router mixing user and agent-capable routes; guarded per route, GET /api/software/download/{filename} left alone (D-02)"
  - "repo_endpoints (/api/repo) and firmware_attestation_endpoints (/api/firmware-attestation) are in the slice by manifest prefix though the plan did not list them; mounted with their owners' guards"

coverage:
  - id: D1
    description: "parity_offenders over slice_modules('devices') is empty"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_devices.py#test_devices_slice_parity"
        status: pass
    human_judgment: false
  - id: D2
    description: "Agent, agent_capable and public routes owned by a devices catalogue carry no guard; deployment result, patch progress and software download are in the walk"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_devices.py#test_device_agent_routes_untouched"
        status: pass
    human_judgment: false
  - id: D3
    description: "Real app: nobody 403 and user (view:patching) not refused on /api/patches; MDM tracer holds; nobody 403 on software inventory, staged deployments and nine device-management reads; tenant_admin not refused"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_devices.py#test_devices_real_app_enforced"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_devices.py#test_device_management_real_app_enforced"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live check that agents still post deployment results and patch progress after deploy"
    verification: []
    human_judgment: true
    rationale: "Structural proof only (D2); nothing was deployed or restarted."

duration: 25min
completed: 2026-10-15
status: complete
---

# Phase 76 Plan 06: Devices Slice Summary

**Patching, approvals, deployments, software updates and every device-management catalogue (Autopilot, MDM, MAM, Android Enterprise, branch sites, app catalog, asset intelligence, config profiles, firmware/drivers) now carry the manifest guard; the agent result, patch-progress and software-download routes are untouched.**

## Accomplishments
- `catalogue_mounts_devices.py`: 14 MOUNTS entries (the 76-01 `mdm_endpoints` entry kept byte-for-byte), plus the shared `SOFTWARE_UPDATES_GUARD`.
- `software_endpoints.py`: 7 user routes take `dependencies=[Depends(SOFTWARE_UPDATES_GUARD)]`; the `get_current_user_or_agent` download route does not.
- `test_catalogue_slice_devices.py`: 4 tests.
- Without the guards the pre-change probe on `GET /api/patches` as a role with no permissions reached the handler (500 in the throwaway env), so the 403s in the tests come from this plan.

## slice_modules("devices") vs expected
Actual (18): android_enterprise, app_catalog, approval, autopilot, branch_site, deployment, device_config_profiles, eol_rogue, **firmware_attestation**, firmware_driver, mam, mdm, patch_core, patch_enrichment, patch_integrity, patch_software, **repo**, software.

| Difference | Handling |
|---|---|
| `firmware_attestation_endpoints` (2 routes, /api/firmware-attestation) not in the plan list | manifest gives it to firmwareDriverUpdates; mounted with the same guard as firmware_driver |
| `repo_endpoints` (4 routes, /api/repo) not in the plan list | manifest gives it to patchManagement; mounted |
| `network_endpoints` expected but not in the slice | the walk assigns no devices-catalogue user route to it; nothing to do here |
| patch_* modules are mounted through `patch_endpoints` | mount key is `(patch_endpoints, router)` |
| `deployment_result_endpoints` (POST /api/deployments/{job_id}/result, PATCH /api/patches/deployment-jobs/{job_id}/progress) | public routes, no guard, asserted by `test_device_agent_routes_untouched` |

## Task Commits
1. `505be864a` (feat): patching, approval, deployment and software routes + slice test
2. `43e05e6df` (feat): device-management routers, full-slice parity, device-management probes

## Numbers
- `test_catalogue_slice_devices.py` 4 + `test_route_auth_baseline.py` 20 + `test_catalogue_route_parity.py` 7 = 31 passed.
- Full backend suite: 3672 passed, 47 skipped, 0 failed (baseline 3668; +4 new tests) in 3m54s.

## Tests changed to fix 403s
None. No existing test failed.

## Deviations from Plan

**1. [Rule 3 - Blocking] Mount key for the patch routers**
- **Found during:** Task 1
- **Issue:** The plan implied one entry per patch_* module, but router_registry loads only the aggregator `patch_endpoints`; entries for the sub-modules never matched and the first parity run reported 19 offenders.
- **Fix:** keyed the guard on `("patch_endpoints", "router")`.
- **Commit:** 505be864a

**2. [Rule 3 - Scope] Two unlisted modules guarded**
- `repo_endpoints` and `firmware_attestation_endpoints` (table above), because the must-have is empty parity over `slice_modules("devices")`.

**Total deviations:** 2 scope/blocking adjustments. **Impact:** none beyond the extra routes enforced.

## Behaviour changes worth knowing
- Reads that were login-only now need the catalogue read permission (or its `manage:` twin): `/api/patches*` and `/api/repo` (view:patching; roles `user`, `tenant_admin`, `platform_support` hold it, `viewer` and analyst roles do not), `/api/software*` (view:software_updates), `/api/deployments*` (view:software_deployment), `/api/autopilot` (view:autopilot), `/api/mam`, `/api/android-enterprise`, `/api/branch-sites`, `/api/app-catalog`, `/api/asset-intelligence`, `/api/device-config-profiles`, `/api/firmware-drivers`, `/api/firmware-attestation`.
- Writes already carried `require_permission` / `rbac_service.has_permission`; the guard is additive (PROH-76-01).

## Manifest corrections for 76-11 (not applied)
- `softwareDeployment.write` is `["manage:settings", "view:software_deployment"]`: it lists a **view** string as a write permission, so any holder of view:software_deployment passes the catalogue guard on writes (the route-level `has_permission` checks still decide). Likely intended `manage:software_deployment`, the value `stagedDeployments` uses.
- `stagedDeployments` owns no route prefix (`/api/deployments` belongs to softwareDeployment), so its stricter write list never applies to `/api/deployments/staged*`.
- `deploymentApprovals.read` is `view:patching`, not `view:approvals`, which the `/api/approvals` routes themselves require; harmless but the two should agree.

## Phase 77 UX notes
- Roles that lose a read (for example `viewer` on patches) still see the sidebar items for these catalogues unless the UI filters by the same read permission; the Phase 77 sidebar/route gating should use the manifest.

## Known Stubs
None.

## Threat Flags
None. No new endpoints, auth paths or schema.

## Self-Check: PASSED
- Files exist: backend/catalogue_mounts_devices.py, backend/tests/test_catalogue_slice_devices.py, backend/software_endpoints.py.
- Commits 505be864a and 43e05e6df are ancestors of HEAD.
- Acceptance: parity_offenders over slice_modules("devices") empty; full suite 3672 passed, 0 failed.
