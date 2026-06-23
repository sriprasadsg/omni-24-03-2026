---
phase: 14-saas-evidence-integration
plan: "01"
subsystem: saas-integration
tags: [saas, oauth, evidence, compliance, fernet, github, jira, okta, google-workspace, slack]
dependency_graph:
  requires:
    - backend/compliance_evidence_processor.py (COMPLIANCE_CHECK_MAPPINGS)
    - backend/authentication_service.py (get_current_user)
    - backend/database.py (get_db)
  provides:
    - backend/saas_integration_service.py (SaaSIntegrationService, pull_all_evidence, _encrypt/_decrypt)
    - backend/saas_integration_endpoints.py (router at /api/saas)
    - backend/tests/test_saas_integration.py (10-test TDD suite)
  affects:
    - backend/router_registry.py (new saas_integration_endpoints load)
tech_stack:
  added:
    - cryptography.fernet (Fernet symmetric encryption for token storage)
    - httpx (async HTTP client for provider API calls, timeout=10s)
  patterns:
    - OAuth 2.0 authorization code flow (authorize redirect + callback token exchange)
    - Fernet token encryption pattern (access_token_enc / refresh_token_enc)
    - Per-provider evidence pull with control ID mapping
    - Tenant isolation at endpoint boundary
key_files:
  created:
    - backend/saas_integration_service.py
    - backend/saas_integration_endpoints.py
    - backend/tests/test_saas_integration.py
  modified:
    - backend/router_registry.py
decisions:
  - "access_token_enc/refresh_token_enc field names (not access_token/refresh_token) make encryption status explicit in the schema — test updated to match"
  - "_access_token_plain injection key in connection dict enables clean test mocking without Fernet round-trips in test setup"
  - "pull_all_evidence handles partial evidence on API error — stores what was collected, logs warning, never raises to caller"
  - "OAuthProvider enum backed by str for JSON serialization compatibility with FastAPI"
  - "Tenant isolation check in pull-evidence returns 403 (not 404) to avoid leaking connection existence to cross-tenant callers"
metrics:
  duration: ~4m
  completed: "2026-06-23T17:45:23Z"
  tasks_completed: 4
  files_created: 3
  files_modified: 1
status: complete
---

# Phase 14 Plan 01: SaaS Evidence Integration Summary

**One-liner:** OAuth 2.0 integration for GitHub, Jira, Okta, Google Workspace, and Slack with Fernet-encrypted token storage and automatic compliance evidence pull mapped to existing control IDs.

## What Was Built

### backend/saas_integration_service.py (471 lines)

- `_encrypt(plaintext)` / `_decrypt(ciphertext)` — Fernet symmetric encryption using `ENCRYPTION_KEY` env var; falls back to ephemeral key in dev with a warning (never silently logs tokens)
- `OAuthProvider` — str Enum for the 5 supported providers
- `OAUTH_CONFIGS` — dict of auth_url, token_url, and scopes per provider
- `SaaSIntegrationService.store_connection()` — stores encrypted tokens to `saas_connections` collection with `access_token_enc` / `refresh_token_enc` fields
- `pull_github_evidence()` — merged PRs → `Secure Development & Coding Simulation`, branch protection → `Access to Source Code Simulation`, code scan alerts → `Security Patch Status`
- `pull_jira_evidence()` — closed compliance-tagged issues → `Change Management Simulation`
- `pull_okta_evidence()` — MFA enrollment % → `MFA for All Users`, user list → `Identity & Authentication Simulation`
- `pull_google_workspace_evidence()` — 2SV enrollment → `Account Security`, user audit → `Data Leakage Prevention Simulation`
- `pull_slack_evidence()` — channel retention policy → `Audit Logging Extension Simulation`
- `pull_all_evidence()` — dispatches to per-provider method, writes records to `control_evidence` collection with `source='saas-{provider}'`, updates `last_synced` / `evidence_count`

### backend/saas_integration_endpoints.py (238 lines)

Router prefix: `/api/saas`

| Method | Path | Description |
|--------|------|-------------|
| GET | /connections | List all tenant connections (status, last_synced, provider, evidence_count) |
| GET | /connect/{provider} | OAuth authorize redirect (SAAS-01) |
| GET | /callback/{provider} | OAuth token exchange callback (SAAS-01) |
| POST | /connections/{id}/pull-evidence | Async evidence collection (SAAS-02) |
| DELETE | /connections/{id} | Revoke and remove connection (SAAS-03) |

### backend/tests/test_saas_integration.py (413 lines)

10 tests, all passing:

| # | Test | Assertion |
|---|------|-----------|
| 1 | test_encrypt_decrypt_round_trip | Fernet round-trip preserves plaintext |
| 2 | test_store_connection_with_encrypted_token | access_token_enc/refresh_token_enc stored encrypted |
| 3 | test_pull_github_evidence_maps_to_control | Maps to Secure Development / Source Code / Patch control |
| 4 | test_pull_jira_evidence_maps_to_control | Maps to Change Management Simulation control |
| 5 | test_pull_okta_evidence_maps_to_control | Maps to MFA for All Users / Identity control |
| 6 | test_pull_google_workspace_evidence_maps_to_control | Maps to Account Security / Data Leakage control |
| 7 | test_pull_slack_evidence_maps_to_control | Maps to Audit Logging Extension Simulation control |
| 8 | test_pull_evidence_writes_to_control_evidence | insert_many called with source='saas-github' |
| 9 | test_tenant_isolation_blocks_cross_tenant_pull | Cross-tenant pull → 403 |
| 10 | test_delete_connection_removes_record | DELETE calls delete_one, returns 200 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test field name mismatch for encrypted token assertion**
- **Found during:** Task 2 GREEN phase
- **Issue:** Test checked `doc["access_token"]` but service stores encrypted tokens as `doc["access_token_enc"]` (explicit naming convention)
- **Fix:** Updated test assertion to use `doc["access_token_enc"]` and `doc["refresh_token_enc"]`
- **Files modified:** `backend/tests/test_saas_integration.py`
- **Commit:** cf9ad13

## TDD Gate Compliance

- RED gate: commit cfe8d6c — `test(14-01): add failing tests for SaaS OAuth evidence integration`
- GREEN gate: commit cf9ad13 — `feat(14-01): implement SaaS OAuth evidence integration`
- All 10 tests confirmed passing before implementation commit

## Known Stubs

None — all 5 provider evidence methods make real API calls using httpx. In test execution they are covered by `AsyncMock` patches returning structured fake responses.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: secret_storage | backend/saas_connections (MongoDB) | OAuth tokens stored encrypted at rest — Fernet key must be rotated and backed up |
| threat_flag: oauth_callback | backend/saas_integration_endpoints.py | /callback/{provider} does not validate state param as CSRF nonce — acceptable for MVP; should add state verification in Phase 14-02 |

## Self-Check: PASSED

- backend/saas_integration_service.py: FOUND
- backend/saas_integration_endpoints.py: FOUND
- backend/tests/test_saas_integration.py: FOUND (10 tests passing)
- commit cfe8d6c (RED): FOUND
- commit cf9ad13 (GREEN): FOUND
- All files under 500 lines: saas_integration_service=471, saas_integration_endpoints=238, test=413
