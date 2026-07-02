---
phase: 07-evidence-lifecycle-staleness-chain-of-custody
fixed_at: 2026-07-02T18:44:20Z
review_path: .planning/phases/07-evidence-lifecycle-staleness-chain-of-custody/07-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 8
skipped: 1
status: partial
---

# Phase 07: Code Review Fix Report

**Fixed at:** 2026-07-02T18:44:20Z
**Source review:** .planning/phases/07-evidence-lifecycle-staleness-chain-of-custody/07-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (3 critical, 6 warning — Info findings excluded per `fix_scope: critical_warning`)
- Fixed: 8
- Skipped: 1

This review was originally produced 2026-06-21. All findings were re-verified against the current codebase before fixing; one warning (WR-05) had already been resolved by later, unrelated work and was left untouched.

## Fixed Issues

### CR-01: Path-traversal guard missing `os.sep` in `delete_control_direct_evidence`

**Files modified:** `backend/compliance_evidence_endpoints.py`
**Commit:** `380338f`
**Applied fix:** Line had drifted from 492 to 494 since the review, but the vulnerable pattern (`str(resolved).startswith(str(_safe_dir))` with no separator) was unchanged. Replaced with the same confinement check already used by `delete_compliance_evidence` and the download handler: `str(resolved).startswith(str(_safe_dir) + os.sep) or resolved == _safe_dir`.

### CR-02: `delete_compliance_evidence` returns `None` (no HTTP response) on unhandled exception

**Files modified:** `backend/compliance_evidence_endpoints.py`
**Commit:** `a83e833`
**Applied fix:** The bare `except Exception as e: logger.error(...)` (now at lines 321-322) fell off the end of the function with no return/raise, exactly as described. Added `raise HTTPException(status_code=500, detail="Internal server error")` after the log call, matching the pattern used by every other handler in the file.

### CR-03: `get_staleness_threshold` does not enforce its documented minimum of 1

**Files modified:** `backend/evidence_staleness.py`
**Commit:** `0ba447a`
**Applied fix:** Added a local `_safe_threshold(raw_val) -> max(1, raw_val)` helper and applied it to both the per-tenant and global document lookups before returning `thresholdDays`, so a `0` or negative value written directly to `system_settings` can no longer make every evidence item appear stale. The hard-coded `7` fallback was already safe and left unchanged.

### WR-01: `compliance_evidence_endpoints` is not registered in `router_registry.py`

**Files modified:** `backend/router_registry.py`
**Commit:** `313ccca`
**Applied fix:** Confirmed the routes are not actually missing — `compliance_endpoints.py` imports `compliance_evidence_endpoints.router as evidence_router` and mounts it via `router.include_router(evidence_router)`, and `compliance_endpoints` itself is loaded through the registry (`_load(app, "compliance_endpoints", "router")`). Rather than adding a duplicate `_load(...)` call (which would double-register every evidence route), added a comment directly above that registry line documenting the alternate load path, per the review's suggested alternative fix.

### WR-02: Inconsistent `_SUPER_ROLES` sets across endpoint files

**Files modified:** `backend/compliance_evidence_lifecycle_endpoints.py`
**Commit:** `36eeb5b`
**Applied fix:** Re-checked both files first. `compliance_evidence_endpoints.py`'s module-level `_SUPER_ROLES` had already been consolidated to a single frozenset containing `admin`, `superadmin`, `super_admin`, `Super Admin`, and `platform-admin` (the review's third inline set at old line 139 no longer exists — already cleaned up by later work). Only `compliance_evidence_lifecycle_endpoints.py`'s `_SUPER_ROLES` was still missing `admin`. Added `admin` to that set so both files now use an identical 5-member role set, plus a comment cross-referencing the sibling file to prevent future drift.

### WR-03: CoC fire-and-forget swallows failures silently in a compliance audit trail

**Files modified:** `backend/evidence_coc.py`
**Commit:** `b9bdc37`
**Applied fix:** No metrics/statsd/prometheus client exists anywhere in this backend, so the review's literal `metrics.increment(...)` suggestion had no library to call into. Applied the "at minimum" fallback instead: added a module-level `_coc_append_failure_count` counter that increments on every write failure and is included in the ERROR log line (`process_total_failures=%d`), giving a log-based alerting rule something concrete to grep/threshold on without inventing new infrastructure.

### WR-04: `EvidenceSettings` does not handle non-OK HTTP responses from `fetchStalenessThreshold`

**Files modified:** `services/apiService.ts`
**Commit:** `7d87064`
**Applied fix:** Added `if (!res.ok) return { thresholdDays: 7 };` before `res.json()` in `fetchStalenessThreshold`, exactly as the review suggested. `tsc` is not installed in this project (no local TypeScript devDependency reachable via `npx`), so Tier 2 syntax verification fell back to Tier 3/Tier 1 (re-read only).

### WR-06: `ChainOfCustodyPanel` uses array index as React list key

**Files modified:** `components/ChainOfCustodyPanel.tsx`
**Commit:** `c94c46f`
**Applied fix:** Replaced `key={idx}` with a derived `entryKey = evidenceId && ts ? \`${evidenceId}-${ts}\` : \`coc-${idx}\`` (falls back to an index-based key only if both fields are missing, which is defensive belt-and-suspenders beyond the review's literal suggestion of an unconditional template string). Same `tsc`-unavailable caveat as WR-04 applies to verification.

## Skipped Issues

### WR-05: `file.text()` called on binary evidence files (PDF, DOCX, XLSX) during ingestion

**File:** `components/AssetComplianceList.tsx:51` (original review line; current line ~62)
**Reason:** Already fixed by later, unrelated work — the root cause described in the review no longer exists in the current codebase.
**Original issue:** `handleFileChange` called `file.text()` unconditionally on every uploaded file, including binary formats, corrupting content ingested into the RAG knowledge base.

Current code (`handleFileChange`, lines 45-69) now gates the `file.text()` call behind an `isIngestibleText` check derived from an `INGESTIBLE_TEXT_TYPES` allowlist (`text/plain`, `text/markdown`, `application/json`, `text/csv`), with a code comment explicitly citing the garbling risk for PDF/DOCX/XLSX. No further action needed.

---

_Fixed: 2026-07-02T18:44:20Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
