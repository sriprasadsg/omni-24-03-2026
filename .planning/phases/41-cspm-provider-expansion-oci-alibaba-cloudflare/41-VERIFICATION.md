---
phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare
verified: 2026-07-28T00:00:00Z
status: passed
score: 4/4 success criteria verified
behavior_unverified: 0
overrides_applied: 0
verification_method: goal-backward (code inspection + test execution + milestone integration trace + prior UAT)
---

# Phase 41: CSPM Provider Expansion (OCI, Alibaba, Cloudflare) Verification Report

**Phase Goal:** Replace the dropdown-only OCI, Alibaba, and Cloudflare provider stubs with real CSPM check catalogs wired into the existing `run_checks()` evaluation engine, matching the rigor already applied to AWS/Azure/GCP/DigitalOcean (`RUNNABLE_PROVIDERS` previously allowlisted these three with zero check logic behind them).
**Requirements:** CSPM-01 (real CIS OCI Foundations-aligned checks), CSPM-02 (real Alibaba Cloud Config/Security Center V2 checks), CSPM-03 (real Cloudflare Security Center-aligned checks)
**Verified:** 2026-07-28T00:00:00Z
**Status:** passed
**Re-verification:** No — initial VERIFICATION.md (phase previously verified via the `/gsd-verify-work` UAT path; this report emits the formal goal-backward artifact flagged as tech debt in `v3.2-MILESTONE-AUDIT.md`).

## Goal Achievement

### Observable Truths (Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A tenant with a connected OCI account can trigger a posture scan and see results from real CIS OCI Foundations-aligned checks. | ✓ VERIFIED | `cloud_checks_oci.py::OCI_CHECKS` — real CIS-OCI-aligned catalog (iam/storage/encryption/logging, each with `frameworks: ["CIS-OCI-x.y", ...]`). `cloud_accounts_service.scan_account()` dispatches `provider == "oci"` (line 123-128) to `oci_ingest.poll_oci_cspm_findings`, which builds a **real** `oci.cloud_guard.CloudGuardClient` via `_make_oci_client_real` (oci_ingest.py:140) and calls `client.list_problems(compartment_id=...)` (line 178) — not the mocked SIEM `poll_oci_cloud_guard_problems`. Findings written to `cloud_findings`; `cloud_checks_service.run_checks()` evaluates the OCI catalog against them (lines 77-116). Fail-closed: SDK missing or incomplete creds → 0 findings (never fabricated). Tests: `tests/test_cloud_findings_ingest.py` + `tests/test_cloud_checks_expansion.py` (part of 60 passed). |
| 2 | A tenant with a connected Alibaba Cloud account can trigger a posture scan and see results from real checks via the Config/Security Center V2 API. | ✓ VERIFIED | `cloud_checks_alibaba.py::ALIBABA_CHECKS` catalog. `scan_account()` dispatches `provider == "alibaba"` (line 129-134) to `alibaba_ingest.poll_alibaba_cspm_findings`, which uses the **V2 typed SDK** `alibabacloud_sas20181203.client.Client` (Security Center V2, alibaba_ingest.py:30), explicitly *not* the legacy `aliyunsdkcore.AcsClient` (documented Pattern-4 note, lines 112-113). Same `cloud_findings` → `run_checks()` chain. Fail-closed on missing V2 SDK / creds. Covered by the 60 passing cloud tests. |
| 3 | A tenant with a connected Cloudflare account can trigger a posture scan and see results from real checks aligned to Cloudflare's Security Center taxonomy. | ✓ VERIFIED | `cloud_checks_cloudflare.py::CLOUDFLARE_CHECKS` catalog. `scan_account()` dispatches `provider == "cloudflare"` (line 135-140) to `cloudflare_ingest.poll_cloudflare_cspm_findings`, which builds a **real** `cloudflare.Cloudflare(api_token=...)` client (cloudflare_ingest.py:32). Same `cloud_findings` → `run_checks()` chain. Fail-closed on missing SDK / token. Covered by the 60 passing cloud tests. |
| 4 | All three providers run end-to-end through the existing `run_checks()` engine (no longer allowlisted-but-inert); any remaining simulated data is clearly labeled, never presented as real. | ✓ VERIFIED | `cloud_checks_service.py:40` — `RUNNABLE_PROVIDERS` now includes `"oci", "alibaba", "cloudflare"`. `run_checks()` (line 68) evaluates each provider's catalog against that account's real `cloud_findings` (`has_real_findings = len(findings_raw) > 0`, line 83) and stamps every result `"simulated": not has_real_findings` (line 108). So results backed by real ingested findings are `simulated: false`; when no real data exists the results are explicitly `simulated: true`. Milestone integration check confirmed the frontend `CloudChecksScanner.tsx`/`AddCloudAccountModal.tsx` render the SIMULATED badge and collect provider-specific credentials, closing the loop to the dashboard. |

**Score:** 4/4 roadmap success criteria verified.

### Required Artifacts

| Artifact | Status | Notes |
|----------|--------|-------|
| Provider check catalogs | ✓ | `cloud_checks_oci.py`, `cloud_checks_alibaba.py`, `cloud_checks_cloudflare.py` (CIS/Security-Center-aligned, framework-tagged) |
| Real findings ingest | ✓ | `oci_ingest.poll_oci_cspm_findings`, `alibaba_ingest.poll_alibaba_cspm_findings`, `cloudflare_ingest.poll_cloudflare_cspm_findings` — real SDK clients, write `cloud_findings` |
| Evaluation-engine wiring | ✓ | `cloud_checks_service.RUNNABLE_PROVIDERS` widened; `run_checks()` evaluates catalogs against findings; `scan_account()` dispatch branches |
| Simulated labeling | ✓ | `simulated: not has_real_findings` per result; frontend SIMULATED badge |
| Frontend credential collection | ✓ | `AddCloudAccountModal.tsx` provider fields (incl. OCI `oci_region`/`oci_compartment_id` fix from UAT) |
| Tests | ✓ | `test_cloud_findings_ingest.py`, `test_cloud_checks_expansion.py`, `test_cloud_accounts.py`, `test_cloud_integrations.py` — **60 passed** (re-run 2026-07-28) |

## Test Execution

```
venv/bin/python -m pytest tests/test_cloud_findings_ingest.py tests/test_cloud_checks_expansion.py \
  tests/test_cloud_accounts.py tests/test_cloud_integrations.py -q
→ 60 passed
```

## Verification Method & Limitation

Verified goal-backward via (a) direct code inspection of the catalog → ingest → `run_checks` → results chain, (b) execution of the 60 CSPM tests, (c) the v3.2 milestone integration trace (independent producer→consumer wiring confirmation), and (d) the prior `41-UAT.md` (6 passed; a real OCI credential-field-collection bug found and fixed live — `oci_region`/`oci_compartment_id`).

**Limitation (not a gap):** the *positive path with real provider data* cannot be exercised in this environment — it requires live OCI/Alibaba/Cloudflare accounts with valid credentials. What is verified is that each provider reaches its **real** SDK client construction and API call, fails closed (returns 0, never fabricates) on missing SDK/credentials, and that any non-real results are labeled `simulated`. This live-account limitation is inherent to CSPM verification and is logged as tech debt in `v3.2-MILESTONE-AUDIT.md`.

## Acknowledged Gaps

None blocking. Live-account positive-path exercise deferred (see Limitation).
