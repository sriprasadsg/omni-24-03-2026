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
  critical: 0
  warning: 1
  info: 0
  total: 1
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-07-02T00:00:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Iteration-2 re-review, verifying iteration-1's fix commits (`1a3d780`, `3bf25a8`, `3bba805`, `318b0ef`, `0e8784c`, `35aac52`, `8850d2e`, `880610a`) against current file contents rather than trusting the fix report.

**Verified independently and confirmed correct:**
- **CR-01** (dropped `cross-001`/`cross-002`): Both re-added to `cloud_checks_aws.py` as `aws-iam-013` ("No secrets in cloud resource tags/labels", line 16, in the IAM block) and `aws-cw-008` ("Monitoring alerts for root/admin logins", line 116, in the CloudWatch block), content byte-identical to the pre-refactor version. `AWS_CHECKS` now has 147 entries (verified via `len()`); combined `CLOUD_CHECKS` = 147+77+69+20+10 = 323, matching the code comment exactly. Full-corpus duplicate-ID scan across all 5 files returned zero collisions.
- **WR-01** (plan/schema field-name mismatch): `17-01-PLAN.md`'s must_have for CC-EXP-02 now documents the actual `frameworks`/`remediation` field names and explicitly notes the original `control_ids`/`remediation_steps` wording was a naming mismatch, not a missing feature. Confirmed no check dict anywhere uses the old field names.
- **WR-02** (ElastiCache casing): All three `aws-ecache-*` checks (lines 166-168) now use lowercase `"service": "elasticache"`, consistent with every other service slug in the 323-check catalog. No leftover `elastiCache` references found anywhere in the codebase.
- **WR-04** (coverage denominator): `RUNNABLE_PROVIDERS = ("aws", "azure", "gcp")` matches the exact allow-list enforced in `cloud_checks_endpoints.py:73` (`payload.provider not in ("aws", "azure", "gcp")`), so the coverage denominator and the actual runnable-provider set are kept in sync by construction rather than by convention.
- **WR-05** (`aws-ev-001` empty frameworks): Now maps to `["NIST-CM-2"]`. Full-corpus scan confirms zero checks with `"frameworks": []` remain.
- **IN-01** (dead `_CHECKS_BY_ID`): Removed; confirmed absent via full-file read and grep.
- **IN-02** (stale comment): Comment now reads `AWS (147) + Azure (77) + GCP (69) + K8s (20) + DO (10) = 323 checks`, which matches the actual computed counts exactly.
- **IN-03**: Correctly left as a process note (no code to fix); the underlying `cloud_check_service.py`/`cloud_checks_endpoints.py`/module files reviewed here are otherwise unaffected by that skip.

**WR-03 deep-dive (flagged by the fix report as needing manual/behavioral verification):** The substring-containment logic itself is now syntactically and semantically correct — `kw in title for title in finding_titles for kw in name_lower.split()[:3] if len(kw) > 3` does perform real substring matching against each finding title, unlike the pre-fix version which tested whole-title set membership and could never match. However, empirical testing (see WR-06 below) surfaces a **new, previously-latent correctness defect** that was invisible before the fix landed (because the fuzzy branch never fired in the old, broken code) and is now real and demonstrable: the keyword branch matches against `finding_titles`, a set built from *all* findings regardless of severity, while the exact-ID branch (`failing_ids`) is deliberately scoped to `critical`/`high`/`medium` severity only. This asymmetry means low/informational-severity findings can now flip unrelated checks to `FAIL` purely via generic single-word overlap (e.g., "enabled", "logging", "used"), which I reproduced empirically against real check data below.

## Warnings

### WR-06: `run_checks` keyword-matching branch ignores severity filtering and produces demonstrable false-FAIL results from generic word overlap

**File:** `backend/cloud_checks_service.py:72-83`
**Issue:**
```python
finding_titles = {f.get("title", "").lower() for f in findings_raw}
failing_ids = {f.get("checkId", "").lower() for f in findings_raw if f.get("severity") in ("critical", "high", "medium")}
...
in_findings = cid.lower() in failing_ids or any(
    kw in title for title in finding_titles for kw in name_lower.split()[:3] if len(kw) > 3
)
```
`failing_ids` is deliberately restricted to findings with `severity in ("critical", "high", "medium")` — the evident intent is that only findings of at least medium severity should be able to fail a check. But `finding_titles` (used by the fuzzy/keyword branch) is built from **all** `findings_raw` with no severity filter at all. Combined with the `len(kw) > 3` minimum-length filter (which, since most AWS/Azure/GCP service acronyms are ≤3 characters — `s3`, `ec2`, `iam`, `rds`, `vpc`, `waf`, `sns`, `sqs` — ends up keeping mostly generic English words like "enabled", "logging", "access", "used", "unused", "public"), this branch now produces a high rate of unrelated false `FAIL` results.

I reproduced this empirically against the real `AWS_CHECKS` catalog with only two synthetic low/informational-severity findings (title: "Unused security group detected", "Logging not enabled for resource X") — neither of which should cause *any* check to fail per the severity-gating intent:

```python
findings_raw = [
    {"title": "Unused security group detected", "checkId": "native-sg-999", "severity": "low"},
    {"title": "Logging not enabled for resource X", "checkId": "native-log-001", "severity": "informational"},
]
# failing_ids ends up empty (no critical/high/medium findings) -> 0 checks should fail
# but the fuzzy branch alone marks 20 of 147 AWS checks (~14%) as FAIL, e.g.:
#   aws-iam-003 "MFA enabled for all IAM users"            <- matched via "enabled"
#   aws-ec2-007 "Unused EC2 security groups removed"       <- matched via "unused"
#   aws-cloudtrail-001 "CloudTrail enabled in all regions" <- matched via "enabled"
#   aws-r53-002 "Route53 query logging enabled"            <- matched via "logging"/"enabled"
#   aws-guardduty-001 "GuardDuty enabled in all regions"   <- matched via "enabled"
#   ...15 more, all via "enabled"/"logging"/"unused"
```
This directly affects the correctness of `POST /api/cloud-checks/run`'s PASS/FAIL determination — the core function delivered by this phase — and will produce compliance dashboards/reports that show unrelated checks as failing based on a single low-severity, unrelated finding sharing a common English word. This is the exact class of behavioral-correctness risk the iteration-1 fix report itself flagged as unverified ("the behavioral correctness of the new substring-matching heuristic against real `cloud_findings` data has not been exercised").

**Fix:** Scope the fuzzy-match title set to the same severity filter used for `failing_ids`, so a low/info finding can never flip a check to FAIL on its own:
```python
significant = [f for f in findings_raw if f.get("severity") in ("critical", "high", "medium")]
failing_ids = {f.get("checkId", "").lower() for f in significant}
failing_titles = {f.get("title", "").lower() for f in significant}
...
in_findings = cid.lower() in failing_ids or any(
    kw in title for title in failing_titles for kw in name_lower.split()[:3] if len(kw) > 3
)
```
Separately (and even after the severity fix), consider whether single generic-word substring matching is precise enough at all — a stopword denylist (e.g., excluding "enabled", "used", "unused", "access", "public", "policy", "logging" from the keyword pool) or requiring 2+ matching keywords would meaningfully reduce the false-FAIL rate demonstrated above, since these words are common across many unrelated check names and finding titles.

---

_Reviewed: 2026-07-02T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
