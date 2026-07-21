---
phase: 44-remediation-sla-escalation
plan: 04
subsystem: ui
tags: [react, typescript, vite, remediation, sla, escalation]

# Dependency graph
requires:
  - phase: 44-03
    provides: "escalation-history GET endpoint + at-risk-window settings GET/PATCH"
  - phase: 44-02
    provides: "SLA sweep + escalation scheduler writing sla_status onto remediation tasks"
provides:
  - "SLA status badge column in the remediation dashboard task table"
  - "Read-only, append-only escalation history panel in the remediation task modal"
  - "apiService client function fetchRemediationEscalations(taskId)"
affects: [remediation, compliance-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SLA_COLORS map cloned beside STATUS_COLORS for a second badge type on the same table row"
    - "EscalationHistoryPanel.tsx extracted as its own file (structural clone of ChainOfCustodyPanel.tsx) when inlining would have breached the CLAUDE.md 500-line limit"

key-files:
  created: [components/EscalationHistoryPanel.tsx]
  modified: [services/apiService.ts, components/RemediationDashboard.tsx, components/RemediationTaskModal.tsx]

key-decisions:
  - "EscalationHistoryPanel extracted to its own file (not inlined in RemediationTaskModal.tsx) — inlining pushed the modal to 501 lines, over the CLAUDE.md 500-line limit"
  - "SLA badge always falls back to the neutral 'none' pill for tasks missing sla_status (legacy pre-migration rows), never renders blank/undefined (T-44-11 mitigation)"
  - "Escalation panel renders only when task?.id is set (never in create mode), fetches on first expand, and contains no edit/delete/confirm/destructive control (T-44-10 mitigation)"

patterns-established:
  - "Second badge-column pattern (SLA_COLORS beside STATUS_COLORS) for adding an additional status dimension to an existing table without restructuring it"

requirements-completed: [SLA-01, SLA-02]

coverage:
  - id: D1
    description: "SLA status badge column visible in the remediation dashboard task table, auto-reflecting due_date (ok/at_risk/breached/none)"
    requirement: "SLA-01"
    verification:
      - kind: unit
        ref: "npx tsc --noEmit (RemediationDashboard.tsx clean)"
        status: pass
      - kind: manual_procedural
        ref: "Task 3 checkpoint step 2 — human confirmed badge colors and neutral fallback in live dashboard"
        status: pass
    human_judgment: true
    rationale: "Visual badge color/placement and auto-computation against live due_date data require human confirmation in the running app; approved 2026-07-21."
  - id: D2
    description: "Append-only escalation history panel viewable by a compliance admin, no edit/delete controls"
    requirement: "SLA-02"
    verification:
      - kind: unit
        ref: "grep -ni 'delete|remove|confirm' components/EscalationHistoryPanel.tsx returns no interactive control matches"
        status: pass
      - kind: manual_procedural
        ref: "Task 3 checkpoint step 3 — human confirmed panel expands, lists Tier N entries, no edit/delete controls"
        status: pass
    human_judgment: true
    rationale: "Confirming the panel is genuinely read-only in the live UI (no hidden controls, correct copy/behavior) requires human visual verification, not just a grep."
  - id: D3
    description: "Notification delivery to assignee + tenant admins on SLA breach, and cross-tenant escalation-history isolation"
    verification:
      - kind: manual_procedural
        ref: "Task 3 checkpoint steps 4-5 — human confirmed bell-icon notifications for assignee + admin, and tenant B cannot see tenant A's escalation history"
        status: pass
    human_judgment: true
    rationale: "End-to-end notification delivery and tenant isolation are runtime/system-integration behaviors (44-02 backend + scheduler) that can only be confirmed by exercising the live app across two tenants; not exercisable via static analysis in this plan's file scope."

# Metrics
duration: 20min (Tasks 1-2; excludes human checkpoint wait time)
completed: 2026-07-21
status: complete
---

# Phase 44 Plan 04: Remediation SLA UI Wiring Summary

**SLA status badge column in RemediationDashboard.tsx plus a read-only, append-only escalation history panel (new EscalationHistoryPanel.tsx) in RemediationTaskModal.tsx, backed by a new apiService.fetchRemediationEscalations client — human-verified end-to-end including notification delivery and tenant isolation.**

## Performance

- **Duration:** ~20 min (Tasks 1-2 automated work), plus a human-verification checkpoint (Task 3) approved same session
- **Completed:** 2026-07-21
- **Tasks:** 3/3 (2 automated + 1 human-verify checkpoint)
- **Files modified:** 3 modified, 1 created

## Accomplishments
- Added `fetchRemediationEscalations(taskId)` to `services/apiService.ts`, cloning `fetchControlAuditLog`'s authFetch pattern, calling `GET /compliance/remediation-tasks/{taskId}/escalations` and typed to the UI-SPEC response shape (`{ task_id, entries: [{ escalation_level, created_at, notified }] }`)
- Added an `SLA_COLORS` map beside `STATUS_COLORS` in `RemediationDashboard.tsx`, a new SLA `<th>` between Status and Actions, and a badge `<td>` that always falls back to the neutral "none" pill for tasks missing `sla_status`; empty-state `colSpan` bumped from 6 to 7
- Built `components/EscalationHistoryPanel.tsx` as a structural clone of `ChainOfCustodyPanel.tsx` — toggle bar, fetch-on-first-expand via `fetchRemediationEscalations(task.id)`, loading/error/empty/entries states with the exact UI-SPEC copy, icons sourced from local `./icons` (not lucide-react), no edit/delete/confirm/destructive control anywhere
- Wired `<EscalationHistoryPanel taskId={task.id}>` into `RemediationTaskModal.tsx` after the Ticketing block, before the footer buttons, rendered only when `task?.id` is set
- Human verification (Task 3) approved: SLA badges visible with correct colors and neutral fallback, escalation panel expands with timestamped Tier-N entries and no edit/delete controls, notifications delivered to assignee + tenant admin on SLA breach, and cross-tenant escalation-history isolation confirmed

## Task Commits

Each task was committed atomically:

1. **Task 1: apiService client for escalation history** - `19c3811` (feat)
2. **Task 2: SLA badge column + escalation panel** - `a9d710f` (feat)
3. **Task 3: Human verification checkpoint** - no code changes (verification-only gate); approved with response "approved"

**Plan metadata:** (this commit) - `docs: complete plan`

## Files Created/Modified
- `services/apiService.ts` - Added `fetchRemediationEscalations(taskId)` client function (line ~4596)
- `components/RemediationDashboard.tsx` - Added `SLA_COLORS` map, SLA badge column, colSpan bump 6→7
- `components/RemediationTaskModal.tsx` - Wired in `EscalationHistoryPanel` after the Ticketing block
- `components/EscalationHistoryPanel.tsx` (NEW) - Read-only, append-only escalation history panel

## Decisions Made
- `EscalationHistoryPanel` extracted to its own new file rather than inlined in `RemediationTaskModal.tsx` — inlining pushed the modal to 501 lines, over the CLAUDE.md 500-line limit; this extraction path was pre-authorized by the plan itself
- SLA badge always falls back to the neutral "none" pill for tasks missing `sla_status` (legacy pre-migration rows) rather than ever rendering blank/undefined — direct implementation of the plan's T-44-11 mitigation
- Escalation panel renders only when `task?.id` is set (never in create mode) and contains zero edit/delete/confirm/destructive controls — direct implementation of the plan's T-44-10 mitigation (SLA-02 locked constraint)

## Deviations from Plan

None - plan executed exactly as written. The `EscalationHistoryPanel.tsx` extraction was an explicitly pre-authorized fallback in the plan's own Task 2 action text ("or extract to a new `components/EscalationHistoryPanel.tsx`... if inlining would push the modal past the 500-line CLAUDE.md limit — planner authorizes the extraction"), so this is not tracked as a deviation.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness

Phase 44 (Remediation SLA & Escalation) is now fully complete across all 4 plans:
- 44-01/44-02: backend SLA computation, scheduler, and escalation writes
- 44-03: escalation-history GET + at-risk-window settings endpoints
- 44-04 (this plan): frontend wiring — SLA badge + escalation panel, human-verified end-to-end

All 4 success criteria from the phase brief are satisfied: SLA status visible and auto-computed (Criterion 1, SLA-01), notification delivery confirmed (Criterion 2), append-only escalation history with no edit/delete (Criterion 3, SLA-02), and tenant scoping confirmed (Criterion 4). Both requirements SLA-01 and SLA-02 are complete. No blockers for the next phase or milestone close-out.

---
*Phase: 44-remediation-sla-escalation*
*Completed: 2026-07-21*
