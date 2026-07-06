---
phase: 25-cloud-checks-execution-gaps
fixed_at: 2026-07-06T13:00:00Z
review_path: .planning/phases/25-cloud-checks-execution-gaps/25-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 2
status: critical_warnings_fixed
---

# Phase 25: Code Review Fix Report

**Fixed at:** 2026-07-06T13:00:00Z
**Source review:** .planning/phases/25-cloud-checks-execution-gaps/25-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (CR-01, CR-02, WR-01 through WR-06 — default fix scope: Critical + Warning)
- Fixed: 8
- Skipped: 2 (IN-01, IN-02 — info-level, out of scope for this pass)

## Fixed Issues

### CR-01: `cfn-ec2-admin-userdata` check has inverted PASS/FAIL logic

**Files modified:** `backend/iac_scanner_service.py`
**Applied fix:** Added the missing `"vulnerable_marker": True` to the `cfn-ec2-admin-userdata` check dict, matching its Terraform analog (`tf-ec2-admin`). Without it, `scan_code()` treated the check as mitigation-style (negative_pattern match = PASS), so an instance whose UserData actually referenced admin/root elevation was reported PASS and a clean instance was reported FAIL — exactly backwards.
**Verification:** Manually constructed a vulnerable CloudFormation template (`UserData` containing `useradd admin`) and a safe one; confirmed `scan_code()` now returns `FAIL` for the vulnerable case and `PASS` for the safe case. Full backend suite (764 passed / 22 skipped) shows no regression.

### CR-02: `cfn-sg-open-ssh`/`cfn-sg-open-rdp` only matched one CidrIp/FromPort ordering

**Files modified:** `backend/iac_scanner_service.py`
**Applied fix:** OR'd both property orderings into the `negative_pattern` regex (`CidrIp...FromPort|FromPort...CidrIp`), matching the shape already used by the pre-existing Terraform siblings (`tf-sg-open-ssh`/`tf-sg-open-rdp`). The original pattern only matched `CidrIp` appearing textually before `FromPort`/`ToPort`, missing the more common `FromPort`/`ToPort`-first property order used in AWS's own example templates — silently passing wide-open security groups in that layout.
**Verification:** Manually constructed a `SecurityGroupIngress` block with `FromPort`/`ToPort` listed before `CidrIp: 0.0.0.0/0`; confirmed `scan_code()` now returns `FAIL` for `cfn-sg-open-ssh` (previously would have returned `PASS`).

## Warnings

### WR-01: `POST /api/cloud-checks/run` and the MCP `run_cloud_check` tool didn't translate `run_checks()` errors into HTTP error codes

**Files modified:** `backend/cloud_checks_endpoints.py`, `backend/mcp_server_endpoints.py`
**Applied fix:** Both call sites now inspect `result.get("error")` after calling `run_checks()` and raise `HTTPException` (404 for "Cloud account not found", 400 otherwise), matching the existing pattern in `cloud_account_endpoints.py`'s `scan_account`, instead of returning the error dict verbatim with a 200 status.

### WR-02: `cfn-eks-public-endpoint` didn't flag the omitted-property case its own description calls out as unsafe

**Files modified:** `backend/iac_scanner_service.py`
**Applied fix:** Inverted to mitigation-style (search for `EndpointPublicAccess: false` as the safe marker, dropped `vulnerable_marker`), matching the pattern already used by `cfn-kms-rotation-disabled`/`cfn-rds-deletion-protection-disabled` for the identical "unsafe default when omitted" scenario. An omitted property (no match) now correctly yields `FAIL`.
**Verification:** Manually confirmed a template omitting `EndpointPublicAccess` entirely now returns `FAIL`, and one with `EndpointPublicAccess: false` returns `PASS`.

### WR-03: Fixed `scope_lines` windows risked false-positive FAILs on larger S3 bucket resources

**Files modified:** `backend/iac_scanner_service.py`
**Applied fix:** Widened `scope_lines` from 15 to 30 for `cfn-s3-public-access`, `cfn-s3-logging-disabled`, and `cfn-s3-versioning-disabled`, reducing the chance that a legitimately-present mitigation (`LoggingConfiguration`, `VersioningConfiguration`, `PublicAccessBlockConfiguration`) falls outside the search window on a bucket resource with several properties before it.

### WR-04: `register_account` didn't validate `account_id` type

**Files modified:** `backend/cloud_account_endpoints.py`
**Applied fix:** Added `isinstance(payload.get("account_id"), str)` check, raising `HTTPException(400)` for non-string values, matching the equivalent guard already present in `mcp_server_endpoints.py`'s `run_cloud_check` handler.

### WR-05: `IacContainerDashboard.tsx` fetch callbacks closed over a stale auth token

**Files modified:** `components/IacContainerDashboard.tsx`
**Applied fix:** Extracted a module-level `authHeaders()` helper that reads `sessionStorage` fresh on each call, and replaced all render-scoped `headers` references (in `fetchIacHistory`, `fetchContainerHistory`, `fetchIacConfig`, `runIacScan`, `runContainerScan`) with calls to `authHeaders()`, instead of closing over a `headers` value computed once during the render that created each `useCallback`.

### WR-06: Single shared `loading` state coupled the IaC and Container tabs

**Files modified:** `components/IacContainerDashboard.tsx`
**Applied fix:** Split the single `loading` state into `iacLoading` and `containerLoading`, each set only by its own tab's scan function and read only by its own tab's button/spinner — starting a scan on one tab no longer disables the button or shows a spinner on the other tab.

## Skipped Issues

### IN-01: `credentialsHint`/`credentials_hint` accepted end-to-end but never used

Deferred — either wiring it into check-evaluation logic or removing the field is a small scope decision better made alongside real per-check credential handling, not a blind removal in a review-fix pass.

### IN-02: Duplicated CFN `Type` prefix pattern fragment repeated 18 times

Deferred — a pure maintainability refactor (factor into a shared constant) with no functional impact; left for a future cleanup pass rather than bundled into a correctness-focused fix commit.

## Notes for follow-up (not fixed, out of scope for this pass)

- None of the 5 new tests added in 25-01/25-02/25-03 asserted on the specific `status` values for the individual new CloudFormation checks — that's how CR-01 and CR-02 shipped untested. A follow-up could add per-check status assertions for all 18 new `cfn-*` rules, not just the ones this review happened to catch.

---

_Fixed: 2026-07-06T13:00:00Z_
_Fixer: Claude Sonnet 5_
_Iteration: 1_
