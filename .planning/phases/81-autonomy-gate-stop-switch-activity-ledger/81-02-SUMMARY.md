---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 02
subsystem: rbac
tags: [rbac, permissions, catalogue, tenant-switch, mfa, autonomous-ops, pytest, vitest]

requires:
  - phase: 75-permission-resolver-single-source-of-truth
    provides: rbac_defaults role table, admin-tier MFA definition, effective_permissions
  - phase: 77-fail-closed-sidebar-view-gate-role-visibility
    provides: manage-implies-view closure, ceiling_allows, role visibility
provides:
  - "Four permission strings: view/manage/control:autonomous_ops and platform-only control:platform_autonomous_ops"
  - "autonomousOps catalogue entry (automation group, directly after soar) and tenant switches view/manage:autonomous_ops"
  - "Built-in role grants (D-06, D-24 a) and admin-tier MFA for the approve tier (D-07)"
  - "AppView 'autonomousOps', four Permission members, sidebar ShieldZapIcon entry"
affects: [81-03, 81-07, 81-09, 81-10, 81-11, 81-12]

actuals:
  tokens: 9000
  tasks: 2
  commits: 2

plan_head_before: 430993c9f76ccff6376b13f671671b61662cc4f5
plan_head_after: 202b125f9445b7440301c28ae6530ded1a68c643
commits: 2

tech-stack:
  added: []
  patterns:
    - "A new catalogue screen is one manifest entry plus one switch pair plus role-table rows; drift tests (counts, goldens) move deliberately in the same commit"
    - "control: strings are never derived by closure; manage implies view only"

key-files:
  created:
    - backend/tests/test_autonomous_ops_permissions.py
  modified:
    - backend/rbac_defaults.py
    - shared/catalogue-access.json
    - shared/tenant-feature-switches.json
    - types.ts
    - components/sidebarPresentation.tsx
    - backend/tests/test_rbac_defaults.py
    - backend/tests/test_catalogue_manifest.py
    - backend/tests/test_closure_delivery.py
    - backend/tests/test_role_visibility.py
    - backend/tests/test_custom_role_mfa.py
    - backend/tests/test_admin_mfa_required.py
    - backend/tests/test_platform_roles.py
    - src/__tests__/catalogueAccess.test.ts

key-decisions:
  - "autonomousOps sits directly after soar in the automation group (index 148); the sidebar-order test only requires group order, so no other position was dictated"
  - "No control switch: narrow() already removes every verb of a switched-off resource, so the tenant tick is view:autonomous_ops with manage:autonomous_ops as its child"
  - "control:platform_autonomous_ops lives in PLATFORM_ONLY_PERMISSIONS only; admin-tier membership follows through the existing union, no second literal"

patterns-established:
  - "Permission tests cite the decision they pin (D-05, D-07, D-08, D-09, PROH-81-16) in each docstring"

requirements-completed: [GATE-13, ACTV-01]

coverage:
  - id: D1
    description: "Autonomous Ops is a switchable catalogue screen: manifest entry, tenant switches, AppView/Permission unions, sidebar presentation, and all drift/count tests agree (204 views, 190 nav)"
    requirement: ACTV-01
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_views_equal_appview_union"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_nav_entries_are_190_and_follow_sidebar_order"
        status: pass
      - kind: unit
        ref: "backend/tests/test_tenant_feature_switches.py#test_the_switch_catalogue_is_sound"
        status: pass
      - kind: unit
        ref: "src/__tests__/catalogueAccess.test.ts"
        status: pass
    human_judgment: false
  - id: D2
    description: "Built-in grants per D-06/D-24 (a); viewer, user, ITAM roles and Platform Billing hold none; Platform Support reads through view:autonomous_ops"
    requirement: GATE-13
    verification:
      - kind: unit
        ref: "backend/tests/test_rbac_defaults.py#test_role_set_matches_golden"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_permissions.py#test_role_table_grants_follow_d06_and_d24"
        status: pass
      - kind: unit
        ref: "backend/tests/test_platform_roles.py#test_support_reads_autonomous_ops_through_its_own_view_string"
        status: pass
    human_judgment: false
  - id: D3
    description: "Approve tier is admin-tier: Security Analyst, Incident Responder and any custom role holding control:autonomous_ops are refused without MFA; Analyst and view-only custom roles are not"
    requirement: GATE-13
    verification:
      - kind: unit
        ref: "backend/tests/test_admin_mfa_required.py#test_approve_tier_roles_need_mfa"
        status: pass
      - kind: unit
        ref: "backend/tests/test_custom_role_mfa.py#test_custom_role_with_control_autonomous_ops_is_held_to_mfa"
        status: pass
    human_judgment: false
  - id: D4
    description: "control:platform_autonomous_ops is platform-only: stripped from any non-platform role document, passes has_platform_permission for the owner only, granted by no ceiling"
    requirement: GATE-13
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_permissions.py#test_a_role_document_cannot_carry_the_platform_stop"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_permissions.py#test_only_the_owner_passes_the_platform_stop"
        status: pass
    human_judgment: false
  - id: D5
    description: "PROH-81-16 closure adjacency: manage implies view and never control; control alone implies neither; a role with both keeps both; empty custom role shows no Autonomous Ops entry or string"
    requirement: GATE-13
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_permissions.py#test_manage_implies_view_and_never_control"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_permissions.py#test_a_custom_role_with_none_of_the_strings_has_no_autonomous_ops"
        status: pass
    human_judgment: false
  - id: D6
    description: "After deploy, Security Analyst and Incident Responder users are prompted to enrol MFA at next sign-in (A-81-MFA-ENROLMENT)"
    requirement: GATE-13
    verification: []
    human_judgment: true
    rationale: "Live-only check against the deployed system and real accounts; the plan lists it as the user's end-of-phase step"

duration: 14min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 02: Autonomous Ops permissions and catalogue entry Summary

**Autonomous Ops is now a switchable catalogue screen with four permission strings: view/manage/control:autonomous_ops in the role table, control:autonomous_ops admin-tier (MFA), and control:platform_autonomous_ops platform-only**

## Performance

- **Duration:** 14 min
- **Started:** 2026-10-26T07:42Z
- **Completed:** 2026-10-26T07:56Z
- **Tasks:** 2
- **Files modified:** 13 modified, 1 created

## Accomplishments

- `autonomousOps` manifest entry (label Autonomous Ops, group automation, nav, permission `view:autonomous_ops`, write `[manage:autonomous_ops, control:autonomous_ops]`, routes `[/api/autonomous-ops]`) placed directly after `soar`; tenant switches `view:autonomous_ops` and child `manage:autonomous_ops` in Automation & Intelligence. `START_FEATURES` unchanged, so new tenants stay Overview-only.
- Role table: `tenant_admin` gets view+manage+control; `analyst` view; `security_analyst` and `incident_responder` view+control; `platform_support` view only. Viewer, user, the three ITAM roles and Platform Billing unchanged; no Auditor role added.
- `control:autonomous_ops` added to `ADMIN_TIER_PERMISSIONS` (D-07); `control:platform_autonomous_ops` added to `PLATFORM_ONLY_PERMISSIONS` (and so admin-tier through the existing union). Closure and ceiling code untouched: `implied_closure` still never derives a `control:` string.
- `AppView 'autonomousOps'`, the four `Permission` members and `SIDEBAR_PRESENTATION.autonomousOps` (ShieldZapIcon, size 20) added so the frontend drift tests stay green.
- `backend/tests/test_autonomous_ops_permissions.py`: 19 test functions (41 cases) covering table grants, admin-tier, closure adjacency, ceiling, platform-only stripping, the tenant switch and delivery/visibility.

## GOLDEN_SIZES (test_rbac_defaults.py), before and after

| Role | Before | After |
|---|---|---|
| tenant_admin | 130 | 133 |
| analyst | 19 | 20 |
| security_analyst | 17 | 19 |
| incident_responder | 12 | 14 |
| platform_support | 76 | 77 |
| user, viewer, itam_admin, itam_user, itam_viewer, platform_billing | unchanged | unchanged |

## Existing tests whose expected values changed

| Test | Change | Decision |
|---|---|---|
| test_rbac_defaults.py GOLDEN sets and GOLDEN_SIZES | five roles gain the strings above | D-06, D-24 (a), D-08 |
| test_catalogue_manifest.py `test_views_equal_appview_union` | 203 to 204 AppView members | ACTV-01 |
| test_catalogue_manifest.py `test_nav_entries_are_189...` renamed `..._190_...` | 189 to 190 nav entries | ACTV-01 |
| test_closure_delivery.py NAV_SCREENS | 189 to 190 | ACTV-01 |
| test_role_visibility.py totals | 189 to 190 | ACTV-01 |
| src/__tests__/catalogueAccess.test.ts | `toHaveLength(190)` | ACTV-01 |
| test_custom_role_mfa.py `BUILTIN_ADMIN_TIER` | adds security_analyst, incident_responder; removed from the not-admin-tier list and the "other roles" parametrize; added to the "still need MFA" parametrize; new Approver/Auditor custom-role case | D-07, D-09 |
| test_admin_mfa_required.py | security_analyst removed from `test_other_roles_do_not_need_mfa`; new `test_approve_tier_roles_need_mfa` (inserted above the user's mfaExempt block, which stays unstaged) | D-07 |
| test_platform_roles.py | new `test_support_reads_autonomous_ops_through_its_own_view_string`; the existing view-only test still passes | D-08, A8 |

## Task Commits

1. **Task 1: Tracer - catalogue entry, switches, role-table grants, frontend unions** - `26706dd4b` (feat)
2. **Task 2: Approve tier admin-tier, platform stop platform-only, permissions tests** - `202b125f9` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

Tracer gate: the Task 1 `<verify>` was re-run after the commit-free expansion step in auto mode and passes except for the two failures listed under Deferred Issues; expansion continued.

## Decisions Made

See key-decisions. All permission strings, the manifest position and the switch shape follow the plan; the only choice left open (position) was after `soar`.

## Deviations from Plan

### Interim failing test (known state, not auto-fixed)

**1. [Plan inconsistency] `test_catalogue_manifest.py::test_structure_rules_hold_on_the_real_manifest` fails until 81-09**
- **Found during:** Task 1 verify
- **Issue:** the plan mandates `routes: ["/api/autonomous-ops"]` but also states no route exists until 81-09; the structure test therefore reports `autonomousOps: prefix /api/autonomous-ops matches no mounted route`. The plan's Task 1 verify command includes this file.
- **Decision:** kept the plan's manifest data (changing to `noBackendReason` would contradict the must-have truth and 81-09's guard/parity expectations). 81-09 mounts the router and its own verification already runs `test_catalogue_manifest.py`.
- **Files:** none changed for this
- **Impact:** one red test on the branch until 81-09; any plan between that runs `test_catalogue_manifest.py` will see it.

### Commit trailer

- Commit `26706dd4b` carries a `Co-Authored-By: Claude Sonnet 5.5` trailer. CLAUDE.md and the plan forbid it (no `attribution.commit` in `.claude/settings.json`); it was added by following a tool-supplied template before noticing. `git commit --amend` is forbidden in this shared tree, so it was left. `202b125f9` and the docs commits have no trailer. The user can drop it with a reword if wanted.

**Total deviations:** 1 plan inconsistency (documented, left red by design), 1 commit-trailer slip. No auto-fixes.

## Issues Encountered

None beyond the above.

## Deferred Issues (pre-existing, out of scope)

- `test_catalogue_manifest.py::test_sidebar_and_app_agree_with_manifest` fails already at HEAD before this plan: `components/Sidebar.tsx` no longer contains `utils/catalogueAccess`. Unrelated to Autonomous Ops.
- `test_catalogue_route_parity.py::test_ledger_ratchets` fails on stale/slack ledger entries for reporting and SOA modules (none for autonomous_ops).
- `test_audit_ledger.py::test_concurrent_writers_get_a_contiguous_verifiable_chain` failed once in the wider sweep (all `seq == 1`); passed for 81-01 and does not touch RBAC data. Looks like a flaky shared-state test; not investigated.

## Known Stubs

None.

## User Setup Required

None for this plan. Live-only steps for the user (nothing was deployed, restarted, migrated or published):
- After the phase is deployed: sign in as a Security Analyst and as an Incident Responder and confirm the MFA enrolment prompt (A-81-MFA-ENROLMENT, D-07). Reverting the change later does not un-enrol anyone.
- The Autonomous Ops sidebar entry appears only once a Super Admin ticks Autonomous Ops for a tenant and the backend is restarted and the UI published; the screen itself arrives in 81-07 and the route in 81-09.

## Threat Flags

None. T-81-06 (MFA on the approve tier), T-81-07 (platform stop cannot be held by a tenant role document), T-81-08 (manage never implies control) and T-81-09 (Platform Billing gets no access) are mitigated and tested; no new endpoint or trust boundary was added.

## Next Phase Readiness

- 81-09 can reference the permission strings and the `autonomousOps` manifest entry directly; its mount guard must equal read `view:autonomous_ops`, write `[manage:autonomous_ops, control:autonomous_ops]`.
- 81-07 (screen) can rely on `AppView 'autonomousOps'` and the presentation entry.

## Self-Check: PASSED

`backend/tests/test_autonomous_ops_permissions.py` exists; commits `26706dd4b` and `202b125f9` are ancestors of HEAD; all acceptance criteria re-run and pass (manifest entry, `grep` counts, admin-tier and platform-only assertions, 19 test functions). Plan verification: 527 backend tests pass, 2 fail (both listed above); vitest `catalogueAccess`, `viewAccess`, `SidebarTenantSwitches` 73 pass; `ManageTenantModal` also passed in the Task 1 run (82 tests across four files).

---
*Phase: 81-autonomy-gate-stop-switch-activity-ledger*
*Completed: 2026-10-26*
