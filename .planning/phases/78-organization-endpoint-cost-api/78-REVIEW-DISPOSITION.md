---
phase: 78
review: 78-REVIEW.md
titles: json
findings:
  - id: WR-07
    severity: warning
    disposition: fixed
    title: "The book-value route maps an unreadable purchase date to \"no depreciation policy\" and does not guard an unreadable cost"
  - id: IN-14
    severity: info
    disposition: fixed
    title: "The new parity test checks route against row for two assets only, so the remaining disagreements in WR-07 stay invisible"
  - id: WR-05
    severity: warning
    disposition: fixed
    title: "A stale preview or save failure is re-thrown to the builder toast, rendering the server's \"Select a tenant\" text for the wrong tenant"
  - id: WR-06
    severity: warning
    disposition: fixed
    title: "Salvage above cost now makes the cost API disagree with the per-asset Finance route for the same asset (parity broken, no test)"
  - id: IN-10
    severity: info
    disposition: fixed
    title: "`handleDeleteConfirm` reads `pending` and `shown` from the render-time closure"
  - id: IN-11
    severity: info
    disposition: fixed
    title: "The new \"Unknown tenant\" 400 is not treated as a blocked state on the frontend"
  - id: IN-12
    severity: info
    disposition: fixed
    title: "The reason code reused for salvage above cost tells the user to fix something that is not wrong"
  - id: IN-13
    severity: info
    disposition: fixed
    title: "The existence check accepts any `tenants` row, including partner organizations"
  - id: IN-06
    severity: info
    disposition: fixed
    title: "Custom report definitions saved before this change under the Owner's own tenant become unreachable"
  - id: IN-07
    severity: info
    disposition: fixed
    title: "A run in flight for a report is not cancelled when that report is deleted"
  - id: IN-08
    severity: info
    disposition: fixed
    title: "Save, preview and delete do not route a \"Select a tenant\" 400 through `takeTenantRejection`"
  - id: IN-09
    severity: info
    disposition: fixed
    title: "`needsTenant` repeats a condition the role helper already covers"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "The shown result is decoupled from `activeKind`/`activeKey`, so a failed or superseded run leaves the previous report on screen with export buttons for a different report"
  - id: IN-04
    severity: info
    disposition: fixed
    title: "The Run button gate depends only on `isSuperAdminRoleName`; other platform tiers fall through to a toast (still open)"
  - id: IN-05
    severity: info
    disposition: fixed
    title: "An export started before a tenant switch is not cancelled and keeps `exportingFormat` set"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "ReportsPanel `runPrebuilt` has no stale-response guard; the tenant-switch reset does not clear `running` (confirms the 78-UI-REVIEW lead)"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "Custom report routes are not tenant-resolved, so an Owner gets cross-tenant book values while the cost surfaces return 400"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "Cost detail route does not return \"the list row\" when the partner asset is disposed or retired"
  - id: IN-01
    severity: info
    disposition: fixed
    title: "A fabricated `X-Tenant-ID` from an Owner is accepted and used for writes"
  - id: IN-02
    severity: info
    disposition: fixed
    title: "Asset value report population filter does not normalize `lifecycleStatus`"
  - id: IN-03
    severity: info
    disposition: fixed
    title: "A salvage value above the purchase cost produces a book value above the purchase cost"
open: 0
total: 21
recorded: 2026-11-17T10:53:35.788Z
---

# Phase 78: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-07 | warning | fixed | 78-REVIEW-FIX.md |
| IN-14 | info | fixed | 78-REVIEW-FIX.md |
| WR-05 | warning | fixed | 78-REVIEW-FIX.md (not in the current review) |
| WR-06 | warning | fixed | 78-REVIEW-FIX.md (not in the current review) |
| IN-10 | info | fixed | 78-REVIEW-FIX.md (not in the current review) |
| IN-11 | info | fixed | 78-REVIEW-FIX.md (not in the current review) |
| IN-12 | info | fixed | 78-REVIEW-FIX.md (not in the current review) |
| IN-13 | info | fixed | 78-REVIEW-FIX.md (not in the current review) |
| IN-06 | info | fixed | no code change needed: live omni_platform has no itam_reports collection (0 documents, checked read-only 2026-11-17), so no definition is stranded; evidence in 78-REVIEW-FIX.md (not in the current review) |
| IN-07 | info | fixed | 78-REVIEW-FIX.md (not in the current review) |
| IN-08 | info | fixed | 78-REVIEW-FIX.md (not in the current review) |
| IN-09 | info | fixed | 78-REVIEW-FIX.md (not in the current review) |
| WR-04 | warning | fixed | gap plan 78-13 (3a3353c21..5f4ddc665); confirmed fixed by the incremental re-review bbe3cb55b ("Targeted findings") (not in the current review) |
| IN-04 | info | fixed | gap plan 78-15 (5bf03c54f..747b2b972); confirmed fixed by the incremental re-review bbe3cb55b ("Targeted findings") (not in the current review) |
| IN-05 | info | fixed | gap plan 78-13 (cd2ac7ab4, 5f4ddc665); confirmed fixed by the incremental re-review bbe3cb55b ("Targeted findings") (not in the current review) |
| WR-01 | warning | fixed | gap plan 78-11 (b26ea046e, 5278952bd); confirmed fixed by the incremental re-review c16cdf34c ("Prior findings re-assessed") (not in the current review) |
| WR-02 | warning | fixed | gap plans 78-12 (79b6bfb9f..8896830ab) and 78-14 (388af39c5..fd11ee317); confirmed fixed by the incremental re-review bbe3cb55b ("Targeted findings") (not in the current review) |
| WR-03 | warning | fixed | 78-REVIEW-FIX.md (not in the current review) |
| IN-01 | info | fixed | 78-REVIEW-FIX.md (not in the current review) |
| IN-02 | info | fixed | 78-REVIEW-FIX.md (not in the current review) |
| IN-03 | info | fixed | 78-REVIEW-FIX.md (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
