---
phase: 85
review: 85-REVIEW.md
titles: json
findings:
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
    disposition: open
    title: "A failure after the status move in `outcomes.post` or `keep_draft` leaves a posted answer, a stuck ledger row and a contradicting hand-off"
  - id: WR-103
    severity: warning
    disposition: open
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
    disposition: open
    title: "the `ticket_staff` audience tag on staff-only comment notices is never enforced, so the feed and socket still tell the reporter"
  - id: WR-202
    severity: warning
    disposition: open
    title: "addressed notices can be marked read or deleted by any tenant user"
  - id: WR-203
    severity: warning
    disposition: open
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
    disposition: open
    title: "A fixed \"now\" plus a 90-day TTL index makes the worker and hand-off tests flaky after about 2027-02-06"
  - id: WR-302
    severity: warning
    disposition: open
    title: "The migration-number assertion breaks as soon as migration 033 ships"
  - id: WR-303
    severity: warning
    disposition: open
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
    disposition: open
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
total: 28
recorded: 2026-11-09T10:13:07.744Z
---

# Phase 85: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-101 | critical | fixed | fixed 791831738, 94afd4eea (85-24) |
| WR-101 | warning | fixed | fixed cf422f817 (85-24) |
| WR-102 | warning | open | - |
| WR-103 | warning | open | - |
| IN-101 | info | open | - |
| IN-102 | info | open | - |
| WR-201 | warning | open | - |
| WR-202 | warning | open | - |
| WR-203 | warning | open | - |
| IN-201 | info | open | - |
| IN-202 | info | open | - |
| IN-203 | info | open | - |
| IN-204 | info | open | - |
| WR-301 | warning | open | - |
| WR-302 | warning | open | - |
| WR-303 | warning | open | - |
| IN-301 | info | open | - |
| IN-302 | info | open | - |
| IN-303 | info | open | - |
| CR-401 | critical | open | - |
| WR-401 | warning | open | - |
| WR-402 | warning | open | - |
| WR-403 | warning | open | - |
| WR-404 | warning | open | - |
| WR-405 | warning | open | - |
| IN-401 | info | open | - |
| IN-402 | info | open | - |
| IN-403 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
