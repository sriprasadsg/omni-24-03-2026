---
status: diagnosed
trigger: "Phase 85 UAT test 4 / gap G-85-4: fix CR-501 (GET /api/notifications/history bypasses the notice audience filter) and WR-502 (staff-only ticket text readable by every non-reporter view:dashboard user)"
created: 2026-11-09
updated: 2026-11-09
goal: find_root_cause_only
symptoms_prefilled: true
---

## Current Focus

hypothesis: CONFIRMED. CR-501 = a second reader of db.notifications (reporting_endpoints.get_notification_history) was written before and never moved onto the shared audience filter; the filter lives as a private helper inside notification_endpoints.py and the only structural test inspects that one module. WR-502 = the platform has no "ticket staff" permission at all; every ticket route is view:dashboard and the projection is keyed on "is the reporter", not on "is staff".
test: reproduction on a throwaway Mongo database (dropped afterwards) calling the route functions directly; code reading of every notifications and ticket route
expecting: n/a (diagnosed)
next_action: hand the diagnosis to /gsd-plan-phase 85 --gaps (no source edits in this session)

## Symptoms

expected: GET /api/notifications/history applies the same audience filter as the other notice routes; staff-only ticket text (hidden comments, desk state, AI drafts) is hidden from every viewer without the ticket-staff permission, not only the reporter.
actual: History query is `{"tenant_id": tenant_id}` (or `{}` for super roles) plus severity; no audience filter. Ticket routes return the stored ticket to everyone except the reporter.
errors: none (authorization / data exposure gap)
reproduction: Test 4 in .planning/phases/85-first-line-service-desk/85-UAT.md
started: UAT 2026-11-09; raised by the gap-round review as CR-501 / WR-502

## Eliminated

- hypothesis: History route leaks across tenants for tenant roles
  evidence: TenantIsolatedCollection._inject_tenant_id (database.py:65-83) forces `tenantId` = context tenant on every find for non-platform contexts, so a tenant user's history is already confined to their tenant. The leak is within the tenant (audience dimensions), plus the Super Admin all-tenant view.
  timestamp: 2026-11-09
- hypothesis: "tenant-less match for non-super roles" (`{"tenant_id": None}`) is exploitable today
  evidence: authentication_service.py:324-340 and :394-408 reject any token without tenant_id (401), and the route takes get_current_user (JWT) only, so `tenant_id` is never None for a signed-in caller; the wrapper adds `tenantId: ctx` anyway. Not reachable now; cheap hardening only.
  timestamp: 2026-11-09
- hypothesis: There are more notification readers than the history route
  evidence: grep of every `notifications.find|find_one|aggregate|update_*|delete_*` in backend (excluding venv/tests): readers for a signed-in user are notification_endpoints.py (4 routes, all via _reader_filter) and reporting_endpoints.py:217 only. Others are system writers/jobs: notification_service.py:83, pending_agents.py:275/351, approval_service.py:168, itdr_service.py:184, send_pending_emails.py:19/36, retention_service.py:73. No first-party UI/agent calls /api/notifications/history (grep over ts/tsx/js/py/rs found only the route and test_catalogue_slice_settings_ops.py:104).
  timestamp: 2026-11-09
- hypothesis: review's suggested permission "manage:tickets" exists, or `_require_ticket_access` is a staff test
  evidence: no `manage:tickets` / `view:tickets` in rbac_defaults.ROLE_DEFAULTS, shared/catalogue-access.json or tenant-feature-switches (only a stale feature_catalog.py:20 label). knowledge_helpdesk_endpoints.py:212-217 `_require_ticket_access` is literally `has_permission("view:dashboard")`. There is no technician role or permission in the backend.
  timestamp: 2026-11-09

## Evidence

- timestamp: 2026-11-09
  checked: backend/reporting_endpoints.py:202-221 (git diff shows only the user's decorator guards on /api/reports/*; the history route is untouched WIP-wise)
  found: query = `{}` for {"Super Admin","super_admin","platform-admin"} else `{"tenant_id": tenant_id}`; optional severity; no recipient / excludeRecipients / tenant_admins clause; no permission lookup.
  implication: CR-501 confirmed at HEAD.
- timestamp: 2026-11-09
  checked: reproduction script (scratchpad repro_85_gap.py) on throwaway DB omni_test_*, notices stored the way send_alert stores them (tenantId and tenant_id both set)
  found: |
    FEED    carol (view:dashboard only): carol-only, staff-for-alice-excluded, tenant-wide
    HISTORY carol:  admins, alice-only, carol-only, staff-for-alice-excluded, tenant-wide
    FEED    alice:  alice-only, tenant-wide
    HISTORY alice:  admins, alice-only, carol-only, staff-for-alice-excluded, tenant-wide   <- the notice she is excluded from, and carol's
    HISTORY super admin: also other-tenant (a per-person notice of tenant t2)
    A notice that carries only tenantId (approval_service JIT, itdr "global") is in carol's FEED but NOT in HISTORY (snake `tenant_id` mismatch).
  implication: history leaks per-person notices (D-33), tenant_admins-audience notices (spec C3) and the excluded staff-comment notice (WR-201) to any view:dashboard user; Super Admin history ignores both the tenant and the person; and history silently omits tenantId-only notices.
- timestamp: 2026-11-09
  checked: backend/notification_endpoints.py:64-90 `_reader_names`, `_reader_filter`; routes at :93-150; backend/tests/test_service_desk_notification_audience.py:223-230
  found: `_reader_filter(current_user, tenant_id)` is private to notification_endpoints, depends only on rbac_service (get_user_permissions) and returns `{"tenantId": ..., "metadata.audience": {"$ne": "tenant_admins"} (unless "*" or manage:agents), "$and": [recipient OR no recipient; excludeRecipients $nin me]}`. The structural test loops over the four names `get_notifications, mark_as_read, mark_all_as_read, delete_notification` of `ne` only, looking for a Name call `_reader_filter`.
  implication: the bypass is structurally untested; moving the helper must keep a Name `_reader_filter` in those four functions (or the test must be updated), and tests patch `ne.rbac_service.get_user_permissions` (a singleton attribute, so it keeps working from a new module).
- timestamp: 2026-11-09
  checked: import graph
  found: notification_endpoints imports database, notification_service, auth_types, tenant_context, rbac_service; reporting_endpoints already imports rbac_utils (which imports rbac_service), notification_service, auth_roles. rbac_service imports authentication_service, database, permission_vocabulary, rbac_defaults, tenant_features; none import reporting_endpoints or notification_endpoints.
  implication: a new module (e.g. backend/notification_audience.py) importing only rbac_service (+typing) cannot form a cycle.
- timestamp: 2026-11-09
  checked: notice writers' field names (notification_service.py:83-88, pending_agents.py:275, approval_service.py:168, itdr_service.py:184)
  found: send_alert and pending_agents write both `tenantId` and `tenant_id`; approval_service writes `tenantId` only; itdr writes `tenantId: "global"`; the wrapper's insert_one sets `tenantId` for tenant contexts. `tenantId` is the field every reader, the retention gate (retention_gate.py:58) and the index (database.py:331) use.
  implication: the review's fix snippet (pop `tenantId`, filter on snake `tenant_id`) would keep the history incomplete; the shared filter's `tenantId` is the right field. Snake `tenant_id` is only ever a secondary copy.
- timestamp: 2026-11-09
  checked: backend/tickets_endpoints.py (all 17 routes), tickets_config_endpoints.py, tickets_workflow_endpoints.py, service_desk_endpoints.py, knowledge_helpdesk_endpoints.py:212
  found: every ticket route is `has_permission("view:dashboard")` except delete_ticket (manage:settings) and template/queue/webhook admin (manage:settings). `_shown` (projection.for_viewer) and `_shown_history` apply the reporter projection only when `projection.is_reporter(ticket, user)`. list_tickets (:57-97) lists every tenant ticket, `reporter` is just an optional client filter (UI "My tickets" checkbox, InternalTicketsDashboard.tsx:457, 510, default false). get_ticket (:118-126), get_history (:271-283), and the returns of update/comment/links/work-log/approve/reject/escalate all return the stored ticket to non-reporters.
  implication: WR-502 confirmed; the staff test does not exist anywhere, so the projection falls back to "not the reporter = staff".
- timestamp: 2026-11-09
  checked: backend/service_desk_endpoints.py:82-85, 87-110, 123-148, 188-207
  found: `_staff_only` refuses only the reporter (403); GET /{id}/service-desk returns `draft = projection.staff_view(...)` (answer text, draftReason, citations) to every non-reporter; send / edit-and-send / discard draft and the cited-article reader (`for_requester = is_reporter`) work for every non-reporter view:dashboard user.
  implication: WR-502 is larger than the review says: it is not only a read exposure; any view:dashboard colleague (role user or viewer) can SEND, edit or discard another person's AI draft. D-10 says "anyone who can reply on the tenant's tickets today", AR-85-01/-04 accepted "staff with ticket access already see every comment", and T-85-93/AR-85-09 accepted a reporter with staff permissions: the user's decision to fix WR-502 supersedes those acceptances, which should be re-recorded.
- timestamp: 2026-11-09
  checked: reproduction of the projection and `_staff_only` (same script)
  found: reporter alice: comments=[c3] desk=False history=[]; colleague carol role=viewer and carol role=user: comments=[c1 staff note, c2 AI draft, c3] desk=True history=[draft_sent, commented]; `_staff_only(carol viewer)` passes (may send/edit/discard), refuses only the reporter.
  implication: confirms the exposure for the two default roles that hold only view:dashboard-class permissions.
- timestamp: 2026-11-09
  checked: backend/rbac_defaults.py:40-148 (ROLE_DEFAULTS), permission_vocabulary.py, shared/catalogue-access.json:171 (internalTickets, permission view:dashboard, routes /api/tickets, no write string)
  found: roles holding view:dashboard: tenant_admin, user, analyst, security_analyst, incident_responder, viewer, platform_support (super_admin via "*"). Not held by itam_*, platform_billing, partner_*. Of these only tenant_admin holds manage:settings; tenant_admin, analyst, security_analyst, incident_responder hold investigate:security; `user` and `viewer` hold neither. The tests' reporter, technician and colleague (ALICE, BOB, CAROL in tests/service_desk_support.py:81) are all role "user", so the test world has no staff/non-staff distinction either.
  implication: an explicit staff test needs a permission string. KNOWN_PERMISSIONS is derived from ROLE_DEFAULTS + catalogue-access.json + tenant-feature-switches, so a new `manage:tickets` is a cross-cutting change (see Resolution).
- timestamp: 2026-11-09
  checked: UI (components/serviceDesk/requesterComments.ts, InternalTicketsDashboard.tsx:741, 922, 1415-1422)
  found: `visibleComments` filters only when `viewerIsReporter` (ticket.reporter == signed-in email, or deskView.isRequester, or unknown viewer); for everyone else it renders all server-returned comments. The dashboard has no permission-based staff concept; it relies on deskView flags and on what the server returns.
  implication: the UI needs no change for WR-502 if the server stops returning other people's tickets / staff text to non-staff; a non-staff viewer then sees only their own (already projected) tickets, which the UI already handles. Optional UI polish: hide staff-only controls (reply picker, draft panel, bulk/merge) for non-staff via a flag from the server.
- timestamp: 2026-11-09
  checked: ticket_notifications.py:116-160 (notify_comment_added), notification_service.py:92-94
  found: staff-only comment notices are tagged `audience: ticket_staff` with title + ticket title, but `_reader_filter` never filters on `ticket_staff` (protection is only `excludeRecipients: [reporter]`). Other ticket notices (created, status changed, assigned, SLA, escalated incl. "Reason: ...") carry no audience and no recipient, so every tenant user reads them in the feed.
  implication: once non-staff are not supposed to read other people's tickets, the shared filter should also hide `audience: ticket_staff` from non-staff (one clause, in one place); the untagged ticket lifecycle notices are the same class of exposure and need a product decision (outside the stated G-85-4 truth).

## Resolution

root_cause: |
  CR-501 (code + structure): `GET /api/notifications/history` (reporting_endpoints.py:202-221) is a second, older reader of
  db.notifications. The gap round (85-28) put the notice audience rules into `_reader_filter`, a private helper of
  notification_endpoints.py, and pointed only the four routes of that module at it. The history route builds its own
  `{"tenant_id": ...}` query (snake-case copy of the tenant, `{}` for super roles), so it has no tenant_admins clause, no
  `metadata.recipient` clause and no `metadata.excludeRecipients` clause, and it omits notices that carry only `tenantId`. The only
  structural test (test_every_notification_route_starts_from_the_reader_filter) inspects four named functions of one module,
  so nothing fails when another module reads the collection. Verified on a throwaway DB: Carol's history shows Alice's per-person
  notice and the tenant_admins notice her feed hides; Alice's history shows the staff notice she is excluded from; the Super Admin
  history shows another tenant's per-person notice. The tenant boundary itself holds for tenant roles (DB wrapper).
  WR-502 (decision gap + missing primitive): the platform has no "ticket staff" test. Ticket access is `view:dashboard` on every
  route (the same permission `_require_ticket_access` and the Tickets catalogue entry name), `manage:tickets` does not exist, and
  there is no technician role. The reporter projection (projection.for_viewer / history_for_viewer, tickets_endpoints._shown /
  _shown_history) and the desk guard (service_desk_endpoints._staff_only) are keyed on `is_reporter`, so "not the reporter" =
  "staff". Result: hidden comments, desk state, AI drafts and history are returned to any view:dashboard user (role user / viewer
  included), GET /api/tickets lists every tenant ticket with no reporter restriction, and the same users can send, edit or
  discard another person's AI draft (service-desk routes). It was a deliberate acceptance (D-10, D-11, AR-85-01/-04, T-85-93) that
  the user has now reversed.
fix: (none; diagnose-only)
verification: (none; diagnose-only)
files_changed: []
