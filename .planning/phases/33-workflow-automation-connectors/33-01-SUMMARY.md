---
phase: 33-workflow-automation-connectors
plan: 01
subsystem: auth
tags: [api-key, sha256, fastapi, webhooks, tenant-isolation]
summary_type: execution
status: completed
requirements: [WF-01, WF-02]

requires:
  - phase: 29-public-trust-center
    provides: non-JWT set_tenant_id precedent for tenant context outside JWT auth
provides:
  - backend/api_key_auth.py — get_current_user_or_api_key dependency (X-API-Key or JWT)
  - keyHash (SHA-256) field written by generate_api_key on tenants.apiKeys[]
  - api-integration narrow role for machine credentials (not in SUPER_ROLES)
  - four webhook routes (list/create/delete/deliveries) accept the API-key path
affects: [33-02-webhook-signing, 33-03-n8n-node, 33-04-zapier-app]

tech-stack:
  added: []
  patterns: [compositional alternative-auth dependency mirroring get_optional_user, hash-at-rest equality lookup on apiKeys.keyHash]

key-files:
  created:
    - backend/tests/test_api_key_auth.py
  modified:
    - backend/api_key_auth.py (pre-existing stub from prior session, verified as-is)
    - backend/tenant_endpoints.py (keyHash on key_doc)
    - backend/webhook_endpoints.py (4 routes swapped to get_current_user_or_api_key)

key-decisions:
  - "No backfill of pre-existing keys — keys created before keyHash cannot authenticate (Pitfall 1, accepted)"
  - "update_webhook/test_webhook/inbound provider hooks stay on get_current_user — connectors only need the subscribe/list lifecycle in v1"
  - "Revoked-flag check added on the matched apiKeys.$ element → 401"

patterns-established:
  - "Machine credentials get the literal 'api-integration' role, provably outside SUPER_ROLES, so every _WEBHOOK_SUPER_ROLES branch resolves tenant-scoped"
---

# Plan 33-01 Summary — API-Key Auth Path (WF-01/WF-02 prerequisite)

## What was built

- `generate_api_key` now persists `keyHash = sha256(plaintext)` alongside the display prefix; plaintext still returned exactly once and never stored recoverably (T-33-KEY).
- `backend/api_key_auth.py` (found as an untested stub from the paused session, verified correct): valid `X-API-Key` → hash lookup on `tenants.apiKeys.keyHash` → `set_tenant_id(tenant)` → `TokenData(role="api-integration", username="api-key")`; wrong/revoked/absent → 401; JWT path delegates to `verify_token_async` unchanged.
- `webhook_endpoints.py`: exactly `get_webhooks`, `create_webhook`, `delete_webhook`, `get_webhook_deliveries` swapped to `Depends(get_current_user_or_api_key)`; SSRF guard and `_WEBHOOK_SUPER_ROLES` branches untouched.

## Verification

- `venv/bin/python -m pytest tests/test_api_key_auth.py -q` — **12 passed** (hash_verify, dependency incl. revoked/JWT-delegation/role-not-super, webhook_route tenant-scoping incl. update-route-unchanged guard).
