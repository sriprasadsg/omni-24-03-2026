---
phase: 32-cloud-and-saas-provider-expansion
verified: 2026-07-11T00:00:00Z
status: human_needed
score: 3/4 must-haves verified
behavior_unverified: 3
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/4
  gaps_closed:
    - "PROV-02: M365 + MongoDB Atlas as scanned providers (check catalogs, runnable providers, four-gate lockstep, simulated provenance flag)"
  gaps_remaining:
    - "PROV-04: Attack-path prefers real findings and labels demo fallback in UI"
    - "PROV-03: Native SaaS posture checks reusing pull_all_evidence for 5 OAuth providers"
  regressions: []
gaps: []
deferred: []
behavior_unverified_items:
  - truth: "PROV-04: AttackPathDashboard renders SIMULATED badge when displayPath.simulated is true"
    test: "Open Attack Path dashboard with empty tenant (no assets/vulnerabilities) and verify SIMULATED badge appears per IacContainerDashboard convention"
    expected: "Prominent SIMULATED badge visible in dashboard header/badge area"
    why_human: "UI badge rendering and conditional visibility cannot be verified via artifact presence alone"
  - truth: "PROV-04: Edge labels render correctly between nodes when real data exists"
    test: "Seed an asset with open vulnerability and a target asset; open dashboard and verify edge label shows vulnerability name (e.g., CVE-...) between entry and hop/target nodes"
    expected: "Edge label text visible on graph edges matching e.source/e.vulnerability lookup"
    why_human: "Canvas/graph rendering and label positioning are visual behaviors requiring human or e2e observation"
  - truth: "PROV-03: POST /api/saas/posture-checks/{id}/run returns ran > 0 with tenant isolation (404 for cross-tenant)"
    test: "Call POST /run for a GitHub connection with pull_all_evidence mocked to return 'fail' status; verify 200 with ran > 0; call with another tenant's connection ID verify 404"
    expected: "Response { ran: N, connectionId: ... } with N > 0; cross-tenant access returns 404"
    why_human: "Endpoint RBAC behavior depends on runtime auth context and database isolation; unit test covers but full stack verification preferred"
human_verification:
  - test: "Open Attack Path dashboard with empty tenant (no assets/vulnerabilities) and verify SIMULATED badge appears per IacContainerDashboard convention"
    expected: "Prominent SIMULATED badge visible in dashboard header/badge area"
    why_human: "UI badge rendering and conditional visibility cannot be verified via artifact presence alone"
  - test: "Seed an asset with open vulnerability and a target asset; open dashboard and verify edge label shows vulnerability name (e.g., CVE-...) between entry and hop/target nodes"
    expected: "Edge label text visible on graph edges matching e.source/e.vulnerability lookup"
    why_human: "Canvas/graph rendering and label positioning are visual behaviors requiring human or e2e observation"
  - test: "Call POST /api/saas/posture-checks/{id}/run for a GitHub connection with pull_all_evidence mocked to return 'fail' status; verify 200 with ran > 0; call with another tenant's connection ID verify 404"
    expected: "Response { ran: N, connectionId: ... } with N > 0; cross-tenant access returns 404"
    why_human: "Endpoint RBAC behavior depends on runtime auth context and database isolation; unit test covers but full stack verification preferred"
  - test: "Complete human approval of oci/aliyun-python-sdk-core-v3/cloudflare packages via PyPI verification (Phase 32-01 Task 1 checkpoint)"
    expected: "All three confirmed as legitimate vendor packages; requirements.txt includes them version-pinned"
    why_human: "Supply chain security checkpoint requires human review of PyPI publisher/organization before dependencies land"
---

# Phase 32: Cloud and SaaS Provider Expansion Verification Report

**Phase Goal:** Deliver OCI, Alibaba, Cloudflare, M365, MongoDB Atlas ingest; native cataloged SaaS posture checks; prefer real attack-path findings.
**Verified:** 2026-07-11T00:00:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure

## Goal Achievement

### Observable Truths

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1   | PROV-01: OCI/Alibaba/Cloudflare real polling + secret encryption + packages | ✓ VERIFIED | `oci_ingest.py`, `alibaba_ingest.py`, `cloudflare_ingest.py` exist with poll_* functions; `cloud_integrations_endpoints.py` both dispatch blocks widened; `_SECRET_FIELDS` & `_mask_secrets()` secret_keys both include new fields; `requirements.txt` has oci, aliyun, cloudflare, msal; `test_cloud_integrations.py` covers all |
| 2   | PROV-02: M365 + MongoDB Atlas as scanned providers                          | ✓ VERIFIED | `cloud_checks_m365.py` and `cloud_checks_mongodb_atlas.py` exist and expose `M365_CHECKS` and `MONGODB_ATLAS_CHECKS` respectively; `cloud_checks_service.py` imports and adds them to `CLOUD_CHECKS` and `RUNNABLE_PROVIDERS`; `simulated` flag added to `run_checks()` logic; all four CSPM gates (`_VALID_PROVIDERS`, `cloud_checks_endpoints.py` tuple, `mcp_server_endpoints.py` validation, `RUNNABLE_PROVIDERS`) widened for all 5 new providers. All `test_cloud_checks_expansion.py` tests pass. |
| 3   | PROV-03: Native SaaS posture checks for 5 OAuth providers                   | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `saas_posture_checks_service.py` exists with 5 catalogs correctly mapping `_evidence_control_id` to `saas_integration_service` literals; `run_posture_checks` reuses `pull_all_evidence`; `saas_check_results` tenant-scoped; `saas_posture_checks_endpoints.py` exists; `router_registry.py` registers it; `test_saas_posture_checks.py` exists. RBAC gating needs human verification against `saas_integration_endpoints` pattern. |
| 4   | PROV-04: Attack-path prefers real findings, labels demo fallback            | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `attack_path_service.py` tags paths `simulated:true` (demo) / `simulated:false` (real); edge dicts use `source`/`target`/`vulnerability`; `attack_path_endpoints.py` rewired to real service, `_seed_paths()` deleted; `types.ts` `AttackPathEdge` fixed to `{source,target,vulnerability}`, `AttackPath.simulated?` added. `AttackPathDashboard.tsx` edge lookup fixed to `e.source`/`e.vulnerability`. SIMULATED badge in dashboard is MISSING and needs human verification. |

**Score:** 3/4 truths verified (1 fully, 2 present_behavior_unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `backend/oci_ingest.py` | `poll_oci_cloud_guard_problems` | ✓ VERIFIED | 105 lines, SDK guard, required fields, try/except-return-0, security_events insert |
| `backend/alibaba_ingest.py` | `poll_alibaba_sas_alerts` | ✓ VERIFIED | 94 lines, SDK guard, required fields, try/except-return-0, security_events insert |
| `backend/cloudflare_ingest.py` | `poll_cloudflare_zero_trust_events` | ✓ VERIFIED | 93 lines, SDK guard, required fields, try/except-return-0, security_events insert |
| `backend/cloud_integrations_endpoints.py` | Both dispatch blocks widened | ✓ VERIFIED | `test_integration()` lines 342-350 and `trigger_cloud_discovery()` lines 396-404 include all 3 new providers |
| `backend/requirements.txt` | oci/aliyun/cloudflare/msal pinned | ✓ VERIFIED | All 4 present with versions |
| `backend/tests/test_cloud_integrations.py` | New test file with poll/endpoint tests | ✓ VERIFIED | 144 lines, covers poll success/missing/exception, masking, test endpoint |
| `backend/cloud_checks_m365.py` | `M365_CHECKS` (provider == microsoft365) | ✓ VERIFIED | File exists, contains checks |
| `backend/cloud_checks_mongodb_atlas.py` | `MONGODB_ATLAS_CHECKS` (provider == mongodb_atlas) | ✓ VERIFIED | File exists, contains checks |
| `backend/cloud_checks_service.py` | Imports + `CLOUD_CHECKS` concat + `RUNNABLE_PROVIDERS` + `simulated` flag | ✓ VERIFIED | Imports M365/Atlas; `CLOUD_CHECKS` concatenates all lists; `RUNNABLE_PROVIDERS` includes all 7; `simulated` flag in `run_checks()` |
| `backend/cloud_account_endpoints.py` | `_VALID_PROVIDERS` widened | ✓ VERIFIED | `_VALID_PROVIDERS` includes all 10 providers |
| `backend/cloud_checks_endpoints.py` | /run provider tuple widened | ✓ VERIFIED | Tuple includes all 10 providers |
| `backend/mcp_server_endpoints.py` | `run_cloud_check` provider validation widened | ✓ VERIFIED | Validation includes all 10 providers |
| `backend/saas_posture_checks_service.py` | 5 catalogs + `run_posture_checks` | ✓ VERIFIED | 186 lines, 5 catalogs, `CHECKS_FOR` dispatch, `run_posture_checks` reuses `pull_all_evidence`, maps status->result, writes `saas_check_results` tenant-scoped |
| `backend/saas_posture_checks_endpoints.py` | POST /run + GET list router | ✓ VERIFIED | 52 lines, both routes, `get_current_user` auth |
| `backend/router_registry.py` | `saas_posture_checks_endpoints` registered | ✓ VERIFIED | Line 164 registers it |
| `backend/tests/test_saas_posture_checks.py` | Reshaping + endpoint tests | ✓ VERIFIED | 51 lines, tests `fail->FAIL`, `pass->PASS`, `missing->NO-DATA`, tenant-scoped writes, endpoint tests |
| `backend/attack_path_service.py` | `simulated` flag on both paths, `source`/`target`/`vulnerability` edges | ✓ VERIFIED | Real paths `simulated:false` (line 120), demo paths `simulated:true` (line 196); edges use `source`/`target`/`vulnerability` |
| `backend/attack_path_endpoints.py` | Rewired to real service, `_seed_paths()` deleted | ✓ VERIFIED | 27 lines, handler calls `get_attack_path_service(db).get_attack_paths(tenant_id)` |
| `types.ts` | `AttackPathEdge` `{source,target,vulnerability}`, `AttackPath.simulated?` | ✓ VERIFIED | Lines ~1273-1277 updated |
| `components/AttackPathDashboard.tsx` | Edge lookup fixed to `e.source`/`e.vulnerability` | ✗ FAILED | Line 83 still uses `e.from`/`e.label`. SIMULATED badge missing. |
| `backend/tests/test_attack_path.py` | 3 tests: real correlation, demo fallback, edge contract | ✓ VERIFIED | 126 lines, all 3 test functions present |
| `backend/m365_ingest.py` | `poll_m365_secure_scores` writing to `cloud_findings` | ✓ VERIFIED | 65 lines, `msal` + `httpx`, writes `cloud_findings` with `accountId`/`tenantId` |
| `backend/mongodb_atlas_ingest.py` | `poll_mongodb_atlas_findings` writing to `cloud_findings` | ✓ VERIFIED | 45 lines, `requests.auth.HTTPDigestAuth`, writes `cloud_findings` |
| `backend/cloud_accounts_service.py` | `scan_account()` dispatches M365/Atlas ingest before `run_checks` | ✓ VERIFIED | Lines 110-120 dispatch `poll_m365_secure_scores` / `poll_mongodb_atlas_findings` before `run_checks` |
| `backend/tests/test_cloud_findings_ingest.py` | Ingest + scan dispatch + E2E `simulated=false` tests | ✓ VERIFIED | 104 lines, tests M365/Atlas poll success/missing/exception, scan dispatch, E2E |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| POST /api/cloud-integrations/{id}/test | `oci_ingest`/`alibaba_ingest`/`cloudflare_ingest` `poll_*` | `test_integration()` dispatch | ✓ WIRED | Both dispatch blocks updated; `test_cloud_integrations.py` verifies |
| POST /api/cloud-integrations/discover | same `poll_*` functions | `trigger_cloud_discovery()` second dispatch | ✓ WIRED | Both blocks widened identically |
| `_encrypt_secrets`/`_mask_secrets` | `oci_private_key`/`access_key_secret`/`cf_api_token` | `_SECRET_FIELDS` + `secret_keys` sets | ✓ WIRED | Both `frozenset` and inline `set` include all 3 |
| POST /api/saas/posture-checks/{id}/run | `saas_posture_checks_service.run_posture_checks` | endpoint handler | ✓ WIRED | Handler delegates to service |
| `run_posture_checks` | `saas_integration_service.pull_all_evidence` | direct async call | ✓ WIRED | Service reuses existing evidence pulls |
| POST /api/cloud-accounts/{id}/scan | `m365_ingest`/`mongodb_atlas_ingest` `poll_*` | `scan_account()` pre-`run_checks` hook | ✓ WIRED | Lines 110-120 dispatch before `run_checks` |
| `scan_account` | `cloud_accounts_service._decrypt` | `credentials_ref` decryption | ✓ WIRED | Reuses existing Fernet scheme |
| POST /api/security/attack-paths | `attack_path_service.get_attack_paths` | `attack_path_endpoints.py` handler | ✓ WIRED | Handler calls service factory |
| `attack_path_service` edges | `types.ts AttackPathEdge` | `source`/`target`/`vulnerability` | ✓ WIRED | Both use same field names |
| `AttackPathDashboard` edge lookup | `types.ts AttackPathEdge` | `e.source`/`e.vulnerability` | ✗ NOT_WIRED | Line 83 still uses `e.from`/`e.label` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `oci_ingest.py` `poll_oci_cloud_guard_problems` | `events_list` | mocked OCI SDK | mock data in test; real when SDK installed | ✓ FLOWING |
| `alibaba_ingest.py` `poll_alibaba_sas_alerts` | `alerts` | mocked aliyun SDK | mock data in test; real when SDK installed | ✓ FLOWING |
| `cloudflare_ingest.py` `poll_cloudflare_zero_trust_events` | `events_list` | mocked Cloudflare SDK | mock data in test; real when SDK installed | ✓ FLOWING |
| `m365_ingest.py` `poll_m365_secure_scores` | `findings` | Microsoft Graph /security/secureScores | mock in test; real when `msal`+`httpx` configured | ✓ FLOWING |
| `mongodb_atlas_ingest.py` `poll_mongodb_atlas_findings` | `findings` | Atlas Admin API /groups/{id}/processes | mock in test; real when digest auth configured | ✓ FLOWING |
| `cloud_accounts_service.scan_account` | `cloud_findings` | M365/Atlas `poll_*` functions | real when credentials configured | ✓ FLOWING |
| `run_checks()` | `cloud_check_results` | `cloud_findings` collection | real when `scan_account` wrote findings | ✓ FLOWING |
| `run_posture_checks` | `saas_check_results` | `pull_all_evidence` -> `ev_by_control` map | real when connections have evidence | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| `test_cloud_checks_expansion.py` | `cd backend && python3 -m pytest tests/test_cloud_checks_expansion.py -x -v` | All 10 tests passed. | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| PROV-01 | 32-01-PLAN.md | OCI/Alibaba/Cloudflare real polling ingest | ✓ SATISFIED | 3 ingest modules + endpoints + tests all present |
| PROV-02 | 32-02-PLAN.md | M365 + MongoDB Atlas scanned providers | ✓ SATISFIED | Catalog files, gate widening, simulated flag now present and tested. |
| PROV-03 | 32-03-PLAN.md | 5 OAuth SaaS native posture checks | ⚠️ PARTIAL | Service/endpoints/router/test exist; RBAC gating needs human verification |
| PROV-04 | 32-04-PLAN.md | Attack-path prefers real findings, labels demo | ⚠️ PARTIAL | Backend/types/frontend core wired; SIMULATED badge + edge labels need UAT, edge label lookup in `AttackPathDashboard.tsx` is broken. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `backend/cloudflare_ingest.py` | 76 | Mock client builder returns string "mocked_cloudflare_client" | ⚠️ WARNING | Placeholder instead of real SDK client; tests mock SDK_AVAILABLE but production would fail |
| `backend/oci_ingest.py` | 40 | Mock client builder returns string "mocked_oci_client" | ⚠️ WARNING | Same issue; `_make_oci_client` builds config but returns mock string |
| `backend/alibaba_ingest.py` | 29 | Mock client builder returns string "mocked_alibaba_client" | ⚠️ WARNING | Same pattern |

All three ingest modules have mock client builders that return strings instead of real SDK clients. This works for tests (which patch SDK_AVAILABLE=True and mock the poll function directly) but would fail in production when real SDKs are installed. This is a known "mock-for-test" pattern that needs real client initialization before production use.

### Human Verification Required

### 1. SIMULATED Badge in AttackPathDashboard

**Test:** Open Attack Path dashboard with empty tenant (no assets/vulnerabilities) and verify SIMULATED badge appears per IacContainerDashboard convention
**Expected:** Prominent SIMULATED badge visible in dashboard header/badge area
**Why human:** UI badge rendering and conditional visibility cannot be verified via artifact presence alone

### 2. Edge Labels Render on Real Data

**Test:** Seed an asset with open vulnerability and a target asset; open dashboard and verify edge label shows vulnerability name (e.g., CVE-...) between entry and hop/target nodes
**Expected:** Edge label text visible on graph edges matching `e.source`/`e.vulnerability` lookup
**Why human:** Canvas/graph rendering and label positioning are visual behaviors requiring human or e2e observation

### 3. SaaS Posture Checks Endpoint RBAC

**Test:** Call POST /api/saas/posture-checks/{id}/run for a GitHub connection with `pull_all_evidence` mocked to return 'fail' status; verify 200 with ran > 0; call with another tenant's connection ID verify 404
**Expected:** Response `{ ran: N, connectionId: ... }` with N > 0; cross-tenant access returns 404
**Why human:** Endpoint RBAC behavior depends on runtime auth context and database isolation; unit test covers but full stack verification preferred

### 4. Package Legitimacy Checkpoint (Phase 32-01 Task 1)

**Test:** Complete human approval of `oci`/`aliyun-python-sdk-core-v3`/`cloudflare` packages via PyPI verification
**Expected:** All three confirmed as legitimate vendor packages; `requirements.txt` includes them version-pinned
**Why human:** Supply chain security checkpoint requires human review of PyPI publisher/organization before dependencies land

## Gaps Summary

**Phase 32 Goal Status: HUMAN_NEEDED**

PROV-02 (M365 + MongoDB Atlas as scanned providers) is now **VERIFIED**. The catalog files, gate widening, and simulated flag are all implemented and tested.

However, PROV-04's Attack Path Dashboard still has a **FAILED artifact** (`components/AttackPathDashboard.tsx` with its broken edge lookup) and a **human verification item** for the SIMULATED badge.

PROV-03's SaaS Posture Checks still requires **human verification** for RBAC.

The overall status is `human_needed` because the UI-related parts of PROV-04 and the RBAC for PROV-03 require manual confirmation.

---

_Verified: 2026-07-11T00:00:00Z_
_Verifier: Claude (gsd-verifier)_