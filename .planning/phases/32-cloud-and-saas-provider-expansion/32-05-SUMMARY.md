---
phase: 32-cloud-and-saas-provider-expansion
plan: 05
subsystem: cloud-providers
tags: [m365, mongodb-atlas, ingest, cloud-findings, prov-02]
requires: [32-02]
provides: [m365_ingest, mongodb_atlas_ingest, scan_account_dispatch]
affects: [cloud_findings, cloud_check_results]
tech-stack:
  added: [msal, requests.auth.HTTPDigestAuth]
  patterns: [azure_defender_ingest never-raise contract, cloud_findings sink, digest-auth via stdlib requests]
key-files:
  created:
    - backend/m365_ingest.py
    - backend/mongodb_atlas_ingest.py
    - backend/tests/test_cloud_findings_ingest.py
  modified:
    - backend/cloud_accounts_service.py
decisions:
  - "M365/Atlas write to cloud_findings (not security_events) keyed by accountId+tenantId — first real writers"
  - "scan_account() dispatches ingest before run_checks so simulated flag flips to false"
  - "Atlas uses requests.auth.HTTPDigestAuth — zero new deps"
metrics:
  duration: ~1h
  completed: 2026-07-11
  tasks: 2
  files: 4
status: complete
---

# Phase 32 Plan 05: M365 and MongoDB Atlas Real-Findings Ingest Summary

M365 Secure Scores poll via msal+httpx and MongoDB Atlas Admin API poll via requests.auth.HTTPDigestAuth; both write to cloud_findings keyed by accountId+tenantId. scan_account() dispatches to matching ingest before run_checks(), flipping simulated=false.

## What Was Built

### backend/m365_ingest.py
- `poll_m365_secure_scores(config, account_id, tenant_id) -> int`
- msal ConfidentialClientApplication for client-credentials auth
- httpx GET to Microsoft Graph /security/secureScores
- Maps controlScores into cloud_findings docs (accountId, tenantId, severity high/medium, title, checkId, provider=microsoft365, ingested_at)
- try/except Exception: log + return 0 (never raises — T-32-07)

### backend/mongodb_atlas_ingest.py
- `poll_mongodb_atlas_findings(config, account_id, tenant_id) -> int`
- `_atlas_get_sync(url, public_key, private_key)` using `requests.auth.HTTPDigestAuth` (zero new deps)
- `asyncio.to_thread()` to run sync requests call in async context
- Maps insecure cluster settings into cloud_findings docs
- Same never-raise try/except contract

### backend/cloud_accounts_service.py (modified)
- scan_account() now dispatches: if provider=="microsoft365" -> poll_m365_secure_scores; if provider=="mongodb_atlas" -> poll_mongodb_atlas_findings
- Ingest runs BEFORE run_checks() so findings are present for evaluation
- Credentials decrypted via existing _decrypt() (no fourth Fernet scheme — T-32-08)
- config parse failure treated as empty dict so ingest's all([...]) gate returns 0
- Existing providers (aws/etc.) untouched — no ingest call

### backend/tests/test_cloud_findings_ingest.py
- Happy path: M365 with mocked msal+httpx returns 1 finding
- Happy path: Atlas with mocked _atlas_get_sync returns 1 finding
- Missing config: both return 0 without API call
- Raising client: both return 0 without propagating (T-32-07)
- scan_account dispatch: verifies mock_ingest called with correct config, mock_run_checks called

## Deviations from Plan

### [Rule 1 - Bug] Fixed hardcoded timestamp in m365_ingest.py
- **Found during:** Task 1
- **Issue:** `ingested_at` was hardcoded to "2026-07-10T12:00:00Z"
- **Fix:** Replaced with `datetime.now(timezone.utc).isoformat()`
- **Files modified:** backend/m365_ingest.py

## Self-Check: PASSED

- backend/m365_ingest.py: FOUND
- backend/mongodb_atlas_ingest.py: FOUND
- backend/tests/test_cloud_findings_ingest.py: FOUND
- backend/cloud_accounts_service.py scan_account() dispatch: FOUND (lines 111-122)
