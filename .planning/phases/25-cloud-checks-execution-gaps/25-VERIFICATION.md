---
phase: 25-cloud-checks-execution-gaps
verified: 2026-07-06T13:24:25Z
status: passed
score: 15/15 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:

  - test: "Open the IaC & Container dashboard (Security → SecOps → iacContainer), run a container scan in an environment without Trivy, and confirm the SIMULATED badge shows on the summary panel, the vulnerabilities table header, and the scan-history row."
    expected: "A yellow/AlertTriangle 'SIMULATED' badge/chip/tag is visibly present at all three sites for a simulated scan result, and absent for real-Trivy results or history rows with no simulated flag."
    why_human: "Visual prominence/placement of the badge across 3 render sites requires a human to view the actually-rendered dashboard; code inspection confirms the conditional JSX exists at all three sites (verified below) but not that it reads as 'unmissable' at runtime. This item was explicitly deferred to end-of-phase by 25-03-PLAN.md Task 2's <human-check> block and flagged human_judgment: true in 25-03-SUMMARY.md."
---

# Phase 25: Cloud Checks Execution Gaps Verification Report

**Phase Goal:** Close the gap between what `backend/cloud_checks_service.py` catalogs and what it actually runs. Kubernetes and DigitalOcean checks are defined but never evaluated by `run_checks()`; CloudFormation IaC scanning returns an explicit "not yet implemented" stub instead of real rules; container image scanning silently fakes CVE results when Trivy isn't installed instead of saying so.
**Verified:** 2026-07-06T13:24:25Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `run_checks()` evaluates kubernetes and digitalocean provider checks, returns `ran > 0` for a registered account of those providers (CHK-01) | ✓ VERIFIED | `backend/cloud_checks_service.py:63-110` — no provider-specific early-return other than the `RUNNABLE_PROVIDERS` gate; `provider_checks = [c for c in CLOUD_CHECKS if c["provider"] == provider]` dispatches k8s (20) / DO (10). Independently confirmed via `test_run_checks_evaluates_kubernetes`/`test_run_checks_evaluates_digitalocean` (pass) and direct import check: `k8s checks: 20 do checks: 10`. |
| 2 | A cloud account with provider=kubernetes or provider=digitalocean can be registered via `POST /api/cloud-accounts` and returns 200 (CHK-01, Gate 1) | ✓ VERIFIED | `backend/cloud_account_endpoints.py:13` `_VALID_PROVIDERS = {"aws","azure","gcp","kubernetes","digitalocean"}`. `test_register_kubernetes_account`/`test_register_digitalocean_account` pass. |
| 3 | `POST /api/cloud-checks/run` and the MCP `run_cloud_check` tool accept kubernetes/digitalocean without a 400 (CHK-01, Gates 2/3) | ✓ VERIFIED | `backend/cloud_checks_endpoints.py:73` and `backend/mcp_server_endpoints.py:78` both gate on the identical 5-provider tuple `("aws","azure","gcp","kubernetes","digitalocean")`. |
| 4 | Coverage denominator (`_RUNNABLE_CHECKS_COUNT`) includes k8s + DO checks so coverage neither exceeds 100% nor is unreachable at 100% | ✓ VERIFIED | `backend/cloud_checks_service.py:36` — `_RUNNABLE_CHECKS_COUNT = len([c for c in CLOUD_CHECKS if c["provider"] in RUNNABLE_PROVIDERS])`. Direct check: `_RUNNABLE_CHECKS_COUNT == 323 == len(CLOUD_CHECKS)` → True. `test_coverage_denominator_includes_new_providers` passes. |
| 5 | Tenant isolation on `run_checks()`/`scan_account()` unchanged — `test_tenant_isolation`/`test_scan_sets_status` still pass (T-25-01) | ✓ VERIFIED | Both tests pass in full suite run; `run_checks()` query still scoped by `{"id": account_id, "tenantId": tenant_id}` (unchanged). |
| 6 | A vulnerable YAML CloudFormation template returns FAIL findings from cfn-* rules via `scan_code()` (CHK-02) | ✓ VERIFIED | `test_iac_scan_cfn_s3_public_acl`/`test_iac_scan_cfn_sg_open_ssh`/`test_iac_scan_cfn_rds_not_encrypted` pass. Independently re-verified `cfn-ec2-admin-userdata` and `cfn-sg-open-ssh` (both orderings) and `cfn-eks-public-endpoint` — see Behavioral Spot-Checks. |
| 7 | A vulnerable JSON CloudFormation template returns FAIL findings from cfn-* rules via `scan_code()` (CHK-02) | ✓ VERIFIED | `_detect_provider()` JSON branch uses `_CFN_TYPE_RE`; `test_detect_provider_json_cloudformation` passes; JSON→cloudformation dispatch shares the same rule-evaluation path as YAML (same `scan_code()` function, provider-filtered). |
| 8 | `_detect_provider()` classifies a YAML-format CloudFormation template as `cloudformation`, not `unknown` | ✓ VERIFIED | `backend/iac_scanner_service.py:111-127` — yaml/yml branch now checks `_CFN_TYPE_RE` after the k8s `kind:` check. `test_detect_provider_yaml_cloudformation` passes; independently confirmed via direct import. |
| 9 | `scan_code()` no longer returns the "not yet implemented" stub for CloudFormation — CFN flows through the shared `IAC_CHECKS` dispatch | ✓ VERIFIED | Grep for "not yet implemented" in `iac_scanner_service.py` returns nothing; `scan_code()` (lines 64-105) has no CFN-specific early return — only the `unknown`-provider branch short-circuits. |
| 10 | `IAC_CHECKS` contains >= 18 rules with `provider=cloudformation` (parity with Terraform's 17) | ✓ VERIFIED | `grep -c '"provider": "cloudformation"' iac_scanner_service.py` → 18. Terraform count → 17 (unchanged), Kubernetes → 9 (unchanged). |
| 11 | A ~400KB adversarial CFN template scans within bounded wall-clock time (no ReDoS, T-25-02) | ✓ VERIFIED | `test_iac_scan_cfn_redos_bounded` passes (elapsed < 5.0s); `scope_lines` preserved/widened (15→30 on 3 S3 checks per WR-03 fix) on every greedy/multi-line CFN rule. |
| 12 | `_simulated_results()` output includes `simulated: true` (CHK-03) | ✓ VERIFIED | `backend/container_scanner_service.py:88` `"simulated": True` present. Direct check: `simulated: True, trivy: False, total: 6` when Trivy mocked absent. |
| 13 | `_parse_trivy_output()` (real-Trivy path) output includes `simulated: false` | ✓ VERIFIED | `backend/container_scanner_service.py:69` `"simulated": False` present, consistent contract shape. |
| 14 | Existing `test_container_scan_image`/`test_container_vuln_severity_counts` still pass unmodified (no fail-closed regression, Pitfall 4) | ✓ VERIFIED | Both pass in full suite run; `scan_image()` control flow unchanged — purely additive field. |
| 15 | The dashboard renders a prominent SIMULATED badge on the Vulnerability Summary panel, Vulnerabilities table, and each simulated Scan-History row (CHK-03) | ⚠️ code confirmed / human_needed | `components/IacContainerDashboard.tsx` lines 367-371 (summary panel), 397-401 (table header chip), 446 (history row "sim" tag) — all three conditionally render only when `simulated`/`h.simulated` is truthy; `npm run build` succeeds with no type errors. Visual/runtime prominence check deferred to human verification (see below) per the plan's own `<human-check>` item. |

**Score:** 15/15 truths present and code-verified; 1 of those (#15) additionally requires a human runtime check for visual prominence, which does not block the score but does block `passed` status per the decision tree.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/tests/test_cloud_checks_expansion.py` | 3 new tests (k8s/DO run_checks, coverage denominator) | ✓ VERIFIED | 57 lines, no longer a 0-line stub; all 3 tests pass |
| `backend/tests/test_cloud_accounts.py` | 2 new registration tests | ✓ VERIFIED | `test_register_kubernetes_account`, `test_register_digitalocean_account` present and passing; pre-existing tests (incl. `test_tenant_isolation`, `test_scan_sets_status`) unmodified and passing |
| `RUNNABLE_PROVIDERS`/`_VALID_PROVIDERS` widened | 5-provider set in both | ✓ VERIFIED | Confirmed identical 5-tuple/set across `cloud_checks_service.py`, `cloud_account_endpoints.py`, plus inline tuples in `cloud_checks_endpoints.py`/`mcp_server_endpoints.py` |
| 18 CloudFormation rule dicts in `IAC_CHECKS` | cfn-s3-public-access … cfn-rds-deletion-protection-disabled | ✓ VERIFIED | All 18 IDs present, verbatim naming matches plan; grep count = 18 |
| `_CFN_TYPE_RE` module constant | compiled regex | ✓ VERIFIED | `iac_scanner_service.py:108` |
| `test_iac_scan_cfn_*`, `test_detect_provider_*`, `test_iac_scan_cfn_redos_bounded` | 6 new tests | ✓ VERIFIED | All 6 present in `test_iac_scanner.py` (182 lines) and passing |
| `simulated` field on both container-result dicts | bool, true/false | ✓ VERIFIED | Present in both `_simulated_results()` and `_parse_trivy_output()` |
| `simulated?: boolean` on `ContainerScanResponse` (TS interface) | optional bool | ✓ VERIFIED | `components/IacContainerDashboard.tsx:37` |
| `test_container_simulated_flag` | new test | ✓ VERIFIED | Present in `test_iac_scanner.py`, passing |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `RUNNABLE_PROVIDERS` (cloud_checks_service.py) | `_VALID_PROVIDERS` (cloud_account_endpoints.py) | identical 5-provider set | ✓ WIRED | Both literally list `("aws","azure","gcp","kubernetes","digitalocean")` |
| ↔ | provider check (cloud_checks_endpoints.py) | identical tuple | ✓ WIRED | Line 73 matches |
| ↔ | provider check (mcp_server_endpoints.py) | identical tuple | ✓ WIRED | Line 78 matches |
| `_detect_provider()` returns `cloudformation` | `scan_code()` dispatch `[c for c in IAC_CHECKS if c['provider']==provider]` | shared provider-filtered list comprehension | ✓ WIRED | No CFN-specific branch remains; same dispatch as Terraform/K8s |
| backend `simulated` flag (container_scanner_service.py) | `ContainerScanResponse.simulated` (IacContainerDashboard.tsx) | JSON response → TS interface → 3 render sites | ✓ WIRED | Field flows through API response into `containerResult.simulated`/`h.simulated`; 3 conditional badge renders confirmed by direct code read |

### Behavioral Spot-Checks (independent, not from SUMMARY.md)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CR-01 fix: `cfn-ec2-admin-userdata` vulnerable case → FAIL, safe case → PASS | Manual `scan_code()` call with UserData containing `useradd admin` vs. benign UserData | vulnerable→FAIL, safe→PASS | ✓ PASS |
| CR-02 fix: `cfn-sg-open-ssh` matches both CidrIp-first AND FromPort-first property orderings | Manual `scan_code()` call with both YAML orderings of `SecurityGroupIngress` | both orderings → FAIL | ✓ PASS |
| WR-02 fix: `cfn-eks-public-endpoint` flags the omitted-property case | Manual `scan_code()` call with `EndpointPublicAccess` omitted vs. explicitly `false` | omitted→FAIL, explicit-false→PASS | ✓ PASS |
| CHK-03: `_simulated_results()` returns `simulated: true` with non-empty data when Trivy mocked absent | `container_scanner_service.scan_image()` with `_find_trivy` patched to `None` | `simulated: True, trivy: False, total: 6` | ✓ PASS |
| CHK-01: `_RUNNABLE_CHECKS_COUNT` recomputes to include all 5 providers | Direct import + count check | `323 == len(CLOUD_CHECKS)`, k8s=20, DO=10 | ✓ PASS |
| Full targeted test suite (35 tests: cloud_checks_expansion + cloud_accounts + iac_scanner) | `pytest tests/test_cloud_checks_expansion.py tests/test_cloud_accounts.py tests/test_iac_scanner.py -v` | 35 passed | ✓ PASS |
| Full backend test suite (regression check) | `pytest tests/ -q` | 777 passed, 22 skipped, 0 failed | ✓ PASS (no regressions; the 13 "pre-existing unrelated failures" baseline noted in 25-02-SUMMARY.md as rate-limiter test-isolation flakiness in `test_auth_mfa.py` did not reproduce in this run — full suite is clean) |
| Frontend build (tsc type-check of widened interface + badge JSX) | `npm run build` | Build succeeded, `IacContainerDashboard` chunk emitted | ✓ PASS |

### Anti-Patterns Found

None. Grepped all 7 phase-modified files (`cloud_checks_service.py`, `cloud_checks_endpoints.py`, `cloud_account_endpoints.py`, `mcp_server_endpoints.py`, `iac_scanner_service.py`, `container_scanner_service.py`, `IacContainerDashboard.tsx`) for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER|not yet implemented|coming soon` — zero matches.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|--------------|------------|-------------|--------|----------|
| CHK-01 | 25-01-PLAN.md | K8s + DigitalOcean checks actually evaluated | ✓ SATISFIED | All 4 gates widened in lockstep; `run_checks()` evaluates 20 k8s + 10 DO checks; tenant isolation unchanged |
| CHK-02 | 25-02-PLAN.md | Real CloudFormation rule engine at parity with Terraform/K8s | ✓ SATISFIED | 18 cfn-* rules (parity with 17 TF rules), `_detect_provider()` fixed for YAML+JSON, stub removed, ReDoS-bounded, CR-01/CR-02 logic-inversion bugs fixed and independently re-verified |
| CHK-03 | 25-03-PLAN.md | Container scan fails closed / labels simulated results | ✓ SATISFIED | `simulated` flag on both result paths, 3 UI badge sites present; visual prominence pending human confirmation |

REQUIREMENTS.md lines 158-160 mark all three `[x]` complete but the traceability table (line ~296-298) still shows them as "Planned" rather than "Complete" — a documentation-consistency lag, not a functional gap. Noting as an info-level observation, not a blocking finding.

No orphaned requirements: REQUIREMENTS.md's Phase 25 section lists exactly CHK-01/02/03, matching all three plans' `requirements:` frontmatter.

### Code Review Fix Re-Verification (adversarial re-check, not trusting 25-REVIEW-FIX.md narrative)

Both CRITICAL findings from `25-REVIEW.md`, claimed fixed in commit `112cef9` (after the SUMMARY.md files were written), were independently re-verified against the current code state — not merely re-read from the review-fix report:

- **CR-01** (`cfn-ec2-admin-userdata` PASS/FAIL inversion): `iac_scanner_service.py:55` now carries `"vulnerable_marker": True`. Confirmed behaviorally: a UserData block containing `useradd admin` → `FAIL`; benign UserData → `PASS`.
- **CR-02** (`cfn-sg-open-ssh`/`cfn-sg-open-rdp` single-ordering regex): `iac_scanner_service.py:43-44` now OR both `CidrIp`-first and `FromPort`-first orderings. Confirmed behaviorally: both property orderings independently return `FAIL` for a wide-open SSH rule.
- **WR-02** (`cfn-eks-public-endpoint` omitted-property false-negative): confirmed inverted to mitigation-style; an omitted `EndpointPublicAccess` property now correctly yields `FAIL`.
- **WR-03** (S3 `scope_lines` false-positive risk): confirmed widened from 15 to 30 for the 3 affected S3 checks.
- **WR-01** (error dicts not translated to HTTP status): confirmed `cloud_checks_endpoints.py` and `mcp_server_endpoints.py` both now check `result.get("error")` and raise the appropriate `HTTPException`.
- **WR-04** (`account_id` type validation): confirmed `isinstance(payload.get("account_id"), str)` check present in `cloud_account_endpoints.py`.
- **WR-05** (stale-closure auth headers): confirmed `authHeaders()` helper reads `sessionStorage` fresh on every call; all fetch sites use it instead of a render-scoped `headers` variable.
- **WR-06** (shared `loading` state): confirmed split into `iacLoading`/`containerLoading`, each independently gating its own tab's spinner/button.

All 8 in-scope findings (CR-01, CR-02, WR-01 through WR-06) are genuinely fixed in the current codebase, not just claimed in the narrative report. IN-01/IN-02 (info-level) remain unaddressed as explicitly and reasonably deferred.

### Human Verification Required

1. **SIMULATED badge visual prominence across 3 dashboard sites**
   **Test:** Open the IaC & Container dashboard (Security → SecOps → iacContainer), run a container scan in an environment without Trivy, and confirm the SIMULATED badge shows on the summary panel, the vulnerabilities table header, and the scan-history row.
   **Expected:** A yellow/AlertTriangle "SIMULATED" badge/chip/tag is visibly and prominently present at all three sites for a simulated scan result; absent for real-Trivy results and pre-existing history rows with no `simulated` flag.
   **Why human:** Conditional JSX rendering at all 3 sites is confirmed present in code (see Required Artifacts / Key Link Verification above) and `npm run build` type-checks cleanly, but whether the badge reads as sufficiently prominent/unmissable at runtime is a visual judgment call, not something grep/static analysis can confirm. This was explicitly deferred to end-of-phase human verification by `25-03-PLAN.md` Task 2's `<human-check>` block and flagged `human_judgment: true` in `25-03-SUMMARY.md`.

### Gaps Summary

No functional gaps. All 15 derived observable truths for CHK-01/CHK-02/CHK-03 are satisfied in the current codebase, independently re-verified beyond what SUMMARY.md/25-REVIEW-FIX.md claim (including a from-scratch behavioral re-test of the two CRITICAL logic-inversion bugs found by code review and supposedly fixed in commit `112cef9`). The only open item is a single end-of-phase visual human-check for the SIMULATED badge's on-screen prominence, which the phase's own plan already scheduled for this stage rather than mid-execution — this routes the phase to `human_needed`, not `gaps_found`.

---

_Verified: 2026-07-06T13:24:25Z_
_Verifier: Claude (gsd-verifier)_
