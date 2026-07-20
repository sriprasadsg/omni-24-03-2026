---
phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare
plan: 04
subsystem: ui
tags: [react, typescript, cspm, cloud-accounts, credentials]

# Dependency graph
requires:
  - phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare (plan 41-03)
    provides: "poll_oci_cspm_findings / poll_alibaba_cspm_findings / poll_cloudflare_cspm_findings reading the exact config keys this plan's credentials object now supplies (oci_tenancy_ocid, oci_user_ocid, oci_fingerprint, oci_private_key, access_key_id, access_key_secret, region_id, cf_api_token, cf_account_id)"
provides:
  - "Fixed addCloudAccount() payload — account_name + credentials_ref JSON string, matching backend register_account contract"
  - "Provider-conditional credential fields in AddCloudAccountModal for OCI/Alibaba/Cloudflare, wired into onSave"
  - "SIMULATED badge in CloudChecksScanner results table driven by result.simulated"
  - "oci/alibaba/cloudflare added to CloudChecksScanner's PROVIDER_ICONS and both provider arrays"
affects: [41-05, cloud-accounts-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Provider-conditional credential fieldset branching on the CloudProvider union value, building a flat Record<string,string> keyed by the exact backend config.get() field names before JSON.stringify"

key-files:
  created: []
  modified:
    - services/apiService.ts
    - components/AddCloudAccountModal.tsx
    - components/CloudChecksScanner.tsx

key-decisions:
  - "AddCloudAccountModalProps.onSave widened to accept an optional credentials?: Record<string,string> field via intersection type, rather than adding credentials to the shared CloudAccount type (credentials are transient input, never a stored/read account field)"
  - "Credential object keys chosen to match the exact config.get(...) keys already read by backend/oci_ingest.py, backend/alibaba_ingest.py, backend/cloudflare_ingest.py's required_fields lists (verified by reading those files directly, not assumed from the pattern doc)"

patterns-established: []

requirements-completed: [CSPM-01, CSPM-02, CSPM-03]

# Metrics
duration: 12min
completed: 2026-07-21
status: complete
---

# Phase 41 Plan 4: CSPM Credential Round-Trip Fix + SIMULATED Badge Summary

**Fixed the addCloudAccount name/credentials field-mapping bug that silently discarded every stored credential, added OCI/Alibaba/Cloudflare-specific credential inputs to the connect-account modal, and surfaced the backend's existing `simulated` flag with a SIMULATED badge plus the three new providers in the Cloud Checks dashboard.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2 code tasks completed + 1 documentation-only task (end-of-phase manual verification, no code change)
- **Files modified:** 3

## Accomplishments
- `addCloudAccount()` now sends `account_name` and a `credentials_ref` JSON string instead of `name`/`credentials`, matching `cloud_accounts_service.register_account()`'s read contract — previously every account ever created through this form stored no usable credentials, for any provider
- `AddCloudAccountModal.tsx` renders provider-specific credential fields (OCI: tenancy OCID/user OCID/fingerprint/private key; Alibaba: access key id/secret/region id; Cloudflare: API token/account id) and assembles them into a `credentials` object passed through `onSave` — the modal previously never collected credentials into `onSave` at all
- `CloudChecksScanner.tsx` renders a SIMULATED badge on results where `result.simulated` is true, and includes `oci`/`alibaba`/`cloudflare` in `PROVIDER_ICONS` and both provider filter/tile arrays

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix addCloudAccount payload + provider-conditional credential fields** - `7474c74` (fix)
2. **Task 2: SIMULATED badge + provider maps in CloudChecksScanner** - `a1abd4e` (feat)
3. **Task 3: End-of-phase human verification of credential round-trip and SIMULATED badge** - no commit (documentation-only, no code change; see "Deferred Manual Verification" below)

## Files Created/Modified
- `services/apiService.ts` - `addCloudAccount` POST body keys corrected to `account_name` + `credentials_ref` (JSON string)
- `components/AddCloudAccountModal.tsx` - provider-conditional credential fieldset (OCI/Alibaba/Cloudflare/generic), `buildCredentials()` helper, `handleSubmit` now passes `credentials` into `onSave`, `onSave` prop type widened to accept it
- `components/CloudChecksScanner.tsx` - `simulated?: boolean` on `CheckResult`, SIMULATED badge in results table, `oci`/`alibaba`/`cloudflare` added to `PROVIDER_ICONS` and both `['aws','azure','gcp']` arrays

## Decisions Made
- Credential field keys (`oci_tenancy_ocid`, `oci_user_ocid`, `oci_fingerprint`, `oci_private_key`, `access_key_id`, `access_key_secret`, `region_id`, `cf_api_token`, `cf_account_id`) were taken directly from the `required_fields` lists already present in `backend/oci_ingest.py`, `backend/alibaba_ingest.py`, `backend/cloudflare_ingest.py` — read directly rather than trusting the pattern doc's paraphrase, so the frontend form and the backend ingest guards use identical key names even before plan 41-03's CSPM poll functions exist.
- `AddCloudAccountModalProps.onSave`'s parameter type was widened with `& { credentials?: Record<string, string> }` rather than adding `credentials` to the shared `CloudAccount` type in `types.ts` — credentials are write-only transient input, never part of the stored/rendered `CloudAccount` shape, and the existing `CloudSecurityDashboard.tsx::handleSaveAccount` (typed as `Omit<CloudAccount, 'id'|'tenantId'|'status'>`) remains structurally assignable to the widened prop under TypeScript's contravariant function-parameter check with no additional changes required.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## Deferred Manual Verification

Task 3 is documentation-only per the plan (`human_verify_mode = end-of-phase`, not a blocking checkpoint). Two manual gates remain outstanding, to be exercised once phase 41 is fully executed (per `41-VALIDATION.md`'s Manual-Only Verifications table):
1. Add a new OCI/Alibaba/Cloudflare account via the UI form and confirm in Mongo that the new `cloud_accounts` doc has a non-empty encrypted `credentials_ref`.
2. Trigger a scan for that account, load the Cloud Checks dashboard, and confirm the SIMULATED badge is visible wherever `result.simulated` is true for a fresh account with no imported findings.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The credential round-trip is now correct for all three new providers, and the frontend is ready to consume plan 41-03's `poll_oci_cspm_findings`/`poll_alibaba_cspm_findings`/`poll_cloudflare_cspm_findings` once those exist (same config key names on both sides).
- Plan 41-05 (test coverage for `cloud_accounts_service.py`'s provider ladder) and the still-outstanding plan 41-03 (CSPM ingest functions) are unaffected by this plan's scope; no blockers introduced.
- End-of-phase manual verification (credential storage confirmation, SIMULATED badge visual check) remains outstanding until the full phase is executed and a live backend/frontend session is available.

---
*Phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare*
*Completed: 2026-07-21*
