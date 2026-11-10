---
phase: 85
review: 85-REVIEW.md
titles: json
findings:
  - id: WR-701
    severity: warning
    disposition: open
    title: "Four staff-visible handlers still fail silently (85-41 \"every staff handler\" is not met)"
  - id: WR-702
    severity: warning
    disposition: open
    title: "Bulk delete or update that fails part-way leaves the list stale"
  - id: IN-701
    severity: info
    disposition: open
    title: "`broadcastable` is imported outside the best-effort block, and it lives in a module that imports `rbac_service` and `ticket_access`"
  - id: IN-702
    severity: info
    disposition: open
    title: "The \"template approval stays\" branch is unreachable through the product API"
  - id: IN-703
    severity: info
    disposition: open
    title: "Bare-integer and Unicode-digit citation edge cases in `parse_reply`"
  - id: IN-704
    severity: info
    disposition: open
    title: "Template admin defaults for the queue and SLA are dropped for requesters"
  - id: WR-601
    severity: warning
    disposition: open
    title: "`canSeeGaps` still derives from `view:dashboard`, so the Gaps tab is offered to people the routes refuse"
  - id: WR-602
    severity: warning
    disposition: fixed
    title: "Live WebSocket push still broadcasts `tenant_admins` notices (agent host details) to every user of the tenant"
  - id: WR-603
    severity: warning
    disposition: fixed
    title: "A requester can still set staff-only fields (assignee, assignee_group, watchers, approval_required, sla_hours, due_date) when creating a ticket"
  - id: WR-604
    severity: warning
    disposition: open
    title: "`reader_filter` does not fail closed on an empty tenant id; the feed, mark-read and delete routes can match notices with no tenant"
  - id: IN-601
    severity: info
    disposition: open
    title: "Stale module docstring in `ticket_access.py`"
  - id: IN-602
    severity: info
    disposition: open
    title: "The own-tickets filter and `is_reporter` can disagree on what \"the same person\" means"
  - id: IN-603
    severity: info
    disposition: open
    title: "The notice-reader structure test accepts a function that calls `reader_filter` but never uses the result"
  - id: IN-604
    severity: info
    disposition: fixed
    title: "No frontend code reads `manage:tickets`; the Tickets screen still offers staff actions to requesters"
  - id: CR-501
    severity: critical
    disposition: fixed
    title: "`GET /api/notifications/history` bypasses the whole notice audience filter (relates to WR-201, WR-202, D-33)"
  - id: WR-501
    severity: warning
    disposition: open
    title: "the reporter projection still returns staff-entered text outside comments (relates to CR-401)"
  - id: WR-502
    severity: warning
    disposition: fixed
    title: "staff-only comments stay readable by every tenant user who is not the reporter (CR-401 residual)"
  - id: WR-503
    severity: warning
    disposition: open
    title: "`send_draft` moves the status first but only undoes it when the turn is lost, not when the turn raises (relates to WR-103)"
  - id: WR-504
    severity: warning
    disposition: open
    title: "`outcomes.post` can revert the status of a ticket whose answer was actually stored (relates to WR-102)"
  - id: IN-501
    severity: info
    disposition: open
    title: "`email` is read from users that never carry one"
  - id: IN-502
    severity: info
    disposition: open
    title: "dashboard list row calls `visibleComments` twice and always with `deskView = null`"
  - id: IN-503
    severity: info
    disposition: open
    title: "the desk fold rewrites ideographic full stops in the posted answer"
  - id: IN-504
    severity: info
    disposition: open
    title: "TypeScript and Python name matching differ for non-ASCII names"
  - id: CR-101
    severity: critical
    disposition: fixed
    title: "Output checks (D-19) can be bypassed with hidden or compatibility characters, so a foreign link or email reaches the requester"
  - id: WR-101
    severity: warning
    disposition: fixed
    title: "The loopback guard can be defeated by environment proxy settings, sending ticket text to a proxy"
  - id: WR-102
    severity: warning
    disposition: fixed
    title: "A failure after the status move in `outcomes.post` or `keep_draft` leaves a posted answer, a stuck ledger row and a contradicting hand-off"
  - id: WR-103
    severity: warning
    disposition: fixed
    title: "`send_draft` makes the answer visible before the status move, and ignores a lost status move"
  - id: IN-101
    severity: info
    disposition: open
    title: "`retrieval.candidates` has no order, so more than 300 Help desk articles are cut at random"
  - id: IN-102
    severity: info
    disposition: open
    title: "Smaller consistency items"
  - id: WR-201
    severity: warning
    disposition: fixed
    title: "the `ticket_staff` audience tag on staff-only comment notices is never enforced, so the feed and socket still tell the reporter"
  - id: WR-202
    severity: warning
    disposition: fixed
    title: "addressed notices can be marked read or deleted by any tenant user"
  - id: WR-203
    severity: warning
    disposition: fixed
    title: "writing an article from a gap with `helpdesk: false` marks the gap group written although the desk can never use the article"
  - id: IN-201
    severity: info
    disposition: open
    title: "the desk branch of the gate does not require ticket-kind actions"
  - id: IN-202
    severity: info
    disposition: open
    title: "a Windows user name between 201 and 256 characters can never match its own tickets"
  - id: IN-203
    severity: info
    disposition: open
    title: "the eval script documents passing the database URL on the command line"
  - id: IN-204
    severity: info
    disposition: open
    title: "body-size bounds on the new Knowledge Base models are checked after full parsing"
  - id: WR-301
    severity: warning
    disposition: fixed
    title: "A fixed \"now\" plus a 90-day TTL index makes the worker and hand-off tests flaky after about 2027-02-06"
  - id: WR-302
    severity: warning
    disposition: fixed
    title: "The migration-number assertion breaks as soon as migration 033 ships"
  - id: WR-303
    severity: warning
    disposition: fixed
    title: "The claim that `--sets` makes no database connection is not actually tested"
  - id: IN-301
    severity: info
    disposition: open
    title: "The Mongo test URL default (127.0.0.1:27017) is duplicated in two places"
  - id: IN-302
    severity: info
    disposition: open
    title: "The injection test's output-check pass is partly circular"
  - id: IN-303
    severity: info
    disposition: open
    title: "An order-tolerant assertion hides the worker's ordering"
  - id: CR-401
    severity: critical
    disposition: fixed
    title: "Requester's comment list renders staff-only comments and, while the desk view is loading or failed, unsent AI drafts"
  - id: WR-401
    severity: warning
    disposition: open
    title: "Tray reports an empty `client.version` on every ticket (`agent_version` is never written to tray-config.json)"
  - id: WR-402
    severity: warning
    disposition: open
    title: "\"Open ticket {number}\" on a desk row drops the ticket id and only opens the Tickets screen"
  - id: WR-403
    severity: warning
    disposition: open
    title: "Unanswered \"My tickets\" window ignores a clicked balloon while the window is already open"
  - id: WR-404
    severity: warning
    disposition: open
    title: "Draft panel decides \"already handled\" by comparing the server's text to a copy string"
  - id: WR-405
    severity: warning
    disposition: open
    title: "Word editor accepts words the server refuses (leading space, hyphen, apostrophe, `&`, `/`, `.`)"
  - id: IN-401
    severity: info
    disposition: open
    title: "Hard-coded user-visible strings outside `serviceDeskCopy.ts`"
  - id: IN-402
    severity: info
    disposition: open
    title: "Redundant length check and stale doc comment"
  - id: IN-403
    severity: info
    disposition: open
    title: "`postTicketComment` returns `Promise<any>`"
open: 35
total: 51
recorded: 2026-11-10T13:20:39.006Z
---

# Phase 85: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-701 | warning | open | - |
| WR-702 | warning | open | - |
| IN-701 | info | open | - |
| IN-702 | info | open | - |
| IN-703 | info | open | - |
| IN-704 | info | open | - |
| WR-601 | warning | open | - (not in the current review) |
| WR-602 | warning | fixed | fixed 0efe58463 (85-39) (not in the current review) |
| WR-603 | warning | fixed | fixed 6fcb73084 (85-39) (not in the current review) |
| WR-604 | warning | open | - (not in the current review) |
| IN-601 | info | open | - (not in the current review) |
| IN-602 | info | open | - (not in the current review) |
| IN-603 | info | open | - (not in the current review) |
| IN-604 | info | fixed | fixed 3f70dbf6a, 200daaaf9 (85-40); 4415379d6, ac80717e6 (85-41), screen half; the manifest write-entry note stays open (not in the current review) |
| CR-501 | critical | fixed | fixed b7e178bd3, 4f5ad02b9 (85-31); tests 975d2d5dc (not in the current review) |
| WR-501 | warning | open | - (not in the current review) |
| WR-502 | warning | fixed | fixed 1a0a5d54b (85-30); fd671c60e (85-32); 6458b0f62, 59e98958d, 03d6efce5 (85-33); 638d655b7, 283a1b71a (85-34); 37b7f2890, 3f2045d09 (85-35) (not in the current review) |
| WR-503 | warning | open | - (not in the current review) |
| WR-504 | warning | open | - (not in the current review) |
| IN-501 | info | open | - (not in the current review) |
| IN-502 | info | open | - (not in the current review) |
| IN-503 | info | open | - (not in the current review) |
| IN-504 | info | open | - (not in the current review) |
| CR-101 | critical | fixed | fixed 791831738, 94afd4eea (85-24) (not in the current review) |
| WR-101 | warning | fixed | fixed cf422f817 (85-24) (not in the current review) |
| WR-102 | warning | fixed | fixed 3a1937b7d, 86cd504bd (85-27) (not in the current review) |
| WR-103 | warning | fixed | fixed ec308e6d9 (85-27) (not in the current review) |
| IN-101 | info | open | - (not in the current review) |
| IN-102 | info | open | - (not in the current review) |
| WR-201 | warning | fixed | fixed 9840a7fdf, b49c68fa4 (85-28) (not in the current review) |
| WR-202 | warning | fixed | fixed 89f7786bd (85-28) (not in the current review) |
| WR-203 | warning | fixed | fixed 9cbe72e1b (85-29) (not in the current review) |
| IN-201 | info | open | - (not in the current review) |
| IN-202 | info | open | - (not in the current review) |
| IN-203 | info | open | - (not in the current review) |
| IN-204 | info | open | - (not in the current review) |
| WR-301 | warning | fixed | fixed 57325f0e7 (85-29) (not in the current review) |
| WR-302 | warning | fixed | fixed 57325f0e7 (85-29) (not in the current review) |
| WR-303 | warning | fixed | fixed 57325f0e7 (85-29) (not in the current review) |
| IN-301 | info | open | - (not in the current review) |
| IN-302 | info | open | - (not in the current review) |
| IN-303 | info | open | - (not in the current review) |
| CR-401 | critical | fixed | fixed 927bcff49, f4ce6404d (85-25, server); 82e9074c4, 3df8d5088 (85-26, screen) (not in the current review) |
| WR-401 | warning | open | - (not in the current review) |
| WR-402 | warning | open | - (not in the current review) |
| WR-403 | warning | open | - (not in the current review) |
| WR-404 | warning | open | - (not in the current review) |
| WR-405 | warning | open | - (not in the current review) |
| IN-401 | info | open | - (not in the current review) |
| IN-402 | info | open | - (not in the current review) |
| IN-403 | info | open | - (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
