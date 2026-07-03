---
phase: "03"
fixed_at: 2026-07-03T16:54:41Z
review_path: .planning/phases/03-audit-ready-export/03-REVIEW.md
iteration: 2
findings_in_scope: 11
fixed: 11
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report — Audit-Ready Export (Iteration 2)

**Fixed at:** 2026-07-03T16:54:41Z
**Source review:** .planning/phases/03-audit-ready-export/03-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 11 (2 critical, 5 warning, 4 info — fix_scope: all)
- Fixed: 11
- Skipped: 0

## Fixed Issues

### CR-01: CSV/XLSX export writes user-controlled text unsanitized — formula injection (CWE-1236)

**Files modified:** `backend/compliance_reporting_data.py`, `backend/compliance_reporting_service.py`, `backend/compliance_reporting_excel.py`
**Commit:** bda4585
**Applied fix:** Added a shared `_sanitize_cell()` helper in `compliance_reporting_data.py` that prefixes any string cell value beginning with a formula-trigger character (`=`, `+`, `-`, `@`, tab, CR) with a leading single-quote, neutralizing spreadsheet formula interpretation while remaining human-readable. Non-string values pass through unchanged so native XLSX numeric formatting is preserved. Applied at all four `csv.writer.writerow()` call sites in `_generate_csv`/`_generate_all_csv` and all four `ws.append()` call sites in `_generate_excel`/`_generate_all_excel`. Verified with `openpyxl` that `=HYPERLINK(...)`-style payloads are no longer interpreted as live formulas.

### CR-02: PDF export crashes (500) on ordinary evidence text containing `<tag>`-like sequences

**Files modified:** `backend/compliance_reporting_pdf.py`
**Commit:** 43785a7
**Applied fix:** Added `import html` and wrapped header/cell text in `html.escape(str(v), quote=False)` before constructing `reportlab.platypus.Paragraph` objects in `make_table()`. Reproduced the exact crash from the review (`Paragraph("Passed <br> review", ...)` raising `ValueError`) and confirmed the escaped version renders without error while preserving readable text.

### WR-01: `list_compliance_reports` reads a field name that `_store_report_meta` never writes

**Files modified:** `backend/compliance_reports_endpoints.py`
**Commit:** 526ca51
**Applied fix:** Changed `doc.get("created") or doc.get("generatedAt") or ""` to `doc.get("createdAt") or doc.get("created") or doc.get("generatedAt") or ""`, matching the key actually persisted by `_store_report_meta`.

### WR-02: Excel sheet-name truncation still exceeds the 31-character OOXML limit

**Files modified:** `backend/compliance_reporting_excel.py`
**Commit:** e48a414
**Applied fix:** Changed the truncation length from `[:24]` to `[:22]` (31 − len(" Controls") = 22, the longer of the two suffixes). Verified with the `"NIST Cybersecurity Framework v2.0"` example from the review that both `"{short} Assets"` (29 chars) and `"{short} Controls"` (31 chars) now stay within the 31-char OOXML limit.

### WR-03: Evidence merge treats two id-less evidence records as duplicates (`None == None`)

**Files modified:** `backend/compliance_reporting_data.py`
**Commit:** a982291
**Applied fix:** Added an `_ev_key()` helper that falls back through `id` → `url` → `name` → `id(e)` (Python object identity) rather than comparing raw `.get("id")` values, so two unrelated id-less records never collide. Verified with a synthetic test that two distinct id-less evidence records are both now retained in the merged list (previously the standalone one was silently dropped).

### WR-04: `_REPORTS_DIR` is cwd-relative, inconsistent with every sibling module

**Files modified:** `backend/compliance_reports_endpoints.py`
**Commit:** 6109be1
**Applied fix:** Changed `_REPORTS_DIR = "static/reports"` to `_REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "reports")`, matching the pattern used by every other sibling module (`app.py`, `compliance_report_endpoints.py`, `ComplianceReportingService.reports_dir`).

### WR-05: `sorted(asset_counts.items())` can raise `TypeError` if any `assetId` is present-but-`None`

**Files modified:** `backend/compliance_reporting_data.py`
**Commit:** 5b415a1
**Applied fix:** Changed `doc.get("assetId", "unknown")` to `doc.get("assetId") or "unknown"` so a present-but-falsy (`None`/`""`) `assetId` is normalized the same way as a missing key, matching the guard already used eleven lines later in the same function. Verified with a synthetic mixed-key dict that `sorted()` no longer raises `TypeError`.

### IN-01: `STATUS_LEGEND` is still a dead export (carried forward, unresolved)

**Files modified:** `backend/compliance_reporting_data.py`
**Commit:** 91d903d
**Applied fix:** Removed the `STATUS_LEGEND` dict entirely after confirming via `grep -rn "STATUS_LEGEND" backend/` that its definition site was the only reference in the codebase.

### IN-02: `test_legacy_download_allows_owner` still doesn't exercise the ownership-check path (carried forward, unresolved)

**Files modified:** `backend/tests/test_audit_export.py`
**Commit:** 9fd6f91
**Applied fix:** Replaced the `patch("os.path.exists", return_value=False)` approach (which made the route 404 before ever reaching the tenant-ownership check) with a real temporary file served from a real reports directory (`tempfile.TemporaryDirectory()` + `patch.object(compliance_reports_endpoints, "_REPORTS_DIR", tmp_dir)`), then asserted `response.status_code == 200`. Verified independently that the same setup with a mismatched tenant in the DB mock genuinely returns 403 — confirming the test now discriminates the ownership-check path rather than short-circuiting on 404.

### IN-03: Broad `except Exception: ... continue` silently skips frameworks in combined reports

**Files modified:** `backend/compliance_reporting_service.py`, `backend/compliance_reporting_excel.py`
**Commit:** 15d16db
**Applied fix:** Narrowed `except Exception as exc` to `except ValueError as exc` in both `_generate_all_csv` and `_generate_all_excel`, matching the one documented failure mode (`_build_report_data` raising `ValueError` for an unresolvable framework). Unexpected exceptions (`KeyError`, `AttributeError`, DB timeouts) now propagate instead of being silently swallowed.

### IN-04: Download route reveals filename existence before checking tenant ownership

**Files modified:** `backend/compliance_reports_endpoints.py`
**Commit:** 9424d8d
**Applied fix:** Reordered `download_compliance_report` so the tenant-ownership DB lookup runs before the filesystem `os.path.exists()` check (the path-traversal guard remains first, since it is a security check unrelated to existence disclosure). A cross-tenant caller now always receives 403 regardless of whether the file exists, eliminating the existence oracle.

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-07-03T16:54:41Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
