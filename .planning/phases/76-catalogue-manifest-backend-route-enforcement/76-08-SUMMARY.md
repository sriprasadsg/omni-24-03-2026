---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 08
subsystem: api
tags: [rbac, catalogue-manifest, security-posture, cloud, vulnerabilities, dlp, pam, d-01, d-11]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: catalogue_guard / MOUNTS convention / parity helpers (76-01), full manifest (76-02), VULNERABILITY_GUARD (76-05)
provides:
  - backend/catalogue_mounts_secposture.py (14 MOUNTS entries over 14 routers)
  - backend/tests/test_catalogue_slice_secposture.py (parity, manifest drift, DevSecOps exclusion, real-app 403/200, vulnerability probe, write strings)
affects: [76-11, 76-12, 77]

requirements-completed: [ACC-04]

actuals:
  tokens: 9000
  tasks: 2
  commits: 1
plan_head_before: ae77363b07b12487cdc82922db9dc1d559da5389
plan_head_after: cdb145e1c1500e8dd165f80ce3e1c7da892ff31a

tech-stack:
  added: []
  patterns:
    - "Mount-level guard only: every router in the slice is user-authenticated and single-owner, so no route file was edited"
    - "Guard drift test: every MOUNTS entry compared to the manifest's resolved read/write"

key-files:
  created:
    - backend/catalogue_mounts_secposture.py
    - backend/tests/test_catalogue_slice_secposture.py
  modified: []

key-decisions:
  - "vuln_endpoints reuses VULNERABILITY_GUARD from catalogue_mounts_assets (D-11: vulnerabilityManagement -> view:vulnerabilities), so security_cases/security_scans route-level guards and the mount share one object"
  - "DevSecOps-owned routers (iac_security, k8s_security, pipeline_security, supply_chain_security, api_security, dam) stay unguarded for the ledger (D-01); a test asserts none carries a tag"

coverage:
  - id: D1
    description: "parity_offenders over slice_modules('secposture') is empty (14 modules, 68 routes)"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_secposture.py#test_secposture_slice_parity"
        status: pass
    human_judgment: false
  - id: D2
    description: "Each mount entry carries exactly the manifest's resolved read/write and is the guard MOUNT_GUARDS exposes"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_secposture.py#test_secposture_guards_match_manifest"
        status: pass
    human_judgment: false
  - id: D3
    description: "Real app: roles without the permission get 403 on cloud, IaC, container, DLP, PAM, pentest, SCA, DAST, attack path, zero trust and PQC reads; holders are not refused; writes with existing strings pass"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_secposture.py#test_secposture_real_app_enforced"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_secposture.py#test_secposture_writes_use_existing_strings"
        status: pass
    human_judgment: false
  - id: D4
    description: "viewer (holds view:cloud_security, not view:vulnerabilities) gets 403 on /api/vulnerabilities; security_analyst and tenant_admin do not (D-11)"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_secposture.py#test_secposture_vulnerability_read_needs_view_vulnerabilities"
        status: pass
    human_judgment: false
  - id: D5
    description: "DevSecOps routers carry no catalogue guard"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_secposture.py#test_secposture_devsecops_routers_left_unguarded"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-10-15
status: complete
---

# Phase 76 Plan 08: Security-Posture Slice Summary

**Cloud accounts/checks/remediation, IaC and container scanning, DAST, SCA, pentest, DLP, PAM, attack path, zero trust/PQC and vulnerability routes now refuse callers without the manifest permission, via one mount-time guard per router; no route file was touched.**

## Accomplishments
- `catalogue_mounts_secposture.py`: 14 MOUNTS entries (cloud_account, cloud_checks, cloud_remediation, iac_scanner, container_scanner, dast_service, sca, pentest, dlp, pam, attack_path, zero_trust_service, pqc, vuln); `iac_scanner`/`container_scanner` share one iacContainer guard and `zero_trust_service`/`pqc` share one zeroTrustQuantum guard.
- `test_catalogue_slice_secposture.py`: 6 tests. Slice file plus `test_catalogue_route_parity` and `test_route_auth_baseline`: 33 passed. Full backend suite: 3683 passed, 47 skipped, 0 failed (baseline 3677 + 6 new).

## slice_modules("secposture") vs candidates
Actual (14): attack_path_endpoints, cloud_account_endpoints, cloud_checks_endpoints, cloud_remediation_endpoints, container_scanner_endpoints, dast_service, dlp_endpoints, iac_scanner_endpoints, pam_endpoints, pentest_endpoints, pqc_endpoints, sca_endpoints, vuln_endpoints, zero_trust_service. 68 routes, all `auth: user`, each module single-owner.

| Candidate / module | Handling |
|---|---|
| `cloud_remediation_endpoints`, `pqc_endpoints` (not in plan) | in the slice (cloudSecurity, zeroTrustQuantum); mounted |
| `iac_security_endpoints`, `k8s_security_endpoints`, `pipeline_security_endpoints`, `supply_chain_security_endpoints`, `api_security_endpoints`, `dam_endpoints` | manifest gives them to the DevSecOps group (enforce:false); left unguarded for the ledger (D-01) |
| `itdr_endpoints`, `insider_threat_endpoints`, `ot_ics_endpoints`, `security_keys_endpoints` | owned by the secops slice (ueba/insiderThreat/ndr/security); already guarded by 76-07 and not re-guarded |

## Task Commits
Both tasks edit the same two files, so they were implemented and verified together and committed as one change:
1. Tasks 1-2: `cdb145e1c` feat(76-08): guard the security-posture slice with the manifest at mount time

## Deviations from Plan

**1. [Process] Tasks 1 and 2 committed together.** Every module in the slice was a clean single-owner user router, so splitting the mount file by family added no value. Single commit `cdb145e1c`. No code deviation.

**Total deviations:** 1 (process only). **Impact:** none; all acceptance criteria met.

## Manifest corrections for 76-11
Followed as written; candidates for review:
- `cloudAccounts` write list contains `view:cloud_security`, so the catalogue write check passes any reader (viewer role). The routes' own guards still decide; consider whether the manifest write list should drop the read string.
- `iacContainer` write contains `view:dashboard`, `zeroTrustQuantum` write contains `view:security`, `vulnerabilityManagement` write contains `view:security`: same pattern (union of existing weak guards).
- `pam` read and write are both `manage:settings`, so a PAM read needs an admin-level permission; `pam` is the only secposture catalogue with a manage: read.

## Phase 77 UX notes
- Roles holding view:cloud_security but not view:vulnerabilities (e.g. viewer) will see Vulnerabilities in data shared by other views now 403; the sidebar must hide the item by the same string.
- `/api/pam/*` needs `manage:settings` even for reads; the PAM page should hide for roles without it.

## Issues Encountered
None. No services restarted, nothing deployed, live database untouched.

## Self-Check: PASSED
- backend/catalogue_mounts_secposture.py and backend/tests/test_catalogue_slice_secposture.py exist.
- Commit cdb145e1c is an ancestor of HEAD.
- parity_offenders over slice_modules("secposture") is empty; full suite 3683 passed, 0 failed.
