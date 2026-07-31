---
phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare
plan: 03
subsystem: api
tags: [oci, cloud-guard, alibaba, alibabacloud-sdk, cloudflare, cspm, cloud-findings, mongodb]

# Dependency graph
requires:
  - phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare
    provides: "41-02: alibabacloud_* V2 SDK packages pinned in requirements.txt and installed in backend/venv"
provides:
  - "poll_oci_cspm_findings(config, account_id, tenant_id) — real oci.cloud_guard.CloudGuardClient.list_problems() call writing cloud_findings"
  - "poll_alibaba_cspm_findings(config, account_id, tenant_id) — V2 typed alibabacloud_sas20181203 ListCheckResult call writing cloud_findings"
  - "poll_cloudflare_cspm_findings(config, account_id, tenant_id) — real cloudflare SDK zone-settings (SSL/min-TLS/WAF) calls writing cloud_findings"
  - "20 hermetic unit tests (success/missing-config/raise-returns-0 per provider) in test_cloud_findings_ingest.py"
affects: [41-cloud_accounts_service-scan_account-wiring, cloud-checks-provider-expansion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "3-arg (config, account_id, tenant_id) -> int CSPM poll function, cloned from mongodb_atlas_ingest.py, writing db.cloud_findings — added alongside (never replacing) the existing 2-arg SIEM poll_* functions that write db.security_events"
    - "Provider-specific real-client builder kept SEPARATE from the existing mocked _make_*_client() helper when un-mocking in place would break a pre-existing SIEM test (OCI); un-mocked in place when it provably would not (Cloudflare)"

key-files:
  created: []
  modified:
    - backend/oci_ingest.py
    - backend/alibaba_ingest.py
    - backend/cloudflare_ingest.py
    - backend/tests/test_cloud_findings_ingest.py

key-decisions:
  - "OCI: added a new _make_oci_client_real() helper rather than un-mocking the existing _make_oci_client() in place — verified live that oci.cloud_guard.CloudGuardClient(oci_config) raises oci.exceptions.InvalidConfig on the placeholder OCID/fingerprint strings the pre-existing test_oci_poll_success (test_cloud_integrations.py) uses without mocking client construction; un-mocking in place would have broken that test"
  - "Cloudflare: _make_cloudflare_client() WAS un-mocked in place (per the plan's literal instruction) — verified live that cloudflare.Cloudflare(api_token=...) never raises on construction regardless of token validity, so this is safe and does not regress the existing poll_cloudflare_zero_trust_events test"
  - "Alibaba: added a real V2 typed client builder (_make_alibaba_v2_client) gated on a new, separate _ALIBABA_V2_SDK_AVAILABLE flag, alongside the untouched V1 _ALIBABA_SDK_AVAILABLE/AcsClient flag and _make_alibaba_client() — zero shared code path with the SIEM function"
  - "Cloudflare CSPM findings check three real zone settings resolved from the installed cloudflare==5.5.0 SDK's type definitions (ssl.py/min_tls_version.py/waf.py): SSL mode (non-compliant if off/flexible), minimum TLS version (non-compliant if 1.0/1.1), and the legacy WAF toggle (non-compliant if off) — required config field is a new cf_zone_id (zone-scoped settings API needs a zone, not the SIEM domain's cf_account_id), with a fallback read of cf_account_id for convenience"
  - "Alibaba CSPM findings call SAS's list_check_result(ListCheckResultRequest) (maps directly to check_id/check_show_name/status/status_message/risk_level) rather than describe_check_warning_summary (a risk-category count rollup) — closer 1:1 match to the plan's 'checkId from the check id, status=FAIL for failing baseline items' shape; only checks whose status is not in {pass, passed, ok, normal} are ingested as FAIL findings"
  - "Alibaba severity mapping uses a new string-keyed _severity_map_v2() (serious/critical/high/medium/low) rather than the existing int-keyed V1 _severity_map(), because the V2 SAS SDK's risk_level field is a string enum, not the V1 SDK's 1-4 int"

patterns-established:
  - "When a plan instructs un-mocking a shared client-builder helper, verify against the ACTUAL installed SDK whether doing so raises for the pre-existing (unmocked-client) SIEM test's placeholder credentials before touching it in place — split into a separate real-variant helper if it would regress that test, sharing helper in place only when proven safe"

requirements-completed: [CSPM-01, CSPM-02, CSPM-03]

coverage:
  - id: D1
    description: "poll_oci_cspm_findings calls real OCI Cloud Guard list_problems and writes account/tenant-scoped findings to cloud_findings (CSPM-01)"
    requirement: "CSPM-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_cloud_findings_ingest.py#test_oci_cspm_poll_success"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cloud_findings_ingest.py#test_oci_cspm_poll_missing_config"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cloud_findings_ingest.py#test_oci_cspm_poll_raise_returns_0"
        status: pass
    human_judgment: false
  - id: D2
    description: "poll_alibaba_cspm_findings uses the V2 typed alibabacloud_sas20181203 SDK (never AcsClient) and writes findings to cloud_findings (CSPM-02)"
    requirement: "CSPM-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_cloud_findings_ingest.py#test_alibaba_cspm_poll_success"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cloud_findings_ingest.py#test_alibaba_cspm_poll_missing_config"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cloud_findings_ingest.py#test_alibaba_cspm_poll_raise_returns_0"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cloud_findings_ingest.py#test_alibaba_cspm_uses_v2_sdk_not_acs_client"
        status: pass
    human_judgment: false
  - id: D3
    description: "poll_cloudflare_cspm_findings reads real zone security settings (SSL mode, min TLS, WAF) and writes findings to cloud_findings (CSPM-03)"
    requirement: "CSPM-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_cloud_findings_ingest.py#test_cloudflare_cspm_poll_success"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cloud_findings_ingest.py#test_cloudflare_cspm_poll_missing_config"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cloud_findings_ingest.py#test_cloudflare_cspm_poll_raise_returns_0"
        status: pass
    human_judgment: false
  - id: D4
    description: "Existing 2-arg SIEM poll_oci_cloud_guard_problems / poll_alibaba_sas_alerts / poll_cloudflare_zero_trust_events keep their signature and security_events write target — no regression"
    verification:
      - kind: unit
        ref: "backend/tests/test_cloud_integrations.py (6/6 passing, re-run after this plan's changes)"
        status: pass
      - kind: other
        ref: "grep -c security_events backend/oci_ingest.py backend/alibaba_ingest.py backend/cloudflare_ingest.py — 2 each, unchanged"
        status: pass
    human_judgment: false

# Metrics
duration: ~30min
completed: 2026-07-21
status: complete
---

# Phase 41 Plan 3: OCI/Alibaba/Cloudflare Real CSPM Findings Ingest Summary

**Three account-scoped `poll_*_cspm_findings(config, account_id, tenant_id) -> int` functions added to oci_ingest.py/alibaba_ingest.py/cloudflare_ingest.py, calling real provider SDKs and writing into `cloud_findings` — Alibaba via the V2 typed `alibabacloud_sas20181203` SDK — with the existing 2-arg SIEM `poll_*` functions left byte-for-byte unchanged.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-07-21
- **Tasks:** 3 (all `type="auto" tdd="true"` except Task 3)
- **Files modified:** 4

## Accomplishments
- `poll_oci_cspm_findings` calls the real `oci.cloud_guard.CloudGuardClient.list_problems(compartment_id=...)` (verified against the installed `oci==2.182.0` SDK's actual method signature) and writes parsed problems into `cloud_findings` with `provider="oci"`
- `poll_alibaba_cspm_findings` uses the V2 typed `alibabacloud_sas20181203.Client.list_check_result(...)` (verified against the installed `alibabacloud-sas20181203==9.3.3`/`alibabacloud-tea-openapi==0.4.5` packages' real response model shape) — never touches `aliyunsdkcore.client.AcsClient`
- `poll_cloudflare_cspm_findings` reads three real Cloudflare zone settings (`ssl`, `min_tls_version`, `waf`) via the official `cloudflare==5.5.0` SDK's `client.zones.settings.get(setting_id, zone_id=...)` and flags non-compliant values as FAIL findings
- All three write the exact 13-key `cloud_findings` document shape (`id, tenantId, accountId, timestamp, provider, service, checkId, title, description, severity, status, remediation, raw_message`), verified by dedicated key-set assertions in the new tests
- Existing 2-arg SIEM `poll_oci_cloud_guard_problems`/`poll_alibaba_sas_alerts`/`poll_cloudflare_zero_trust_events` are unmodified — their own 6-test suite (`test_cloud_integrations.py`) still passes 6/6 after this plan's changes
- 20 new/extended hermetic unit tests in `test_cloud_findings_ingest.py` (all passing; no live network/SDK credentials required)

## Task Commits

Each task was committed atomically:

1. **Task 1: OCI and Cloudflare CSPM ingest functions** - `b82f928` (feat)
2. **Task 2: Alibaba CSPM ingest function (V2 typed SDK)** - `af3fc4b` (feat)
3. **Task 3: Unit tests for the three CSPM ingest functions** - `5f7a013` (test)

**Plan metadata:** (this commit)

_Note: implementation and its unit tests were designed together for correctness, then committed in the plan's task order — the test commit (Task 3) depends on the implementation commits (Tasks 1/2) to be green, matching the plan's own file-scope split._

## Files Created/Modified
- `backend/oci_ingest.py` - Added `_make_oci_client_real`, `_parse_oci_cloud_guard_problem`, `poll_oci_cspm_findings`; existing mocked `_make_oci_client`/2-arg `poll_oci_cloud_guard_problems` untouched
- `backend/alibaba_ingest.py` - Added V2 SDK import guard (`_ALIBABA_V2_SDK_AVAILABLE`), `_make_alibaba_v2_client`, `_severity_map_v2`, `_parse_alibaba_check`, `poll_alibaba_cspm_findings`; existing V1 `AcsClient` import/`_make_alibaba_client`/2-arg `poll_alibaba_sas_alerts` untouched
- `backend/cloudflare_ingest.py` - Un-mocked `_make_cloudflare_client` to build a real `cloudflare.Cloudflare(api_token=...)` client (safe for the shared 2-arg SIEM path — verified); added `_cloudflare_setting_is_compliant`, `_parse_cloudflare_setting`, `poll_cloudflare_cspm_findings`
- `backend/tests/test_cloud_findings_ingest.py` - Extended the autouse `mock_get_db` fixture to also patch `oci_ingest`/`alibaba_ingest`/`cloudflare_ingest` `get_database`; added 20 tests total (success/missing-config/raise-returns-0 per new provider, plus an AcsClient-absence assertion for Alibaba)

## Decisions Made
- OCI real client construction genuinely raises `oci.exceptions.InvalidConfig` on non-OCID-shaped placeholder strings (verified live against the installed SDK) — so the plan's literal "un-mock `_make_oci_client`" instruction was adapted to a separate `_make_oci_client_real()` helper to avoid regressing the pre-existing `test_oci_poll_success` (in `test_cloud_integrations.py`), which calls the 2-arg SIEM function with placeholder creds and does not mock client construction. Cloudflare's client construction was verified live to never raise regardless of token content, so `_make_cloudflare_client` WAS safely un-mocked in place as the plan instructed.
- Alibaba's V2 SAS `list_check_result` (per-check `status`/`check_id`/`risk_level`) was chosen over `describe_check_warning_summary` (a risk-category count rollup) as the primary API call, since it maps far more directly onto the plan's required `_parse_alibaba_check` shape (`checkId` from the check id, `status="FAIL"` for failing items).
- New `cf_zone_id` config field introduced for the Cloudflare CSPM path (zone-scoped settings genuinely require a zone id, distinct from the SIEM domain's `cf_account_id`), with a same-value fallback to `cf_account_id` for convenience if a caller only populated that field.
- Alibaba V2 severity mapping added as a new string-keyed `_severity_map_v2()` rather than reusing the existing int-keyed V1 `_severity_map()`, since the V2 SDK's `risk_level` field is a string enum (`serious`/`high`/`medium`/`low`), not the V1 SDK's `1`-`4` int.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] OCI: used a separate real-client helper instead of un-mocking `_make_oci_client()` in place**
- **Found during:** Task 1 (OCI ingest implementation)
- **Issue:** The plan's action text says to "un-mock `_make_oci_client`... to instantiate `oci.cloud_guard.CloudGuardClient(oci_config)`". Verified live against the installed `oci` SDK: constructing `CloudGuardClient` with the exact placeholder OCID/fingerprint strings the pre-existing `test_oci_poll_success` (in `test_cloud_integrations.py`, out of this plan's file scope) uses raises `oci.exceptions.InvalidConfig`. That test calls the still-live 2-arg `poll_oci_cloud_guard_problems` without mocking client construction — un-mocking `_make_oci_client` in place would have made that pre-existing, unrelated test start failing, directly violating the plan's own acceptance criterion ("poll_oci_cloud_guard_problems... unchanged").
- **Fix:** Added a new, separate `_make_oci_client_real(config)` helper used only by the new `poll_oci_cspm_findings`; left `_make_oci_client` and the 2-arg SIEM function completely untouched.
- **Files modified:** `backend/oci_ingest.py`
- **Verification:** `test_cloud_integrations.py` re-run after the change — 6/6 still passing; `test_cloud_findings_ingest.py -k oci` — 6/6 passing.
- **Committed in:** `b82f928` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — Rule 3)
**Impact on plan:** Necessary to satisfy the plan's own explicit acceptance criterion that the SIEM 2-arg functions and their existing tests remain unaffected. No scope creep — Cloudflare's un-mock-in-place was verified safe and executed exactly as the plan specified.

## Issues Encountered
None beyond the OCI deviation above.

## User Setup Required
None - no external service configuration required. (Alibaba V2 SDK packages were already installed by the prerequisite plan 41-02, confirmed present in `backend/requirements.txt` and importable in `backend/venv` before starting this plan.)

## Next Phase Readiness
- All three CSPM poll functions are ready to be wired into `cloud_accounts_service.scan_account()`'s if/elif ladder (Pattern 2 from `41-RESEARCH.md`) — not this plan's scope, tracked separately per `41-PATTERNS.md`.
- Full backend suite re-run after this plan: 1292 passed / 35 skipped / 3 failed — all 3 failures pre-existing and unrelated (`test_agentic_ai.py::test_run_calls_anthropic_with_tool_choice_any`, `test_e2e_integration.py::test_golden_path_evidence_to_remediation`, `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls`), none touching `oci_ingest.py`/`alibaba_ingest.py`/`cloudflare_ingest.py`/`test_cloud_findings_ingest.py`.

---
*Phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare*
*Completed: 2026-07-21*

## Self-Check: PASSED

All created/modified files confirmed present on disk; all 3 task commit hashes (`b82f928`, `af3fc4b`, `5f7a013`) confirmed in `git log --oneline --all`.
