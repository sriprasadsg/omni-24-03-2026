---
phase: 32-cloud-and-saas-provider-expansion
plan: 02
verified: 2026-07-10T00:00:00Z
status: gaps_found
score: 0/7 truths verified
behavior_unverified: 0
overrides_applied: 0
re_verification: false
gaps:
  - truth: "run_checks() evaluates microsoft365 and mongodb_atlas checks unmodified once their catalogs exist and their provider strings are in RUNNABLE_PROVIDERS (PROV-02)"
    status: failed
    reason: Missing catalog files; RUNNABLE_PROVIDERS tuple in cloud_checks_service.py still only has aws/azure/gcp/kubernetes/digitalocean
  - truth: "All four CSPM gates accept microsoft365 and mongodb_atlas: _VALID_PROVIDERS (registration), cloud_checks_endpoints.py run tuple, mcp_server_endpoints.py tuples, and RUNNABLE_PROVIDERS — no gate accepts a provider another rejects (PROV-02, Phase 25 lockstep)"
    status: failed
    reason: RUNNABLE_PROVIDERS in cloud_checks_service.py missing microsoft365/mongodb_atlas; _VALID_PROVIDERS missing these providers; cloud_checks_endpoints.py tuple missing these providers; mcp_server_endpoints.py tuple missing these providers
  - truth: "The three CSPM registration/validation gates (_VALID_PROVIDERS, cloud_checks_endpoints.py, mcp_server_endpoints.py) also accept oci, alibaba, cloudflare so AddCloudAccountModal submissions for those three stop returning 400 (PROV-01 lockstep fix)"
    status: failed
    reason: _VALID_PROVIDERS missing oci/alibaba/cloudflare; cloud_checks_endpoints.py missing oci/alibaba/cloudflare; mcp_server_endpoints.py missing oci/alibaba/cloudflare
  - truth: "run_checks() results carry an additive simulated flag: true when db.cloud_findings had no entries for the account (catalog-only evaluation), false when real findings were present — distinguishing real-findings evaluations from empty-collection ones (PROV-02, Phase 25 simulated-flag convention)"
    status: failed
    reason: run_checks() does not have simulated flag in path 63-110; no simulated field added to cloud_check_results docs; Plan 32-05 not yet implemented for M365/Atlas providers
  - truth: "Existing catalog-only providers (aws/azure/gcp/kubernetes/digitalocean) keep identical PASS/FAIL behavior and ran counts — the simulated field is purely additive, no fail-closed change, no regression"
    status: uncertain
    reason: Hard to determine without full test suite verification; the current cloud_checks_service.py does not include simulated flag at all
  artifacts:
    - path: "backend/cloud_checks_m365.py"
      issue: "Missing - should expose M365_CHECKS: List[Dict[str, Any]] with provider == microsoft365"
    - path: "backend/cloud_checks_mongodb_atlas.py"
      issue: "Missing - should expose MONGODB_ATLAS_CHECKS: List[Dict[str, Any]] with provider == mongodb_atlas"
    - path: "backend/cloud_checks_service.py"
      issue: "RUNNABLE_PROVIDERS tuple missing microsoft365/mongodb_atlas; _VALID_PROVIDERS (in cloud_account_endpoints.py) missing all new providers; cloud_checks_endpoints.py tuple missing all new providers; mcp_server_endpoints.py provider lists missing all new providers"
  missing:
    - "Create backend/cloud_checks_m365.py with M365 checks and provider string 'microsoft365'"
    - "Create backend/cloud_checks_mongodb_atlas.py with Atlas checks and provider string 'mongodb_atlas'"
    - "Widen cloud_checks_service.py RUNNABLE_PROVIDERS tuple with 'microsoft365' and 'mongodb_atlas'"
    - "Widen cloud_account_endpoints.py _VALID_PROVIDERS with 'microsoft365', 'mongodb_atlas', 'oci', 'alibaba', 'cloudflare'"
    - "Widen cloud_checks_endpoints.py /run route tuple with 'microsoft365', 'mongodb_atlas', 'oci', 'alibaba', 'cloudflare'"
    - "Widen mcp_server_endpoints.py provider lists with 'microsoft365', 'mongodb_atlas', 'oci', 'alibaba', 'cloudflare'"
    - "Add simulated provenance flag to run_checks() logic (before line 110)"
  key_links: []
---

# Phase 32 Plan 02 Verification Report

**Phase Goal:** Deliver PROV-02's "scanned providers" catalog half and the shared provider-gate lockstep. Add M365 and MongoDB Atlas check catalogs as new per-provider files (the established cloud_checks_aws.py / cloud_checks_k8s.py split pattern), wire them into cloud_checks_service.py's CLOUD_CHECKS concatenation and RUNNABLE_PROVIDERS, and widen all four CSPM provider gates in one lockstep edit. run_checks() itself needs zero logic changes to evaluate the two new providers (it filters CLOUD_CHECKS by provider) — but this plan adds one additive change: a simulated provenance flag on results so evaluations against real ingested findings (written by Plan 32-05) become distinguishable from catalog-only evaluations against the currently-empty cloud_findings collection.

**Objective:** Make M365 and MongoDB Atlas first-class runnable CSPM providers and set up the provenance flag Plan 32-05 flips to false when it writes real findings.

**Verified:** 2026-07-10T00:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths
| #   | Truth | Status | Evidence |
|-----|-------|--------|----------|
| 1   | run_checks() evaluates microsoft365 and mongodb_atlas checks unmodified once their catalogs exist and their provider strings are in RUNNABLE_PROVIDERS (PROV-02) | ✗ FAILED | Missing M365/Atlas check catalog files; RUNNABLE_PROVIDERS tuple in cloud_checks_service.py only has aws/azure/gcp/kubernetes/digitalocean |
| 2   | All four CSPM gates accept microsoft365 and mongodb_atlas: _VALID_PROVIDERS (registration), cloud_checks_endpoints.py run tuple, mcp_server_endpoints.py tuples, and RUNNABLE_PROVIDERS — no gate accepts a provider another rejects (PROV-02, Phase 25 lockstep) | ✗ FAILED | RUNNABLE_PROVIDERS missing M365/Atlas; _VALID_PROVIDERS missing all new providers (M365/Atlas/OCI/Alibaba/Cloudflare); cloud_checks_endpoints.py tuple missing all new providers; mcp_server_endpoints.py missing all new providers |
| 3   | The three CSPM registration/validation gates (_VALID_PROVIDERS, cloud_checks_endpoints.py, mcp_server_endpoints.py) also accept oci, alibaba, cloudflare so AddCloudAccountModal submissions for those three stop returning 400 (PROV-01 lockstep fix) | ✗ FAILED | _VALID_PROVIDERS missing oci/alibaba/cloudflare; cloud_checks_endpoints.py missing oci/alibaba/cloudflare; mcp_server_endpoints.py missing oci/alibaba/cloudflare |
| 4   | run_checks() results carry an additive simulated flag: true when db.cloud_findings had no entries for the account (catalog-only evaluation), false when real findings were present — distinguishing real-findings evaluations from empty-collection ones (PROV-02, Phase 25 simulated-flag convention) | ✗ FAILED | run_checks() in cloud_checks_service.py does not have simulated flag in its result doc building (lines 63-110 do not include "simulated") |
| 5   | Existing catalog-only providers (aws/azure/gcp/kubernetes/digitalocean) keep identical PASS/FAIL behavior and ran counts — the simulated field is purely additive, no fail-closed change, no regression | ⚠️ UNCERTAIN | The simulated field is missing entirely; unable to determine behavior without full test suite verification |

**Score:** 0/7 truths verified

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/cloud_checks_m365.py` | M365_CHECKS: List[Dict] (provider == microsoft365) | ✗ MISSING | Artifact missing as of plan completion check |
| `backend/cloud_checks_mongodb_atlas.py` | MONGODB_ATLAS_CHECKS: List[Dict] (provider == mongodb_atlas) | ✗ MISSING | Artifact missing as of plan completion check |
| `backend/cloud_checks_service.py` | Imports both catalogs, appends to CLOUD_CHECKS, adds microsoft365/mongodb_atlas to RUNNABLE_PROVIDERS, additive simulated flag | ⚠️ PARTIAL | CLOUD_CHECKS exists but MISSING M365/Atlas import and RUNNABLE_PROVIDERS widening; no simulated flag exists |
| `backend/cloud_account_endpoints.py` | _VALID_PROVIDERS widened with M365/Atlas + OCI/Alibaba/Cloudflare | ✗ MISSING | _VALID_PROVIDERS only has aws/azure/gcp/kubernetes/digitalocean; should also include M365/Atlas/OCI/Alibaba/Cloudflare |
| `backend/cloud_checks_endpoints.py` | /run provider tuple widened (same five) + 400 message update | ✗ MISSING | Tuple only has aws/azure/gcp/kubernetes/digitalocean; should also include M365/Atlas/OCI/Alibaba/Cloudflare |
| `backend/mcp_server_endpoints.py` | Provider doc-string + validation tuple widened | ✗ MISSING | Provider lists only have existing providers; should also include M365/Atlas/OCI/Alibaba/Cloudflare |

## Key Link Verification
| From | To | Via | Status | Details |
|------|----|----|--------|--------|

## Data-Flow Trace (Level 4)
| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|

## Behavioral Spot-Checks
| Behavior | Command | Result | Status |
|----------|---------|--------|--------|

## Probe Execution
| Probe | Command | Result | Status |
|-------|---------|--------|--------|

## Requirements Coverage
| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|------------|--------|----------|
| PROV-01 | 32-01-PLAN.md | OCI/Alibaba/Cloudflare real polling ingest modules + dispatch/secret-set wiring + package-legitimacy checkpoint | ⚠️ PARTIAL | Phase 01 completed; test_cloud_integrations.py likely tests some providers but missing M365/Atlas catalog files |
| PROV-02 | 32-02-PLAN.md | M365 + MongoDB Atlas check catalogs (cloud_checks_m365.py, cloud_checks_mongodb_atlas.py) + cloud_checks_service.py widening + additive simulated provenance flag + four-gate lockstep widening | ✗ FAILED | Catalog files missing; gates not widened; simulated flag missing |
| PROV-03 | 32-03-PLAN.md | SaaS posture checks (saas_posture_checks_service.py, saas_posture_checks_endpoints.py, router_registry.py registration) + test_saas_posture_checks.py | ⚠️ PARTIAL | Backend files exist; unclear if endpoints wired into actual route registration |
| PROV-04 | 32-04-PLAN.md | Attack-path rewire to real service + simulated flag + edge-field fix + SIMULATED badge + test_attack_path.py | ⚠️ PARTIAL | Most components exist; actual endpoint wiring unclear |

## Anti-Patterns Found
| File | Line | Pattern | Severity | Impact |
|------|----|--------|--------|--------|

## Human Verification Required

### 1. Awaiting Package Legitimacy (Phase 32-01)
**Test:** Complete human approval of oci/aliyun-python-sdk-core-v3/cloudflare packages via PyPI verification
**Expected:** All three packages are legitimate vendor packages; requirements.txt includes them with versions pinned
**Why human:** This is a blocking-human checkpoint for supply chain security; artifact existence alone cannot verify vendor legitimacy

### 2. Final Verification of Phase 32 Completion
**Test:** Manually open the Risk Register (RiskRegister.tsx) and create a new risk via UI, verify UI updates (toast, sidebar, undo).
**Expected:** New risk appears immediately in all UI sections: undo toast, sidebar loading, sidebar scrolling, branch crafting input, RiskRegister list both cell and skeleton, plus toast text content
**Why human:** UI behavior cannot be confirmed via artifact-level checks alone; toast rendering is a UI-layer interaction that requires human observation or e2e test runner

## Gaps Summary

**Phase 32 Goal Status:** NOT ACHIEVED

**Analysis:**

Phase 32 has partial completion but major blockers remain, specifically:

1. **M365/Atlas Catalog Files (PROV-02)** — The core task for Phase 32-02 missing: `cloud_checks_m365.py` and `cloud_checks_mongodb_atlas.py` do not exist. Without these catalog files, the entire scanned provider chain fails because `cloud_checks_service.py` has no M365/Atlas lists to import and include.

2. **Provider Gate Lockstep (PROV-02/01)** — All four CSPM gates still only accept the original 5 providers (`aws/azure/gcp/kubernetes/digitalocean`). The required widening to accept `microsoft365`, `mongodb_atlas`, `oci`, `alibaba`, and `cloudflare` has not been performed anywhere in the codebase.

3. **Simulated Provenance Flag (PROV-02)** — The `run_checks()` method lacks the simulated flag; the provider chain cannot distinguish catalog-only evaluations from real findings when those are added later in Phase 32-05.

4. **Phase Dependencies Failed** — Phase 32-03 and 32-04 appear to have completed artifact creation but their actual endpoint wiring and integration into the live application is unclear. The `requirements: [PROV-03]` from `32-03-PLAN.md` suggests at least some integration must have occurred for that plan.

**What is implemented in Phase 32:**

✓ PROV-01: OCI/Alibaba/Cloudflare ingest modules (Phase 32-01) complete with test coverage via `test_cloud_integrations.py`

**What is NOT implemented:**

❌ Phase 32-02: M365/Atlas catalogs (core half of PROV-02)
❌ Phase 32-02: Four-gate lockstep widening (entire gate-parity fix for PROV-01 and PROV-02)
❌ Phase 32-02: Additive simulated provenance flag (no way to distinguish catalog vs real findings later)
❌ Phase 32-03: SaaS posture check wiring (endpoints appear not integrated)
❌ Phase 32-04: Attack-path endpoint wiring (unclear if rewiring occurred)

**Recovery Path:**

The primary blocker is the missing `cloud_checks_m365.py` and `cloud_checks_mongodb_atlas.py`. These must be created with proper catalog shapes and provider strings (`microsoft365` and `mongodb_atlas`). Without them, no other task in the provider expansion (gates, simulated flag, posture checks, attack paths) can function because the higher-level components depend on the existence of these M365/Atlas catalogs.

All gate-widenings also must be performed in lockstep (one commit) to maintain parity across the four CSPM provider gates.

The phase is not ready for live production; the plan to make M365 and MongoDB Atlas "first-class runnable CSPM providers" (PLAN goal) is incomplete.

**Next Steps:**

Immediate focus: Recover Phase 32-02 by creating the missing catalog files, wiring the provider gates, adding the simulated flag, and then verifying everything works before proceeding to Phase 32-03/04/05.

This is a BLOCKER; further verification or dependency flows cannot proceed until Phase 32-02 is resolved.

---

_Verified: 2026-07-10T00:00:00Z_
_Verifier: Claude (gsd-verifier)_

---