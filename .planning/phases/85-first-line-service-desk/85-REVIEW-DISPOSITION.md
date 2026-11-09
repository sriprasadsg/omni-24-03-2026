---
phase: 85
review: 85-REVIEW.md
titles: json
findings:
  - id: CR-501
    severity: critical
    disposition: open
    title: "`GET /api/notifications/history` bypasses the whole notice audience filter (relates to WR-201, WR-202, D-33)"
  - id: WR-501
    severity: warning
    disposition: open
    title: "the reporter projection still returns staff-entered text outside comments (relates to CR-401)"
  - id: WR-502
    severity: warning
    disposition: open
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
open: 26
total: 37
recorded: 2026-11-09T20:02:31.543Z
---

# Phase 85: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-501 | critical | open | - |
| WR-501 | warning | open | - |
| WR-502 | warning | open | - |
| WR-503 | warning | open | - |
| WR-504 | warning | open | - |
| IN-501 | info | open | - |
| IN-502 | info | open | - |
| IN-503 | info | open | - |
| IN-504 | info | open | - |
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
