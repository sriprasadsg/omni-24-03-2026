---
phase: 85-first-line-service-desk
reviewed: 2026-11-09T00:00:00Z
depth: standard
files_reviewed: 31
files_reviewed_list:
  - backend/knowledge_helpdesk_endpoints.py
  - backend/notification_endpoints.py
  - backend/notification_service.py
  - backend/service_desk/checks.py
  - backend/service_desk/lifecycle.py
  - backend/service_desk/messages.py
  - backend/service_desk/model.py
  - backend/service_desk/outcomes.py
  - backend/service_desk/projection.py
  - backend/service_desk/sanitize.py
  - backend/service_desk/worker.py
  - backend/tests/service_desk_support.py
  - backend/tests/service_desk_worker_support.py
  - backend/tests/test_service_desk_comments.py
  - backend/tests/test_service_desk_eval_script.py
  - backend/tests/test_service_desk_handoff.py
  - backend/tests/test_service_desk_knowledge_gaps.py
  - backend/tests/test_service_desk_lifecycle.py
  - backend/tests/test_service_desk_model.py
  - backend/tests/test_service_desk_notification_audience.py
  - backend/tests/test_service_desk_output_checks.py
  - backend/tests/test_service_desk_output_fold.py
  - backend/tests/test_service_desk_reporter_ticket.py
  - backend/tests/test_service_desk_worker.py
  - backend/tests/test_service_desk_write_order.py
  - backend/ticket_notifications.py
  - backend/tickets_endpoints.py
  - components/InternalTicketsDashboard.tsx
  - components/serviceDesk/requesterComments.ts
  - shared/service-desk-requester-comments.json
  - src/__tests__/ServiceDeskRequesterComments.test.tsx
findings:
  critical: 1
  warning: 4
  info: 4
  total: 9
status: issues_found
---

# Phase 85: Code Review Report (gap-round re-review)

**Reviewed:** 2026-11-09
**Depth:** standard
**Files Reviewed:** 31
**Status:** issues_found

This is the **gap-round re-review** of the gap-closure commits 791831738..155ae53dc (plans 85-24..85-29). The prior review
was written at commit `2f8ed35b1` (28 findings, CR-101..IN-403). All findings below are numbered in the 5xx range and do not
reuse a 1xx-4xx ID. For `backend/tickets_endpoints.py` and `components/InternalTicketsDashboard.tsx` the committed code
(`HEAD`) was reviewed; the user's uncommitted attachment-download hunks were not.

## Summary

Verification of the claimed fixes:

| Old ID | Claim | Verdict |
|--------|-------|---------|
| CR-101 | output check bypass via hidden / full-width chars | Closed for the vectors listed. Probed: ZWSP, soft hyphen, bidi override, word joiner, variation selector, CGJ, tag characters, full-width domain, U+3002 / U+FF0E dots, U+2024 dot leader, Cyrillic look-alike label all return `foreign_link`. The folded answer is what `pipeline.answer` posts (`parsed.answer`), so shown text equals checked text. |
| CR-401 | reporter sees staff-only comments | Closed for staff-only **comments** on the reporter's own ticket on every route in `tickets_endpoints.py`. Residual gaps: WR-501 (other ticket fields and history text) and WR-502 (every non-reporter user). |
| WR-101 | httpx `trust_env` | Closed (`model.py:130`, only one `AsyncClient` in the desk). |
| WR-102 / WR-103 | write order | Closed for the documented cases. Residual edge cases: WR-503, WR-504. |
| WR-201 | staff-notice audience | Closed on the feed (`excludeRecipients`) and the socket. **But the same notices are still served unfiltered by a second route, CR-501.** |
| WR-202 | write-route filter | Closed on the four `notification_endpoints.py` routes. Same bypass, CR-501. |
| WR-203 | gap article must be Help desk | Closed (422 before any row is claimed). |
| WR-301..303 | time-stable tests, eval-script DB isolation | Closed. The 355 tests of the changed suites pass on the private mongod (27998). |

The 355 tests in the listed backend suites pass, but they are blind to CR-501 because they only exercise `notification_endpoints.py`.

## Critical Issues

### CR-501: `GET /api/notifications/history` bypasses the whole notice audience filter (relates to WR-201, WR-202, D-33)

**File:** `backend/reporting_endpoints.py:202-221` (consumer of the data the gap round protects in `backend/notification_endpoints.py:64-90`)
**Issue:** The gap round made `_reader_filter` "the one filter" of the notice routes (tenant-admin audience, per-person
`metadata.recipient`, `metadata.excludeRecipients`). The router `reporting_endpoints` is mounted
(`router_registry.py:343`) and exposes `GET /api/notifications/history`, guarded only by `NOTIFICATIONS_GUARD`, whose read
permission is `view:dashboard` (`catalogue_mounts_settings_ops.py:52`), a permission nearly every role holds, including
a ticket's reporter. Its query is `{"tenant_id": tenant_id}` plus an optional severity, over the same `db.notifications`
collection and with no audience filter at all. So any `view:dashboard` user of a tenant still reads:
- the staff-only comment notice the reporter was supposed to be excluded from (WR-201),
- every per-person notice (D-33), including the 100-character preview of staff replies written to other requesters,
- `audience: tenant_admins` notices that carry host details (spec C3), which `_reader_filter` hides from users without `manage:agents`.

The new tests (`test_service_desk_notification_audience.py`) call only the four routes of `notification_endpoints.py`, and
`test_every_notification_route_starts_from_the_reader_filter` inspects only that module, so the bypass is untested.
**Fix:** Move `_reader_filter` to a shared module (for example `notification_audience.py`) and use it in
`get_notification_history` too, keeping the snake-case `tenant_id` field and the severity filter:
```python
from notification_audience import reader_filter
...
query = await reader_filter(_current_user, tenant_id) if user_role not in _NOTIF_SUPER_ROLES else {}
if user_role not in _NOTIF_SUPER_ROLES:
    query.pop("tenantId", None); query["tenant_id"] = tenant_id
```
Also reject a missing tenant for non-super roles (today `{"tenant_id": None}` matches tenant-less platform notices). Extend the structural
test to cover every route in the repository that reads `db.notifications` for a user (`grep "notifications.find"` finds this one).

## Warnings

### WR-501: the reporter projection still returns staff-entered text outside comments (relates to CR-401)

**File:** `backend/service_desk/projection.py:116-147` (`reporter_history`, `reporter_ticket`)
**Issue:** `reporter_ticket` removes only `desk`, filters `comments` and applies `reporter_history`. Everything else of the
stored ticket reaches the reporter unchanged: `work_logs[].description` (technicians' free-text diagnostic notes, same
class as a staff-only comment), `rejection_reason`, `watchers` (other people's e-mail addresses), `custom_fields`,
`endpoint_info`. `reporter_history` keeps every non-`commented` entry whole, so `approved` (`changes.comment`), `rejected`
(`changes.reason`), `merged` (`changes.reason`), `escalated` reasons and `updated` entries (old and new description,
custom fields, watchers) are readable by the reporter through `GET /api/tickets/{id}`, the list, and `/history`.
`test_the_work_log_route_projects_for_the_reporter` only asserts that the planted *comment* text is absent.
**Fix:** Make the projection an allow-list. Drop `work_logs` text (keep hours if wanted) and `watchers`/`custom_fields` that the portal
does not show, and in `reporter_history` pass through only `created`, `updated` entries whose `changes` keys are in
`{"status","priority","assignee"}`, and the commented entries already allowed; drop `approved`, `rejected`, `merged`, `escalated`
or reduce them to action names with `changes = {}`.

### WR-502: staff-only comments stay readable by every tenant user who is not the reporter (CR-401 residual)

**File:** `backend/tickets_endpoints.py:41-46, 118-126` (`_shown`, `get_ticket`) with `backend/service_desk/projection.py:81-86, 143-148`
**Issue:** Authorisation to read a ticket is `view:dashboard` alone (every route in the file). The projection is applied only when
`is_reporter(ticket, user)` is true. So the hidden comments, `desk` state and drafts are removed for the person who raised
the ticket but returned in full to any other user of the tenant with `view:dashboard`, for example an end user who raised a
different ticket, a finance or reporting role, or a colleague of the reporter. `GET /api/tickets?...` also lists every
tenant ticket without a reporter restriction. The D-11 promise (the requester never reads staff text) is only as strong as
"the reporter does not ask a colleague". If the product intends this (all `view:dashboard` roles are staff), it should be
stated and the dashboard permission for ticket reads should be the technician permission; if not, this is the remaining
half of CR-401.
**Fix:** Decide the staff test explicitly. For example, apply `reporter_ticket` to every viewer who lacks the ticket-staff permission
(`manage:tickets` or the permission `_require_ticket_access` uses elsewhere), not only to the reporter, and restrict the list to
`reporter == user` for those viewers.

### WR-503: `send_draft` moves the status first but only undoes it when the turn is lost, not when the turn raises (relates to WR-103)

**File:** `backend/service_desk/lifecycle.py:116-130`
**Issue:** After `move_status(... "pending_customer")` succeeds, `_turn_draft` is awaited unguarded. If it raises (connection loss,
write concern), the exception leaves `send_draft` with the ticket at `pending_customer` (SLA hold clock running as
paused, requester told "waiting on you") and the draft still `draft`. `_put_status_back` runs only on `not won`.
The route returns a 500 and nothing repairs the status; the old order (turn first, then status) had the opposite failure and
WR-103 chose this one deliberately, so the failure path must restore it.
**Fix:**
```python
try:
    won = await _turn_draft(...)
except Exception:
    if moved:
        await _put_status_back(db, tenant_id, ticket_id, comment_id, prior, actor, now)
    raise
```

### WR-504: `outcomes.post` can revert the status of a ticket whose answer was actually stored (relates to WR-102)

**File:** `backend/service_desk/outcomes.py:93-109`
**Issue:** An exception from `ticket_writes.add_comment` is treated as "not stored": the status is moved back to `open`
and `post` returns False. If the write committed and the exception came afterwards (motor `AutoReconnect` or a timeout
after the server acknowledged), the answer comment `sd-<action>` is already visible to the requester while the ticket is
`open`. The caller then runs `post_lost_to_draft` and `keep_draft`, whose `add_comment` is idempotent on the id and so
adds nothing, leaving `desk.draftWaiting = true` for a comment that is a posted `ai_answer`. This is exactly the
"visible answer undone by a later write" situation WR-102 set out to remove. It is narrow, but the code can detect it.
**Fix:** After an exception, re-read the ticket; if a comment with `comment_id` exists, treat it as stored and continue
with the guarded steps instead of reverting:
```python
except Exception as exc:
    logger.error(...)
    added = await _comment_exists(db, tenant, ticket["id"], comment_id)
```

## Info

### IN-501: `email` is read from users that never carry one

**File:** `backend/notification_endpoints.py:64-67`, `backend/service_desk/projection.py:81-86`
**Issue:** `TokenData` (`auth_types.py:6-26`) has only `username`; `authentication_service.verify_token` never sets an
`email`. Both `_reader_names` and `is_reporter` therefore match the username only in production, while
`test_the_exclusion_matches_case_insensitively_and_by_email` and the reporter tests use stand-ins with an `email`, so they
verify a path that cannot happen. The result is right only while the username is the e-mail address stored as the
ticket's reporter. If a user's username differs from the address stored in `ticket.reporter` (agent-raised tickets use
`email or username`, `agent_tasks_endpoints.py:369`), the server does not project, and the browser filter
(`requesterComments.ts`, which compares against the e-mail) becomes the only guard.
**Fix:** Resolve the user's address once from the profile (or put it into the token) and test both names, or drop the dead
`email` read and the by-email tests.

### IN-502: dashboard list row calls `visibleComments` twice and always with `deskView = null`

**File:** `components/InternalTicketsDashboard.tsx:913` (committed line of the row count)
**Issue:** The count is computed twice per row, and `viewerIsReporter(..., null)` treats a viewer with an empty
`userEmail` as the reporter of every row, so staff without an e-mail see an undercounted comment badge on every ticket
(the fail-closed rule of `viewerIsReporter`). The selected ticket uses the real `deskView`.
**Fix:** `const n = visibleComments(t, userEmail, null).length;` once per row, or hide the badge when `userEmail` is empty.

### IN-503: the desk fold rewrites ideographic full stops in the posted answer

**File:** `backend/service_desk/sanitize.py:38, 107-117`
**Issue:** Mapping U+3002 to "." is applied to the whole text that is posted. Probed: "请重启电脑。然后再试一次。" becomes
"请重启电脑.然后再试一次." and then fails the check as `foreign_link` (the IDN rule reads "电脑.然后再试一次" as a domain).
The desk only answers English (D-20, `is_english`), so today this fails closed and is harmless; it becomes a false-positive
handoff for any future non-English answers, and NFKC also silently changes "…" to "..." in posted text.
**Fix:** Keep the dot mapping only for the check (fold a copy), or document that the desk is English-only and add the CJK
case to `test_service_desk_output_fold.py` as the accepted limit.

### IN-504: TypeScript and Python name matching differ for non-ASCII names

**File:** `components/serviceDesk/requesterComments.ts:25-33` and `backend/service_desk/projection.py:77-86`
**Issue:** The two rules are pinned to one case table, but the name comparison itself differs: `trim().toLowerCase()` against
`strip().casefold()` (for example "straße" against "STRASSE", or a U+FEFF edge), and the table has no non-ASCII case.
**Fix:** Add a non-ASCII author case to `shared/service-desk-requester-comments.json`, or normalise both sides to
`toLowerCase()` / `lower()` plus NFKC.

---

_Reviewed: 2026-11-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
