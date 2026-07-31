---
phase: 21-notification-domain-scanner
plan: 01
subsystem: notifications
tags: [fastapi, slack, webhook, dns, tls, ssrf-hardening]

requires: []
provides:
  - NotificationService (channels, rules, send_notification dispatch to Slack/email/webhook)
  - POST/GET /api/notifications/channels, /api/notifications/rules
  - DomainScannerService (subdomain/port/TLS/DNS record scanning, scheduled scans)
  - GET /api/domain-scanner/scan, POST/GET /api/domain-scanner/scheduled
  - NotificationsDashboard.tsx
affects: [compliance-score-dashboard, evidence-review-workflow]

tech-stack:
  added: []
  patterns:
    - "SSRF guard on both notification webhook URLs and domain-scanner targets before any outbound request or persistence"
    - "Domain scan I/O (socket/TLS/DNS) run in a thread pool executor rather than directly in the async event loop"

key-files:
  created:
    - backend/notification_service.py
    - backend/notification_endpoints.py
    - backend/domain_scanner_service.py
    - backend/domain_scanner_endpoints.py
    - backend/tests/test_notification_service.py
  modified:
    - backend/router_registry.py
    - components/NotificationsDashboard.tsx

key-decisions:
  - "notification_service module import fixed (CR-01) — the four new routes raised NameError on every single call in the originally-reviewed code; this shipped completely non-functional until the review cycle caught it"
  - "SSRF validation added to both the notification webhook path (CR-07) and the domain scanner's target-host acceptance (CR-08) — the domain scanner's core purpose (scan arbitrary hosts) required a deliberate allowlist/denylist design rather than blanket rejection"
  - "Domain scan socket/TLS/DNS calls moved off the async event loop into a thread executor (CR-09) — the original implementation blocked the entire server on every scan"

requirements-completed: [NOTIF-01, NOTIF-02, SCAN-01, SCAN-02]

duration: unknown (retroactively documented); fix cycle completed 2026-07-04
completed: 2026-07-04
status: complete
---

# Phase 21: Notification Routing & Domain Scanner Summary

**Multi-channel notification routing (Slack/email/webhook) with rule-based dispatch, plus a domain scanner (subdomains, open ports, TLS cert info, DNS records) with scheduled scanning — after a code review cycle that caught the feature shipping completely non-functional (routes raised `NameError` on every call) with multiple SSRF and cross-tenant vulnerabilities.**

## Performance
- **Duration:** unknown for initial implementation — retroactively summarized. The code-review/fix cycle (22 findings, all fixed) was completed 2026-07-04.
- **Files modified:** 7 (notification_service.py, notification_endpoints.py, domain_scanner_service.py, domain_scanner_endpoints.py, test_notification_service.py, router_registry.py, NotificationsDashboard.tsx)

## Accomplishments
- `NotificationService`: channel CRUD, rule CRUD, `send_notification(event_type, payload, tenant_id)` dispatching to matched channels
- Slack (webhook POST), email (logged, SMTP deferred per plan), and webhook (JSON POST) senders
- `DomainScannerService`: subdomain discovery, common-port scanning, TLS certificate inspection, DNS record lookup (A/MX/TXT/NS), scheduled recurring scans
- `NotificationsDashboard.tsx` UI
- 7/7 unit tests passing in `test_notification_service.py` (0/7 passed before the fix cycle — CR-10)
- Full code review: **22 findings** (10 critical, 7 warning, 5 info) in `21-REVIEW.md` — the highest severity count of any phase in this milestone. All 22 fixed and verified in `21-REVIEW-FIX.md` (status: all_fixed).

## Task Commits
Initial implementation bundled into a mislabeled commit from an adjacent phase's session (pre-existing repo-history quirk).

Selected fixes (22 total — see `21-REVIEW-FIX.md` for the complete list):
1. **CR-01** fix missing `notification_service` import causing `NameError` on every route call
2. **CR-03/CR-06** stop caller-supplied `id`/`tenantId` from overriding server-assigned values; enforce `tenantId` on all writes
3. **CR-04** redact secrets from `GET /api/notifications/channels` for non-privileged roles
4. **CR-05** tenant-filter Slack webhook config lookup (was leaking cross-tenant)
5. **CR-07/CR-08** add SSRF validation to notification webhooks and domain-scanner targets
6. **CR-09** move domain-scan socket/TLS/DNS I/O off the async event loop into a thread executor
7. **CR-10** fix the fully-broken test suite (0/7 → 7/7 passing)
8. **d2e66b02** remove dead, colliding `/api/notifications/config` duplicate route registration
9. **6bbcf78b** resolve CR-01/CR-02 notification channel/rule route crashes (initial pass, superseded by the fuller fix above)

## Files Created/Modified
- `backend/notification_service.py` — channel/rule CRUD + dispatch (546 lines — **exceeds the CLAUDE.md 500-line limit; flagged for a future split, not addressed in this cycle**)
- `backend/notification_endpoints.py` — router at `/api/notifications`
- `backend/domain_scanner_service.py` — scan logic (113 lines)
- `backend/domain_scanner_endpoints.py` — router at `/api/domain-scanner`
- `backend/tests/test_notification_service.py` — 7-test suite
- `backend/router_registry.py` — registers both routers
- `components/NotificationsDashboard.tsx` — UI, fixed to check HTTP status before declaring success (WR-01) and to write the correct per-channel-type config key (WR-02)

## Decisions & Deviations
None beyond the review-fix cycle. Plan executed as specified functionally, but the initial implementation shipped in a materially broken and insecure state (see Issues Encountered) — the review cycle was load-bearing here, not a formality.

**Known outstanding item:** `notification_service.py` is 546 lines, over the project's 500-line file-size guideline. Not fixed in this cycle; worth a follow-up split (e.g. separate channel-CRUD from dispatch/sender logic).

## Issues Encountered
This phase's initial implementation was unusually broken for code that had reached a review stage: the core notification routes raised `NameError` on every invocation (a missing import), the test suite was 0/7 passing, and there were 10 Critical-severity findings including two distinct SSRF vectors and two distinct cross-tenant data leaks (unredacted secrets, cross-tenant Slack config lookup). All were caught and fixed during code review rather than reaching production. `SUMMARY.md` was not created at execution time, causing downstream tooling to treat the phase as unimplemented despite this review/fix cycle being complete.

## Next Phase Readiness
Phase 21 implemented, reviewed (22/22 findings fixed), and tested (7/7 passing). Ready for `/gsd-verify-work 21` (human UAT) and `/gsd-secure-phase 21`. Recommend prioritizing the `notification_service.py` line-count split before further feature work on this file.

---
*Phase: 21-notification-domain-scanner*
*Completed: 2026-07-04*
