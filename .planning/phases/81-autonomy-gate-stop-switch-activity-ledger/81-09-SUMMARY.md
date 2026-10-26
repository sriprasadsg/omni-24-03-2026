---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 09
subsystem: api
tags: [fastapi, rbac, catalogue-guard, autonomous-ops, stop-switch, api-keys, tenant-isolation, pytest]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-01)
    provides: settings (level, maximum level, shadow), ledger, stop state documents
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-02)
    provides: autonomousOps catalogue entry and the four permission strings
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-04)
    provides: approvals.approve/deny/undo, breaker.restore
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-05)
    provides: stop.press/clear/can_clear
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-11)
    provides: protected never-touch API, messages
provides:
  - "Tenant router /api/autonomous-ops: status, actions, stop, resume, settings/level, settings/restore-level, never-touch, approve, deny, undo"
  - "Platform router /api/platform/autonomous-ops: status, actions, stop, resume, tenants/{id}/max-level, tenants/{id}/shadow, never-touch"
  - "views.py response shaping (Caller, resolve_tenant, status_payload, platform_status_payload, present_row, display_actor)"
  - "catalogue_mounts_autonomous_ops (AUTONOMOUS_OPS_GUARD) and both routers required at startup"
  - "probe_real_app auth mode session_capable"
affects: [81-10, 81-verification]

actuals:
  tokens: 26300
  tasks: 2
  commits: 4

plan_head_before: 89948c0f1c2ebb95e347dff2a17e67f198670f5b
plan_head_after: f0238aeea87bf2e481da8d327bde00cbc8d7a1fb
commits: 4

tech-stack:
  added: []
  patterns:
    - "Route-level _require_* dependencies on top of the include-level catalogue guard: the guard checks the manifest strings, each write route adds the exact permission and the interactive-session rule"
    - "D-25 masking decided in one function (display_actor) used by StopView and control rows"
    - "Platform staff pass tenantId (owner writes, support reads); a tenant role may only name its own tenant"

key-files:
  created:
    - backend/autonomous_ops/views.py
    - backend/autonomous_ops_endpoints.py
    - backend/autonomous_ops_platform_endpoints.py
    - backend/catalogue_mounts_autonomous_ops.py
    - backend/tests/test_autonomous_ops_endpoints.py
    - backend/tests/test_autonomous_ops_endpoints_writes.py
    - backend/tests/_autonomous_ops_http.py
    - backend/tests/test_catalogue_slice_autonomous_ops.py
  modified:
    - backend/router_registry.py
    - backend/tests/_route_walk.py
    - backend/autonomous_ops/messages.py

key-decisions:
  - "The tenant router authenticates through get_current_user_or_api_key; approve, deny, undo, resume, level, restore-level and never-touch writes refuse an API key (and the legacy tenant integration key) with 403 through _require_interactive_session, so only reads and pressing a stop work on a key"
  - "Resume needs manage:autonomous_ops plus stop.can_clear: a manage holder clears only a tenant stop pressed at tenant tier, a Super Admin clears any; approve/deny/undo need control:autonomous_ops"
  - "Platform Support is refused on every write through the route dependencies (not only through the guard), and reads only with an explicit tenantId (400 without it)"
  - "Built-in never-touch entries derived from this server (interface addresses, platform URL host, platform agents) are shown to platform staff only; tenants see the general special ranges plus one line standing for the rest"
  - "Counts and total are sent on the first page only (no cursor), as 81-07 reads them"
  - "Control rows carry an additive by field (masked per D-25); action rows carry by null"
  - "Dependency/storage failures answer 503 with a fixed message instead of a 500"

requirements-completed: [GATE-13, GATE-09, GATE-08]

coverage:
  - id: D1
    description: "GET /status and /actions serve the fixed payloads with display-ready labels, buckets, cursor paging (each row once, newest first, shared createdAt) and counts"
    requirement: ACTV-01
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints.py#test_tracer_analyst_reads_status_and_display_ready_rows"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints.py#test_paging_walks_each_row_once_newest_first_with_shared_created_at"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints.py#test_control_row_and_action_row_with_the_same_created_at_both_appear"
        status: pass
    human_judgment: false
  - id: D2
    description: "Read access for exactly the roles D-06 names (analyst, security analyst, incident responder, tenant admin, Super Admin, Platform Support with tenantId, read-scoped key); viewer, user, itam_admin, Platform Billing, an unticked tenant and a wrong-scope key get 403"
    requirement: GATE-13
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints.py#test_read_routes_are_open_to_exactly_the_roles_d06_names"
        status: pass
    human_judgment: false
  - id: D3
    description: "Stop, resume, level, maximum level, shadow, restore-level, never-touch, approve, deny and undo enforce the permission split; API keys can press a stop but nothing else; Platform Support writes nothing"
    requirement: GATE-13
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints_writes.py#test_write_permission_matrix_on_the_mounted_app"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints_writes.py#test_platform_router_matrix_on_the_mounted_app"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints_writes.py#test_press_a_stop_then_press_again_then_resume_with_a_reason"
        status: pass
    human_judgment: false
  - id: D4
    description: "Level is capped by the maximum level (equal accepted, above 403, unknown 422); only the platform route changes the maximum and lifts the shadow flag; the platform organization stays off (409)"
    requirement: GATE-09
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints_writes.py#test_level_is_capped_by_the_maximum_and_only_the_platform_router_changes_the_maximum"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints_writes.py#test_only_the_platform_route_lifts_a_tenants_shadow_flag"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints_writes.py#test_the_platform_organization_cannot_be_raised_above_off"
        status: pass
    human_judgment: false
  - id: D5
    description: "Never-touch entries: tenant add/list/delete with ip/cidr parsed, caps and scoping, built-in 403, unknown 404, platform entries via the platform router only"
    requirement: GATE-08
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints_writes.py#test_never_touch_entries_for_a_tenant"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints_writes.py#test_a_tenant_cannot_delete_another_tenants_or_a_platform_entry"
        status: pass
    human_judgment: false
  - id: D6
    description: "A platform person's name is private from tenant viewers (status stop and control rows) and shown to platform staff; tenant-scope names show to everyone"
    requirement: GATE-06
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints.py#test_platform_stop_name_is_private_from_tenants_and_visible_to_platform_staff"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_endpoints_writes.py#test_platform_wide_stop_and_resume_and_name_masking"
        status: pass
    human_judgment: false
  - id: D7
    description: "The routes work on the live server after a backend restart and the screen (81-10) talks to them"
    human_judgment: true
    rationale: "A restart and a UI publish are the user's steps; tests use throwaway databases and the mounted app, never :5000"

duration: 17min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 09: Autonomous Ops HTTP routes Summary

**Tenant and platform routers for Autonomous Ops: status and activity reads for the screen, stop/resume, level, maximum level, shadow lift, never-touch, approve/deny/undo, with API keys limited to reads and pressing a stop and platform staff names masked from tenants**

## Performance

- **Duration:** about 17 min (12:49Z to 13:06Z)
- **Tasks:** 2 (Task 1 tracer, Task 2 auto; both TDD with a red commit first)
- **Files:** 8 created, 3 modified

## Accomplishments

- `GET /api/autonomous-ops/status|actions` serve the fixed payloads (81-07 contract) with labels from `messages`, one bucket per row, cursor paging and counts. A tenant's list also carries the platform-scope control rows. Tracer verified end to end before expansion (14 passed after Task 1).
- Every write route carries its own `_require_*` dependency on top of the catalogue guard. API keys press stops (and the platform stop with the platform scope) but get 403 on resume, approve, deny, undo, level, restore-level, never-touch and the platform shadow/maximum/resume routes.
- D-25: `display_actor` masks a platform person as "Platform administrator" for tenant viewers in the status StopView, the 409 `by` and the control rows; platform staff and tenant-scope entries show the real name.
- Both routers are in `_REQUIRED_ROUTERS`; the tenant router is mounted through `catalogue_mounts_autonomous_ops.MOUNTS`. `test_catalogue_manifest.py::test_structure_rules_hold_on_the_real_manifest` is green now that `/api/autonomous-ops` is mounted.

## Task Commits

1. **Task 1 (tracer): status and activity reads** - `c3527301c` (test, red), `725e49cf5` (feat, green)
2. **Task 2: write routes, platform router, permission matrix** - `677818af4` (test, red), `f0238aeea` (feat, green)

**Plan metadata:** committed with this SUMMARY (docs: complete plan).

## Route table (81-10 and the OpenAPI docs read from this)

Tenant router, prefix `/api/autonomous-ops`. Mount guard on every route: read `view:autonomous_ops` (or manage twin), write `manage:autonomous_ops` or `control:autonomous_ops`, auth `get_current_user_or_api_key`. `tenantId` query parameter: honoured only for platform staff (owner reads and writes, Support reads only); a tenant role passing another tenant's id gets 403.

| Route | Extra rule | Key allowed |
|-------|-----------|-------------|
| GET /status, GET /actions | none beyond the guard | yes (scope view) |
| GET /never-touch | none beyond the guard | yes (scope view) |
| POST /stop `{reason?}` | `_require_stop_permission` (control; Support refused) | yes (scope control) |
| POST /resume `{reason}` | `_require_manage` + `_require_interactive_session`; then `stop.can_clear` | no |
| PUT /settings/level `{level}` | manage + interactive | no |
| POST /settings/restore-level | manage + interactive | no |
| POST /never-touch `{kind, value, note?}` | manage + interactive | no |
| DELETE /never-touch/{entry_id:path} | manage + interactive | no |
| POST /actions/{id}/approve | `_require_control` + interactive | no |
| POST /actions/{id}/deny `{reason?}` | control + interactive | no |
| POST /actions/{id}/undo | control + interactive | no |

Platform router, prefix `/api/platform/autonomous-ops`; every route needs `control:platform_autonomous_ops` (`_require_platform_autonomy_control`: platform owner, and an API key's scope must name it); every route except POST /stop also `_require_interactive_session`.

| Route | Effect |
|-------|--------|
| GET /status | `{scope:"platform", stop:{platform}, tenantStopsCount, canStopPlatform, canResumePlatform}` |
| GET /actions | platform-scope control rows, same paging as the tenant list |
| POST /stop `{reason?}` | platform-wide stop (a scoped key may press it) |
| POST /resume `{reason}` | clears the platform-wide stop |
| PUT /tenants/{tenant_id}/max-level `{maxLevel}` | only route that changes a maximum level (lowers the level when above) |
| PUT /tenants/{tenant_id}/shadow `{shadow: bool}` | only route that lifts or restores a tenant's shadow flag (D-03) |
| GET, POST (201), DELETE /never-touch | platform-wide entries; built-in ids 403 |

## HTTP status map for service results

| Service result | HTTP |
|---|---|
| stop.press `stopped` | 200 status payload (tenant: tenant status; platform: platform status) |
| stop.press `already_stopped` | 409 `{detail, by}` (`by` masked per D-25) |
| stop.press / clear `invalid_reason`, body validation (reason over 500, blank resume reason, unknown level, bad ip/cidr, note over 200) | 422 |
| stop.clear `cleared` | 200 status payload |
| stop.clear `not_stopped` | 409 |
| stop.clear `forbidden` | 403 |
| settings.set_level `ok` / `above_max` / `platform_tenant` / `invalid` | 200 status payload / 403 / 409 / 422 |
| set_max_level and set_shadow `platform_tenant` / unknown tenant | 409 / 404 |
| breaker.restore `restored` / `not_tripped` | 200 status payload / 409 |
| approvals `dispatched` / `denied` / `undone` | 200 `{status, action: Row}` (undo adds `breakerTripped`) |
| approvals `not_found` | 404 |
| approvals `already_handled`, `stopped`, `expired`, `refused` (with reason), `no_undo`, undo of a non-undoable state | 409 with a plain-words `detail` |
| never-touch add over the 500 cap | 409; delete of `builtin:` id 403; unknown or out-of-scope id 404 |
| platform staff `tenantId` missing / unknown tenant | 400 / 404 |
| storage unreachable | 503 `Autonomous Ops is temporarily unavailable` |

## Payload deviations from the interfaces block (81-07 and 81-10 must know)

- Control rows (and only they) carry an additive `by` string (D-25 masked); action rows have `by: null`. The 81-07 client ignores unknown fields.
- `counts` and `total` are present on the first page only (no cursor); `total` counts the rows of the requested bucket, including platform-scope control rows under All.
- `level` and `maxLevel` in the status are the stored values (both `off` for the platform organization); `eligible` is false for the platform organization.
- `GET /never-touch` items are `{id, scope, kind, value, note, builtin}`; POST returns the created entry with 201.
- Everything else matches the interfaces block exactly.

## Decisions Made

See `key-decisions` above. The two worth repeating for the verifier: API keys refused for every non-press write (PROH-81-10), and Platform Support refused by route dependencies as well as by the guard (PROH-81-15).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Built-in never-touch entries disclosed this server's own addresses**
- **Found during:** Task 2 (GET /never-touch)
- **Issue:** `protected.builtin_entries` includes the host's interface addresses and networks, the platform URL host and every platform agent's hostname/IP; returning them to a tenant analyst or a read-scoped API key would disclose platform infrastructure.
- **Fix:** `views.visible_entries` shows those to platform staff only; tenants see the general special ranges and one line "This platform's own servers and agents" (id `builtin:platform-infrastructure`, still not deletable).
- **Files modified:** backend/autonomous_ops/views.py
- **Verification:** `test_never_touch_entries_for_a_tenant`
- **Committed in:** f0238aeea

**2. [Rule 3 - Blocking] Delete route could not match built-in ids**
- **Found during:** Task 2
- **Issue:** Built-in ids such as `builtin:cidr:127.0.0.0/8` contain a slash, so `DELETE /never-touch/{entry_id}` answered 404 instead of the required 403.
- **Fix:** path converter `{entry_id:path}` on both delete routes.
- **Committed in:** f0238aeea

### CLAUDE.md / plan-shape adjustments

**3. [CLAUDE.md: files under 500 lines] Test modules split**
- The plan names one endpoints test module; it would have been about 760 lines. Reads stay in `test_autonomous_ops_endpoints.py` (258 lines), writes and the matrices are in `test_autonomous_ops_endpoints_writes.py` (447), shared fixtures in `tests/_autonomous_ops_http.py` (82).

**4. [Plan wording] Slice parity cannot use the shared partition**
- The automation group is not an enforced catalogue group, so `slice_modules` does not list this module. `test_catalogue_slice_autonomous_ops.py` checks the same parity directly for the module's routes and the guard against the manifest.

**5. [Plan wording] Probe status codes**
- The probe interpreter has no database, so an allowed read answers 503, not 200. The matrices assert "not 403" (200 or 503 for reads) for allowed callers and exactly 403 for refused ones; the 200 payloads are asserted against a real throwaway MongoDB.

**Total deviations:** 2 auto-fixed (1 Rule 2, 1 Rule 3), 3 plan-shape adjustments. **Impact:** none on scope.

## Issues Encountered

- `test_catalogue_route_parity.py::test_ledger_ratchets` and `test_catalogue_manifest.py::test_sidebar_and_app_agree_with_manifest` fail as before this plan (stale ledger entries for modules outside Phase 81; sidebar checks). Not touched.
- The probe tests start a fresh interpreter per call (about 10 s each); the matrices batch all cases into one call.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: info-disclosure-mitigated | backend/autonomous_ops/views.py | Built-in never-touch entries expose this server's addresses; filtered for non-staff (see Deviation 1) |

## Known Stubs

None.

## Steps for the user (not done here by rule)

- Restart `omni-backend.service` so the live backend mounts both routers (it runs from this checkout without reload); both are required routers, so a broken import will stop startup and say why.
- Publish the UI build when 81-10 is done; until then the 81-07 screen reads these routes.
- No migration is needed for this plan.

## Next Phase Readiness

- 81-10 can render the status card, Stop/Resume controls and the Super Admin "Stop/Resume all organizations" buttons from `canStop`, `canResume`, `canStopPlatform` and `canResumePlatform`, and call `POST /stop`, `POST /resume` and the platform equivalents with `{reason}`.
- Level, maximum level, shadow lift and never-touch editing stay API-only in Phase 81 (D-22), documented in the OpenAPI summaries.

## Self-Check: PASSED

- Files exist: backend/autonomous_ops/views.py, backend/autonomous_ops_endpoints.py, backend/autonomous_ops_platform_endpoints.py, backend/catalogue_mounts_autonomous_ops.py, backend/tests/test_autonomous_ops_endpoints.py, backend/tests/test_autonomous_ops_endpoints_writes.py, backend/tests/_autonomous_ops_http.py, backend/tests/test_catalogue_slice_autonomous_ops.py
- Commits present: c3527301c, 725e49cf5, 677818af4, f0238aeea
- Verification: 180 of 182 tests pass across the plan's verification set; the two failures are the known pre-existing reds listed above
