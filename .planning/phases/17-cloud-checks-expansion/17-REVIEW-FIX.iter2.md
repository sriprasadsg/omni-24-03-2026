---
phase: 17-cloud-checks-expansion
fixed_at: 2026-07-01T23:11:37Z
review_path: .planning/phases/17-cloud-checks-expansion/17-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 8
skipped: 1
status: partial
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-07-01T23:11:37Z
**Source review:** .planning/phases/17-cloud-checks-expansion/17-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9
- Fixed: 8
- Skipped: 1

## Fixed Issues

### CR-01: Two pre-existing checks silently dropped during the module split ("cross-001", "cross-002")

**Files modified:** `backend/cloud_checks_aws.py`
**Commit:** `1a3d780`
**Applied fix:** Re-added the two dropped checks (secrets-in-tags/labels and root/admin-login monitoring alert) with `aws-`-prefixed IDs matching the module split's convention: `aws-iam-013` (alongside the other IAM checks) and `aws-cw-008` (alongside the other CloudWatch checks). Content, severity, frameworks, and remediation text preserved exactly from the pre-refactor version. AWS_CHECKS grew from 145 to 147 entries; no duplicate IDs introduced (verified via a full-file ID uniqueness scan).

### WR-01: Check field names diverge from the plan's required schema (`control_ids`/`remediation_steps` vs `frameworks`/`remediation`)

**Files modified:** `.planning/phases/17-cloud-checks-expansion/17-01-PLAN.md`
**Commit:** `3bf25a8`
**Applied fix:** Chose the documentation-alignment option over a coordinated schema rename. A full rename (`frameworks`→`control_ids`, `remediation`→`remediation_steps`) would touch all 323 check dicts across 5 backend files plus `CloudChecksScanner.tsx`'s consumption of `c.frameworks`/`r.remediation` — a large, purely cosmetic change with real regression risk for a naming preference that the review itself confirms causes no runtime break today. Updated the plan's must_have wording (CC-EXP-02) to state the actual, consistent `frameworks`/`remediation` schema and note why the original wording was a naming mismatch rather than a distinct requirement, so future readers don't misread this as an open gap.

### WR-02: Inconsistent service-name casing for new ElastiCache checks

**Files modified:** `backend/cloud_checks_aws.py`
**Commit:** `3bba805`
**Applied fix:** Changed `"service": "elastiCache"` to `"service": "elasticache"` (lowercase, matching every other service slug in the check catalog) across all three ElastiCache checks (`aws-ecache-001/002/003`).

### WR-03: `run_checks` keyword-matching heuristic can never actually match

**Files modified:** `backend/cloud_checks_service.py`
**Commit:** `318b0ef`
**Applied fix:** Changed the fuzzy-match branch from testing whole-title set membership (`kw in finding_titles`) to substring containment against each finding title (`kw in title for title in finding_titles`), and added a minimum keyword length filter (`len(kw) > 3`) to avoid false positives from short stopword-like tokens. **This is a logic-bug fix — flagging for human verification** (see status note below) since it changes PASS/FAIL determination behavior for check evaluation and only syntax-level verification was performed here.

### WR-04: `coverage` metric structurally can never reach 100%

**Files modified:** `backend/cloud_checks_service.py`
**Commit:** `0e8784c`
**Applied fix:** Introduced `RUNNABLE_PROVIDERS = ("aws", "azure", "gcp")` (matching the provider allow-list already enforced in `cloud_checks_endpoints.py`'s `/run` endpoint) and `_RUNNABLE_CHECKS_COUNT`, then changed `get_summary()`'s coverage denominator from `len(CLOUD_CHECKS)` to `_RUNNABLE_CHECKS_COUNT`. K8s and DigitalOcean checks (never evaluable via `run_checks()`) no longer artificially cap the coverage percentage below 100%.

### WR-05: `aws-ev-001` ships with an empty `frameworks` list

**Files modified:** `backend/cloud_checks_aws.py`
**Commit:** `35aac52`
**Applied fix:** Mapped `aws-ev-001` ("EventBridge schema registry enabled") to `["NIST-CM-2"]` (configuration management / discoverability control), matching the fix suggestion. This is now the only previously-unmapped check with framework coverage restored.

### IN-01: Dead code — `_CHECKS_BY_ID` is built but never used

**Files modified:** `backend/cloud_checks_service.py`
**Commit:** `8850d2e`
**Applied fix:** Removed the unused `_CHECKS_BY_ID` module-level dict (confirmed via `grep -rn "_CHECKS_BY_ID" backend/` showing only the definition, no consumers).

### IN-02: Comment overstates total check count

**Files modified:** `backend/cloud_checks_service.py`
**Commit:** `880610a`
**Applied fix:** Updated the stale `# Combined check list: ... = ~330 checks` comment to the exact, current figures: `AWS (147) + Azure (77) + GCP (69) + K8s (20) + DO (10) = 323 checks`. Counts were recomputed after CR-01 added 2 checks back into `cloud_checks_aws.py` (145 → 147), and verified by importing `cloud_checks_aws.py` directly and checking `len(AWS_CHECKS)`.

## Skipped Issues

### IN-03: Phase-17 changes landed inside a commit mislabeled as phase-16

**File:** N/A (git history, not source)
**Reason:** No code fix applies — the review itself states "No code fix needed; process note for the phase pipeline." This is a process/workflow observation about commit scoping and missing SUMMARY.md artifacts, not a source-code defect. Left for the GSD pipeline maintainers to address (ensuring execute-phase commits are scoped to a single phase, flagging phases without a SUMMARY.md before completion).
**Original issue:** `git log` shows the AWS/Azure/GCP check expansion and module split were introduced in commit `e52393a7`, titled `feat(phase-16): implement program control grouping`, alongside unrelated program-control-grouping work.

---

**Note on WR-03:** The keyword-matching fix (commit `318b0ef`) changes runtime PASS/FAIL determination logic in `run_checks()`. Only Tier 1 (re-read) and Tier 2 (Python syntax check) verification were performed — the behavioral correctness of the new substring-matching heuristic against real `cloud_findings` data has not been exercised. Recommend manual verification of check evaluation results (e.g., running `POST /api/cloud-checks/run` against a test account with known findings) before this is considered fully verified.

_Fixed: 2026-07-01T23:11:37Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
