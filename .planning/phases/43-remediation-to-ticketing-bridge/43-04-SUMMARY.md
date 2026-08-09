---
phase: 43-remediation-to-ticketing-bridge
plan: 04
subsystem: ui
tags: [react, typescript, ticketing, jira, servicenow, tailwind]

# Dependency graph
requires:
  - phase: 43-01
    provides: "ticketing_bridge.create_ticket_for_remediation_task + close-loop scheduler backend surface"
  - phase: 43-02
    provides: "priority-gated auto-create hook on task creation (D-01)"
  - phase: 43-03
    provides: "POST /api/compliance-remediation/tasks/{task_id}/create-ticket manual endpoint (Literal-validated provider, tenant-scoped 404/502) + GET /api/ticketing/config"
affects: [44]
provides:
  - "types.ts RemediationTask.ticket_provider/ticket_ref/ticket_url (optional fields)"
  - "services/apiService.ts createTicketForRemediationTask(taskId, provider) and getTicketingConfig() client wrappers"
  - "components/RemediationTaskModal.tsx Ticketing section — Create Ticket button + provider picker + read-only ticket-display block, wired end-to-end to the backend"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "handleCreateTicket clones handleSuggest's exact async-action+toast shape (guard task?.id, set loading flag, await api call, showToast success, onRefresh, catch->showToast error, finally clear flag)"
    - "Three-state conditional render (ticket_ref truthy -> read-only block; unsaved/unconfigured -> hidden; otherwise -> button + optional picker) driven by a background getTicketingConfig() effect on modal open, never assumed configured"
    - "Provider badge and radio-tile styling clone existing components (RemediationDashboard's pill class, AddCloudAccountModal's radio-tile pattern) rather than introducing new UI primitives"

key-files:
  created: []
  modified:
    - types.ts
    - services/apiService.ts
    - components/RemediationTaskModal.tsx

key-decisions:
  - "getTicketingConfig() uses the safe-default try/catch shape (never throws) since hasJira/hasServiceNow drive conditional rendering, not an error path — a config-fetch failure should hide the Ticketing section, not crash the modal"
  - "Provider values are restricted to the 'jira'|'servicenow' string literal union throughout (state, radio tiles, API call) — no free-text provider input anywhere"

patterns-established: []

requirements-completed: [REM-01]

coverage:
  - id: D1
    description: "Create Ticket action (+ provider picker when both Jira and ServiceNow configured) appears on a saved remediation task with ticketing configured, hidden for unsaved tasks or when no provider is configured"
    requirement: "REM-01"
    verification:
      - kind: automated_ui
        ref: "npm run build (type-check clean, all three render branches compile)"
        status: pass
      - kind: manual_procedural
        ref: "43-04-PLAN.md Task 3 checkpoint:human-verify — provider picker (two tiles, indigo selected state), hidden-state rules for unsaved/unconfigured tasks"
        status: pass
    human_judgment: false
  - id: D2
    description: "Clicking Create Ticket shows a Creating.../spinner state, then a success toast and switches to the read-only ticket-display block (provider badge, ticket reference, working outbound link); a forced failure shows the exact error toast and never blocks the task view (D-04)"
    requirement: "REM-01"
    verification:
      - kind: manual_procedural
        ref: "43-04-PLAN.md Task 3 checkpoint:human-verify — spinner->success toast->read-only block transition; forced failure (fake test credentials) -> error toast, task remains usable"
        status: pass
      - kind: other
        ref: "Orchestrator live pre-verification: both Jira/ServiceNow configured against a fresh backend instance, D-01 medium-priority auto-create firing live, 502/422/404 all correct"
        status: pass
    human_judgment: false

# Metrics
duration: ~14min (commit-to-commit across tasks 1-2, plus checkpoint wait)
completed: 2026-07-21
status: complete
---

# Phase 43 Plan 04: Frontend Ticketing UI (Create Ticket action + provider picker + ticket-display block) Summary

**Three-state Ticketing section added to `RemediationTaskModal.tsx` — Create Ticket button with a Jira/ServiceNow provider picker (D-02), a read-only provider/ref/link display once a ticket exists, and a non-blocking error toast on failure (D-04) — closing REM-01's frontend gap on top of the Plan 01-03 backend.**

## Performance

- **Duration:** ~14 min (first task commit to second task commit: 18:03:02 → 18:03:59 IST), plus a human-verification checkpoint wait
- **Started:** 2026-07-21T18:03:02+05:30
- **Completed:** 2026-07-21 (checkpoint approved same session)
- **Tasks:** 3/3 completed (2 auto, 1 checkpoint:human-verify)
- **Files modified:** 3

## Accomplishments
- `RemediationTask` (types.ts) gained optional `ticket_provider`/`ticket_ref`/`ticket_url` fields
- `apiService.ts` gained `createTicketForRemediationTask(taskId, provider)` (POST, throws on non-2xx, clones the existing remediation-wrapper throw shape) and `getTicketingConfig()` (GET, safe-default try/catch, used only to compute `hasJira`/`hasServiceNow`)
- `RemediationTaskModal.tsx` gained a `handleCreateTicket(provider)` handler cloning `handleSuggest`'s async-action+toast pattern exactly, plus a three-state Ticketing section: (1) read-only ticket-display block (provider badge, ticket ref, working outbound link) once `ticket_ref` is truthy; (2) hidden entirely for an unsaved task or when neither provider is configured; (3) otherwise a `Create Ticket` button, with a "Choose a provider" radio-tile picker shown only when both providers are configured
- Provider badge reuses `RemediationDashboard`'s existing pill class string with only the color pair swapped (blue Jira / green ServiceNow); radio tiles clone `AddCloudAccountModal`'s pattern with `p-2` padding and an indigo selected state per UI-SPEC
- Human verification (Task 3, checkpoint:human-verify, gate=blocking) confirmed: provider picker with two tiles renders correctly, Create Ticket shows spinner→success toast→read-only block transition, a forced failure (fake test credentials) surfaces the exact error toast without blocking the task view, the Ticketing section is correctly hidden for unsaved/unconfigured cases, and no visual regressions were introduced
- Ahead of presenting the checkpoint, the orchestrator additionally pre-verified the backend paths live against a fresh backend instance: both Jira and ServiceNow configured, the D-01 medium-priority auto-create hook firing live on task creation, and 502/422/404 all returning correctly — a stale long-running dev backend process was discovered during this check and worked around by repointing the Vite proxy, without touching that stale process

## Task Commits

Each task was committed atomically:

1. **Task 1: Add ticket fields to RemediationTask type + apiService client wrappers** - `4053117` (feat)
2. **Task 2: Add the Ticketing section (button, provider picker, ticket-display) to RemediationTaskModal.tsx** - `21dab2d` (feat)
3. **Task 3: Human verification of the Ticketing UI** - checkpoint:human-verify, no code changes; approved by user ("approved") after confirming all 5 verification steps in the plan's `<how-to-verify>` block

**Plan metadata:** (this commit)

## Files Created/Modified
- `types.ts` - adds `ticket_provider`/`ticket_ref`/`ticket_url` optional fields to `RemediationTask`
- `services/apiService.ts` - adds `createTicketForRemediationTask` and `getTicketingConfig` client wrappers
- `components/RemediationTaskModal.tsx` - adds `handleCreateTicket`, ticketing-related state, and the three-state Ticketing section

## Decisions Made
- `getTicketingConfig()` never throws (safe-default try/catch) since it drives conditional visibility, not an error-handling path — a fetch failure should just hide the Ticketing section rather than surface an error
- Provider selection is strictly the `'jira' | 'servicenow'` literal union end-to-end (state, radio tiles, API call) — no free-text provider input anywhere in the flow

## Deviations from Plan

None - plan executed exactly as written. Task 3 was a verification-only checkpoint gate with no code changes; the user approved after exercising all 5 steps in the plan's `<how-to-verify>` block.

## Issues Encountered

None in the frontend implementation. During the checkpoint's live pre-verification, the orchestrator found a stale long-running dev backend process serving outdated code; this was worked around by repointing the Vite proxy to a fresh backend instance rather than modifying the stale process, since that process was out of this plan's scope.

## User Setup Required

None - no external service configuration required. Jira/ServiceNow provider configuration (via `TicketingIntegration.tsx`, delivered in an earlier phase) is a per-tenant prerequisite for the Ticketing section to render at all, but no new setup was introduced by this plan.

## Next Phase Readiness
- REM-01 (manual ticket creation with provider picker, read-only ticket display) is now fully delivered end-to-end: backend (43-01/43-02/43-03) + frontend (43-04).
- Phase 43 (Remediation-to-Ticketing Bridge) is complete — REM-01 and REM-02 both done.
- Phase 44 (Remediation SLA & Escalation) can proceed; it mutates the same `compliance_remediation_tasks` document this phase touched but does not depend on any specific frontend artifact from this plan.
- No blockers.

---
*Phase: 43-remediation-to-ticketing-bridge*
*Completed: 2026-07-21*

## Self-Check: PASSED

- FOUND: types.ts
- FOUND: services/apiService.ts
- FOUND: components/RemediationTaskModal.tsx
- FOUND: 4053117 (Task 1 commit)
- FOUND: 21dab2d (Task 2 commit)
- FOUND: `ticket_ref` present in types.ts
- FOUND: `createTicketForRemediationTask`/`getTicketingConfig` present in services/apiService.ts
- FOUND: `handleCreateTicket` present in components/RemediationTaskModal.tsx
