---
status: testing
phase: 25-cloud-checks-execution-gaps
source: [25-VERIFICATION.md]
started: 2026-07-06T13:26:07Z
updated: 2026-07-06T13:26:07Z
---

## Current Test

number: 1
name: SIMULATED badge visual prominence across 3 dashboard sites
expected: |
  Open the IaC & Container dashboard (Security → SecOps → iacContainer), run a
  container scan in an environment without Trivy, and confirm the SIMULATED
  badge shows on the summary panel, the vulnerabilities table header, and the
  scan-history row. A yellow/AlertTriangle "SIMULATED" badge/chip/tag should be
  visibly and prominently present at all three sites for a simulated scan
  result, and absent for real-Trivy results and pre-existing history rows with
  no `simulated` flag.
awaiting: user response

## Tests

### 1. SIMULATED badge visual prominence across 3 dashboard sites
expected: |
  Open the IaC & Container dashboard (Security → SecOps → iacContainer), run a
  container scan in an environment without Trivy, and confirm the SIMULATED
  badge shows on the summary panel, the vulnerabilities table header, and the
  scan-history row. A yellow/AlertTriangle "SIMULATED" badge/chip/tag should be
  visibly and prominently present at all three sites for a simulated scan
  result, and absent for real-Trivy results and pre-existing history rows with
  no `simulated` flag.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
