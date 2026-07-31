---
phase: 17-cloud-checks-expansion
reviewed: 2026-07-02T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - backend/cloud_checks_aws.py
  - backend/cloud_checks_azure.py
  - backend/cloud_checks_gcp.py
  - backend/cloud_checks_k8s.py
  - backend/cloud_checks_service.py
findings:
  critical: 1
  warning: 5
  info: 3
  total: 9
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-07-02T00:00:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed `cloud_checks_aws.py`, `cloud_checks_azure.py`, `cloud_checks_gcp.py`, `cloud_checks_k8s.py`, and `cloud_checks_service.py` against `17-01-PLAN.md`'s must_haves. There is no SUMMARY.md for this phase — history confirms the implementation actually landed inside a commit mislabeled `feat(phase-16): implement program control grouping` (`e52393a7`), which is why it wasn't traceable through normal phase artifacts.

The check-count expansion goal was met (67/91 → 321 checks, well past 300, all new-service coverage bullets from the plan are present, no duplicate IDs, all required data fields present, file sizes all comfortably under 500 lines). However, comparing the check dictionaries against the pre-refactor version of `cloud_checks_service.py` (commit `e52393a7^`) surfaces a real regression: **two pre-existing checks (`cross-001`, `cross-002`) were silently dropped** during the AWS/Azure/GCP module split, directly violating the plan's explicit must_have "Existing 67 checks are not modified or removed." There's also a plan-vs-implementation field-naming mismatch (`control_ids`/`remediation_steps` required by the plan vs. `frameworks`/`remediation` actually shipped — though this matches the codebase's pre-existing convention, so it's not a runtime break), an inconsistent service-name casing bug in the new ElastiCache checks, and a couple of quality issues in `cloud_checks_service.py`'s check-evaluation logic and dead code.

## Critical Issues

### CR-01: Two pre-existing checks silently dropped during the module split ("cross-001", "cross-002")

**File:** `backend/cloud_checks_aws.py`, `backend/cloud_checks_azure.py`, `backend/cloud_checks_gcp.py`, `backend/cloud_checks_k8s.py`, `backend/cloud_checks_service.py` (checks missing from all of them)

**Issue:** Before the phase-17 refactor, `cloud_checks_service.py` (at commit `e52393a7^`) contained 89 checks, including two "cross-provider" checks that don't fit the `aws-`/`azure-`/`gcp-`/`k8s-` ID-prefix convention used to split checks into per-provider modules:

```python
{"id": "cross-001", "name": "No secrets in cloud resource tags/labels", "description": "Resource tags and labels must not contain sensitive values", "provider": "aws", "service": "general", "severity": "high", "frameworks": ["NIST-SA-3", "PCI-3.2"], "remediation": "Scan resource tags for secrets and rotate any exposed credentials."},
{"id": "cross-002", "name": "Monitoring alerts for root/admin logins", "description": "Alerts must be triggered on root or privileged account sign-in", "provider": "aws", "service": "cloudwatch", "severity": "high", "frameworks": ["CIS-4.3", "NIST-AC-2", "SOC2-CC7.3"], "remediation": "Create CloudWatch/Monitor alert for root or admin login events."},
```

Both were tagged `"provider": "aws"` internally but used an ID prefix (`cross-`) that doesn't match `aws-`. Whoever performed the module split (likely by grep/filter on ID prefix or by manual copy) missed these two entries — they do not appear anywhere in the 5 files under review today (verified via `grep -rn "cross-001\|cross-002" backend/cloud_checks_*.py` → no matches). Both are `severity: high` checks with real security value (secret leakage in tags, missing root-login alerting) and are gone with no replacement or equivalent added.

This is a direct violation of the plan's must_have: *"Existing 67 checks are not modified or removed."* It is a silent data-loss/coverage regression — any tenant relying on `GET /api/cloud-checks` for these two checks (or any dashboard/report referencing `cross-001`/`cross-002` by ID) will see them vanish without any deprecation notice, and the org's "root login monitored" and "no secrets in tags" controls silently stop being checked.

**Fix:** Re-add the two checks (with corrected `aws-` prefixed IDs to fit the new convention, e.g. `aws-general-001` / `aws-cw-008`, or keep them ID-stable as `cross-001`/`cross-002` in a small `CROSS_CHECKS` list appended in `cloud_checks_service.py` if cross-provider checks are meant to stay provider-agnostic):

```python
# in cloud_checks_aws.py, alongside the other IAM/CloudWatch checks:
{"id": "aws-iam-013", "name": "No secrets in cloud resource tags/labels", "description": "Resource tags and labels must not contain sensitive values", "provider": "aws", "service": "iam", "severity": "high", "frameworks": ["NIST-SA-3", "PCI-3.2"], "remediation": "Scan resource tags for secrets and rotate any exposed credentials."},
{"id": "aws-cw-008", "name": "Monitoring alerts for root/admin logins", "description": "Alerts must be triggered on root or privileged account sign-in", "provider": "aws", "service": "cloudwatch", "severity": "high", "frameworks": ["CIS-4.3", "NIST-AC-2", "SOC2-CC7.3"], "remediation": "Create CloudWatch/Monitor alert for root or admin login events."},
```
Also audit for any other orphaned/non-prefix-conforming IDs that may have been dropped by the same mechanism (none others were found in this diff, but the split process should be re-run with an assertion that `len(old_checks) <= len(new_checks)` and that every old ID has a corresponding new ID).

## Warnings

### WR-01: Check field names diverge from the plan's required schema (`control_ids`/`remediation_steps` vs `frameworks`/`remediation`)

**File:** `backend/cloud_checks_aws.py:4-183`, `backend/cloud_checks_azure.py:4-98`, `backend/cloud_checks_gcp.py:4-87`, `backend/cloud_checks_k8s.py:4-30`
**Issue:** The plan's must_have (CC-EXP-02) states: *"Each new check has: id, name, description, provider, service, severity, **control_ids list, remediation_steps**"*. Every check dict in all four modules instead uses `frameworks` (list) and `remediation` (string), e.g.:
```python
{"id": "aws-iam-001", ..., "frameworks": ["CIS-1.1", "NIST-IA-2", "PCI-8.3", "SOC2-CC6.1"], "remediation": "Enable MFA for the root account via IAM console."}
```
This matches the pre-existing schema used by the original 67/89 checks and by `DO_CHECKS`/`CloudChecksScanner.tsx` (frontend reads `c.frameworks` / `r.remediation`), so nothing breaks at runtime today — but it means the phase's own acceptance criterion for field naming was not honored, and any consumer built against the plan's documented contract (e.g. automated compliance-mapping tooling expecting `control_ids`) will fail to find the expected keys.
**Fix:** Either update the plan/must_have language to reflect the actual (and consistent) `frameworks`/`remediation` naming, or do a coordinated rename (`frameworks` → `control_ids`, `remediation` → `remediation_steps`) across all check dicts, `cloud_checks_service.py` (`run_checks`, `list_checks`), and `CloudChecksScanner.tsx`. Don't rename only the new checks — that would create an inconsistent schema within `CLOUD_CHECKS`.

### WR-02: Inconsistent service-name casing for new ElastiCache checks

**File:** `backend/cloud_checks_aws.py:164-166`
**Issue:** The three new ElastiCache checks use `"service": "elastiCache"` (camelCase) while every other one of the 321 checks uses a lowercase service slug (`ec2`, `s3`, `rds`, `dynamodb`, etc.):
```python
{"id": "aws-ecache-001", ..., "service": "elastiCache", ...},
{"id": "aws-ecache-002", ..., "service": "elastiCache", ...},
{"id": "aws-ecache-003", ..., "service": "elastiCache", ...},
```
`cloud_checks_service.py.list_checks()` does an exact string match: `checks = [c for c in checks if c["service"] == service]`. A caller filtering `?service=elasticache` (the lowercase convention used everywhere else) will get zero results, and this service will render as a differently-cased, orphaned entry in any UI that builds its service filter dropdown from distinct `service` values (e.g. `CloudChecksScanner.tsx`'s `[...new Set(checks.map(c => c.service))]`).
**Fix:**
```python
{"id": "aws-ecache-001", ..., "service": "elasticache", ...},
{"id": "aws-ecache-002", ..., "service": "elasticache", ...},
{"id": "aws-ecache-003", ..., "service": "elasticache", ...},
```

### WR-03: `run_checks` keyword-matching heuristic can never actually match

**File:** `backend/cloud_checks_service.py:68-77`
**Issue:**
```python
finding_titles = {f.get("title", "").lower() for f in findings_raw}
failing_ids = {f.get("checkId", "").lower() for f in findings_raw if f.get("severity") in ("critical", "high", "medium")}
...
name_lower = check["name"].lower()
in_findings = cid.lower() in failing_ids or any(kw in finding_titles for kw in name_lower.split()[:3])
```
`finding_titles` is a set of *whole, lowercased finding titles*. The second branch of the `or` iterates over individual *words* (`kw`) from the first three words of the check name and tests `kw in finding_titles` — i.e., it checks whether a single word (e.g. `"s3"`) is itself an entire finding title, not whether that word appears as a substring within any finding title. This will essentially never be true (a finding title would have to be the literal single word `"s3"`), so in practice every check's `PASS`/`FAIL` result is determined solely by exact `checkId` equality (`cid.lower() in failing_ids`). This silently defeats the apparent intent of doing fuzzy/keyword matching against native-scanner findings whose `checkId` doesn't exactly equal the platform's own `aws-*`/`azure-*`/`gcp-*` IDs, which will bias results heavily toward false `PASS`.
**Fix:** If keyword matching against titles is intended, check substring containment against each title, not set membership of whole titles:
```python
in_findings = cid.lower() in failing_ids or any(
    kw in title for title in finding_titles for kw in name_lower.split()[:3] if len(kw) > 3
)
```
(add a minimum keyword length filter too, otherwise short stopword-like tokens such as "no", "all", "use" will produce too many false positives once the substring check is fixed).

### WR-04: `coverage` metric structurally can never reach 100% — worsened by this phase's new DO_CHECKS

**File:** `backend/cloud_checks_service.py:14-29, 102-133`
**Issue:** `get_summary()` computes `"coverage": round(total / len(CLOUD_CHECKS) * 100)` where `total` is the number of check *results* actually stored for the tenant/account. But `POST /api/cloud-checks/run` (in `cloud_checks_endpoints.py`) only accepts `provider in ("aws", "azure", "gcp")`, so the 20 `K8S_CHECKS` and — newly added in this same file during this phase — the 10 `DO_CHECKS` (lines 15-26) can never be evaluated by `run_checks()` and will never appear in `cloud_check_results`. This caps the maximum achievable `coverage` value at `291/321 ≈ 90.6%` regardless of how thoroughly a tenant scans their AWS/Azure/GCP accounts, which is misleading in any dashboard that surfaces this percentage as "compliance coverage." Adding `DO_CHECKS` inline in this phase made the ceiling worse (was ~93.6% with just K8s excluded) without adding any way to actually run DigitalOcean checks.
**Fix:** Either exclude non-runnable providers from the `coverage` denominator (`len([c for c in CLOUD_CHECKS if c["provider"] in ("aws","azure","gcp")])`), or extend `run_checks`/the endpoint to accept `kubernetes` and `digitalocean` as valid providers so all check families are actually reachable.

### WR-05: `aws-ev-001` ships with an empty `frameworks` list

**File:** `backend/cloud_checks_aws.py:159`
**Issue:**
```python
{"id": "aws-ev-001", "name": "EventBridge schema registry enabled", ..., "frameworks": [], "remediation": "Enable schema discovery on EventBridge event buses."},
```
This is the only check (of 321) with an empty `frameworks` list — every other check maps to at least one compliance control. Any compliance-mapping view or report built off `frameworks` will silently omit this check from coverage-by-framework rollups.
**Fix:** Map it to an applicable control, e.g. `"frameworks": ["NIST-CM-2"]` (configuration management / discoverability), or confirm intentionally unmapped and document why.

## Info

### IN-01: Dead code — `_CHECKS_BY_ID` is built but never used

**File:** `backend/cloud_checks_service.py:31`
**Issue:** `_CHECKS_BY_ID: Dict[str, Dict] = {c["id"]: c for c in CLOUD_CHECKS}` is computed at import time but there is no reference to `_CHECKS_BY_ID` anywhere else in the file or codebase (`grep -rn "_CHECKS_BY_ID" backend/` returns only this definition). It's unused work done on every import.
**Fix:** Remove it, or use it in `run_checks`/`list_checks` to avoid the O(n) provider-filter scans (e.g. `provider_checks = [c for c in CLOUD_CHECKS if c["provider"] == provider]` at line 73 could stay as-is since perf is out of scope, but at minimum delete the unused dict to reduce confusion).

### IN-02: Comment overstates total check count

**File:** `backend/cloud_checks_service.py:28`
**Issue:** `# Combined check list: AWS (~145) + Azure (~80) + GCP (~75) + K8s (~20) + DO (~10) = ~330 checks` — actual counts are AWS 145, Azure 77, GCP 69, K8s 20, DO 10 = **321**, not ~330. Minor, but a stale/approximate comment that will confuse the next person trying to verify the 300+ must_have without re-counting.
**Fix:** Update to the exact figures or regenerate the comment from `len(...)` at doc-build time.

### IN-03: Phase-17 changes landed inside a commit mislabeled as phase-16

**File:** N/A (git history, not source)
**Issue:** `git log` shows the AWS/Azure/GCP check expansion and module split were introduced in commit `e52393a7`, titled `feat(phase-16): implement program control grouping`, alongside unrelated program-control-grouping work. This is why no `17-*-SUMMARY.md` exists and why this review had to reconstruct scope from `git diff` against the pre-existing check list rather than a plan-linked summary. This made the CR-01 regression harder to catch and will make future `git blame`/`git bisect` on cloud-checks changes point to the wrong phase.
**Fix:** No code fix needed; process note for the phase pipeline — ensure execute-phase commits are scoped to a single phase, and that phases without a SUMMARY.md are flagged before being considered complete.

---

_Reviewed: 2026-07-02T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
