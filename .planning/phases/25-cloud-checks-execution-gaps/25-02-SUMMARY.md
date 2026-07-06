---
phase: 25-cloud-checks-execution-gaps
plan: 02
subsystem: api
tags: [iac-scanner, cloudformation, regex, security, python]

# Dependency graph
requires:
  - phase: 25-cloud-checks-execution-gaps
    provides: "Plan 01 (CHK-01) widened provider allowlist gates — no file overlap with this plan"
provides:
  - "18 CloudFormation (cfn-*) security rules in IAC_CHECKS at parity with Terraform's 17"
  - "Fixed _detect_provider() YAML CloudFormation detection (was silently 'unknown')"
  - "scan_code() CloudFormation dispatch through the same shared provider-filtered path as Terraform/Kubernetes (stub removed)"
affects: [iac-container-security-dashboard, cloud-checks-execution-gaps-phase-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "IaC rule-dict shape (id/name/description/provider/severity/pattern/negative_pattern/vulnerable_marker/scope_lines) extended to a third provider (cloudformation) without any new evaluation function"
    - "scope_lines-bounded negative_pattern matching used as the standing ReDoS mitigation for every greedy/DOTALL CFN rule"

key-files:
  created: []
  modified:
    - backend/iac_scanner_service.py
    - backend/tests/test_iac_scanner.py

key-decisions:
  - "18 CFN rules added verbatim from 25-RESEARCH.md Pattern 2 — no new rule shape, no new cfn-specific scan function"
  - "_CFN_TYPE_RE module-level compiled regex added; _detect_provider() now checks it in the yaml/yml branch, the json/template branch, and as an extension-less fallback before returning 'unknown'"
  - "CloudFormation early-return stub in scan_code() deleted — CFN now flows through the same `[c for c in IAC_CHECKS if c['provider'] == provider]` dispatch as Terraform/Kubernetes"

patterns-established: []

requirements-completed: [CHK-02]

coverage:
  - id: D1
    description: "18 CloudFormation rule dicts (cfn-s3-public-access ... cfn-rds-deletion-protection-disabled) added to IAC_CHECKS at parity with Terraform's 17 rules"
    requirement: CHK-02
    verification:
      - kind: unit
        ref: "backend/tests/test_iac_scanner.py#test_iac_scan_cfn_s3_public_acl"
        status: pass
      - kind: unit
        ref: "backend/tests/test_iac_scanner.py#test_iac_scan_cfn_sg_open_ssh"
        status: pass
      - kind: unit
        ref: "backend/tests/test_iac_scanner.py#test_iac_scan_cfn_rds_not_encrypted"
        status: pass
    human_judgment: false
  - id: D2
    description: "_detect_provider() correctly classifies YAML- and JSON-format CloudFormation templates as 'cloudformation' instead of 'unknown' (pre-existing bug fix)"
    requirement: CHK-02
    verification:
      - kind: unit
        ref: "backend/tests/test_iac_scanner.py#test_detect_provider_yaml_cloudformation"
        status: pass
      - kind: unit
        ref: "backend/tests/test_iac_scanner.py#test_detect_provider_json_cloudformation"
        status: pass
    human_judgment: false
  - id: D3
    description: "CloudFormation 'not yet implemented' stub removed from scan_code(); CFN scans return real findings via the shared provider dispatch, and a ~400KB adversarial CFN template scans within bounded wall-clock time (no ReDoS) thanks to scope_lines-bounded negative_pattern matching"
    requirement: CHK-02
    verification:
      - kind: unit
        ref: "backend/tests/test_iac_scanner.py#test_iac_scan_cfn_redos_bounded"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-07-06
status: complete
---

# Phase 25 Plan 02: CloudFormation IaC Rule Engine Summary

**Added 18 regex-based CloudFormation security rules to IAC_CHECKS and fixed a pre-existing bug where YAML-format CFN templates were silently classified as "unknown" and never scanned**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-07-06T12:45:57Z
- **Completed:** 2026-07-06T12:50:02Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- 18 new `cfn-*` rule dicts appended to `IAC_CHECKS` in `backend/iac_scanner_service.py`, matching the existing Terraform rule-dict shape exactly (id/name/description/provider/severity/pattern/negative_pattern/vulnerable_marker/scope_lines) — rule-count parity with Terraform's 17 rules
- `_detect_provider()` fixed: added module-level `_CFN_TYPE_RE = re.compile(r'"?Type"?\s*:\s*"?AWS::')`, checked in the yaml/yml branch (before falling through), the json/template branch, and as a final extension-less fallback before returning `"unknown"` — YAML-format CFN templates (the dashboard's advertised default authoring style) are now correctly detected
- Deleted the `if provider == "cloudformation": return {...}` early-return stub in `scan_code()` — CloudFormation templates now flow through the same `[c for c in IAC_CHECKS if c["provider"] == provider]` dispatch as Terraform/Kubernetes
- Every CFN rule with a greedy/DOTALL `negative_pattern` (e.g. `cfn-ec2-admin-userdata`, `cfn-sg-open-ssh`, `cfn-sg-open-rdp`) carries a `scope_lines` bound, mirroring the existing `tf-hardcoded-key`/`tf-plaintext-secret` ReDoS mitigation pattern — verified against a ~400KB adversarial template completing in well under 1 second
- 6 new tests authored TDD-style (RED before implementation, GREEN after): 3 CFN rule-firing tests, 2 `_detect_provider` tests (YAML + JSON), 1 ReDoS-bound test
- Module docstring updated: "26 checks (17 Terraform, 9 Kubernetes)" -> "44 checks (17 Terraform, 9 Kubernetes, 18 CloudFormation)"

## Task Commits

Each task was committed atomically:

1. **Task 1: Author Wave 0 CloudFormation + detection + ReDoS tests (RED)** - `1987f5d` (test)
2. **Task 2: Add 18 CFN rules, fix _detect_provider(), remove the stub (GREEN)** - `8be2527` (feat)

**Plan metadata:** pending (docs: complete plan commit follows this summary)

_Note: This plan follows an implicit RED/GREEN task split (Task 1 authors failing tests, Task 2 implements to green) though the plan frontmatter is `type: execute`, not `type: tdd` — both gate commits exist in git log._

## Files Created/Modified
- `backend/iac_scanner_service.py` - Added 18 `cfn-*` rule dicts to `IAC_CHECKS`, added `_CFN_TYPE_RE` module constant, fixed `_detect_provider()` YAML/JSON CFN classification, removed the CFN "not yet implemented" stub branch in `scan_code()`, updated module docstring (129 -> 148 lines, well under the 500-line CLAUDE.md limit)
- `backend/tests/test_iac_scanner.py` - Added 6 new test functions: `test_iac_scan_cfn_s3_public_acl`, `test_iac_scan_cfn_sg_open_ssh`, `test_iac_scan_cfn_rds_not_encrypted`, `test_detect_provider_yaml_cloudformation`, `test_detect_provider_json_cloudformation`, `test_iac_scan_cfn_redos_bounded` (8 -> 14 tests in file; no existing test modified)

## Decisions Made
- Used the 18-rule `CFN_CHECKS` list verbatim from `25-RESEARCH.md` Pattern 2 (AWS-doc-verified property defaults for `PublicAccessBlockConfiguration`, `DeletionProtection`, `EndpointPublicAccess`, `EnableKeyRotation`) rather than drafting new rules from scratch
- Preserved every `scope_lines` value from the research list on rules with greedy/multi-line `negative_pattern`s — this is the load-bearing ReDoS mitigation (threat T-25-02), not an optional detail
- Kept the existing `scan_code()` evaluation loop, `_detect_provider()`'s non-CFN branches, and all Terraform/Kubernetes rule dicts untouched — this was a pure additive/bugfix change per RESEARCH.md's "disciplined imitation" framing, no new abstractions introduced

## Deviations from Plan

None — plan executed exactly as written. One minor observation, not a deviation: `test_detect_provider_json_cloudformation` passed immediately during the RED phase (Task 1) rather than failing, because JSON-format CloudFormation detection was already correct in the pre-existing code (`_detect_provider()`'s bug was specific to the YAML/YML branch, confirmed by direct read in RESEARCH.md Pattern 3). This is expected — the test still asserts the (already-passing) contract stays correct after the YAML fix lands, and the plan's own acceptance criteria only required "existing tests still pass" and "6 new tests collected," which held true.

## Issues Encountered

None specific to this plan's files. During the full-suite regression check, 4-5 pre-existing failures were observed in `backend/tests/test_auth_mfa.py` (`TestLoginEndpoint`/`TestMFAVerifyLogin` tests hitting `429 Too Many Requests` instead of expected status codes). These are confirmed to be a pre-existing rate-limiter test-isolation issue (`slowapi` global rate-limit state shared across tests in that file) unrelated to `iac_scanner_service.py` or `test_iac_scanner.py` — out of scope per the executor's SCOPE BOUNDARY rule (only auto-fix issues directly caused by the current task's changes). Re-running `backend/tests/test_auth_mfa.py` in isolation reproduces the same failures independent of this plan's changes, confirming no regression was introduced.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- CHK-02 fully satisfied: 18 CFN rules, YAML detection fix, stub removal, and ReDoS bound all verified by passing tests
- `backend/tests/test_iac_scanner.py` at 14/14 passing (8 pre-existing + 6 new); full backend suite at 772 passed / 22 skipped / 4 pre-existing unrelated failures (rate-limiter flakiness in `test_auth_mfa.py`, confirmed independent of this plan)
- Plan 25-03 (CHK-03, container scan simulated-data labeling) has no file overlap with this plan (`container_scanner_service.py`, `IacContainerDashboard.tsx`) and can proceed independently

---
*Phase: 25-cloud-checks-execution-gaps*
*Completed: 2026-07-06*

## Self-Check: PASSED

- FOUND: backend/iac_scanner_service.py
- FOUND: backend/tests/test_iac_scanner.py
- FOUND: .planning/phases/25-cloud-checks-execution-gaps/25-02-SUMMARY.md
- FOUND: commit 1987f5d
- FOUND: commit 8be2527
