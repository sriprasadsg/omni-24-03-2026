---
phase: 85-first-line-service-desk
reviewed: 2026-11-09T00:00:00Z
depth: standard
files_reviewed: 36
files_reviewed_list:
  - backend/knowledge_helpdesk_endpoints.py
  - backend/notification_audience.py
  - backend/notification_endpoints.py
  - backend/rbac_defaults.py
  - backend/reporting_endpoints.py
  - backend/service_desk/projection.py
  - backend/service_desk_endpoints.py
  - backend/tests/service_desk_knowledge_support.py
  - backend/tests/service_desk_portal_support.py
  - backend/tests/service_desk_support.py
  - backend/tests/test_notification_audience_structure.py
  - backend/tests/test_notification_history_audience.py
  - backend/tests/test_rbac_defaults.py
  - backend/tests/test_service_desk_comments.py
  - backend/tests/test_service_desk_knowledge_gaps.py
  - backend/tests/test_service_desk_notification_audience.py
  - backend/tests/test_service_desk_portal_routes.py
  - backend/tests/test_service_desk_reporter_ticket.py
  - backend/tests/test_service_desk_staff_routes.py
  - backend/tests/test_service_desk_tracer.py
  - backend/tests/test_ticket_staff_access.py
  - backend/tests/test_ticket_staff_actions.py
  - backend/tests/test_ticket_staff_lists.py
  - backend/tests/test_ticket_staff_routes_structure.py
  - backend/tests/test_tickets.py
  - backend/ticket_access.py
  - backend/ticket_reports_endpoints.py
  - backend/tickets_config_endpoints.py
  - backend/tickets_config_mixin.py
  - backend/tickets_endpoints.py
  - backend/tickets_service.py
  - backend/tickets_workflow_endpoints.py
  - components/RoleEditorModal.tsx
  - shared/catalogue-access.json
  - src/__tests__/RoleEditorModal.test.tsx
  - types.ts
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
status: issues_found
---

# Phase 85: Code Review Report (second gap round, G-85-4)

**Reviewed:** 2026-11-09
**Depth:** standard (incremental: `git diff 009402280..HEAD`, with surrounding code read as needed)
**Files Reviewed:** 36
**Status:** issues_found

## Summary

Reviewed the G-85-4 changes (plans 85-30..85-35): the shared notice audience filter (CR-501), the
`manage:tickets` ticket-staff test (`ticket_access.py`), the router-level `ticket_viewer` guard, the own-tickets
scope in lists/stats/reports/CSV, the staff gating of draft and workflow routes, and the role table, manifest and
role-editor additions. Working copies of `tickets_endpoints.py`, `reporting_endpoints.py` and
`catalogue-access.json` equal HEAD, as stated.

The core design holds up. I traced the following and found no defect:
- The guard covers every `{ticket_id}` route of the five routers. Route registration order does not let a
  single-segment `{ticket_id}` route shadow `/webhooks`, `/stats` or `/bulk`.
- The `$and` own-tickets scope is not overwritten anywhere. `list_tickets`, `get_stats` and all report filters
  spread or extend the base filter without a competing `$and` key.
- Staff and API-key narrowing are consistent between `is_ticket_staff` and `has_permission`.
- `projection` fails closed when `staff` is omitted, and there are no other call sites of `for_viewer`,
  `history_for_viewer` or `staff_view`.
- Role defaults merge from the table, so existing tenants' stored role documents need no migration.
- The new permission is in the permission vocabulary through the role table and the manifest.

The remaining problems are gaps around the new rules: one flag still follows the old rule, one live channel
bypasses the new audience filter, requesters can still set staff-only fields at creation, and the shared filter
does not fail closed. No critical issue.

## Warnings

### WR-601: `canSeeGaps` still derives from `view:dashboard`, so the Gaps tab is offered to people the routes refuse

**File:** `backend/knowledge_helpdesk_endpoints.py:343` (routes at 213-226, 249-263, 283)
**Issue:** Plan 85-35 moved every gap route (`/helpdesk/gaps`, dismiss, restore, `/helpdesk/articles`) to
`manage:tickets` plus `manage:ai_risks` through `_require_ticket_access`. `list_flags` still computes
`"canSeeGaps": manage and has("view:dashboard")`. `KnowledgeBaseDashboard.tsx:69-73, 206` uses that flag to show
the tab and to fire `fetchGaps`.
- A Knowledge Base editor with `manage:ai_risks` and `view:dashboard` but not `manage:tickets` (any custom role
  built as the new D-40 default, or the built-in `user`/`viewer` plus an AI-risk grant) now sees a Gaps tab and a
  count request that both 403.
- The reverse case, `manage:tickets` plus `manage:ai_risks` but no `view:dashboard`, can use the routes but never
  sees the tab.
- `test_the_flags_follow_the_callers_permissions` (`tests/test_service_desk_knowledge.py:170`) still encodes the
  old rule ("editor" = manage without view:dashboard) and passes only because "manager" holds both permissions. It
  does not exercise the new rule.

**Fix:**
```python
manage = has("manage:ai_risks")
return {
    "canManageArticles": manage,
    "canSeeGaps": manage and has(ticket_access.TICKET_STAFF),   # same rule as _require_ticket_access
    ...
}
```
Better, derive both from one helper so the flag and the route guard cannot drift again. Add a case to the flags
test for a role that holds `manage:ai_risks` and `view:dashboard` without `manage:tickets`. Note that
`ticket_access.is_ticket_staff` also applies API-key scope narrowing, which `has()` here does not.

### WR-602: Live WebSocket push still broadcasts `tenant_admins` notices (agent host details) to every user of the tenant

**File:** `backend/notification_service.py:91-100` and `backend/pending_agents.py:275-290` (outside the listed files; same theme as CR-501)
**Issue:** The new `reader_filter` hides `metadata.audience == "tenant_admins"` notices from users without
`manage:agents`, but only on the REST routes. Two live-push paths ignore the audience:
- `notification_service.send_alert` skips the socket only for `audience == "ticket_staff"`. Notices with
  `audience == "tenant_admins"` (the desk breaker notice in `service_desk/withdraw.py:133-136`) go to
  `broadcast_notification(tenant_id, ...)`, which emits to every connected client of the tenant
  (`websocket_manager.py:380`).
- `pending_agents._post_in_app` broadcasts the full title, message and metadata, with no audience check. The
  text names the agent's hostname and seat usage, which the filter comment itself calls "host details of agents
  waiting for approval (spec C3)".
- `NotificationCenter.tsx:124` renders every pushed `notification` event.

So a viewer or requester in the tenant receives in real time what the CR-501 fix now hides from the feed and
history.

**Fix:** Treat every audience-tagged notice like the `ticket_staff` one: skip the tenant broadcast whenever
`metadata.audience` is set, or push to a per-permission room. In `_post_in_app`, skip the broadcast (the feed has
the record) or broadcast only a generic title with no hostname or counts, since the socket cannot be filtered.
```python
if tenant_id and not (metadata or {}).get("audience"):
    ...  # broadcast
```
Add the audience-tagged case to `test_service_desk_notification_audience.py`.

### WR-603: A requester can still set staff-only fields (assignee, assignee_group, watchers, approval_required, sla_hours, due_date) when creating a ticket

**File:** `backend/tickets_endpoints.py:138-201` (fields in `backend/tickets_models.py:34-52`; consumed at `tickets_service.py:173`)
**Issue:** G-85-4 (D-39) makes assigning, watchers, approval, bulk update, merge and escalation staff-only.
`POST /api/tickets` stays open to every `view:dashboard` caller (`create_ticket` is on the structure test's
`OPEN_ROUTES` list with the reason "the reporter is set from the caller"). It passes `body.model_dump()` straight
into `tickets_service.create_ticket`, so a requester supplies all those fields. The structure test classifies
the route by its permission, not by which body fields it honours, so it cannot catch this.
- `watchers` is the practical hole. `add_watcher` now needs `manage:tickets`, but a requester can put arbitrary
  addresses (including addresses outside the tenant) in `watchers` at creation. `ticket_notifications._recipients`
  emails watchers on escalation (reason and priority text), on staff-comment notices (ticket title) and other
  events, so that address receives staff-side ticket traffic.
- `assignee`/`assignee_group` let a requester route their ticket to a chosen technician and skip `auto_assign`.
- `approval_required` and `sla_hours` let a requester influence workflow and SLA state.

**Fix:** In `create_ticket`, drop the staff-only keys when the caller is not ticket staff:
```python
if not await ticket_access.is_ticket_staff(current_user):
    for key in ("assignee", "assignee_group", "watchers", "approval_required", "sla_hours", "due_date"):
        data.pop(key, None)
```
Also apply this to the `template_id` default-merge branch. Add a test that a requester's `watchers` and
`assignee` are not stored.

### WR-604: `reader_filter` does not fail closed on an empty tenant id; the feed, mark-read and delete routes can match notices with no tenant

**File:** `backend/notification_audience.py:31` (callers: `backend/notification_endpoints.py:73, 87, 104, 119`)
**Issue:** The filter is documented as the one audience filter, but for a non-`all_tenants` call it builds
`{"tenantId": tenant_id}` with whatever it is given. If `get_tenant_id()` returns `None` or `""` (the history
route guards this with a 403 for non-Super-Admins; the four notification routes do not), the query becomes
`{"tenantId": None}`, which in MongoDB also matches documents where `tenantId` is missing or null. The code writes
such documents: `approval_service.py:168-176` stores `"tenantId": request.get("tenantId") or None`, and the
`tenantId` index is the only tenant guard. Those notices would then be listed, marked read and deleted across
tenants by a caller with no tenant context. D-41 says a non-Super-Admin without a tenant must get 403. That is
enforced for one route, not in the shared filter.

**Fix:** Make the shared filter refuse instead of widening:
```python
if not all_tenants and not tenant_id:
    raise HTTPException(status_code=403, detail="Tenant context required")
```
or return a match-nothing query, for example `{"tenantId": {"$in": []}}`. Then drop the duplicated check in
`get_notification_history`.

## Info

### IN-601: Stale module docstring in `ticket_access.py`

**File:** `backend/ticket_access.py:11-13`
**Issue:** The docstring says "A later gap plan adds the own-tickets scope here", but `own_tickets_filter` and
`tickets_scope` are already in the same file (lines 70-82).
**Fix:** Describe the module as it is: staff test, viewer guard, own-tickets scope.

### IN-602: The own-tickets filter and `is_reporter` can disagree on what "the same person" means

**File:** `backend/ticket_access.py:70-75` vs `backend/service_desk/projection.py:73-86`
**Issue:** `is_reporter` compares `strip().casefold()` of both sides: the stored reporter is stripped and fully
Unicode casefolded. `own_tickets_filter` matches the caller's stripped name against the raw stored `reporter`
with an anchored `re.IGNORECASE` regex. A stored reporter with leading or trailing whitespace, or a name whose
casefold differs from simple case-insensitive matching (for example `ß`, Turkish dotted I), passes
`ticket_viewer` (the person can open the ticket) but is missing from their list, stats and reports. The opposite
mismatch is not possible. Both rules are meant to be one, per UD-2, so they should be defined once.
**Fix:** Normalise `reporter` when it is written (`create_ticket` stores the stripped, casefolded actor) and note
that invariant in `own_tickets_filter`, or allow optional surrounding whitespace in the pattern
(`^\s*{name}\s*$`).

### IN-603: The notice-reader structure test accepts a function that calls `reader_filter` but never uses the result

**File:** `backend/tests/test_notification_audience_structure.py:97-98` (touch list at 29-32)
**Issue:** `filtered` is true if the function calls `reader_filter` anywhere. A route that calls it for show and
queries with its own dict passes the scan (the header lists this under `no_claim`). The `_TOUCHING` set also
omits `bulk_write`, `count`, `estimated_document_count` and `find_raw_batches`, so a route using one of them on
`db.notifications` is not seen. The scan then relies only on the four-route floor.
**Fix:** Require that a name assigned from `reader_filter(...)` (or the call itself) appears in the arguments of a
touching call in the same function. Add the missing method names to `_TOUCHING`.

### IN-604: No frontend code reads `manage:tickets`; the Tickets screen still offers staff actions to requesters

**File:** `types.ts:237`, `components/RoleEditorModal.tsx:37` (only consumers); `shared/catalogue-access.json:171`
**Issue:** The only frontend references to the new permission are the type and the role-editor label. Ticket
screens do not check it, so a requester (`user`, `viewer`, a custom role without it) still sees assign, approve,
escalate, merge, bulk and watcher controls that now return 403, and a staff-only draft panel is simply absent.
The manifest `write` list for `internalTickets` still includes `view:dashboard`, so the catalogue guard does not
narrow these writes; only the route-level guard does. If the plan defers the UI to a later phase, record it in
the disposition file so it does not get lost.
**Fix:** Gate the staff controls on `manage:tickets` in the ticket screens, and give the manifest `write` entry
the same intent comment as the other mixed-permission entries.

---

_Reviewed: 2026-11-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
