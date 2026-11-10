---
phase: 85-first-line-service-desk
reviewed: 2026-11-10T00:00:00Z
depth: standard
files_reviewed: 25
files_reviewed_list:
  - backend/notification_audience.py
  - backend/notification_service.py
  - backend/pending_agents.py
  - backend/scripts/service_desk_eval.py
  - backend/service_desk/checks.py
  - backend/service_desk/handoff.py
  - backend/service_desk/messages.py
  - backend/service_desk/model.py
  - backend/service_desk/pipeline.py
  - backend/service_desk/sanitize.py
  - backend/tests/fixtures/service_desk/output_checks.jsonl
  - backend/tests/test_pending_agents.py
  - backend/tests/test_service_desk_citations.py
  - backend/tests/test_service_desk_eval_script.py
  - backend/tests/test_service_desk_injection.py
  - backend/tests/test_service_desk_notification_audience.py
  - backend/tests/test_service_desk_output_checks.py
  - backend/tests/test_service_desk_sanitize.py
  - backend/tests/test_ticket_staff_create_fields.py
  - backend/tickets_endpoints.py
  - components/InternalTicketsDashboard.tsx
  - src/__tests__/ServiceDeskReplyVisibility.test.tsx
  - src/__tests__/ServiceDeskRequesterComments.test.tsx
  - src/__tests__/TicketsRequesterControls.test.tsx
  - src/__tests__/TicketsStaffActionErrors.test.tsx
findings:
  critical: 0
  warning: 2
  info: 4
  total: 6
status: issues_found
---

# Phase 85: Code Review Report (third gap round, plans 85-37..85-41)

**Reviewed:** 2026-11-10
**Depth:** standard (diff against 101bc4e581770fa4339fd45429b535cdd3171dbe, whole files read for context)
**Files Reviewed:** 25
**Status:** issues_found

This report replaces the second-gap-round report (101bc4e58, IDs CR-6xx/WR-6xx/IN-6xx; earlier reports 2f8ed35b1 and 009402280). This round uses the 7xx series. `backend/tickets_endpoints.py` and `components/InternalTicketsDashboard.tsx` were reviewed as `git show HEAD:<file>`; the user's uncommitted hunks (download route, Download button) were not reviewed.

## Summary

The server-side changes are sound. I traced all five areas and found no correctness or security defect in them:

- `checks.given_citations` and `parse_reply` (85-37).
- The `rule=` hand-off path through `handoff`, `ledger.record_desk_event(desk=...)` and `OUTPUT_RULE_LABELS` (85-38). Every rule `check` or `verdict` can return is a key of the label table, and the rule stays in the staff note and ledger row only.
- `notification_audience.broadcastable` in `send_alert` and `_post_in_app` (85-39).
- The `create_ticket` field drop (85-39).
- The A-id prompt change (85-37).

The two warnings are in the front end. Plan 85-41 set out to make every staff action report its failure, but a few handlers were left bare. One bulk-action path can also leave the list out of step with the server after a failure. The Info items are small robustness or dead-code notes.

Not re-reported, per the orchestrator: A-85-G38, G39, G40, G43, and WR-601/604/IN-601..603.

## Warnings

### WR-701: Four staff-visible handlers still fail silently (85-41 "every staff handler" is not met)

**File:** `components/InternalTicketsDashboard.tsx:1090,1092` (title edit), `:1287` (security-incident "Start Investigation"), `:622` (staff-note comment), `:630-641` (`handleUpload`)
**Issue:** `reportFailure` was added to the other handlers but not to these four:
- Title edit: `updateTicket(selected.id, {title: titleDraft}).then(t => setSelected(t))` in `onBlur` and `onKeyDown` has no `.catch`. A refused (403) or failed (500) rename is an unhandled promise rejection with no toast. The input has already closed, so the title reverts with no explanation, which is the same "silent failure" UAT G-85-4b reported.
- Start Investigation: `onClick={() => updateTicket(selected.id, {status:'in_progress'}).then(t => setSelected(t))}` has the same problem.
- Staff note: in `handleComment`, `if (!toRequester) throw e;` rethrows out of an async click handler. A failed staff-only note (the default reply target) gives no toast, and the typed comment stays in the box with no explanation.
- Attachment upload: `await uploadTicketAttachment(...)` is outside any try/catch, so a rejected upload (size limit, 403) is an unhandled rejection with no message. The reload after it can also be skipped.

Also, `handleUpload` shadows the event parameter `e` in its own `catch (e)`, and the first `const t = await fetchTickets({ }).then(() => null)` is a dead extra fetch.
**Fix:**
```tsx
const patchTitle = async () => {
  setEditingTitle(false);
  try { setSelected(await updateTicket(selected.id, { title: titleDraft })); }
  catch (e) { reportFailure(e, 'Failed to rename ticket'); }
};
// onBlur={patchTitle}; Enter -> patchTitle(); Start Investigation -> handlePatch({ status: 'in_progress' })
// handleComment:  } catch (e) { if (!toRequester) { reportFailure(e, 'Failed to add note'); return; } ... }
// handleUpload:   try { await uploadTicketAttachment(...) } catch (err) { reportFailure(err, 'Failed to upload attachment'); return; }
```
Add a test case for each to `TicketsStaffActionErrors.test.tsx`.

### WR-702: Bulk delete or update that fails part-way leaves the list stale

**File:** `components/InternalTicketsDashboard.tsx:760-776` (`handleBulkAction`)
**Issue:** `await Promise.all(ids.map(id => deleteTicket(id)))` rejects on the first failure while the other deletes still run. The `catch` then shows a toast, but `setTickets(...)`, `setSelectedIds(new Set())` and `load()` sit inside the `try` after the await, so they never run. After a partial failure the screen still lists tickets that were deleted on the server, and the selection and bulk bar stay up. A second click on Apply re-sends deletes that now 404. The same applies to a `bulkUpdateTickets` failure, but there the data is unchanged, so it is harmless.
**Fix:**
```tsx
} catch (e) {
  reportFailure(e, action === 'delete' ? 'Failed to delete tickets' : 'Failed to update tickets');
  load();                       // show what the server really holds
}
```
For delete, use `Promise.allSettled` and remove only the fulfilled ids from state; toast the count of failures.

## Info

### IN-701: `broadcastable` is imported outside the best-effort block, and it lives in a module that imports `rbac_service` and `ticket_access`

**File:** `backend/notification_service.py:95`, `backend/pending_agents.py:282`, `backend/notification_audience.py:12-13`
**Issue:** The WebSocket push has always been wrapped in `try/except` and treated as non-fatal. The new `from notification_audience import broadcastable` runs before that `try`, after `notifications.insert_one` and after the email, SMS and Slack sends. `broadcastable` is a pure dict predicate, but `notification_audience` imports `rbac_service` and `ticket_access` at module level (and through them `authentication_service`, `database`, `jwt` and `fastapi`). If that import ever fails, for example in a CLI or test context or through a future import cycle, `send_alert` or `_post_in_app` raises after the notice was stored and sent, and the caller sees a failure. This is low likelihood in the running backend.
**Fix:** Move `broadcastable` (and nothing else) into a small import-free module, or into `ticket_access`'s dependency-free top section. Alternatively put the import and the predicate call inside the existing `try`, with the safe default (no push) on failure.

### IN-702: The "template approval stays" branch is unreachable through the product API

**File:** `backend/tickets_endpoints.py:169-173` (HEAD), `backend/tickets_config_mixin.py:60-76,93`
**Issue:** `create_template` writes only `type, priority, assignee, assignee_group, tags, title_template, body_template, custom_fields, sla_hours` into `defaults`, `CreateTemplateRequest` has no `approval_required`, and `update_template` allow-lists the same keys. No code path stores `defaults.approval_required`, so the `defaults.get("approval_required") is True` branch can only fire for a template document inserted by hand, as `test_ticket_staff_create_fields.py` does. The strict `is True` also means a hand-inserted truthy non-bool such as `"true"` or `1` is treated as no approval for a requester, while the same template creates a pending-approval ticket for staff. That is the fail-open direction the comment says it avoids. This does not contradict A-85-G38, but the decision currently protects nothing in production.
**Fix:** Either add `approval_required` to the template create and update model and allow-list (so the decided behaviour exists), or note the branch as forward-looking. If kept, use `bool(defaults.get("approval_required"))` to match how `tickets_service.create_ticket` reads it.

### IN-703: Bare-integer and Unicode-digit citation edge cases in `parse_reply`

**File:** `backend/service_desk/checks.py:81,84-92`
**Issue:** (a) A JSON integer such as `1` is kept as article 1, but the string `"1"` maps to 0 (an unknown citation). The prompt and the Ollama schema now ask for `"A1"`-style strings, so a model that answers `"cited": ["1"]` is handed off as `unknown_citation`, while `[1]` would pass. The asymmetry is surprising but fail-closed. (b) `_A_ID = r"A(\d{1,6})"` uses `\d`, which in Python 3 matches any Unicode decimal digit, so `"A١"` (Arabic-Indic one) becomes article 1. No bypass follows, because the cited number must still be a given article, but it differs from the documented "A<n>" form.
**Fix:** `_A_ID = re.compile(r"A([0-9]{1,6})")`, and decide explicitly whether a digit-only string should count as that article, then document it in `Reply`'s docstring.

### IN-704: Template admin defaults for the queue and SLA are dropped for requesters

**File:** `backend/tickets_endpoints.py:169-171` (HEAD)
**Issue:** After the template merge, all six staff-only keys are removed again for a requester, including `assignee_group`, `assignee` and `sla_hours`. Those values come from an admin-built template, not from the requester. A requester who picks a template therefore loses the template's queue and SLA routing and falls through to `auto_assign` and the priority SLA. That matches the stated "drop six fields before and after the template merge", so it is probably the decided behaviour, but it makes the template's routing fields useless on the portal. The negative assertions in the tests (`stored["sla_hours"] != 2`) would also pass for any other value, so they do not pin the replacement behaviour.
**Fix:** If template routing should still apply, keep the template-sourced `assignee_group`, `assignee` and `sla_hours` and drop only the keys the request body supplied. Otherwise record the loss as decided and assert the exact fallback values in the tests.

---

_Reviewed: 2026-11-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
