---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 01
subsystem: api
tags: [fastapi, rbac, catalogue-manifest, route-guard, pytest, vitest]

requires:
  - phase: 75-permission-resolver-single-source-of-truth
    provides: rbac_defaults table, verify_permission, effective_permissions, _scopes_allow
provides:
  - shared/catalogue-access.json manifest seed (8 groups, mobileDeviceManagement)
  - catalogue_guard / check_catalogue_access / catalogue_exempt / manage_twin
  - MOUNT_GUARDS registry with per-slice catalogue_mounts_*.py files and the router_registry._load hook
  - backend/tests/_route_walk.py (shared walker, real-app walk, real-app probe)
  - backend/tests/_catalogue_parity.py (owner_of, parity_offenders, SLICES, slice_modules)
  - utils/catalogueAccess.ts typed frontend reader
affects: [76-02, 76-03, 76-04, 76-05, 76-06, 76-07, 76-08, 76-09, 76-10, 76-11, 76-12]

actuals:
  tokens: 12000
  tasks: 3
  commits: 3
plan_head_before: b3cde98c518a4681247d34c3172c0256e3f2b21a
plan_head_after: 8447e4c26518a11ab408bd5d6ce3bb3ea7254070

tech-stack:
  added: []
  patterns:
    - "Mount-time guard: catalogue_mounts_*.py MOUNTS dict -> router_registry._load adds Depends(guard) to include_router"
    - "Guard tag attribute __catalogue_guard__ read by the route walker, matched to the manifest by the parity helper"
    - "Real-app tests run in a fresh interpreter with an unroutable Mongo URL and a throwaway DB name"

key-files:
  created:
    - shared/catalogue-access.json
    - backend/catalogue_guards.py
    - backend/catalogue_mounts.py
    - backend/catalogue_mounts_devices.py
    - backend/tests/test_catalogue_guards.py
    - backend/tests/_route_walk.py
    - backend/tests/_catalogue_parity.py
    - backend/tests/test_catalogue_route_parity.py
    - utils/catalogueAccess.ts
    - src/__tests__/catalogueAccess.test.ts
  modified:
    - backend/router_registry.py
    - backend/tests/test_route_auth_baseline.py

key-decisions:
  - "MDM write permission is manage:assets, the string every existing mdm_endpoints write guard already requires; no new string introduced, so the guard is strictly additive (PROH-76-01)"
  - "Read closure (view:X or manage:X) lives only in the guard; rbac_service.py and rbac_defaults.py are untouched (D-07)"
  - "Walker expands include-level dependency subtrees (get_dependant) so a mount guard's own auth dependency counts toward the auth class; results for the existing baseline are byte-identical to the old walk"
  - "secops slice is the 35 Security catalogues remaining after secposture's 14 (49 - 14); the plan's 'through securityAudit' wording would yield 25"

patterns-established:
  - "catalogue_guard(..., auth=...) takes the route family's auth dependency; tests pass a stub auth to be immune to authentication_service reloads"
  - "Synthetic-app walker tests import authentication_service lazily at call time"

requirements-completed: [ACC-03, ACC-04, ACC-05]

coverage:
  - id: D1
    description: "Mobile Device Management defined once in the manifest; backend guard and frontend reader both resolve view:mdm"
    requirement: ACC-03
    verification:
      - kind: unit
        ref: "src/__tests__/catalogueAccess.test.ts#resolves the Mobile Device Management permission from the shared manifest"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_route_parity.py#test_mdm_routes_carry_manifest_guard"
        status: pass
    human_judgment: false
  - id: D2
    description: "On the real mounted app a role lacking view:mdm/manage:mdm gets 403 from /api/mdm and a role holding view:mdm does not"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_guards.py#test_tracer_mdm_enforced_on_real_app"
        status: pass
    human_judgment: false
  - id: D3
    description: "Guard semantics: read twin closure, writes exact, any-of reads, super-admin bypass, role-then-scope order"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_guards.py (16 matrix tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Shared route walker plus parity helper that names untagged and mis-tagged in-scope routes; baseline tests unchanged"
    requirement: ACC-05
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_route_parity.py#test_offender_named_for_untagged_route"
        status: pass
      - kind: unit
        ref: "backend/tests/test_route_auth_baseline.py (20 tests)"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-10-13
status: complete
---

# Phase 76 Plan 01: Catalogue Manifest Tracer Summary

**Mobile Device Management enforced end to end: a shared JSON manifest entry, a tagged `catalogue_guard` mounted through `router_registry._load` (403 on the real app), a shared route walker, a parity helper that names offenders, and a typed frontend reader of the same file.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-10-13T04:14:48Z
- **Completed:** 2026-10-13T04:27:00Z
- **Tasks:** 3
- **Files modified:** 12 (10 created, 2 modified)

## Accomplishments
- Manifest seed with the eight Sidebar groups (enforce true for infra, security, mgmt) and the `mobileDeviceManagement` catalogue; `utils/catalogueAccess.ts` reads the same file (vitest + `npm run build` pass).
- `catalogue_guard` enforces D-03 (read accepts view:X or manage:X, writes only the declared list), D-07 (closure in the guard only) and D-02 (role check, then API-key scope). The `/api/mdm` router is guarded at mount time by `catalogue_mounts_devices.py`.
- `_route_walk.py` extracted from the baseline test with identical results (total 1601, 57 unauthenticated, 28 login-only writes); per-route records add auth class (user 1500, public 57, agent 29, agent_capable 15), tags, exemption and known-guard; 12 routes carry the MDM tag.
- `_catalogue_parity.py` with longest-prefix `owner_of`, `parity_offenders` (D-05 message shape), the 104-view `SLICES` partition and `slice_modules`; negative controls prove an untagged and a mis-tagged route are named.

## Task Commits

1. **Task 1: Tracer, MDM from manifest to 403 on the real app and the frontend reader** - `229bf3fc7` (feat)
2. **Task 2: Shared route walker and parity helper with negative controls** - `ec03fe7eb` (feat)
3. **Task 3: Guard behaviour matrix** - `8447e4c26` (test)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `shared/catalogue-access.json` - manifest seed
- `backend/catalogue_guards.py` - guard factory, access check, exempt marker, manage_twin
- `backend/catalogue_mounts.py` - MOUNT_GUARDS collector and mount_dependencies
- `backend/catalogue_mounts_devices.py` - devices slice, seeded with mdm_endpoints
- `backend/router_registry.py` - `_load` appends mount dependencies to include_router
- `backend/tests/_route_walk.py` - walker, memoized real-app walk, real-app probe
- `backend/tests/_catalogue_parity.py` - manifest helpers, parity_offenders, SLICES
- `backend/tests/test_route_auth_baseline.py` - now imports the walk (same 20 tests and assertions)
- `backend/tests/test_catalogue_guards.py`, `test_catalogue_route_parity.py` - 17 + 7 new tests
- `utils/catalogueAccess.ts`, `src/__tests__/catalogueAccess.test.ts` - frontend reader and test

## Decisions Made
- MDM write = `["manage:assets"]` (existing mdm_endpoints write guards use it); read = `view:mdm`, so `manage:mdm` holders also read via the twin.
- Probe roles: denying `viewer` (no view:mdm, manage:mdm), allowing `admin` (tenant_admin holds view:mdm).
- Matrix tests use real default roles (viewer, itam_viewer, itam_admin, admin, Super Admin) and a stub auth dependency, so no role document or Mongo is needed and `authentication_service` reloads cannot break dependency identity.
- `secops` slice holds the 35 Security catalogues left after secposture (see key-decisions).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Matrix tests initially patched effective_permissions only**
- **Found during:** Task 3 mutation check
- **Issue:** `get_database()` raised "Database not connected" before the patched resolver ran, so denial paths relied on the fail-closed branch.
- **Fix:** also patch `rbac_utils.get_database` in the autouse fixture.
- **Files modified:** backend/tests/test_catalogue_guards.py
- **Committed in:** 8447e4c26

**2. [Rule 1 - Bug] Parity synthetic tests could break after test_authentication reloads authentication_service**
- **Found during:** Task 3
- **Issue:** a module-level `get_current_user` import goes stale after a reload and the walker would classify the synthetic route as public.
- **Fix:** import `authentication_service` lazily inside the helper.
- **Files modified:** backend/tests/test_catalogue_route_parity.py
- **Committed in:** 8447e4c26

### TDD note (Task 3)
The matrix tests were written against the guard Task 1 already built per the plan, so they passed on first run (no RED to observe). Substituted a mutation check: removing the twin closure failed `test_read_allowed_with_manage_twin_only`, and skipping the role denial for scoped keys failed `test_role_is_checked_before_scopes`; the guard was restored unchanged. Gate sequence is therefore `test(76-01)` only, with the guard `feat` in Task 1.

---

**Total deviations:** 2 auto-fixed (2 bugs in new test code) plus the TDD note
**Impact on plan:** none on scope; stronger test isolation.

## Issues Encountered
- The plan's secops description ("35 catalogues from security through securityAudit") does not match its own count (25); used 49 Security minus the 14 secposture ones = 35.
- Context-monitor hooks reported 91% context use during the run; actual token budget was ample and work was not truncated.

## Baseline and run numbers
- Before: `test_route_auth_baseline.py` 20 + `test_rbac_defaults.py` 38 = 58 passed. After: same files unchanged in count (58), plus 24 new tests; the four-file command reports 82 passed.
- Full backend suite: 3300 passed, 47 skipped (baseline 3276 / 47; +24 new tests, no regressions) in 3m50s.
- Real-app walk: about 7.7 s (memoized per pytest session).
- `git diff --quiet 6b1972be9 -- backend/rbac_service.py backend/rbac_defaults.py` exits 0.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None. `unownedPrefixes` is intentionally empty and the manifest holds one catalogue; 76-02 fills both.

## Threat Flags
None. The only new surface is an additive dependency on `/api/mdm`; no new endpoints.

## Next Phase Readiness
- 76-02 can author the full manifest against the interfaces; 76-06 fills `catalogue_mounts_devices.py`; other slice files follow the same `MOUNTS` contract.
- Many unrelated working-tree changes exist and were left untouched.

## Self-Check: PASSED

---
*Phase: 76-catalogue-manifest-backend-route-enforcement*
*Completed: 2026-10-13*
