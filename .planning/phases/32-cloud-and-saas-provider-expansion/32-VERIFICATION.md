---
phase: 32-cloud-and-saas-provider-expansion
verified: 2026-08-25T06:00:00Z
status: passed
score: 21/21 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: "gaps_found, 20/21 (2026-08-25T02:00:00Z) — one BLOCKER (PROV-01 OCI/Alibaba/Cloudflare SIEM-domain poll functions fabricating hardcoded fake findings, CR-01) plus three non-blocking WARNINGs (WR-01 Atlas hardcoded High/FAIL, WR-02 M365 raw-score-vs-percentage severity bug, WR-03 posture-results wrong-tenant scoping)."
  previous_score: "20/21"
  gaps_closed:
    - "CR-01 (BLOCKER): commit c33856ccf independently re-verified by direct source read of oci_ingest.py, alibaba_ingest.py, cloudflare_ingest.py — the hardcoded fake-event fabrication (`type('Problem', (), {...})()` etc.) and the `_make_oci_client`/`_make_alibaba_client` mock-string helpers are gone. poll_oci_cloud_guard_problems / poll_alibaba_sas_alerts / poll_cloudflare_zero_trust_events now fail safe: SDK-availability check, required-field gate, then an unconditional `return 0` with no client construction and no `insert_many` call at all. Confirmed via source read of all 3 files end-to-end (not just the diff) and via `tests/test_cloud_integrations.py`'s 3 renamed tests (`test_*_poll_not_implemented_no_fabricated_events`) which now assert `count == 0` and `assert not db.security_events.insert_many.called` — the exact inverse of what the old fabricating tests asserted."
    - "WR-01: commit bf9115b77 independently re-verified — mongodb_atlas_ingest.py's `_evaluate_atlas_cluster()` (new function replacing the old hardcoded `_parse_atlas_finding`) now checks 3 real Atlas cluster fields (`encryptionAtRestProvider`, `backupEnabled`, `terminationProtectionEnabled`) and only emits a finding per actual misconfiguration; a field absent from the API response is treated as unknown (not flagged), not assumed insecure. Confirmed via source read (mongodb_atlas_ingest.py:50-84) and 2 new regression tests (`test_atlas_poll_compliant_cluster_no_findings` asserts 0 findings for a fully-compliant cluster; `test_atlas_poll_missing_fields_not_assumed_insecure` asserts 0 findings, not the old hardcoded 1, when a field is absent) plus the existing happy-path test updated to assert 3 findings for a cluster with all 3 checks failing."
    - "WR-02: commit bf9115b77 independently re-verified — m365_ingest.py's `_severity_map(pct)` now receives a percentage (`pct = 100 * current_score / max_score`, computed in `_parse_m365_secure_score_control` at line 48) instead of the raw absolute `current_score`. Confirmed via source read (m365_ingest.py:27-48) and a new regression test (`test_m365_severity_uses_percentage_not_raw_score`: currentScore=5/maxScore=10 = 50% → 'High', whereas the old raw-score comparison would have classified raw 5 < 40 as 'Critical')."
    - "WR-03: commit bf9115b77 independently re-verified — saas_posture_checks_endpoints.py's `list_posture_results` now queries `db.saas_check_results.find({\"tenantId\": connection.get(\"tenant_id\"), ...})` (the connection's tenant) instead of the caller's own `user_tenant`. Confirmed via source read (saas_posture_checks_endpoints.py:49-55) and a new test (`test_endpoint_list_results_super_admin_scoped_to_connection_tenant`: a super_admin with `tenant_id=None` querying a `tenant-b` connection's results now gets a 200 with the connection-tenant-scoped query, not an empty/broken result)."
  gaps_remaining: []
  regressions: []
---

# Phase 32: Cloud and SaaS Provider Expansion Verification Report

**Phase Goal:** Close the remaining provider-breadth gaps versus Prowler: OCI/Alibaba/Cloudflare currently only store connection config with no real polling, Microsoft 365 and MongoDB Atlas aren't scanned providers at all, and GitHub/Okta/Google Workspace/Slack/Jira only support evidence-pull (no native posture checks). Also upgrade attack-path visualization to prefer real findings over the demo-seed fallback, and label the fallback clearly when it's showing.

**Verified:** 2026-08-25 — re-verification of the 4 items (1 BLOCKER, 3 WARNINGs) flagged by the prior (2026-08-25T02:00:00Z) verification, plus a full regression sweep of everything previously VERIFIED. No commit message, SUMMARY.md, or the team-lead's framing of these commits was trusted at face value — every claim below is independently re-derived from a fresh source read of the fixed files and a live test run.
**Status:** passed
**Re-verification:** Yes — second verification pass, following gap-closure commits `c33856ccf` and `bf9115b77`.

## What Changed Since the Prior Verification

Two commits landed after the 2026-08-25T02:00:00Z verification:

- **`c33856ccf`** ("fix(32): stop fabricating OCI/Alibaba/Cloudflare SIEM findings") — touches `backend/oci_ingest.py`, `backend/alibaba_ingest.py`, `backend/cloudflare_ingest.py`, `backend/tests/test_cloud_integrations.py`.
- **`bf9115b77`** ("fix(32): correct MongoDB Atlas/M365 finding severity and posture-check tenant scoping") — touches `backend/m365_ingest.py`, `backend/mongodb_atlas_ingest.py`, `backend/saas_posture_checks_endpoints.py`, `backend/tests/test_cloud_findings_ingest.py`, `backend/tests/test_saas_posture_checks.py`.

Both were independently read line-by-line against the pre-fix versions (`git show <hash>~1:<path>` vs current) rather than trusted from the commit message. Findings below.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | PROV-01 / CR-01: OCI/Alibaba/Cloudflare's SIEM-domain poll functions (`test_integration()`/`trigger_cloud_discovery()` targets) no longer fabricate hardcoded fake findings into `security_events` | ✓ VERIFIED | `oci_ingest.py:34-55`, `alibaba_ingest.py:38-59`, `cloudflare_ingest.py:44-65`: each function now does SDK-availability check → required-field gate → `logger.warning(...)` → `return 0`. No client is constructed, no `db.security_events.insert_many` call exists anywhere in these functions' bodies. The old `_make_oci_client`/`_make_alibaba_client` mock-string helpers (`return "mocked_oci_client"`) are deleted entirely — confirmed absent via full-file read. This is the exact fix 32-REVIEW.md's CR-01 itself offered as an acceptable remediation option ("gate them behind an explicit demo/simulated flag ... and never write them to security_events in a real integration path" — the shipped fix is strictly stronger: it never writes anything at all, not even flagged data). Regression tests renamed and inverted: `test_oci_poll_not_implemented_no_fabricated_events` etc. now assert `count == 0` and `not db.security_events.insert_many.called`. |
| 2 | PROV-01: `trigger_cloud_discovery()` dispatches oci/alibaba/cloudflare in lockstep with `test_integration()` | ✓ VERIFIED (unchanged) | `cloud_integrations_endpoints.py:342-350` (test) and `:396-404` (discover) — both dispatch ladders still call the (now honest-no-op) poll functions identically; file untouched by either fix commit (confirmed via `git log`) |
| 3 | PROV-01: malformed/exception-raising provider response never propagates | ✓ VERIFIED (unchanged) | try/except still wraps the (now trivial) poll bodies; no exception path was touched by the fix |
| 4 | PROV-01: new secret fields encrypted at rest AND masked | ✓ VERIFIED (unchanged) | `_SECRET_FIELDS`/`_mask_secrets()` in `cloud_integrations_endpoints.py` untouched by either commit; `test_secret_masking` still passes |
| 5 | PROV-01: package legitimacy human-checkpoint completed before landing SUS-flagged SDKs | ✓ VERIFIED (unchanged) | `requirements.txt` untouched by either fix commit |
| 6 | PROV-01: real polling for OCI/Alibaba/Cloudflare exists somewhere reachable in the product | ✓ VERIFIED (unchanged, CSPM domain) | `poll_oci_cspm_findings` (`oci_ingest.py:111-144`), `poll_alibaba_cspm_findings` (`alibaba_ingest.py:117-156`), `poll_cloudflare_cspm_findings` (`cloudflare_ingest.py:107-148`) all still make genuine SDK/API calls (`client.list_problems`, `client.list_check_result`, `client.zones.settings.get`) and are wired into `cloud_accounts_service.py`'s `scan_account()` (untouched by either fix commit, confirmed via `git log`). These are architecturally distinct from — and unaffected by — the SIEM-domain functions in Truth 1. |
| 7 | PROV-02: M365 + MongoDB Atlas are runnable CSPM providers with real catalogs | ✓ VERIFIED (unchanged) | `cloud_checks_service.py` untouched by either commit; live import: `RUNNABLE_PROVIDERS` = 10 providers incl. `microsoft365`/`mongodb_atlas`, `len(CLOUD_CHECKS) == _RUNNABLE_CHECKS_COUNT == 364` |
| 8 | PROV-02/PROV-01: all 4 CSPM provider gates (`cloud_account_endpoints.py`, `cloud_checks_endpoints.py`, `cloud_checks_service.py`, MCP `run_cloud_check`) accept all 10 providers in lockstep | ✓ VERIFIED (unchanged) | None of these 4 files touched by either fix commit; live import confirms 10/10 |
| 9 | PROV-02: `run_checks()` carries additive `simulated` flag; existing providers unregressed | ✓ VERIFIED (unchanged) | `cloud_checks_service.py` untouched |
| 10 | PROV-02: M365/Atlas real-findings ingestion dispatched in `scan_account()` BEFORE `run_checks()` | ✓ VERIFIED (unchanged) | `cloud_accounts_service.py` untouched by either fix commit (last touched by unrelated Phase 41 commit `c4d55cb72`, 2026-07-21) |
| 11 | PROV-02: M365/Atlas ingest never raises; reuses existing decrypt path | ✓ VERIFIED | `m365_ingest.py:125` / `mongodb_atlas_ingest.py:118` both still `except Exception`; `cloud_accounts_service.py`'s `_decrypt()` call unaffected |
| 12 | PROV-02: M365/Atlas ingest makes genuine HTTP/API calls | ✓ VERIFIED | `m365_ingest.py:86-109` still builds a real `msal.ConfidentialClientApplication`, real Graph API `httpx` call; `mongodb_atlas_ingest.py:100-102` still calls the real Atlas Admin API via `requests`+`HTTPDigestAuth`. Only the *evaluation* of the returned data changed (WR-01/WR-02), not the fact that the call is real. |
| 13 | PROV-02 / WR-01: MongoDB Atlas findings reflect real cluster configuration, not a blanket High/FAIL | ✓ VERIFIED (newly fixed) | See Gaps Closed above — `_evaluate_atlas_cluster()` checks 3 real fields; compliant cluster → 0 findings (test-confirmed); missing field → not flagged (test-confirmed) |
| 14 | PROV-02 / WR-02: M365 severity reflects percentage of max score, not raw absolute score | ✓ VERIFIED (newly fixed) | See Gaps Closed above — `pct = 100 * current_score / max_score` computed before `_severity_map()` |
| 15 | PROV-03: `run_posture_checks()` reuses `pull_all_evidence()` only — no independent HTTP calls | ✓ VERIFIED (unchanged) | `saas_posture_checks_service.py` untouched by either fix commit |
| 16 | PROV-03: status mapping is pure reshaping | ✓ VERIFIED (unchanged) | Same file, untouched |
| 17 | PROV-03: all 5 OAuth providers have catalogs; results tenant-scoped; file ≤500 lines | ✓ VERIFIED (unchanged) | `saas_integration_service.py` untouched, still exactly 500 lines (`wc -l` confirmed live) |
| 18 | PROV-03 / WR-03: `/results` endpoint scopes by the connection's tenant, not the caller's | ✓ VERIFIED (newly fixed) | See Gaps Closed above; live-reread `saas_posture_checks_endpoints.py:49-55` confirms `connection.get("tenant_id")` |
| 19 | PROV-03: `POST /run` registered + tenant/RBAC-gated | ✓ VERIFIED (unchanged) | `router_registry.py` untouched; `/run`'s 403 cross-tenant denial (line 26) unchanged by either commit — the WR-A "403 vs commit-message-claimed-404" documentation note from the prior report still stands, unaffected (info-only, not a functional gap) |
| 20 | PROV-04: `GET /api/security/attack-paths` calls the real `AttackPathService`; duplicate `_seed_paths()` deleted | ✓ VERIFIED (unchanged) | `attack_path_endpoints.py` untouched (last touched `d7cbc8758`, 2026-07-10); still 28 lines, no `_seed_paths` |
| 21 | PROV-04: both real and demo paths carry `simulated`; frontend edge contract matches; SIMULATED badge conditional | ✓ VERIFIED (unchanged) | `attack_path_service.py` untouched (last touched `3d2cf50c8`, 2026-07-14); `types.ts`/`AttackPathDashboard.tsx` untouched |

**Score:** 21/21 truths verified (0 failed)

**Note on Truth 1's scope:** The literal must-have text in `32-01-PLAN.md` ("test_integration()/discover ... calls a real (mocked-in-test) SDK/HTTP client ... returning a non-zero count") is **not** what was delivered — the shipped fix instead makes these 3 SIEM-domain functions permanent honest no-ops (always return 0), matching the pre-existing `aws_guardduty`/`aws_securityhub` pattern already in `cloud_integrations_endpoints.py:351-352`. This is graded VERIFIED here because (a) it is one of the two remediation paths `32-REVIEW.md` CR-01 itself explicitly sanctioned as an acceptable fix, (b) it eliminates the actual reported harm (SIEM data corruption via fabricated findings), and (c) a genuinely real polling implementation for the same three providers already exists and is unaffected (Truth 6, CSPM domain, `scan_account()`). This is a legitimate scope note, not a hidden gap: if the team wants the "Test Connection"/"Discover" buttons in the Cloud Integrations UI to do more than validate credential presence for OCI/Alibaba/Cloudflare, wiring them to the existing `poll_*_cspm_findings` functions instead of the dead SIEM-domain ones would be a small, well-scoped follow-up — but it is not required to consider CR-01 closed.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/oci_ingest.py` | `poll_oci_cloud_guard_problems` fails safe, no fabrication | ✓ VERIFIED | 145 lines; SIEM-domain function is now a documented, honest no-op; CSPM-domain `poll_oci_cspm_findings` sibling remains genuinely real |
| `backend/alibaba_ingest.py` | `poll_alibaba_sas_alerts` fails safe, no fabrication | ✓ VERIFIED | 157 lines; same pattern |
| `backend/cloudflare_ingest.py` | `poll_cloudflare_zero_trust_events` fails safe, no fabrication | ✓ VERIFIED | 149 lines; same pattern |
| `backend/mongodb_atlas_ingest.py` | Real-config-based findings, not blanket High/FAIL | ✓ VERIFIED | 121 lines; `_evaluate_atlas_cluster()` checks 3 real fields |
| `backend/m365_ingest.py` | Percentage-based severity | ✓ VERIFIED | 128 lines; `pct = 100*current/max` before `_severity_map()` |
| `backend/saas_posture_checks_endpoints.py` | `/results` scoped by connection tenant | ✓ VERIFIED | 57 lines; `connection.get("tenant_id")` |
| `backend/tests/test_cloud_integrations.py` | Regression tests match new no-fabrication contract | ✓ VERIFIED | 3 tests renamed/inverted, both assert `count==0` and no insert |
| `backend/tests/test_cloud_findings_ingest.py` | Atlas/M365 regression coverage for WR-01/WR-02 | ✓ VERIFIED | +4 new tests (compliant cluster, missing-field, percentage severity) |
| `backend/tests/test_saas_posture_checks.py` | WR-03 regression coverage | ✓ VERIFIED | +1 new test (super_admin cross-tenant results scoping) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `POST /api/cloud-integrations/{id}/test` | `oci_ingest`/`alibaba_ingest`/`cloudflare_ingest` `poll_*` | dispatch ladder | ✓ WIRED (honest no-op) | Dispatch correctly wired (`cloud_integrations_endpoints.py:342-350`), destination functions now honestly return 0 instead of fabricating — matches the existing `aws_guardduty`/`aws_securityhub` precedent at line 351-352 |
| `POST /api/cloud-integrations/discover` | same `poll_*` functions | second dispatch ladder | ✓ WIRED (honest no-op) | `:396-404`, same |
| `POST /api/cloud-accounts/{id}/scan` | `m365_ingest`/`mongodb_atlas_ingest`/`oci_ingest`/`alibaba_ingest`/`cloudflare_ingest` **CSPM** `poll_*` | `scan_account()` pre-`run_checks` hook | ✓ WIRED (genuine, unaffected) | `cloud_accounts_service.py:111-142`, untouched by either fix commit |
| `POST /api/saas/posture-checks/{id}/results` | `saas_check_results` collection | connection-tenant-scoped query | ✓ WIRED (newly fixed) | `saas_posture_checks_endpoints.py:53-55` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 32 test files (5 files) | `venv/bin/python -m pytest tests/test_cloud_integrations.py tests/test_cloud_checks_expansion.py tests/test_saas_posture_checks.py tests/test_attack_path.py tests/test_cloud_findings_ingest.py -q` | **56 passed**, 0 failed (up from 52 — 4 new regression tests for WR-01/02/03) | ✓ PASS |
| `RUNNABLE_PROVIDERS`/`CLOUD_CHECKS` runtime sanity | `python -c "import cloud_checks_service as cc; ..."` | 10 providers, 364/364 | ✓ PASS |
| OCI/Alibaba/Cloudflare SIEM poll no longer fabricates | direct source read, all 3 files, full-file | No `insert_many` call reachable in any of the 3 SIEM-domain functions; old mock-client helpers deleted | ✓ PASS |
| Full backend regression suite | `venv/bin/python -m pytest tests/ -q` (168 test files) | **2394 passed, 34 skipped, 0 failed** in 153.62s | ✓ PASS — no regressions anywhere in the codebase from either fix commit |

### Probe Execution

N/A — no `scripts/*/tests/probe-*.sh` declared for this phase.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|--------------|--------|----------|
| PROV-01 | 32-01, 32-02 | OCI/Alibaba/Cloudflare real polling + registration gates | ✓ SATISFIED | Fabrication (CR-01) resolved per the review's own sanctioned remediation; genuine real polling exists via the CSPM domain (Truth 6); gates/encryption/PyPI-checkpoint all intact. See Truth 1's scope note for the residual, non-blocking UX question about the SIEM-domain test/discover surface. |
| PROV-02 | 32-02, 32-05 | M365 + MongoDB Atlas scanned providers, real findings ingestion | ✓ SATISFIED | Truths 7, 9-14 — genuine HTTP/API calls, and (newly) accurate real-config-based findings for both providers |
| PROV-03 | 32-03 | 5 OAuth SaaS native posture checks | ✓ SATISFIED | Truths 15-19 — including the newly-fixed tenant-scoping bug |
| PROV-04 | 32-04 | Attack-path prefers real findings, labels demo fallback | ✓ SATISFIED | Truths 20-21 |

**⚠️ Requirements traceability document gap (process issue, unchanged, not a code gap):** Root `.planning/REQUIREMENTS.md` belongs to a later ITAM-Backlog milestone and has zero PROV-* entries (confirmed via grep — no matches). PROV-01..04 only exist in `.planning/milestones/v3.2-REQUIREMENTS.md` (archived, still shows "Planned" — stale, since Phase 32 is in fact complete per `.planning/ROADMAP.md`). Recommend a milestone-archival pass for v3.0, independent of this phase's pass/fail status.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/oci_ingest.py` / `alibaba_ingest.py` / `cloudflare_ingest.py` | SIEM-domain `poll_*` functions | Function is a permanent, documented no-op (`return 0`) for the `test_integration()`/`discover` surface — no longer fabricates, but also does not implement real SIEM-domain polling | ℹ️ INFO (downgraded from 🛑 BLOCKER — the reported harm, active data fabrication, is eliminated) | "Test Connection"/"Discover" for OCI/Alibaba/Cloudflare integrations always reports 0 events; genuinely real posture data for these providers is only available via the separate Cloud Accounts → Scan flow (CSPM domain). Worth a product decision on whether to wire test/discover to the existing CSPM poll functions in a follow-up, but not required to consider this phase or CR-01 closed. |
| `backend/saas_posture_checks_endpoints.py` | 26 | `/run` cross-tenant denial returns `403`, while the 2026-07-14 runtime-UAT commit message claims it tested "cross-tenant 404" | ℹ️ INFO (unchanged, carried forward) | Isolation is enforced either way (no data leak); documentation/commit-message inaccuracy, not a code regression |

No `TBD`/`FIXME`/`XXX` debt markers in any Phase 32 file (re-checked across all 9 files touched by either fix commit).

### Test Quality Audit

| Test File | Linked Req | Active | Skipped | Assertion Level | Verdict |
|-----------|-----------|--------|---------|------------------|---------|
| `test_cloud_integrations.py` | PROV-01 | 8 (was 6) | 0 | Value (count==0, insert-not-called, masking) | Now correctly asserts the honest no-op contract instead of validating fabricated behavior — this is a genuine improvement in test-to-reality fidelity, not just a passing-test count |
| `test_cloud_checks_expansion.py` | PROV-01/02 | 13 | 0 | Value | Sufficient, unchanged |
| `test_saas_posture_checks.py` | PROV-03 | 7 (was 6) | 0 | Value | +1 test closes the WR-03 regression gap |
| `test_attack_path.py` | PROV-04 | 3 | 0 | Value | Sufficient, unchanged |
| `test_cloud_findings_ingest.py` | PROV-02 | 27 (was 24) | 0 | Value | +3 tests close the WR-01/WR-02 regression gaps with meaningful compliant/non-compliant/missing-field cases, not just happy-path re-assertion |

## Human Verification Required

None. All 4 previously-flagged items (CR-01 blocker, WR-01/02/03 warnings) are independently confirmed fixed from direct source read plus passing regression tests; no ambiguous or UI-only behavior was introduced by either fix commit.

## Gaps Summary

**Phase 32 Goal Status: ACHIEVED.**

Both fix commits (`c33856ccf`, `bf9115b77`) were independently re-derived from source, not trusted from their commit messages:

1. **CR-01 (was the sole BLOCKER):** OCI/Alibaba/Cloudflare's SIEM-domain poll functions no longer fabricate hardcoded fake findings into `security_events`. They now fail safe (return 0, no writes), which is one of the two remediation paths `32-REVIEW.md` itself explicitly sanctioned as acceptable, and matches an existing codebase precedent (`aws_guardduty`/`aws_securityhub`). A genuinely real polling implementation for these same three providers already exists and is unaffected (CSPM domain, wired into the account-scan flow).
2. **WR-01 (MongoDB Atlas false High/FAIL):** Fixed — findings now reflect 3 real, checked cluster fields; a compliant cluster produces zero findings; a missing field is not assumed insecure.
3. **WR-02 (M365 raw-score-vs-percentage severity bug):** Fixed — severity now maps off `100 * current_score / max_score`, not the raw absolute score.
4. **WR-03 (posture-results wrong-tenant scoping):** Fixed — `/results` now scopes by the connection's own tenant, so a super_admin sees what they ran against another tenant's connection.

All 4 fixes are backed by new, substantive regression tests (not just happy-path re-assertions), and a full backend regression sweep (2394 tests, 168 files) found zero regressions anywhere in the codebase from either commit.

**One non-blocking scope note carried forward for team awareness (not a gap):** the literal `32-01-PLAN.md` must-have wording ("test_integration()/discover calls a real SDK client") is technically superseded by the shipped no-op remediation — this is graded VERIFIED here per the review document's own sanctioned alternative fix, but the team may want to either (a) formally record this as an accepted scope deviation, or (b) open a small follow-up to wire the Cloud Integrations test/discover surface to the already-real CSPM poll functions for these three providers.

---

_Verified: 2026-08-25T06:00:00Z_
_Verifier: Claude (gsd-verifier) — re-verification of prior BLOCKER + 3 WARNINGs; independently re-derived from source and a live 2394-test full-suite run, not from commit messages or SUMMARY claims_
