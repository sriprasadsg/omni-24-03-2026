---
phase: 77
review: 77-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "Permission refresh reloads app data with the OLD permissions"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "Sync `mfa_required_for` fails closed for every non-admin custom role (WebSocket rejects)"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "MFA role cache is never invalidated; the 60s promotion window is per worker, and the helper is dead code"
  - id: WR-04
    severity: warning
    disposition: open
    title: "A role holding any now-unknown or banned permission string can never be edited"
  - id: WR-05
    severity: warning
    disposition: open
    title: "`role_usage` caps the holder and mapping scan at 5000, so a role in use can be deleted"
  - id: WR-06
    severity: warning
    disposition: open
    title: "`resolveHashView` returns inherited `Object.prototype` members for `#constructor` and `#__proto__`"
  - id: WR-07
    severity: warning
    disposition: open
    title: "A Super Admin cannot pick a tenant's custom roles when creating or editing a user"
  - id: WR-08
    severity: warning
    disposition: fixed
    title: "Overlapping `loadAllData` runs have no ordering; the 30s tick still loads with the stale list and can overwrite the refreshed load"
  - id: WR-09
    severity: warning
    disposition: fixed
    title: "The periodic data load now waits on an `/auth/me` request that has no timeout and no rejection handling"
  - id: WR-10
    severity: warning
    disposition: fixed
    title: "An aborted `/auth/me` retry after a 401 token refresh signs the user out"
  - id: WR-11
    severity: warning
    disposition: open
    title: "`authFetch` still signs the user out when a caller's `AbortSignal` fires during the post-401 retry"
  - id: IN-01
    severity: info
    disposition: open
    title: "Role names that differ only by repeated whitespace render like a built-in role"
  - id: IN-02
    severity: info
    disposition: open
    title: "No unique index backs the role-name uniqueness rule"
  - id: IN-03
    severity: info
    disposition: open
    title: "`isEditable` is ignored by PUT and DELETE"
  - id: IN-04
    severity: info
    disposition: open
    title: "A role change is committed even if its audit entry cannot be written"
  - id: IN-05
    severity: info
    disposition: open
    title: "Smaller correctness and consistency points"
  - id: IN-06
    severity: info
    disposition: open
    title: "Test coverage relies on source-text matching"
  - id: IN-07
    severity: info
    disposition: open
    title: "The WR-01 source guard test is order-in-text only and brittle"
  - id: IN-08
    severity: info
    disposition: open
    title: "`refreshPermissions` and the Initial Data Load effect both reload data on a changed list"
  - id: IN-09
    severity: info
    disposition: fixed
    title: "The 10 s timeout does not bound the token-refresh wait, and the test does not cover the 401 or near-expiry paths"
  - id: IN-10
    severity: info
    disposition: open
    title: "A timed-out `/auth/me` request is abandoned, not cancelled"
  - id: IN-11
    severity: info
    disposition: open
    title: "The synchronous token path is dead in production and its docstrings are stale"
  - id: IN-12
    severity: info
    disposition: fixed
    title: "MFA cache invalidation is not in a `finally`, and an in-flight lookup can re-store the old answer"
  - id: IN-13
    severity: info
    disposition: open
    title: "A `create_role` whose read-after-write check fails leaves the role created, unaudited, and answers 503"
open: 17
total: 24
recorded: 2026-10-19T17:51:37.822Z
---

# Phase 77: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-01 | warning | fixed | a1f4488d1 (ref set before loadAllData; guard in catalogueAccess.test.ts) |
| WR-02 | warning | fixed | bee9299ce (socket connect awaits verify_token_async; tests in test_custom_role_mfa.py) |
| WR-03 | warning | fixed | bee9299ce (role writes invalidate the tenant cache; store error never less strict than last answer; 60 s TTL kept for other workers) |
| WR-04 | warning | open | - |
| WR-05 | warning | open | - |
| WR-06 | warning | open | - |
| WR-07 | warning | open | - |
| WR-08 | warning | fixed | b76b8af8d (refreshThenLoad; confirmed resolved in incremental review pass 2) |
| WR-09 | warning | fixed | 41fb29db5 (timeout + catch; confirmed resolved in review pass 3), timeout reworked in 3bb575186 |
| WR-10 | warning | fixed | 3bb575186 (race instead of abort; regression test reproduces the sign-out; not re-reviewed) |
| WR-11 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |
| IN-07 | info | open | - |
| IN-08 | info | open | - |
| IN-09 | info | fixed | 3bb575186 (race also bounds a stalled /auth/refresh; WR-10 test covers the 401 path) |
| IN-10 | info | open | - |
| IN-11 | info | open | - |
| IN-12 | info | fixed | 2bc310005 (per-tenant generation guard; role writes inside _role_write; confirmed resolved in review pass 5) |
| IN-13 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
