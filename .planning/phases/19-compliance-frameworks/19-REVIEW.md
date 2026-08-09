---
phase: 19-compliance-frameworks
reviewed: 2026-07-04T00:00:00Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - backend/frameworks/ens.py
  - backend/frameworks/mas_trm.py
  - backend/frameworks/irap.py
  - backend/frameworks/iso_27017.py
  - backend/frameworks/iso_27018.py
  - backend/frameworks/bsi_c5.py
  - backend/frameworks/ffiec.py
  - backend/frameworks/owasp_top10.py
  - backend/frameworks/tisax.py
  - backend/frameworks/aws_well_architected.py
  - backend/frameworks/rbi_csf.py
  - backend/frameworks/tic_3_0.py
  - backend/frameworks/kisa_isms.py
  - backend/frameworks/fedramp_high.py
  - backend/frameworks/__init__.py
findings:
  critical: 3
  warning: 3
  info: 2
  total: 8
status: issues_found
---

# Phase 19: Code Review Report

**Reviewed:** 2026-07-04
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

14 new compliance-framework data modules (`ens`, `mas_trm`, `irap`, `iso_27017`, `iso_27018`, `bsi_c5`, `ffiec`, `owasp_top10`, `tisax`, `aws_well_architected`, `rbi_csf`, `tic_3_0`, `kisa_isms`, `fedramp_high`) were added under `backend/frameworks/`, following this codebase's real convention of `.py` modules with `FRAMEWORK_ID` / `FRAMEWORK_NAME` / `FRAMEWORK_VERSION` / `CONTROLS` (the plan's `.json` schema wording is stale and is not treated as a defect here — the `.py` convention matches every pre-existing framework file, e.g. `nist_800_53.py`). All 15 files parse and import cleanly, control dictionaries are internally well-formed (no duplicate IDs, no missing keys), and `backend/frameworks/__init__.py` was updated to import and re-export the 14 new modules.

However, the implementation falls short of the phase's stated objective ("reach feature parity with Probo and Comp AI... a much wider range of... frameworks") in three material ways, all confirmed by direct inspection:

1. Every one of the 14 modules has far fewer controls than the plan's explicit must-have minimums (in several cases less than a third of the target).
2. None of the 14 modules define the `evaluate_controls(db)` entry point that this codebase's serving path (`compliance_frameworks_endpoints.py`) requires from every framework module — so even if wired up, calling any of them would raise `AttributeError`.
3. None of the 14 frameworks are registered anywhere a user-facing code path can reach them: they are absent from both seed files (`seed_compliance_frameworks_a.py`, `seed_compliance_frameworks_b.py`) that populate the `compliance_frameworks` Mongo collection, and absent from `compliance_frameworks_endpoints.py`'s `_REGISTRY` dict, which is the only consumer of framework modules found in the codebase (`continuous_compliance_service.py` has its own, much smaller, hardcoded 3-entry framework map and also does not reference any of the 14).

Net effect: the 14 files exist, import without error, and satisfy a superficial "loadable" check, but are functionally dead code — unreachable by any API, and non-functional (missing evaluation logic) even if reachability were fixed. This does not meet the phase's parity objective.

## Critical Issues

### CR-01: 14 new frameworks are not registered in any code path a user can reach — completely invisible in the product

**File:** `backend/compliance_frameworks_endpoints.py:13-56`, `backend/seed_compliance_frameworks_a.py`, `backend/seed_compliance_frameworks_b.py`, `backend/continuous_compliance_service.py:23-25`
**Issue:** `compliance_frameworks_endpoints.py` (the only router that serves framework data/evaluation to the frontend) imports a fixed set of framework modules and builds `_REGISTRY` from them (lines 13-56); none of `ens, mas_trm, irap, iso_27017, iso_27018, bsi_c5, ffiec, owasp_top10, tisax, aws_well_architected, rbi_csf, tic_3_0, kisa_isms, fedramp_high` are imported or added to `_REGISTRY`. The `GET /api/frameworks` list endpoint (line 78) also only reflects rows already present in the `db.compliance_frameworks` Mongo collection — grepping both seed files that populate that collection (`seed_compliance_frameworks_a.py`, `seed_compliance_frameworks_b.py`) shows zero entries for any of the 14 new framework IDs. `continuous_compliance_service.py` has an independent, separate framework map (lines 23-25) with only 3 hardcoded entries (`nist_csf`, `cis_v8`, `iso27001_2022`) and likewise references none of the 14. Since `backend/frameworks/__init__.py` is the only place the 14 modules are imported, and nothing downstream consumes that import for anything user-visible, these frameworks cannot appear in the frameworks list, cannot be evaluated via `GET /api/frameworks/{id}`, cannot have evidence auto-collected via `POST /api/frameworks/{id}/auto-evidence`, and cannot appear in gap reports — for any user, ever, in the current state of the code.
**Fix:** Add each new module to `_REGISTRY` in `compliance_frameworks_endpoints.py` (import + dict entry, mirroring the existing 30 entries), and add a `compliance_frameworks` seed document for each of the 14 IDs in `seed_compliance_frameworks_a.py`/`_b.py` (mirroring the existing `nist_800_53`, `gdpr`, etc. entries) so `GET /api/frameworks` can list them. This must be done in addition to fixing CR-02 below, since wiring alone does not make the modules functional.

### CR-02: All 14 new framework modules are missing `evaluate_controls()` — calling any of them (once wired) will crash

**File:** `backend/frameworks/ens.py`, `mas_trm.py`, `irap.py`, `iso_27017.py`, `iso_27018.py`, `bsi_c5.py`, `ffiec.py`, `owasp_top10.py`, `tisax.py`, `aws_well_architected.py`, `rbi_csf.py`, `tic_3_0.py`, `kisa_isms.py`, `fedramp_high.py` (entire files — none define `evaluate_controls`)
**Issue:** Every consumer of a framework module in this codebase calls `await mod.evaluate_controls(db)` (see `compliance_frameworks_endpoints.py:105`, `:127`, `:161`, `:219`, and `continuous_compliance_service.py`). The established per-file convention (see `backend/frameworks/nist_800_53.py:65-159`) is: a private `async def _run_check(db, ctrl)` that maps each control's `check_type` to an actual MongoDB-backed check, plus a public `async def evaluate_controls(db) -> List[Dict[str, Any]]` that iterates `CONTROLS` and calls `_run_check` per control. None of the 14 new files define either function — they contain only static `CONTROLS` data. Confirmed via `grep -c "def evaluate_controls"` against all 14 files: zero matches in every file. `_run_check` in `nist_800_53.py` is a module-private helper (single leading underscore, not re-exported by `frameworks/__init__.py`), so it cannot be reused by the new modules without being duplicated or refactored into a shared helper — and it wasn't. This means even after fixing CR-01's wiring gap, any call to `evaluate_framework`, `all_frameworks_summary`, `collect_auto_evidence`, or `framework_gaps` for one of these 14 IDs raises `AttributeError: module 'ens' has no attribute 'evaluate_controls'` and 500s.
**Fix:** Implement `_run_check`/`evaluate_controls` in each of the 14 modules (or, better, extract a shared, generic check-dispatch helper — most `check_type` values reused here, e.g. `mfa_configured`, `disk_encrypted`, `tls_enabled`, `rbac_configured`, already exist in `nist_800_53.py`'s `_run_check` — into a shared `frameworks/_common_checks.py` and have each module call into it) before these frameworks can be considered functional, not just importable.

### CR-03: Every new framework's control count falls far short of the phase's explicit must-have minimums

**File:** `backend/frameworks/ens.py`, `mas_trm.py`, `irap.py`, `iso_27017.py`, `iso_27018.py`, `bsi_c5.py`, `ffiec.py`, `tisax.py`, `aws_well_architected.py`, `rbi_csf.py`, `tic_3_0.py`, `kisa_isms.py`, `fedramp_high.py`
**Issue:** `.planning/phases/19-compliance-frameworks/19-01-PLAN.md` (`must_haves.truths`, lines 28-41) specifies minimum control counts per framework. Verified by parsing `CONTROLS` in each module with `ast`:

| Framework | Actual (`len(CONTROLS)`) | Plan minimum | Shortfall |
|---|---|---|---|
| `ens` | 22 | 75+ | -53 |
| `mas_trm` | 18 | 30+ | -12 |
| `irap` | 27 | 40+ | -13 |
| `iso_27017` | 24 | 37 | -13 |
| `iso_27018` | 15 | 25 | -10 |
| `bsi_c5` | 30 | 55+ | -25 |
| `ffiec` | 25 | 50+ | -25 |
| `owasp_top10` | 10 | 10 | meets target |
| `tisax` | 26 | 40+ | -14 |
| `aws_well_architected` | 15 | 32 | -17 |
| `rbi_csf` | 20 | 30+ | -10 |
| `tic_3_0` | 15 | 20+ | -5 |
| `kisa_isms` | 34 | 80+ | -46 |
| `fedramp_high` | 131 | 421 | -290 |

Only `owasp_top10` meets its target (10/10, which matches the fixed, well-known list of 10 OWASP risk categories — an appropriate ceiling). Every other framework is materially under-delivered; `fedramp_high` (the plan's #1 priority item, described as "NIST 800-53 High baseline, 421 controls") ships less than a third of the required control set, and `ens`/`kisa_isms` ship roughly a quarter to a third of theirs. This is a direct must-have violation for FW-01, not a stylistic shortfall — the phase objective was explicitly to reach "feature parity" on framework breadth, and the delivered breadth is 20-75% short across the board.
**Fix:** Expand each `CONTROLS` list to at least the plan's stated minimum, sourcing additional controls from the actual published framework documents (e.g., FedRAMP High control baseline spreadsheet from NIST 800-53 Rev 5, KISA's 12 ISMS domains with their full sub-control lists, ENS's 5 dimensions x their full measure catalog) rather than a representative subset.

## Warnings

### WR-01: No test coverage added for any of the 14 new framework modules

**File:** `backend/tests/` (no corresponding test files); `backend/frameworks/ens.py` through `fedramp_high.py`
**Issue:** Searching `backend/tests/` for references to any of the 14 new framework IDs (`ens`, `mas_trm`, `fedramp_high`, `kisa_isms`, etc.) returns no matches. There is no test verifying that `CONTROLS` is well-formed, that `FRAMEWORK_ID` matches the module filename (a convention this codebase clearly relies on given `_REGISTRY` keys), or — once CR-02 is fixed — that `evaluate_controls` behaves correctly for representative DB states. Given 14 new modules were added in one phase, the complete absence of tests is a coverage gap for a change of this size.
**Fix:** Add a parametrized test (e.g., `test_frameworks_schema.py`) that iterates every module exported from `backend/frameworks/__init__.py` and asserts `FRAMEWORK_ID`/`FRAMEWORK_NAME`/`FRAMEWORK_VERSION` are non-empty strings, `CONTROLS` is a non-empty list of dicts with the required keys, control `id`s are unique, and (once implemented) `evaluate_controls` returns one result per control.

### WR-02: Several controls' `check_type` does not semantically match their `title`/`description`, which will produce misleading evaluation results once `evaluate_controls` is implemented

**File:** `backend/frameworks/kisa_isms.py:6` (`ISMS-2.1`), `kisa_isms.py:11` (`ISMS-3.2`), `kisa_isms.py:15` (`ISMS-14.2`), `iso_27018.py:8` (`ISO27018-7.1.1`)
**Issue:** `ISMS-2.1` ("CEO commitment", i.e., a governance/sign-off control) is mapped to `check_type: "separation_of_duties"`, which checks something structurally unrelated. `ISMS-3.2` ("Risk treatment") and `ISMS-14.2` ("Internal audit") are both mapped to `check_type: "pen_testing"`, conflating a treatment-plan control and an internal-audit control with an external penetration test. `ISO27018-7.1.1` ("Disclosure of PII" — i.e., restricting who PII is disclosed to) is mapped to `check_type: "incident_reporting"`, which is a breach-notification check, not an access-restriction check. Because `check_type` is the only signal `_run_check`-style dispatch logic (see `nist_800_53.py`) uses to decide what to actually check in the database, these mismatches will cause a future `evaluate_controls` implementation to report pass/fail status for the wrong underlying condition, producing compliance results that don't reflect the stated control.
**Fix:** Audit `check_type` assignments across all 14 files against their `title`/`description` and correct mismatches, or introduce new `check_type` values where no existing one semantically fits, before implementing CR-02.

### WR-03: Inconsistent coding style across the 14 new files undermines maintainability

**File:** `backend/frameworks/ens.py:2-26`, `mas_trm.py`, `irap.py`, `iso_27018.py`, `bsi_c5.py`, `ffiec.py`, `owasp_top10.py`, `tisax.py`, `aws_well_architected.py`, `rbi_csf.py`, `tic_3_0.py`, `kisa_isms.py` vs. `iso_27017.py`, `fedramp_high.py`
**Issue:** 12 of the 14 files pack `FRAMEWORK_ID`/`FRAMEWORK_NAME`/`FRAMEWORK_VERSION` onto a single semicolon-separated line and each control dict onto one dense unindented/unspaced line (e.g., `ens.py:2`, every line in `mas_trm.py`). The other 2 (`iso_27017.py`, `fedramp_high.py`) use `from __future__ import annotations`, explicit `List[Dict[str, Any]]` typing, and normally-formatted multi-line control blocks, matching the style of the pre-existing `nist_800_53.py`. This inconsistency (no type hints, no per-field spacing, semicolon-chained module-level assignment) is a step down from the codebase's established formatting for this file family and makes the 12 dense files harder to diff and review.
**Fix:** Reformat the 12 dense-style files to match `iso_27017.py`/`fedramp_high.py`'s (and the pre-existing `nist_800_53.py`'s) typed, multi-line style for consistency.

## Info

### IN-01: `fedramp_high.py` docstring makes a false claim about its own control count

**File:** `backend/frameworks/fedramp_high.py:1`
**Issue:** The module docstring reads `"""FedRAMP High — NIST 800-53 High baseline (421+ controls)."""`, but `CONTROLS` in this same file contains only 131 entries (see CR-03). The comment is not just aspirational — it directly misstates the file's own contents to anyone reading the source.
**Fix:** Update the docstring to reflect the actual count (or remove the specific number) until CR-03 is resolved, e.g. `"""FedRAMP High — NIST 800-53 High baseline (partial; 131 of 421 controls)."""`.

### IN-02: Dense single-line control definitions reduce readability and diff quality

**File:** `backend/frameworks/ens.py`, `mas_trm.py`, `irap.py`, `iso_27018.py`, `bsi_c5.py`, `ffiec.py`, `owasp_top10.py`, `tisax.py`, `aws_well_architected.py`, `rbi_csf.py`, `tic_3_0.py`, `kisa_isms.py`
**Issue:** Each `CONTROLS` entry is written as a single long line with no spacing around `:`/`,` (e.g. `{"id":"ENS-mp1","theme":"Organization","check_type":"policies_present",...}`), unlike the multi-line, spaced style used elsewhere in this file family. This is a minor style nit distinct from WR-03's broader typing/consistency point — future diffs adding or editing a single control field will show the entire line as changed, obscuring the actual edit.
**Fix:** Reformat with one key per visual field grouping or run through a standard formatter (e.g., `black`) to normalize spacing.

---

_Reviewed: 2026-07-04_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
