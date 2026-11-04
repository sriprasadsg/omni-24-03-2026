---
phase: 87
review: 87-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "[backend] Partner roles are listed and readable to every tenant admin"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "[backend] Unique-index races on tenant name surface as HTTP 500 and (for appoint) are not cleaned up consistently"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "[backend] `invite()` leaves an unreachable, un-resendable user when issuing the link fails"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "[backend] Invited users are stored lower-cased but login matches the email exactly"
  - id: WR-05
    severity: warning
    disposition: fixed
    title: "[backend] A 0-seat customer can be moved into a suspended partner (claim returns True for n == 0 without any check)"
  - id: WR-06
    severity: warning
    disposition: fixed
    title: "[backend] A losing compare-and-set transiently over-claims the pool and can refuse an unrelated, valid request"
  - id: WR-07
    severity: warning
    disposition: fixed
    title: "[backend] Pool reconcile is placed ahead of the other seat upkeep in the same try and sleeps inside request paths"
  - id: WR-08
    severity: warning
    disposition: fixed
    title: "[frontend] Partners screen keeps a stale customer list for any partner that is collapsed during a refresh"
  - id: WR-09
    severity: warning
    disposition: fixed
    title: "[frontend] Expiry dates display in the browser's time zone but are saved and edited as UTC days"
  - id: WR-10
    severity: warning
    disposition: fixed
    title: "[frontend] Seat, screen and move modals work from a row snapshot that a refusal-triggered refetch does not update"
  - id: WR-11
    severity: warning
    disposition: fixed
    title: "[frontend] A failed quiet reload empties the whole screen, and overlapping reloads can land out of order"
  - id: IN-01
    severity: info
    disposition: open
    title: "[backend] Customer first admin cannot be re-invited by the partner (no resend path)"
  - id: IN-02
    severity: info
    disposition: open
    title: "[backend] Name and email clash responses are enumeration oracles for platform-wide data"
  - id: IN-03
    severity: info
    disposition: open
    title: "[backend] `claim` tolerates a malformed pool document and can over-allocate"
  - id: IN-04
    severity: info
    disposition: open
    title: "[backend] Duplicated constants and helpers"
  - id: IN-05
    severity: info
    disposition: open
    title: "[backend] Invite and password-reset rows are not cleaned up on tenant delete"
  - id: IN-06
    severity: info
    disposition: open
    title: "[backend] `current_partner` reports a stale or mis-typed token as \"suspended\""
  - id: IN-07
    severity: info
    disposition: open
    title: "[frontend] Accept-invite page maps every status-check failure to \"Couldn't reach the platform\""
  - id: IN-08
    severity: info
    disposition: open
    title: "[frontend] `PartnerPortal` and `PartnersDashboard` render a second `<main>` inside the shell's `<main id=\"main-content\">`"
  - id: IN-09
    severity: info
    disposition: open
    title: "[frontend] Partner viewer briefly sees admin-only controls while the overview loads or fails"
  - id: IN-10
    severity: info
    disposition: open
    title: "[frontend] Appoint, Move and Suspend/Reinstate submit guards are state-only, unlike the portal modals"
open: 10
total: 21
recorded: 2026-11-03T20:02:09.391Z
---

# Phase 87: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-01 | warning | fixed | a1a845740 |
| WR-02 | warning | fixed | a1a845740 |
| WR-03 | warning | fixed | a1a845740 |
| WR-04 | warning | fixed | a1a845740 |
| WR-05 | warning | fixed | a1a845740 |
| WR-06 | warning | fixed | 668056bef |
| WR-07 | warning | fixed | 668056bef |
| WR-08 | warning | fixed | d9543f351 |
| WR-09 | warning | fixed | d9543f351 |
| WR-10 | warning | fixed | d9543f351 |
| WR-11 | warning | fixed | d9543f351 |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |
| IN-07 | info | open | - |
| IN-08 | info | open | - |
| IN-09 | info | open | - |
| IN-10 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
