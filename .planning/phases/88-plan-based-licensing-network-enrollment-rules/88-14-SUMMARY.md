---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 14
subsystem: ui
tags: [pending-agents, holds, network-range, cross-tenant, restore, react, vitest]
status: complete

requires:
  - phase: 88-05
    provides: approve body widenTo, 422 widen errors, new_network hold
  - phase: 88-07
    provides: cross_tenant_duplicate hold, platform-only crossTenant field, 409 reason_changed
  - phase: 88-09
    provides: GET /api/agents/pending/moved and POST /api/agents/pending/{id}/restore
provides:
  - PendingAgentsPanel reads trial_ended, new_network and cross_tenant_duplicate holds plainly (no organization name for tenant admins)
  - Allow network with an optional range sent as widenTo; Approve move with a confirmation; reason_changed reload
  - components/PendingMovedAgents.tsx, the platform list of moved agents with Restore
affects: [88-16]

tech-stack:
  added: []
  patterns:
    - "approve() keeps the typed range in the seat-shortage state so the raise-limit retry sends the same widenTo"
    - "success toast text comes from one helper (approvedText) driven by the server answer and the row's reason"
    - "S7 list renders as a sibling of the amber card, and alone when nothing is waiting"

key-files:
  created:
    - components/PendingMovedAgents.tsx
    - src/__tests__/PendingMovedAgents.test.tsx
  modified:
    - components/PendingAgentsPanel.tsx
    - src/__tests__/PendingAgentsPanel.test.tsx

key-decisions:
  - "UI-SPEC wins over the plan text: the panel's early return keeps the moved list for deciders when nothing waits, PendingMovedAgents takes a refreshKey that the panel moves after every load"
  - "Bulk approve confirms (window.confirm) only when the selection holds cross-tenant or new-network rows; there is no range field in bulk"
  - "The moved list is a sibling of the amber card (a neutral .card), not nested inside it"
  - "A moved row without a hostname reads 'Agent' and without an organization 'another organization'"

patterns-established:
  - "Cross-tenant organization names are rendered only for canDecide and only when the server sent crossTenant (D-36)"

requirements-completed: [LIC-05, LIC-06, LIC-03]

duration: 12 min
completed: 2026-11-11

actuals:
  tokens: 21000
  tasks: 2
  commits: 4
plan_head_before: ed446019995e162ea8bb5a1fc8a19f9068171a36
plan_head_after: e44298d20249c3183f1503866d84e4ac5523693c

coverage:
  - deliverable: "Tenant admins read the new holds plainly with no organization name and no controls"
    verification:
      - kind: test
        ref: "src/__tests__/PendingAgentsPanel.test.tsx#tenant admins read each hold plainly, get no controls and never see another organization"
        status: pass
    human_judgment: false
  - deliverable: "Allow network with optional range (widenTo), 422 inline, retry keeps the range"
    verification:
      - kind: test
        ref: "src/__tests__/PendingAgentsPanel.test.tsx#allows the exact address when the range is empty and sends widenTo only when typed"
        status: pass
      - kind: test
        ref: "src/__tests__/PendingAgentsPanel.test.tsx#keeps the typed range when a seat shortage turns into approve-and-raise"
        status: pass
    human_judgment: false
  - deliverable: "Cross-tenant move shown to deciders and approved only after confirmation; reason_changed reloads"
    verification:
      - kind: test
        ref: "src/__tests__/PendingAgentsPanel.test.tsx#shows the other organization to the decider and approves a move only after confirmation"
        status: pass
      - kind: test
        ref: "src/__tests__/PendingAgentsPanel.test.tsx#a changed reason shows a warning, reloads the list and drops the typed range"
        status: pass
    human_judgment: false
  - deliverable: "Bulk approve confirmation and not-blocked reject wording"
    verification:
      - kind: test
        ref: "src/__tests__/PendingAgentsPanel.test.tsx#bulk approve confirms moves and new networks first, and only when they are selected"
        status: pass
    human_judgment: false
  - deliverable: "Moved agents list with Restore, also when nothing is waiting"
    verification:
      - kind: test
        ref: "src/__tests__/PendingMovedAgents.test.tsx"
        status: pass
      - kind: test
        ref: "src/__tests__/PendingAgentsPanel.test.tsx#deciders still see the moved list when nothing is waiting"
        status: pass
    human_judgment: false
  - deliverable: "Visual fit of the new controls (min-h-8 range field, buttons, moved card) in the live dense table"
    human_judgment: true
    rationale: "No test asserts spacing, contrast or layout; the user checks it when the UI is published (88-16)"
---

# Phase 88 Plan 14: Pending holds, network range and moved agents Summary

**Pending agents panel now shows the trial, new-network and cross-tenant holds, lets a platform decider allow a network (exact address or a typed range sent as widenTo) and confirm a cross-tenant move, and lists/restores agents retired by a move.**

## Accomplishments

- Tenant admins read `Free trial ended`, `New network {ip}, waiting for platform approval` and the unnamed cross-tenant sentence, with no Approve/Reject/range control and no other organization's name (D-36).
- New-network rows: `Allow network` button, `Range (optional)` field with helper, empty field posts `{raiseLimitBy: 0}`, a typed range adds `widenTo`; a 422 shows under the field and the row keeps its typed value; a row without an observed address has the button disabled with the stated helper. The seat-shortage retry keeps the typed range.
- Cross-tenant rows: deciders see `Live in {org} as {host}` and `Approve move`, which confirms the move and retirement first; `409 reason_changed` shows the warning toast, drops the typed range and reloads.
- Bulk approve confirms when the selection holds cross-tenant or new-network rows; reject of cross-tenant/duplicate holds says the machine is not blocked; intro text no longer speaks only of seats; success toasts name the allowed network, the not-added case and the move.
- `PendingMovedAgents`: lists `GET /api/agents/pending/moved` as `{host} in {org}, moved {Mon D, YYYY} ({silent copy | approved move})` with a confirmed Restore; renders nothing on empty, 403 or failure; refetches on `refreshKey`; stays visible when nothing is waiting.

## Task Commits

1. Task 1 RED: `0e06878f9` (test) - GREEN: `8972119b7` (feat)
2. Task 2 RED: `b9619b63b` (test) - GREEN: `e44298d20` (feat)

## Deviations from Plan

### UI-SPEC deltas applied (binding contract)

**1. [Contract delta 1] Moved list also renders when the pending list is empty; refreshKey prop**
- **Found during:** Task 2
- **Fix:** early return is now "no data: nothing; no agents and not canDecide: nothing; no agents and canDecide: only the moved list"; the panel increments a `refreshKey` after every load and passes it down. No file outside the plan's files_modified was touched (the panel increments it internally, so `AgentsDashboard` is unchanged).

**2. [Contract deltas 2-5] Bulk confirm, retry keeps widenTo, new intro text, not-blocked reject wording** - implemented in Task 1 as the UI-SPEC states.

### Auto-fixed Issues

**3. [Rule 1 - Test adaptation] Existing PendingAgentsPanel tests adjusted**
- **Found during:** Tasks 1 and 2
- **Issue:** the read-only test asserted the old seat-only intro (`Contact your provider to add seats`), which the UI-SPEC replaces; and once the panel renders the moved list its extra request would have consumed the existing `mockResolvedValueOnce` queues.
- **Fix:** the intro assertion now matches the new text; the apiService mock routes `/agents/pending/moved` to its own `movedFetch` so the existing queues are unchanged.
- **Files modified:** src/__tests__/PendingAgentsPanel.test.tsx
- **Commits:** 0e06878f9, b9619b63b

**4. [Rule 3 - Layout] The moved list is a sibling of the amber card**
- **Issue:** the plan says "under the pending table"; the UI-SPEC says "under the pending card" with a neutral card, and nesting a `.card` inside the amber tint would clash.
- **Fix:** the panel returns a fragment with the amber card and the moved list side by side.

**Total deviations:** 4 (2 contract deltas, 1 test adaptation, 1 layout note). **Impact:** none on scope; all within the plan's four files.

## Verification

- `npx vitest run src/__tests__/PendingMovedAgents.test.tsx src/__tests__/PendingAgentsPanel.test.tsx`: 28 passed.
- `npx vitest run src/__tests__`: 125 files, 2010 tests passed.
- `npm run typecheck`: no errors for PendingAgentsPanel or PendingMovedAgents.
- `npm run build`: built (dist-new, git-ignored, not published).
- PendingAgentsPanel.tsx 393 lines, PendingMovedAgents.tsx 98 lines.

## Threat Model

T-88-36 (information disclosure) mitigated: `crossTenant` is rendered only when `canDecide` and only when the server sent it; the tenant text is the fixed unnamed sentence; the tenant test asserts the rendered HTML contains neither the other organization's name nor its host.

## Known Stubs

None.

## Issues Encountered

None. Not done here by design: no push, no service restart, no UI publish (88-16 hands those to the user).

## Next Phase Readiness

Ready for 88-15 / 88-16. The panel's focus moves to its heading after an approve, reject or restore (the removed row's button is gone).

## Self-Check: PASSED

- components/PendingMovedAgents.tsx, src/__tests__/PendingMovedAgents.test.tsx: found.
- Commits 0e06878f9, 8972119b7, b9619b63b, e44298d20: found on HEAD.
