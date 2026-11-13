---
phase: 86-activity-reporting-hardening-live-validation
plan: 06
subsystem: autonomous-ops-reporting
tags: [export, csv, pdf, reportlab, csv-injection, pytest, autonomous-ops]
status: complete

requires:
  - phase: 86-01
    provides: reporting package constants (EXPORT_ROW_CAP), stats.compute/fold/time_saved/format_minutes, rule_names
provides:
  - D-18 commit of the user's seven export-controls files (HEAD no longer depends on uncommitted files)
  - views.activity_filter (the one filter behind the Activity list and the export)
  - reporting/export.py (ExportResult, build, csv_bytes, file_name, cap_sentence, CSV_HEADER, STATE_WORDS)
  - reporting/export_pdf.py (render_pdf: summary page, page break, rows table)
affects: [86-08, 86-11]

actuals:
  tokens: 16047
  tasks: 3
  commits: 5
plan_head_before: 70c94a725399962a8c21e10545f926d0d27b2d4c
plan_head_after: 0037d66db95ccc0102c0f6bbecb2ac02964a1e33

tech-stack:
  added: []
  patterns:
    - one filter object shared by the list and the export, so the file holds what the screen shows
    - export rows are plain 9-cell string lists; CSV sanitizes at write time, PDF escapes at Paragraph time
    - lazy import of export_pdf inside build to keep the CSV path free of reportlab

key-files:
  created:
    - backend/autonomous_ops/reporting/export.py
    - backend/autonomous_ops/reporting/export_pdf.py
    - backend/tests/test_autonomous_ops_export.py
    - backend/export_controls.py
    - backend/email_utils.py
  modified:
    - backend/autonomous_ops/views.py
    - backend/export_report_endpoint.py
    - backend/export_service.py
    - backend/app_middleware.py
    - backend/dlp_service.py
    - backend/reporting_endpoints.py

key-decisions:
  - "The D-18 files were committed whole and byte-identical after a secret scan found only credential-shaped regexes (dlp_service) and environment-variable reads (email_utils)."
  - "Export rows are limited by createdAt (not finishedAt) so the period matches the Activity list ordering and the 86-01 statistics window."
  - "A platform approver is identified by approval.approver.tier == 'platform' (set by views.actor_for); anything else is shown by name."
  - "The PDF per-rule and counts tables use the same fold as the Statistics card for the same window, so the two never disagree."

requirements-completed: [ACTV-06]

coverage:
  - id: D1
    description: "The user's seven export-controls files are one standalone, unchanged, secret-free commit on HEAD"
    requirement: ACTV-06
    verification:
      - kind: integration
        ref: "git archive HEAD snapshot imports app_middleware, export_report_endpoint, export_controls, dlp_service, reporting_endpoints; backend/tests/test_audit_export.py 6 passed"
        status: pass
      - kind: other
        ref: "sha256sum of the seven files after the commit equals the value recorded before it"
        status: pass
    human_judgment: false
  - id: D2
    description: "export.build returns the rows the Activity list shows for a state and period, newest first, capped at 5,000 with a Note row, none for zero rows"
    requirement: ACTV-06
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_export.py#test_activity_filter_gives_the_rows_the_list_shows"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_export.py#test_cap_keeps_the_newest_five_thousand_and_says_so"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_export.py#test_exactly_the_cap_is_not_truncated_and_has_no_note"
        status: pass
    human_judgment: false
  - id: D3
    description: "The CSV is formula-safe and a platform approver is shown to tenants as Platform administrator"
    requirement: ACTV-06
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_export.py#test_a_cell_starting_like_a_formula_cannot_run_as_one"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_export.py#test_a_platform_approver_is_named_only_to_platform_staff"
        status: pass
    human_judgment: false
  - id: D4
    description: "The PDF opens with a summary page (counts, per-rule table, labelled time-saved estimate, cap sentence), then the rows, with every cell escaped"
    requirement: ACTV-06
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_export.py#test_pdf_has_a_summary_page_then_the_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_export.py#test_pdf_cell_text_is_shown_literally_never_as_markup"
        status: pass
    human_judgment: true
    rationale: "Page layout and readability of the PDF are judged by eye; tests assert the text, page break and header repeat only."

duration: ~25min
completed: 2026-11-13
---

# Phase 86 Plan 06: Export builder Summary

**The user's export-controls work is committed as one standalone commit, and one tested builder (`export.build`) now turns exactly what the Activity list shows into a 5,000-row-capped, formula-safe CSV or a PDF whose first page is an honest summary (counts, per-rule table, a time-saved figure labelled as an estimate with its method).**

## What was built

- **D-18 commit (db8b8cd4c):** the seven files (`export_report_endpoint.py`, `export_service.py`, `app_middleware.py`, `dlp_service.py`, `reporting_endpoints.py`, `export_controls.py`, `email_utils.py`) were committed whole and unchanged. A clean `git archive` snapshot of HEAD imports all five named modules and passes `test_audit_export.py` (6 passed) on the private mongod.
- **`views.activity_filter`:** the scope and bucket filter that `list_page` built, extracted unchanged; `list_page` calls it. `views.py` went 448 to 455 lines (limit +10). A parity test compares the export's filter with `list_page` for four buckets.
- **`reporting/export.py` (132 lines):** `build` combines the filter with `createdAt >= now - days` (unless "all"), counts, takes the newest `EXPORT_ROW_CAP` by `(createdAt, id)` descending, presents rows with `views.present_row` and `views._host_names`, and returns `ExportResult`. CSV: fixed nine-column header, every text cell through `sanitize_csv_cell`, a final `Note` row with the cap sentence when cut. Zero rows gives `content=None, total=0`. Unknown period or format raises `ValueError`.
- **`reporting/export_pdf.py` (96 lines):** landscape letter; summary page (title, generated time UTC, filter line, four counts, per-rule table, `Time saved (estimate): {format_minutes}` plus the UI-SPEC 2d method sentence, cap sentence when cut), `PageBreak`, rows table with `repeatRows=1`. Every string passes through `xml.sax.saxutils.escape`. `build(fmt="pdf")` feeds it `stats.compute/fold/time_saved` for the same window and the organization name from `tenants`.

## D-18 evidence (before and after sha256, identical)

Status before: `M` for export_report_endpoint.py, export_service.py, app_middleware.py, dlp_service.py, reporting_endpoints.py; `??` for export_controls.py and email_utils.py. After the commit all seven read clean and `git diff --quiet HEAD` holds.

| File | sha256 (before = after) |
|------|-------------------------|
| backend/export_report_endpoint.py | d89f81622a91b49585a222590d9ae71da268487a4e5ddf9e08ad1dfc80e0a799 |
| backend/export_service.py | c5a37c8c2a48df0ce96cb7f7d03206fd61777dc5289532c1e9ccf2d9f5425b8f |
| backend/app_middleware.py | 9c465ddb83c66419023279aabeab688c32f8d9a305ef4577b6413af8da8cc58f |
| backend/dlp_service.py | dbea4c00f1d8f3f08f9c7faacab5960700cce5602e31c4226f30f95cf075d3f9 |
| backend/reporting_endpoints.py | eec89176787ccdafda1281fae615f2dde71c794207e1fde5a08d235beb8f4225 |
| backend/export_controls.py | 29412ee5b7dfbae5f5c6f0f708ae2c421c22969001f273c7e4e6907cd63351de |
| backend/email_utils.py | 4e92e5f8db1603f562f159bf3fd92fe63c0ba5214e1e9aaee577573f36977f63 |

Secret scan: no hits for private-key headers, AKIA ids, quoted literals of 8 or more characters assigned to password/secret/token/api_key, bearer tokens, credentialed mongodb URLs or SMTP passwords. A broader keyword grep was read in full: the only matches are the DLP detection regexes in `dlp_service.py`, `SECRET_KEY` imported (not defined) in `export_controls.py`, and `os.getenv("SMTP_*", "")` reads in `email_utils.py`. Nothing was pushed.

## Task Commits

| Task | Phase | Commit | Message |
|------|-------|--------|---------|
| 1 | n/a | db8b8cd4c | chore(export): commit the user's existing export-controls work (D-18) |
| 2 | RED | 8c8fcccca | test(86-06): add failing tests for the activity export builder |
| 2 | GREEN | 0795028ad | feat(86-06): shared Activity filter and the capped CSV export builder |
| 3 | RED | 78930af07 | test(86-06): add failing tests for the activity export PDF |
| 3 | GREEN | 0037d66db | feat(86-06): activity export PDF with a summary page and the rows |

## TDD Gate Compliance

- **RED, Task 2:** target `test_file_name_carries_the_tenant_and_the_day` failed on `'' == 'autonomous-ops-activity-t1-20261112.csv'` against an inert `export.py` skeleton (18 of 18 failed; the unrelated imports resolved so failures are assertions or the missing `views.activity_filter`). JUnit evidence passed `gsd-tools check tdd-red-evidence` with `RED_EVIDENCE_OK`. Semantic assessment: the target ran and failed on the planned assertion for the intended reason.
- **RED, Task 3:** target `test_pdf_has_a_summary_page_then_the_rows` failed on the empty bytes of an inert `export_pdf.py` skeleton (6 failed, 18 passed), `RED_EVIDENCE_OK`. Same semantic assessment.
- **GREEN:** both feat commits pass. No refactor commit was needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Plan note] Test wording for PDF escaping**
- **Found during:** Task 3 RED
- **Issue:** the plan's behavior line says a title appears escaped ('&lt;b&gt;', '&amp;') in the uncompressed stream. reportlab's Paragraph decodes the entities, so the stream holds the literal text `Pay <b>now</b> & win`; the escaped form never reaches the stream.
- **Fix:** the test asserts the literal text is present as one run, that no entity text appears, and that an unbalanced `<b>open & <i>never closed` renders (it would raise without the escape). This proves "shows literally and never changes the page", which is the plan's stated purpose.
- **Files modified:** backend/tests/test_autonomous_ops_export.py
- **Commit:** 78930af07, 0037d66db

**2. [Plan note] Task 2 builder handles CSV only until Task 3**
- `MEDIA_TYPES` held only `csv` in the Task 2 commit so a pdf request could not return CSV bytes; Task 3 added `pdf` and the lazy import. No behaviour specified by the plan changed.

**3. [Plan note] `build` takes an optional `now`**
- Added `now: Optional[datetime] = None` so period edges and the file name are testable. Routes (86-08) omit it.

**Total deviations:** 3 notes, 0 behaviour changes. **Impact:** none on the contract 86-08 and 86-11 rely on.

## Verification

- Task 1: both verify commands pass (commit file list exact, files tracked and clean; snapshot imports plus `test_audit_export.py` 6 passed).
- Task 2 and 3 verify commands plus `test_audit_export.py` and `test_autonomous_ops_endpoints.py`: 127 passed, 0 skipped on the private mongod (27998). Nothing ran against 27017.
- Acceptance greps: `activity_filter` defined once and called twice in views.py (455 lines); `sanitize_csv_cell` 3 and `EXPORT_ROW_CAP` 3 in export.py; `escape(` 1, `PageBreak` 2, `Time saved (estimate)` 1 in export_pdf.py; export.py 132 and export_pdf.py 96 lines.
- No backend restart, no UI publish, no push.

## Known Stubs

None.

## Threat Flags

None. No new endpoint or trust boundary; T-86-11 to T-86-14 are covered by the tests above and the D-18 scan.

## Notes for later plans

- 86-08 should call `export.build(db, tenant_id, bucket=..., days=..., fmt=..., viewer_is_platform_staff=...)`, answer 204 when `content is None`, and write the audit event from `shown`, `total`, `truncated`.
- `ExportResult.rows` holds the unsanitized nine-cell rows; only the CSV writer sanitizes.
- The export count for the `simulation` bucket uses `shadow` rows only; control rows appear only in the `all` bucket.

## Self-Check: PASSED

All created files exist (`export.py`, `export_pdf.py`, `test_autonomous_ops_export.py`, `export_controls.py`, `email_utils.py`) and all five commits (db8b8cd4c, 8c8fcccca, 0795028ad, 78930af07, 0037d66db) are ancestors of HEAD.
