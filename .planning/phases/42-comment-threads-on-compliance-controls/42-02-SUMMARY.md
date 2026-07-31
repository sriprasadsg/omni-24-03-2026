---
phase: 42-comment-threads-on-compliance-controls
plan: 02
subsystem: api
tags: [fastapi, mongodb, motor, pytest, notifications, mentions]

# Dependency graph
requires:
  - phase: 42-comment-threads-on-compliance-controls
    plan: 01
    provides: control_comments_service.add_comment/list_comments + control_comments_endpoints.post_control_comment/get_control_comments (committed and green)
provides:
  - "control_comments_service.extract_mention_tokens/resolve_mentions"
  - "post_control_comment @mention notification dispatch via get_notification_service(db).send_alert(channels=[])"
  - "notification_service.send_alert channels=[] now honored as explicit no-dispatch (fixed pre-existing bug)"
affects: [42-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Plain-identifier @mention regex (r'@([\\w.-]+)'), never the tickets email-shaped mention pattern"
    - "Notification dispatch wrapped in try/except so it never fails the primary write it's attached to"
    - "channels=[] as an explicit, distinguishable no-dispatch signal to NotificationService.send_alert (vs. None which still defaults to email)"

key-files:
  created: []
  modified:
    - backend/control_comments_service.py
    - backend/control_comments_endpoints.py
    - backend/tests/test_control_comments.py
    - backend/notification_service.py
    - backend/tests/test_notification_service.py

key-decisions:
  - "42-02: resolve_mentions tries username -> email-local-part -> case-insensitive name match against db.users, in that order (RESEARCH.md Assumption A1); unresolved tokens are silently skipped and never raise"
  - "42-02: notification dispatch loop wrapped per-mention in try/except Exception: pass, mirroring tickets_endpoints.py's non-fatal notification convention (T-42-07)"
  - "42-02: fixed notification_service.py's send_alert to distinguish channels=None (defaults to email) from channels=[] (explicit no-dispatch) — a pre-existing bug that silently defaulted BOTH cases to email, which would have violated this plan's own D-02 in-app-only guarantee outside of mocked tests"

patterns-established:
  - "@mention resolution as a three-tier lookup (username, email-local-part, case-insensitive name) against db.users, reusable by any future comment/mention feature"

requirements-completed: [CMT-01]

# Metrics
duration: ~25min
completed: 2026-07-21
status: complete
---

# Phase 42 Plan 02: @Mention Notification Dispatch Summary

**Plain-text @mention parsing resolves to a tenant user's email and fires exactly one in-app-only notification (`channels=[]`) per mention, wired into the existing comment POST without ever failing the comment write.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-21
- **Tasks:** 3
- **Files modified:** 5 (0 created, 5 modified — 2 beyond the plan's declared file list, see Deviations)

## Accomplishments
- `extract_mention_tokens(text)` — plain-identifier regex `r'@([\w.-]+)'`, deliberately not the tickets email-shaped mention pattern (which would match nothing for `@bob`).
- `async resolve_mentions(db, text)` — resolves each extracted token to a user's email via `db.users`, trying exact `username` match, then email-local-part match, then case-insensitive exact `name` match, in that order; unresolved tokens are silently skipped (never raises); resolved emails are de-duplicated.
- `post_control_comment` now loops over `resolve_mentions(db, body.text)` after persisting the comment and fires `get_notification_service(db).send_alert(..., channels=[], metadata={"control_id", "event": "mention"})` per resolved mention — imported via the `get_notification_service` factory, never the broken `notification_service` module-level singleton `ticket_notifications.py` relies on. Each dispatch is wrapped in `try/except Exception: pass` so a notification failure never fails the comment write.
- 2 new hermetic unit tests (`test_mention_triggers_notification`, `test_mention_is_in_app_only`) — RED confirmed before implementation (`get_notification_service` didn't exist on the module yet), GREEN after. Full `test_control_comments.py` suite: 5/5 passing.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing mention-notification tests** - `5837150` (test)
2. **Task 2: Implement plain-text mention extraction + user resolution** - `636c3f1` (feat)
3. **Task 3: Wire in-app-only notification dispatch into the POST handler** - `4fd14bd` (feat, includes the notification_service.py Rule 1 fix below)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `backend/control_comments_service.py` - added `extract_mention_tokens(text)` / `async resolve_mentions(db, text)`
- `backend/control_comments_endpoints.py` - `post_control_comment` now dispatches `get_notification_service(db).send_alert(channels=[])` per resolved mention; imports `get_notification_service` and `resolve_mentions`
- `backend/tests/test_control_comments.py` - `test_mention_triggers_notification`, `test_mention_is_in_app_only`, plus `_make_mock_db_with_mention_user` helper (users + notifications mock collections)
- `backend/notification_service.py` - Rule 1 fix: `send_alert`'s channels-default check changed from `if not channels` to `if channels is None`
- `backend/tests/test_notification_service.py` - added `test_send_alert_explicit_empty_channels_means_no_dispatch` regression test

## Decisions Made
- Resolution order for `resolve_mentions` follows RESEARCH.md's Assumption A1 exactly: `username` (exact) → `email` (local-part prefix match) → `name` (case-insensitive exact). This mirrors the real `db.users` doc shape confirmed in `authentication_endpoints.py` (reliable `email`/`name`, sparse `username`).
- Notification dispatch is intentionally non-fatal per-mention (`try/except Exception: pass` inside the loop, not around the whole POST), matching `tickets_endpoints.py`'s existing mention-notification error-handling convention and satisfying threat T-42-07 (broken/unresolved mention must never crash the comment POST).
- `tenant_id` (already resolved and guarded earlier in the handler) is passed straight into `send_alert`'s `tenant_id` kwarg for defense-in-depth alongside `resolve_mentions`'s own tenant-scoped `db.users` lookup (T-42-06).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `notification_service.py`'s `send_alert` did not honor an explicit empty `channels` list**
- **Found during:** Task 3, while verifying the plan's own must-have truth ("channels=[] so no email/sms/slack side-effect dispatch occurs") against the real (non-mocked) `send_alert` implementation, not just the mocked unit tests.
- **Issue:** `if not channels: channels = ["email"]` treats an explicitly-passed empty list (`channels=[]`) identically to an omitted/`None` value — both are falsy in Python. This meant that even after wiring `channels=[]` into the mention dispatch call exactly as the plan and `42-PATTERNS.md` specified, a real (unmocked) `send_alert` call would silently fall back to dispatching an "email" channel (in this environment, `_send_email`'s no-SMTP-configured fallback logs to `notifications.log`; with `SMTP_HOST` configured in production, it would send a real email) — directly violating this plan's D-02 in-app-only guarantee. Confirmed empirically: a live `NotificationService.send_alert(..., channels=[])` call returned `result["channels"] == {"email": {...}}` before the fix. `42-PATTERNS.md`'s own "CRITICAL" note asserting that `channels=[]` was already "non-empty-check-safe" was itself incorrect against the actual code.
- **Fix:** Changed the check to `if channels is None: channels = ["email"]` — `None`/omitted still defaults to email (no behavior change for every existing caller, all of which pass non-empty explicit channel lists or omit the parameter), while an explicit `channels=[]` now correctly results in zero channel dispatch (only the unconditional `db.notifications.insert_one` audit write still fires).
- **Files modified:** `backend/notification_service.py`, `backend/tests/test_notification_service.py` (new regression test)
- **Verification:** `test_send_alert_explicit_empty_channels_means_no_dispatch` (new) asserts `channels=[]` yields `result["channels"] == {}` and `channels=None`/omitted still yields `"email" in result["channels"]`. Checked all existing `send_alert` callers (`send_sla_breach_alert`, `send_critical_patch_alert`, `send_deployment_complete_alert`, `ticket_notifications.py::_send`, `reporting_endpoints.py`'s `channels=data.get("channels", ["email"])`) — none pass an explicit empty list, so none are affected by the behavior change; the fix only changes the empty-list case, which previously had no correct-behaving caller anywhere in the codebase.
- **Committed in:** `4fd14bd` (part of Task 3 commit — the fix and its wiring caller are inseparable; splitting them would leave an intermediate commit where the wired dispatch call still silently violates D-02)

---

**Total deviations:** 1 auto-fixed (Rule 1), outside the plan's declared `files_modified` list but required to make the plan's own must-have truth actually true outside of mocked tests.
**Impact on plan:** No plan-file behavior change beyond what was specified; the fix is confined to `notification_service.py`'s channel-selection logic and does not alter any other existing caller's behavior.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Backend @mention notification dispatch is complete and verified: `test_control_comments.py` 5/5 green, `test_notification_service.py` 8/8 green (7 pre-existing + 1 new regression). Full backend suite run (excluding the 3 files that fail at collection time on a live network dependency, per 42-01's documented precedent): **1310 passed / 34 skipped / 7 failed** — all 7 failures reproduce the exact same set 42-01-SUMMARY.md already logged as pre-existing and unrelated (`test_log_heartbeat.py`, `test_virustotal.py`, `test_webhook_logic.py` jira/zoho intent parsing, `test_agentic_ai.py::TestRunCallsAnthropicWithToolChoiceAny`, `test_e2e_integration.py::test_golden_path_evidence_to_remediation`, `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls`).

Ready for 42-03 (frontend `ControlCommentsPanel.tsx` + `apiService.ts` wrappers + `FrameworkDetail.tsx` mount) to consume `GET`/`POST /api/control-comments` — the backend (persistence + role gating + @mention notifications) is now fully complete.

---
*Phase: 42-comment-threads-on-compliance-controls*
*Completed: 2026-07-21*

## Self-Check: PASSED

All created/modified files confirmed present on disk; all 4 commit hashes (`5837150`, `636c3f1`, `4fd14bd`, `936b9c8`) confirmed present in `git log`.
