---
phase: 32-cloud-and-saas-provider-expansion
plan: 02
verified: 2026-09-28T00:00:00Z
status: passed
score: 5/5 truths verified
behavior_unverified: 0
overrides_applied: 0
re_verification: true
previous_status: gaps_found
previous_score: 0/7 truths
gaps_closed:
  - "M365 + MongoDB Atlas check catalogs created (backend/cloud_checks_m365.py, backend/cloud_checks_mongodb_atlas.py) — 6 checks each, real content (MFA/conditional-access/mailbox-audit/external-sharing for M365; IP-allowlist/encryption-at-rest/auditing/network-isolation for Atlas)"
  - "RUNNABLE_PROVIDERS (cloud_checks_service.py:40) widened to include microsoft365, mongodb_atlas, oci, alibaba, cloudflare"
  - "_VALID_PROVIDERS (cloud_account_endpoints.py:13) widened to the same 10 providers"
  - "cloud_checks_endpoints.py /run route tuple (line 73) widened to the same 10 providers"
  - "Fourth gate (formerly mcp_server_endpoints.py's own tuple) now lives in mcp_server.py:62-64, which imports RUNNABLE_PROVIDERS directly from cloud_checks_service as its single source of truth — stronger than the originally planned duplicated tuple, since it cannot drift out of lockstep"
  - "simulated provenance flag added at cloud_checks_service.py:108 (\"simulated\": not has_real_findings)"
gaps_remaining: []
regressions: []
key_links:
  - from: "cloud_checks_service.py:13-14"
    to: "cloud_checks_m365.py / cloud_checks_mongodb_atlas.py"
    via: "from cloud_checks_m365 import M365_CHECKS / from cloud_checks_mongodb_atlas import MONGODB_ATLAS_CHECKS"
    status: WIRED
  - from: "cloud_checks_service.py:34"
    to: "CLOUD_CHECKS"
    via: "AWS_CHECKS + ... + M365_CHECKS + MONGODB_ATLAS_CHECKS + OCI_CHECKS + ALIBABA_CHECKS + CLOUDFLARE_CHECKS"
    status: WIRED
  - from: "mcp_server.py:62"
    to: "cloud_checks_service.RUNNABLE_PROVIDERS"
    via: "from cloud_checks_service import RUNNABLE_PROVIDERS (runtime import, single source of truth)"
    status: WIRED
---

# Phase 32 Plan 02 Verification Report

**Phase Goal:** Deliver PROV-02's "scanned providers" catalog half and the shared provider-gate lockstep. Add M365 and MongoDB Atlas check catalogs as new per-provider files (the established cloud_checks_aws.py / cloud_checks_k8s.py split pattern), wire them into cloud_checks_service.py's CLOUD_CHECKS concatenation and RUNNABLE_PROVIDERS, and widen all four CSPM provider gates in one lockstep edit. run_checks() itself needs zero logic changes to evaluate the two new providers (it filters CLOUD_CHECKS by provider) — but this plan adds one additive change: a simulated provenance flag on results so evaluations against real ingested findings (written by Plan 32-05) become distinguishable from catalog-only evaluations against the currently-empty cloud_findings collection.

**Objective:** Make M365 and MongoDB Atlas first-class runnable CSPM providers and set up the provenance flag Plan 32-05 flips to false when it writes real findings.

**Verified:** 2026-09-28T00:00:00Z
**Status:** passed
**Re-verification:** Yes — the 2026-07-10 report (`status: gaps_found`, 0/7 truths) predates commits `7c37c94f` and `a418d553` ("feat(phase-32-02): M365 + MongoDB Atlas catalogs, wire into CLOUD_CHECKS + RUNNABLE_PROVIDERS"), which closed every gap it listed. This report re-verifies against current code and the current test suite rather than assuming the prior report was still accurate — it was not; it had gone stale.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | run_checks() evaluates microsoft365 and mongodb_atlas checks unmodified once their catalogs exist and their provider strings are in RUNNABLE_PROVIDERS (PROV-02) | ✓ VERIFIED | `cloud_checks_m365.py` (64 lines, `M365_CHECKS`, 6 entries) and `cloud_checks_mongodb_atlas.py` (64 lines, `MONGODB_ATLAS_CHECKS`, 6 entries) both exist with real check content; imported and concatenated into `CLOUD_CHECKS` at `cloud_checks_service.py:13-14,34`; both provider strings present in `RUNNABLE_PROVIDERS` (line 40). `test_run_checks_evaluates_microsoft365` and `test_run_checks_evaluates_mongodb_atlas` (`tests/test_cloud_checks_expansion.py:56,65`) call `run_checks()` directly and assert `result["ran"] == 6` for each — both pass. |
| 2 | All four CSPM gates accept microsoft365 and mongodb_atlas: `_VALID_PROVIDERS` (registration), `cloud_checks_endpoints.py` run tuple, the MCP provider gate, and `RUNNABLE_PROVIDERS` — no gate accepts a provider another rejects (PROV-02, Phase 25 lockstep) | ✓ VERIFIED | `cloud_account_endpoints.py:13` `_VALID_PROVIDERS` includes both; `cloud_checks_endpoints.py:73` run-route tuple includes both; `RUNNABLE_PROVIDERS` includes both (above). The MCP gate is no longer a duplicated tuple in `mcp_server_endpoints.py` (that file is now a 6-line legacy stub with no provider logic — superseded by a refactor) — it moved to `mcp_server.py:56-66`'s `run_cloud_check()`, which imports `RUNNABLE_PROVIDERS` from `cloud_checks_service` at call time (line 62) as "the single source of truth," per its own docstring. This is stronger than the originally-planned fourth duplicated tuple: it cannot drift out of lockstep by construction. `test_all_gates_accept_microsoft365_and_mongodb_atlas` (`tests/test_cloud_checks_expansion.py:139`) passes. |
| 3 | The CSPM registration/validation gates also accept oci, alibaba, cloudflare so AddCloudAccountModal submissions for those three stop returning 400 (PROV-01 lockstep fix) | ✓ VERIFIED | All three present in `_VALID_PROVIDERS`, the `/run` route tuple, and `RUNNABLE_PROVIDERS` (same lines as above). `test_registration_gates_accept_oci_alibaba_cloudflare_now_runnable` (`tests/test_cloud_checks_expansion.py:149`) passes. |
| 4 | run_checks() results carry an additive simulated flag: true when db.cloud_findings had no entries for the account (catalog-only evaluation), false when real findings were present | ✓ VERIFIED | `cloud_checks_service.py:108`: `"simulated": not has_real_findings,`. `test_simulated_flag_true_when_no_findings` and `test_simulated_flag_false_when_findings_present` (`tests/test_cloud_checks_expansion.py:74,86`) both pass. |
| 5 | Existing catalog-only providers (aws/azure/gcp/kubernetes/digitalocean) keep identical PASS/FAIL behavior and ran counts — the simulated field is purely additive, no regression | ✓ VERIFIED | `test_no_regression_for_existing_providers` and `test_coverage_denominator_includes_new_providers` (`tests/test_cloud_checks_expansion.py:98,161`) pass; `test_run_checks_evaluates_kubernetes`/`_digitalocean` (lines 38,47) unaffected. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/cloud_checks_m365.py` | `M365_CHECKS: List[Dict[str, Any]]`, provider == `microsoft365` | ✓ VERIFIED | 64 lines, 6 checks (MFA enforcement, conditional access coverage, mailbox audit logging, external sharing restriction, and 2 more), each with id/name/description/provider/service/severity/frameworks/remediation |
| `backend/cloud_checks_mongodb_atlas.py` | `MONGODB_ATLAS_CHECKS: List[Dict[str, Any]]`, provider == `mongodb_atlas` | ✓ VERIFIED | 64 lines, 6 checks (no 0.0.0.0/0 access, encryption at rest, database auditing, private network access, and 2 more) |
| `backend/cloud_checks_service.py` | Imports both catalogs, appends to CLOUD_CHECKS, widens RUNNABLE_PROVIDERS, additive simulated flag | ✓ VERIFIED | Lines 13-14 (imports), 34 (concatenation), 40 (RUNNABLE_PROVIDERS), 108 (simulated flag) |
| `backend/cloud_account_endpoints.py` | `_VALID_PROVIDERS` widened with all 5 new providers | ✓ VERIFIED | Line 13 — set literal includes all 10 providers |
| `backend/cloud_checks_endpoints.py` | `/run` provider tuple widened + 400 message updated | ✓ VERIFIED | Lines 73-74 — tuple and error-detail string both list all 10 providers |
| MCP provider gate | Validation tuple widened | ✓ VERIFIED (refactored) | `mcp_server_endpoints.py` is now a superseded 6-line stub; the real gate is `mcp_server.py:62-64`, which imports `RUNNABLE_PROVIDERS` live instead of duplicating it |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full expansion + ingest + integration suite | `PYTHONPATH=. venv/bin/python3.12 -m pytest tests/test_cloud_checks_expansion.py tests/test_cloud_findings_ingest.py tests/test_cloud_integrations.py -q` | `43 passed in 0.97s` | PASS |
| `run_checks("acct-1", "microsoft365", "tenant-a")` | direct call in `test_run_checks_evaluates_microsoft365` | `result["ran"] == 6`, no error | PASS |
| `run_checks("acct-1", "mongodb_atlas", "tenant-a")` | direct call in `test_run_checks_evaluates_mongodb_atlas` | `result["ran"] == 6`, no error | PASS |

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PROV-02 | 32-02-PLAN.md | M365 + MongoDB Atlas check catalogs + cloud_checks_service.py widening + additive simulated provenance flag + four-gate lockstep widening | ✓ SATISFIED | All 5 truths verified above; 43/43 relevant tests pass |

## Anti-Patterns Found

None. No TBD/FIXME/XXX/HACK markers in `cloud_checks_m365.py` or `cloud_checks_mongodb_atlas.py`.

## Gaps Summary

**Plan 32-02 Goal Status:** ACHIEVED

None of the 7 originally-reported gaps remain. The 2026-07-10 report was accurate for the code as it stood on that date, but commits `7c37c94f` and `a418d553` closed every item shortly after (catalogs created, all providers wired into every gate, simulated flag added) — that work was simply never reflected back into this file, so it kept reporting a stale blocker. This re-verification confirms the current code and test suite directly rather than trusting either the old report or the newer `32-VERIFICATION.md` summary at face value.

Note: the phase-level `32-VERIFICATION.md` (2026-07-14 re-verification) already recorded this same gap closure in its `gaps_closed` list. This plan-level report was the one still out of sync; it's now consistent with the phase-level record.

**What remains open in Phase 32 overall** (tracked separately, not part of PROV-02 / this plan): `PROV-03` (SaaS posture checks) and `PROV-04` (attack-path SIMULATED badge + edge labels) — both flagged `human_needed` in `32-VERIFICATION.md`, i.e. wired in code but pending live-browser confirmation, not known defects.

---

_Verified: 2026-09-28T00:00:00Z_
_Verifier: Claude (re-verification against live code + test suite, prompted by a stale-report correction during a production-readiness audit)_
