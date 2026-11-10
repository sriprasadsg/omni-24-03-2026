---
status: diagnosed
gap_id: G-85-4b
phase: 85-first-line-service-desk
found: 2026-11-10 UAT round 3 (test 4, headless Chromium on the published UI index-fZpr5iK1.js)
goal: find_root_cause_only
---

# Requesters see staff controls on the Tickets screen and they fail silently

## Symptom
Signed in as a temporary ABC User-role requester: the list correctly shows only own tickets, but the ticket
panel shows `→ in progress / → resolved / → closed`, Add watcher, Escalate (with reason box), the Work Log tab,
Links and the row checkboxes + bulk bar. Clicking them sends `PATCH /api/tickets/{id}` 403,
`POST /api/tickets/{id}/escalate` 403 and `POST /api/tickets/{id}/watchers` 403 (nginx log, 08:37 UTC); the
browser console shows `Failed to load resource: ... 403` and nothing appears on screen. Merge is disabled.
Screenshots: `~/omni-archives/uat85-test3/uat85-t4-*.png`.

## Root cause
1. `components/InternalTicketsDashboard.tsx` renders every staff control for every viewer: status buttons
   (~1056-1063), bulk bar (~864-870), watchers (~1276), Escalate (~1323-1335), Merge (~1339-1350), Work Log tab
   (`TABS` ~145) and link/approve controls. It reads `useUser()` (line 436) but never asks
   `hasPermission('manage:tickets')`; the only requester-aware branch is the reply picker
   (`!deskView?.isRequester`, ~1415). This is review finding IN-604 ("no frontend code reads manage:tickets").
2. The handlers `handlePatch` (581-586), `handleEscalate` (651-655), the watcher, work-log, link, approve and
   bulk handlers await the API with no try/catch, so a 403 becomes an unhandled rejection with no toast
   (`showToast` from `utils/toast` is already imported and used for create, merge and download errors).
3. Backend side is correct since G-85-4 (85-30..36): these routes require `ticket_access.TICKET_STAFF`
   (`backend/tickets_endpoints.py` lines 114, 235, 357, 375, 393, 560, 592, 609, 628).

## Fix directions (for the planner, not binding)
- Derive `isTicketStaff = hasPermission('manage:tickets')` once and hide the staff-only controls and the Work Log
  tab for non-staff (a requester keeps New Ticket, own list, the answer panel, comments to IT, files).
- Catch errors in every staff handler and show the API detail with `showToast(..., 'error')` so a control that is
  still reachable never fails silently.
- Hide the staff hint "Comments are visible to staff only unless marked Sent to requester" from requesters
  (copy nit seen in the same run).
- `components/InternalTicketsDashboard.tsx` and `App.tsx` carry the user's uncommitted WIP (+15/-1 and +20/-16):
  the executor must keep those hunks out of the commits (set aside and 3-way restore, as in 85-30..36).

## Evidence
- `.planning/phases/85-first-line-service-desk/85-UAT.md` test 4.
