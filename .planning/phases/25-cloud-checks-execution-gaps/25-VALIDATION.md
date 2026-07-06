---
phase: 25
slug: cloud-checks-execution-gaps
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-06
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`pytest.ini` at repo root: `testpaths = . backend`, `asyncio_mode = auto`) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `cd backend && python -m pytest tests/test_iac_scanner.py tests/test_cloud_checks_expansion.py tests/test_cloud_accounts.py -v` |
| **Full suite command** | `cd backend && python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds (quick), full suite per Phase 24 baseline |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/test_iac_scanner.py tests/test_cloud_checks_expansion.py tests/test_cloud_accounts.py -v`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs are assigned by the planner; requirement-level rows below are the contract the planner must map tasks onto (per `25-RESEARCH.md` § Validation Architecture).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | CHK-01 | — | K8s check evaluated by `run_checks()` for a registered k8s cloud account | unit | `pytest backend/tests/test_cloud_checks_expansion.py::test_run_checks_evaluates_kubernetes -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHK-01 | — | DigitalOcean check evaluated by `run_checks()` for a registered DO cloud account | unit | `pytest backend/tests/test_cloud_checks_expansion.py::test_run_checks_evaluates_digitalocean -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHK-01 | — | `cloud_check_results` coverage percentage recomputes correctly once k8s/DO are runnable | unit | `pytest backend/tests/test_cloud_checks_expansion.py::test_coverage_denominator_includes_new_providers -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHK-01 | T-25-01 | Cloud account registration accepts `provider=kubernetes`/`digitalocean` without loosening tenant isolation on `run_checks()`/`scan_account()` | integration | `pytest backend/tests/test_cloud_accounts.py::test_register_kubernetes_account -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHK-02 | — | CloudFormation S3/IAM/SG/RDS/EKS/KMS rules fire FAIL on vulnerable YAML+JSON templates | unit | `pytest backend/tests/test_iac_scanner.py::test_iac_scan_cfn_* -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHK-02 | — | `_detect_provider` correctly classifies YAML-format CloudFormation as `"cloudformation"`, not `"unknown"` | unit | `pytest backend/tests/test_iac_scanner.py::test_detect_provider_yaml_cloudformation -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHK-02 | T-25-02 | New CFN regex rules use `scope_lines`-bounded matching (no unbounded backtracking) against up to 500KB user-submitted templates | unit | `pytest backend/tests/test_iac_scanner.py -k redos -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHK-03 | — | `_simulated_results()` output includes `simulated: true`; existing `test_container_scan_image`/`test_container_vuln_severity_counts` still pass unmodified | unit | `pytest backend/tests/test_iac_scanner.py -k container -x` | ✅ (2 existing + 1 new) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_cloud_checks_expansion.py` — currently a 0-line empty stub; needs the entire CHK-01 test suite (closes a pre-existing Phase 17 coverage gap)
- [ ] New test functions in `backend/tests/test_iac_scanner.py` for CFN rules, `_detect_provider` YAML classification, and the `simulated` field — reuse existing `_mkdb`/`_mkuser`/`_build` helpers already in that file, no new fixture files needed
- [ ] New test function in `backend/tests/test_cloud_accounts.py` for k8s/DigitalOcean account registration
- [ ] Framework install: none — pytest already configured and passing 8/8 for `test_iac_scanner.py` today

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
