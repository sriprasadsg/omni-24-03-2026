---
phase: 73-api-integrations
plan: 06
subsystem: ui
tags: [react, typescript, webhooks, itam, jira, servicenow, ticketing]

requires:
  - phase: 73-04
    provides: "POST /api/itam/tickets manual create-ticket route, its entity-kind/entity-id/provider request contract, and its three-key response shape"
provides:
  - "Eight new ITAM WebhookEvent union members selectable in the existing webhook subscription picker (D-14, no separate reference doc)"
  - "ItamTicketProvider type and createItamTicket API client function"
  - "Three-state Create Ticket row action (hidden / text link / provider dropdown) on both the Check-Out/In and Asset Requests ITAM tables, converting into a linked provider badge + reference once a ticket exists"
affects: [itam-console, webhook-management]

tech-stack:
  added: []
  patterns:
    - "Cloned dropdown-menu state shape (row-id-keyed open state + outside-click-close ref) reused verbatim from the existing Label menu for the ticket-provider picker"
    - "Ticketing config booleans (hasJira/hasServiceNow) derived client-side from getTicketingConfig's field presence, never rendering the response itself"

key-files:
  created: []
  modified:
    - types.ts
    - services/apiService.ts
    - components/WebhookManagement.tsx
    - components/itam/LifecyclePanel.tsx
    - components/itam/RequestsPanel.tsx

key-decisions:
  - "Task 3 (held-out visual checkpoint) required no code change — it verified Task 1/2 output in a live browser; user approved all four checks (16-entry picker with no layout shift, dropdown fully on-screen at normal and tablet width, ticket reference/badge/link on one line with no wrap, and the no-provider/failed-creation/new-tab behaviors)."

requirements-completed: [ITAM-API-02, ITAM-API-03]

coverage:
  - id: D1
    description: "Eight ITAM webhook event types appear in the existing subscription picker, byte-identical to backend dispatch strings"
    requirement: ITAM-API-02
    verification:
      - kind: unit
        ref: "npx tsc --noEmit && grep -c asset.audit_overdue types.ts components/WebhookManagement.tsx backend/itam_webhook_events.py"
        status: pass
      - kind: manual_procedural
        ref: "Task 3 checkpoint check 1: 16-entry picker, exact strings, existing scroll container absorbs growth with no layout shift"
        status: pass
    human_judgment: false
  - id: D2
    description: "Operator creates a Jira or ServiceNow ticket from any asset row or asset-request row without leaving the ITAM console, three-state gated by provider configuration"
    requirement: ITAM-API-03
    verification:
      - kind: unit
        ref: "npx tsc --noEmit && npm run build && npx vitest run src/__tests__ components/ui/__tests__"
        status: pass
      - kind: manual_procedural
        ref: "Task 3 checkpoint checks 2-4: provider dropdown fully on-screen at normal and tablet width; ticket badge/reference/link on one line with no wrap; no-provider-configured hides the action, failed creation shows only the error toast, outward link opens in a new tab"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-08-18
status: complete
---

# Phase 73 Plan 06: Webhook Event Picker + Manual ITAM Ticketing UI Summary

**Eight ITAM webhook events wired into the existing subscription picker, plus a three-state Create Ticket row action on both ITAM tables that becomes a linked Jira/ServiceNow reference once a ticket exists — held-out visual checks (event-picker growth, dropdown edge clipping, long ticket reference) all confirmed in a live browser.**

## Performance

- **Duration:** 12 min (this continuation session; Tasks 1-2 executed and committed in the same run before the checkpoint)
- **Completed:** 2026-08-18
- **Tasks:** 3 (2 auto, 1 checkpoint:human-verify — approved)
- **Files modified:** 5

## Accomplishments
- `WebhookEvent` union extended with the 8 new ITAM event types, cross-checked character-for-character against `backend/itam_webhook_events.py`; `WebhookManagement.tsx`'s `availableEvents` array extended with the same 8 strings, no markup/scroll-container changes needed
- `ItamTicketProvider` type (`'jira' | 'servicenow'`) plus additive `ticket_ref`/`ticket_provider`/`ticket_url` fields on `Asset` and `ItamAssetRequest`; `createItamTicket` API client function added, throwing on non-ok responses so callers drive the error toast
- Three-state Create Ticket row action added to `LifecyclePanel.tsx` and `RequestsPanel.tsx`: hidden when no provider configured, direct-create text link when exactly one provider is configured, cloned dropdown menu when both are configured; ticket-reference display (provider badge + reference + outward link, `noopener noreferrer`, new tab) replaces the action once a ticket exists
- All four held-out visual checks from the UI-SPEC (webhook picker growth to 16 entries, provider dropdown at the table's right edge at normal and tablet width, long ticket reference on one line, no-provider/failure/new-tab-link behaviors) verified live and approved by the user — no code changes required by the checkpoint itself

## Task Commits

1. **Task 1: Types, API client function, and the webhook event picker entries** - `2dd52163f` (feat)
2. **Task 2: Three-state Create Ticket row action on both ITAM tables** - `2cc11573f` (feat)
3. **Task 3: Held-out visual checks** - checkpoint:human-verify, approved, no code change (verification-only per plan text)

**Plan metadata:** (this commit) `docs: complete plan`

## Files Created/Modified
- `types.ts` - `WebhookEvent` union +8 ITAM events; `ItamTicketProvider` type; `ticket_ref`/`ticket_provider`/`ticket_url` on `Asset` and `ItamAssetRequest`
- `services/apiService.ts` - `createItamTicket(entityKind, entityId, provider)` client function
- `components/WebhookManagement.tsx` - `availableEvents` array extended with the 8 new event strings
- `components/itam/LifecyclePanel.tsx` - `ticketMenuAssetId`/`ticketActioningId` state, three-state ticket row action, ticket-reference display
- `components/itam/RequestsPanel.tsx` - `ticketMenuRequestId` state (reused `actioningId`), three-state ticket row action, ticket-reference display

## Decisions Made
- Task 3 is a verification-only checkpoint per its plan text (`type="checkpoint:human-verify"`, no `<files>` or `<action>` producing a diff) — the user's live-browser approval satisfies its acceptance criteria with no commit of its own, matching the plan's held-out-check framing.

## Deviations from Plan

None — plan executed exactly as written across all three tasks. No Rule 1-4 auto-fixes were needed during Tasks 1-2 (confirmed via commit messages and diffs); Task 3 required no code and none was added.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

ROADMAP success criteria 2 and 3 for Phase 73 are both complete end-to-end: operators can discover and subscribe to all 8 ITAM event types through the existing webhook picker, and can create a Jira/ServiceNow ticket from either ITAM table with the resulting reference linked back to the provider. Requirements ITAM-API-02 and ITAM-API-03 fully delivered (backend in 73-04, frontend in this plan). No blockers for subsequent Phase 73 plans.

---
*Phase: 73-api-integrations*
*Completed: 2026-08-18*

## Self-Check: PASSED

All 5 modified files confirmed present on disk (`types.ts`, `services/apiService.ts`, `components/WebhookManagement.tsx`, `components/itam/LifecyclePanel.tsx`, `components/itam/RequestsPanel.tsx`), plus this SUMMARY.md. Both task commits (`2dd52163f`, `2cc11573f`) confirmed present in `git log --oneline --all`.
