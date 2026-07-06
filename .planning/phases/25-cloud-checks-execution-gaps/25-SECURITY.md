---
phase: 25
slug: cloud-checks-execution-gaps
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-06
---

# Phase 25 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|----------------|
| client → `POST /api/cloud-accounts` | Untrusted provider string at account registration (Gate 1) | provider enum string |
| client → `POST /api/cloud-checks/run` | Untrusted provider string at direct check run (Gate 2) | provider enum string |
| MCP client → `POST /api/mcp/execute/run_cloud_check` | Untrusted provider string via MCP tool call (Gate 3) | provider enum string |
| service → `run_checks()` / `scan_account()` | tenantId-scoped DB queries against `cloud_accounts` / `cloud_findings` / `cloud_check_results` | tenant-scoped documents |
| client → `POST /api/iac/scan` | Up to 500KB of untrusted user-submitted IaC code (existing 413 cap) into the regex engine | IaC template text |
| `container_scanner_service` → API response → dashboard | Scan-authenticity signal (real vs. simulated) crossing from backend into the compliance-facing UI | boolean `simulated` flag |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-25-01 | Tampering / inconsistent enforcement | 4 provider-allowlist gates + `run_checks()`/`scan_account()` tenant scoping | high | mitigate | All four gates widened in lockstep to the identical 5-provider tuple (independently re-verified this session); zero changes to tenantId filters; `test_tenant_isolation`/`test_scan_sets_status` pass unmodified | closed |
| T-25-01b | Elevation of Privilege | `POST /api/cloud-accounts` / `/scan` RBAC (`has_permission` gates) | low | accept | RBAC gates untouched by this phase; `test_insufficient_permission_rejected` covers regression | closed |
| T-25-02 | Denial of Service (ReDoS / catastrophic backtracking) | CFN rules with greedy/DOTALL `negative_pattern`s over ≤500KB templates | medium | mitigate | Every CFN rule with a `.*`-style pattern carries `scope_lines`; existing 500KB body cap is the outer bound; `test_iac_scan_cfn_redos_bounded` asserts a ~400KB template scans in <5s — passes | closed |
| T-25-02b | Tampering (false-negative from misdetection) | `_detect_provider()` returning `"unknown"` for YAML CFN | medium | mitigate | Detection fixed so YAML CFN classifies correctly; `test_detect_provider_yaml_cloudformation` guards it — passes | closed |
| T-25-03 | Spoofing (of scan authenticity) | container scan result contract + `IacContainerDashboard` render sites | high | mitigate | Explicit machine-readable `simulated` field on both result paths + unmissable SIMULATED badge at all 3 sites (summary panel, vulnerabilities table, scan-history rows). Independently verified this session by actually running the app end-to-end (login → navigate → trigger scan → screenshot) — all 3 sites confirmed visually prominent, not just present in JSX | closed |
| T-25-03b | Denial of Service (fail-closed regression) | `scan_image()` control flow | medium | accept | Explicitly not failing closed — labeling is the chosen fix, matching the `finops_service` simulated-spend precedent; `scan_image()` flow untouched, both pre-existing container tests pass unmodified | closed |
| T-25-SC | Tampering (supply chain) | package installs | low | accept | No new dependencies added anywhere in this phase (stdlib `re`/`json`/`uuid` only); no install task in any of the 3 plans | closed |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-25-01 | T-25-01b | RBAC permission gates for cloud-account registration/scan are out of scope for a provider-allowlist widening phase; existing regression test already covers this path | Claude (gsd-secure-phase, short-circuit per plan-time register) | 2026-07-06 |
| AR-25-02 | T-25-03b | Labeling simulated container-scan data as such is a better user outcome than failing closed on missing Trivy; this was an explicit, documented plan decision (25-03-PLAN.md), not an oversight | Claude (gsd-secure-phase, short-circuit per plan-time register) | 2026-07-06 |
| AR-25-03 | T-25-SC | Zero new dependencies across all 3 plans in this phase | Claude (gsd-secure-phase, short-circuit per plan-time register) | 2026-07-06 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-06 | 7 | 7 | 0 | Claude (gsd-secure-phase, L1 short-circuit — register authored at plan time, ASVS level 1, threats_open: 0) |

Note: the register was authored at plan time in all three PLAN.md `<threat_model>` blocks (`register_authored_at_plan_time: true`), and every mitigation was already independently re-verified during this session's code-review-fix pass and goal-backward verification — including a from-scratch live-browser confirmation of T-25-03 (the phase's only high-severity `mitigate` threat), which is stronger evidence than the L1 grep-depth this short-circuit path normally relies on. Per the short-circuit rule (`threats_open: 0 AND register_authored_at_plan_time: true AND asvs_level == 1`), spawning `gsd-security-auditor` for a repeat L1 grep pass was skipped as redundant.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-06
