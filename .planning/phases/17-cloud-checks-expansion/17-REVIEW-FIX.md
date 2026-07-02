---
phase: 17-cloud-checks-expansion
fixed_at: 2026-07-02T13:14:27+05:30
review_path: .planning/phases/17-cloud-checks-expansion/17-REVIEW.md
iteration: 2
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-07-02T13:14:27+05:30
**Source review:** .planning/phases/17-cloud-checks-expansion/17-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 1 (0 Critical + 1 Warning + 0 Info; `fix_scope: all`)
- Fixed: 1
- Skipped: 0

## Fixed Issues

### WR-06: `run_checks` keyword-matching branch ignores severity filtering and produces demonstrable false-FAIL results from generic word overlap

**Files modified:** `backend/cloud_checks_service.py`
**Commit:** `0848f21`
**Applied fix:** Scoped the fuzzy title-matching branch to the same severity-filtered set used by the exact-`checkId` branch. Replaced the separate `finding_titles` (built from *all* `findings_raw`, no severity filter) and `failing_ids` (already correctly filtered to `critical`/`high`/`medium`) with a single `significant_findings` list, then derived both `failing_titles` and `failing_ids` from it. `in_findings` now reads `kw in title for title in failing_titles for kw in name_lower.split()[:3] if len(kw) > 3` — a low/informational-severity finding can no longer flip an unrelated check to `FAIL` on its own.

Verified two ways:
1. Reproduced the review's exact empirical case (two synthetic `low`/`informational` findings with titles "Unused security group detected" / "Logging not enabled for resource X") against the live 147-entry `AWS_CHECKS` catalog — pre-fix this flagged 20 unrelated checks (`aws-iam-003`, `aws-ec2-007`, `aws-cloudtrail-001`, etc. via "enabled"/"logging"/"unused"); post-fix it flags **0**.
2. Confirmed a genuine `high`-severity finding (title "MFA not enabled for IAM users", matching `checkId` `aws-iam-003`) still correctly flags `aws-iam-003` (via exact-ID match) plus the expected keyword-overlap checks (`aws-cloudtrail-001`, `aws-guardduty-001`, etc.), so the fix does not regress true-positive detection — it only removes the severity blind spot.

Also re-verified all eight iteration-1 fixes (CR-01 cross-checks, WR-01 plan wording, WR-02 elasticache casing, WR-04 coverage denominator, WR-05 `aws-ev-001` framework, IN-01 dead code, IN-02 comment accuracy) against current file contents: `CLOUD_CHECKS` = 323 entries, zero duplicate IDs, zero empty `frameworks` lists, `elasticache` lowercase everywhere, `_CHECKS_BY_ID` absent — all still correctly in place with no regressions from this fix.

## Skipped Issues

None.

---

_Fixed: 2026-07-02T13:14:27+05:30_
_Fixer: Claude_
_Iteration: 2_
