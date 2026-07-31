---
phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare
plan: 01
subsystem: cspm
tags: [cloud-checks, oci, alibaba, cloudflare, cis-benchmark, security-posture]

# Dependency graph
requires: []
provides:
  - "OCI_CHECKS (10 entries, CIS OCI Foundations-aligned) in backend/cloud_checks_oci.py"
  - "ALIBABA_CHECKS (9 entries, Alibaba Config/Security Center-aligned) in backend/cloud_checks_alibaba.py"
  - "CLOUDFLARE_CHECKS (10 entries, Security Center taxonomy-aligned) in backend/cloud_checks_cloudflare.py"
  - "run_checks() evaluates oci/alibaba/cloudflare providers (RUNNABLE_PROVIDERS widened)"
  - "CSPM coverage denominator (_RUNNABLE_CHECKS_COUNT) and get_summary byProvider now include the 3 new providers"
affects: [41-02, 41-03, cloud_accounts_service, mcp_server]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Flat-dict check-definition catalog module (id/name/description/provider/service/severity/frameworks/remediation), matching cloud_checks_aws.py exactly"

key-files:
  created:
    - backend/cloud_checks_oci.py
    - backend/cloud_checks_alibaba.py
    - backend/cloud_checks_cloudflare.py
  modified:
    - backend/cloud_checks_service.py
    - backend/tests/test_cloud_checks_expansion.py
    - backend/mcp_server.py
    - backend/tests/test_mcp_server.py

key-decisions:
  - "service category for all 29 new checks (OCI 10 + Alibaba 9 + Cloudflare 10) drawn strictly from the D-03-mandated shared set {iam, storage, encryption, logging} per plan spec, not each provider's native category vocabulary"
  - "frameworks tags use CIS-OCI-x.y for OCI, ALIBABA-Config-*/ALIBABA-SAS-*/CIS-Alibaba-x.y for Alibaba, CF-SecurityCenter-<topic> for Cloudflare, matching the plan's naming contract"

patterns-established:
  - "New CSPM provider catalog = single flat-dict-list module cloned from cloud_checks_aws.py, wired into cloud_checks_service.py via 1 import + 1 CLOUD_CHECKS append + 1 RUNNABLE_PROVIDERS append — no other file needs to change since cloud_account_endpoints.py's _VALID_PROVIDERS and mcp_server.py's run_cloud_check both already read/derive from the same generic sources"

requirements-completed: [CSPM-01, CSPM-02, CSPM-03]

# Metrics
duration: 20min
completed: 2026-07-20
status: complete
---

# Phase 41 Plan 01: CSPM Provider Expansion (OCI, Alibaba, Cloudflare) Summary

**Three new CIS/Security-Center-aligned check catalogs (OCI, Alibaba, Cloudflare — 29 checks total) wired into the single `RUNNABLE_PROVIDERS` gate so `run_checks()` actually evaluates them and their results count toward CSPM coverage.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-20
- **Tasks:** 3/3
- **Files modified:** 7 (3 created, 4 modified)

## Accomplishments
- `backend/cloud_checks_oci.py` — `OCI_CHECKS` (10 entries: 4 iam, 2 storage, 2 encryption, 2 logging), CIS OCI Foundations-aligned
- `backend/cloud_checks_alibaba.py` — `ALIBABA_CHECKS` (9 entries: 3 iam, 2 storage, 2 encryption, 2 logging), Alibaba Cloud Config/Security Center baseline-aligned
- `backend/cloud_checks_cloudflare.py` — `CLOUDFLARE_CHECKS` (10 entries: 2 iam, 2 storage, 4 encryption, 2 logging), Security Center taxonomy-aligned
- `cloud_checks_service.py`: 3 new imports, `CLOUD_CHECKS` extended (now 364 total checks), `RUNNABLE_PROVIDERS` widened to include `"oci"`, `"alibaba"`, `"cloudflare"` — this is the single load-bearing gate that makes `run_checks()` actually evaluate the new providers and contributes their results to the CSPM coverage denominator (D-05)
- `test_cloud_checks_expansion.py`: added `test_run_checks_evaluates_oci/alibaba/cloudflare`; repaired the now-inverted `test_registration_gates_accept_oci_alibaba_cloudflare` (renamed to `..._now_runnable`, assertions flipped to `in RUNNABLE_PROVIDERS`)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create OCI and Cloudflare check-definition catalogs** - `5ecb1c0` (feat)
2. **Task 2: Create Alibaba check-definition catalog** - `0081866` (feat)
3. **Task 3: Wire catalogs into cloud_checks_service and extend/repair expansion tests** - `6e68075` (feat)

_Note: Task 3's commit also includes the mcp_server.py deviation fix described below (same task, same file-scope class of change)._

## Files Created/Modified
- `backend/cloud_checks_oci.py` - `OCI_CHECKS` list (10 entries)
- `backend/cloud_checks_alibaba.py` - `ALIBABA_CHECKS` list (9 entries)
- `backend/cloud_checks_cloudflare.py` - `CLOUDFLARE_CHECKS` list (10 entries)
- `backend/cloud_checks_service.py` - 3 imports added; `CLOUD_CHECKS` and `RUNNABLE_PROVIDERS` extended
- `backend/tests/test_cloud_checks_expansion.py` - 3 new provider tests; 1 inverted gate test repaired
- `backend/mcp_server.py` - stale docstring on `run_cloud_check` corrected (Rule 1)
- `backend/tests/test_mcp_server.py` - stale rejection test rewritten to assert delegation (Rule 1)

## Decisions Made
- `service` category for every new check (all 29) is one of the D-03-mandated shared set `{iam, storage, encryption, logging}` per the plan's explicit instruction, not each cloud's native taxonomy (e.g. OCI's "Identity", Cloudflare's "SSL/TLS") — this keeps `byService` aggregation consistent across all providers in `get_summary()`.
- `frameworks` tags: `CIS-OCI-x.y` for OCI, a mix of `CIS-Alibaba-x.y` / `ALIBABA-Config-*` / `ALIBABA-SAS-*` for Alibaba (matching the plan's stated naming options), `CF-SecurityCenter-<topic>` for Cloudflare.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed stale MCP `run_cloud_check` rejection test and docstring**
- **Found during:** Task 3 verification (full-suite regression pass, not part of the plan's declared `<verify>` command but caught via the standard task-commit protocol's post-change regression check)
- **Issue:** `backend/mcp_server.py::run_cloud_check` derives its accepted-provider set directly from `cloud_checks_service.RUNNABLE_PROVIDERS` ("the accepted set is the single source of truth in cloud_checks_service" per its own docstring). Widening `RUNNABLE_PROVIDERS` in Task 3 to include oci/alibaba/cloudflare made the pre-existing `tests/test_mcp_server.py::test_run_cloud_check_rejects_ingest_only_providers` fail — it asserted the now-obsolete claim that these three providers must be rejected with a 400. The docstring's "OCI/Alibaba/Cloudflare are ingest-only... not valid here" comment was also now factually wrong.
- **Fix:** Updated the `run_cloud_check` docstring to drop the stale ingest-only claim (kept the accurate "single source of truth" statement). Rewrote the test as `test_run_cloud_check_delegates_for_oci_alibaba_cloudflare`, asserting the tool now delegates to `cloud_checks_service.run_checks(account_id, provider, tenant_id)` for all three providers, mirroring the existing `test_run_cloud_check_delegates_to_service` pattern for `"aws"`.
- **Files modified:** `backend/mcp_server.py`, `backend/tests/test_mcp_server.py`
- **Verification:** `venv/bin/python -m pytest tests/test_mcp_server.py tests/test_cloud_checks_expansion.py tests/test_cloud_accounts.py tests/test_dead_endpoints_closure.py -q` → 52 passed.
- **Committed in:** `6e68075` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug fix)
**Impact on plan:** Directly caused by and in-scope of Task 3's core change (widening `RUNNABLE_PROVIDERS`); no scope creep — no other file was touched.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required. (Real-scanner ingest for these providers — un-mocking `oci_ingest.py`/`alibaba_ingest.py`/`cloudflare_ingest.py`'s `poll_*_cspm_findings` — is out of this plan's scope per the phase's remaining plans.)

## Next Phase Readiness
- `run_checks()` now evaluates oci/alibaba/cloudflare end-to-end against whatever `cloud_findings` documents exist for an account (currently none until ingest is wired — checks will PASS with `simulated: true` until a later plan un-mocks the `*_ingest.py` poll functions, per `41-PATTERNS.md`).
- Full regression pass: 1282 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai.py::TestRunCallsAnthropicWithToolChoiceAny`, `test_e2e_integration.py::test_golden_path_evidence_to_remediation`, `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls` — all reproduce on unrelated files, none touch this plan's file scope).
- Ready for the phase's next plan(s) (ingest wiring / `cloud_accounts_service.py` `scan_account()` ladder / frontend provider-map updates) per `41-PATTERNS.md`.

---
*Phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare*
*Completed: 2026-07-20*

## Self-Check: PASSED

All created files and commit hashes verified present in the working tree / git log.
