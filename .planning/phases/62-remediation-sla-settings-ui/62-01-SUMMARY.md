---
phase: 62-remediation-sla-settings-ui
plan: 01
subsystem: ui
tags: [react, typescript, vitest, testing-library, settings, sla]

# Dependency graph
requires:
  - phase: 44-remediation-sla-escalation
    provides: "Live GET/PATCH /api/settings/remediation-sla route (compliance_remediation_sla_endpoints.py), locked Copywriting Contract in 44-UI-SPEC.md"
provides:
  - "components/RemediationSlaSettings.tsx — UI consumer for the tenant's remediation SLA at-risk window"
  - "services/apiService.ts fetchRemediationSlaWindow/saveRemediationSlaWindow client wrappers"
  - "components/SettingsDashboard.tsx unrestricted 'Remediation' tab"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Verbatim structural clone of an existing settings panel (EvidenceSettings.tsx) with locked copy substitutions and one documented typography deviation"
    - "Unrestricted settings tab pattern — no client-side permission gate, server enforces admin-only write via 403"

key-files:
  created:
    - components/RemediationSlaSettings.tsx
    - src/__tests__/RemediationSlaSettings.test.tsx
  modified:
    - services/apiService.ts
    - components/SettingsDashboard.tsx

key-decisions:
  - "Section-label typography deviates from the clone source (font-medium, not font-semibold) to hold the project's 2-weight typography ceiling — locked by 62-UI-SPEC.md, verified by Task 3's conformance gate"
  - "No client-side role/permission conditional anywhere on the Remediation tab, input, or Save button (D-04) — the backend's admin-only PATCH gate is the sole authorization boundary; a non-admin's 403 surfaces as the same generic error toast as any other save failure"

patterns-established:
  - "Contract-conformance gate as a dedicated final task (Task 3) that re-verifies locked copy, typography, color, placement, and scope against the UI-SPEC even when earlier tasks already built to spec correctly — catches drift invisible to behavior tests"

requirements-completed: [SLA-03]

coverage:
  - id: D1
    description: "Unrestricted 'Remediation' tab renders in the Settings tab bar for every authenticated user, outside every permission-gated tab group; clicking it mounts the panel"
    requirement: "SLA-03"
    verification:
      - kind: unit
        ref: "src/__tests__/RemediationSlaSettings.test.tsx#renders: section label, field label, helper text, unit suffix, and idle button label"
        status: pass
      - kind: other
        ref: "grep conformance: SettingsDashboard.tsx placement/label/icon checks (Task 3 acceptance criteria)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Panel shows the tenant's current at-risk window in days and persists edits through the live PATCH route with the success toast 'SLA window updated'"
    requirement: "SLA-03"
    verification:
      - kind: unit
        ref: "src/__tests__/RemediationSlaSettings.test.tsx#save: edits the at-risk window and persists it with a success toast"
        status: pass
      - kind: unit
        ref: "src/__tests__/RemediationSlaSettings.test.tsx#fetch: settles the input to the resolved windowDays value"
        status: pass
    human_judgment: false
  - id: D3
    description: "Read-wrapper soft-fail: panel never renders blank on fetch failure or a payload missing windowDays, always falls back to 7"
    requirement: "SLA-03"
    verification:
      - kind: unit
        ref: "src/__tests__/RemediationSlaSettings.test.tsx#fetch: soft-fails to the default of 7 when the wrapper resolves its own fallback"
        status: pass
      - kind: unit
        ref: "src/__tests__/RemediationSlaSettings.test.tsx#fetch: never renders blank when the resolved payload has no windowDays key"
        status: pass
    human_judgment: false
  - id: D4
    description: "Any save failure (403/422/5xx/network) surfaces one generic error toast with no role/status/path leakage; success toast never fires on failure (D-04)"
    requirement: "SLA-03"
    verification:
      - kind: unit
        ref: "src/__tests__/RemediationSlaSettings.test.tsx#error: a rejected save shows the generic error toast, never the success toast, and never leaks role/status/path"
        status: pass
    human_judgment: false
  - id: D5
    description: "Client clamps input to [1,365] on change; out-of-range held value disables Save and shows the validation message"
    requirement: "SLA-03"
    verification:
      - kind: unit
        ref: "src/__tests__/RemediationSlaSettings.test.tsx#validat: clamps the input to [1, 365] on change"
        status: pass
      - kind: unit
        ref: "src/__tests__/RemediationSlaSettings.test.tsx#validat: an out-of-range held value (server response outside 1-365) shows the validation message and disables Save"
        status: pass
    human_judgment: false
  - id: D6
    description: "In-flight save disables the button and shows 'Saving...' (backstop truth)"
    requirement: "SLA-03"
    verification:
      - kind: unit
        ref: "src/__tests__/RemediationSlaSettings.test.tsx#save: while a save is in flight, the button is disabled and reads \"Saving...\""
        status: pass
    human_judgment: false
  - id: D7
    description: "Visual/UX sign-off — tab glyph and one-word label, visual hierarchy (input reads first), typography weight parity with sibling labels, accent reserved to Save button and active tab, and the non-admin save flow shows the generic toast with no role/permission wording, all confirmed live in the running app"
    verification: []
    human_judgment: true
    rationale: "Task 3's <human-check> requires visually opening Settings in the running app and signing in as a non-admin to confirm toast copy end-to-end — this is a judgment call on rendered UI, not something a unit test asserts. workflow.human_verify_mode is end-of-phase, so this is deferred to the phase's consolidated UAT rather than blocking this plan's execution."

# Metrics
duration: 15min
completed: 2026-08-10
status: complete
---

# Phase 62 Plan 01: Remediation SLA Settings UI Summary

**Unrestricted "Remediation" Settings tab wiring the already-live GET/PATCH `/api/settings/remediation-sla` route into a verbatim clone of `EvidenceSettings.tsx`, closing the last piece of v3.2's Remediation SLA & Escalation feature (SLA-03).**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-08-10T12:35:00Z (approx.)
- **Completed:** 2026-08-10T12:50:05Z
- **Tasks:** 3 (1 tracer, 1 tdd test-expansion, 1 conformance gate)
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- New `RemediationSlaSettings.tsx` panel — structural clone of `EvidenceSettings.tsx` with locked copy, the declared section-label typography substitution (`font-medium` not `font-semibold`), and zero client-side permission logic
- Two new `apiService.ts` client wrappers (`fetchRemediationSlaWindow` soft-fails to `{windowDays: 7}`, `saveRemediationSlaWindow` throws on `!res.ok`) routed through `authFetch`
- New unrestricted "Remediation" tab in `SettingsDashboard.tsx`, sitting in the same ungated trio as Security/Evidence, with `ClipboardListIcon` and the single-word label
- 9-test suite covering all five SLA-03 behaviors (renders/fetch/save/error/validat) plus the optional in-flight backstop, each selectable via its documented `-t` filter
- Task 3's contract-conformance gate found **zero drift** — every locked string, the typography deviation, accent reservation, unrestricted placement, and the D-04 no-permission-logic rule were already correct from Task 1

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end tracer (mount/read/edit/write/toast, all four layers)** - `f0602ca` (feat)
2. **Task 2: Expand SLA-03 behavior coverage out from the proven slice** - `a4948c1` (test)
3. **Task 3: Contract-conformance gate** - no commit (verification-only; zero drift found, nothing to correct)

**Plan metadata:** committed separately after this SUMMARY (docs: complete plan)

## Files Created/Modified
- `services/apiService.ts` - `fetchRemediationSlaWindow`/`saveRemediationSlaWindow`, mirroring the `fetchStalenessThreshold`/`saveStalenessThreshold` pair
- `components/RemediationSlaSettings.tsx` - new settings panel component
- `components/SettingsDashboard.tsx` - `SettingsView` union member, icon import, component import, tab button, panel mount (4 additive edits)
- `src/__tests__/RemediationSlaSettings.test.tsx` - 9 tests covering all SLA-03 behaviors

## Decisions Made
- Followed the plan's locked clone-and-substitute design exactly — no deviation from the UI-SPEC's Copywriting Contract, Typography contract, or Color contract was needed
- Task 3 (the conformance gate) is documented as having made no code changes since Task 1's implementation already matched every locked assertion; this is recorded explicitly rather than silently treating the task as a no-op

## Deviations from Plan

None - plan executed exactly as written. All acceptance criteria across all three tasks passed on first implementation; the contract-conformance gate (Task 3) confirmed zero drift rather than finding and fixing any.

## Issues Encountered

One test authoring note (not a plan deviation): the initial "renders" test asserted synchronously before the mount `useEffect`'s promise had flushed, producing a React `act()` warning. Fixed by wrapping the assertion in `waitFor` on the input's settled value first, per the plan's own guidance to prefer `waitFor` over bare assertions for anything depending on the mount promise. No production code affected.

## TDD Gate Compliance

Task 2 (`tdd="true"`) is a test-expansion task by design — the plan explicitly forbids touching `components/RemediationSlaSettings.tsx` in that task, since the underlying behavior was already fully implemented in Task 1's tracer commit (`feat`). All 8 new tests in Task 2 therefore passed immediately against the existing implementation with no RED phase; this is the expected shape for a tracer-then-expand plan structure, not a gate violation. The classical RED-before-GREEN commit ordering does not apply here because Task 1 (type=`tracer`, not `tdd`) already delivered the GREEN implementation before Task 2's test-only commit.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- SLA-03 fully delivered; the v3.2 Remediation SLA & Escalation feature (SLA-01/02/03) is now complete end-to-end
- One human-check item remains for end-of-phase UAT (per `workflow.human_verify_mode: end-of-phase`): visually open Settings, click the Remediation tab, and confirm the sign-in-as-non-admin save flow shows the generic error toast with no role/permission wording — see Task 3's `<human-check>` in `62-01-PLAN.md`
- No blockers for future phases

---
*Phase: 62-remediation-sla-settings-ui*
*Completed: 2026-08-10*

## Self-Check: PASSED

All created/modified files confirmed present on disk (`services/apiService.ts`, `components/RemediationSlaSettings.tsx`, `components/SettingsDashboard.tsx`, `src/__tests__/RemediationSlaSettings.test.tsx`, this SUMMARY). All referenced commit hashes (`f0602ca`, `a4948c1`, `80b87d1`) confirmed present in `git log`.
