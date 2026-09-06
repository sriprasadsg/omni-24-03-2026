---
audit_acknowledged:
  milestone: v4.1
  at: 2026-08-26
  gap_snapshot: "unknown::scenarios=0"
---

# UAT Report: Phase 33 — Workflow Automation Connectors

## Overview

Validation of API-key authentication, HMAC webhook signing, and the n8n/Zapier connector packages against the must-have truths in plans 33-01..33-04. All artifacts verified present in git (commits 64acf247, 032fd4d1, 0cb6a8dd) — not taken on faith from summaries.

## Test Cases

| ID | Description | Result | Notes |
|----|-------------|--------|-------|
| 1 | API key stored as SHA-256 hash only (never recoverable) | Pass | `test_api_key_auth.py` (12/12, 2026-07-14) |
| 2 | X-API-Key auth resolves tenant on /api/webhooks GET/POST/DELETE + deliveries | Pass | `test_api_key_auth.py` |
| 3 | API-key requests carry narrow `api-integration` role, tenant-scoped | Pass | `test_api_key_auth.py` |
| 4 | Wrong / revoked / missing key rejected with 401 | Pass | `test_api_key_auth.py` |
| 5 | Outbound webhook with secret carries `X-Webhook-Signature: sha256=<hmac>` over exact wire bytes | Pass | `test_webhook_signing.py` (2/2, 2026-07-14) |
| 6 | Webhook without secret still delivers, no signature header, no error | Pass | `test_webhook_signing.py` |
| 7 | n8n community-node package compiles clean | Pass | `npx tsc --noEmit` clean 2026-07-14; eslint/build clean per commit 0cb6a8dd |
| 8 | Zapier CLI app offline tests (subscribe/unsubscribe/list/perform) | Pass | `npm test` 4/4 (2026-07-14), mocked HTTP, no live account |
| 9 | Live round trip: X-API-Key subscribe → real signed HTTP delivery → HMAC verified at receiver → delivery listed → unsubscribe | Pass | Full stack 2026-07-14: API key minted via POST /api/tenants/{id}/api-keys; webhook created/listed/deleted with X-API-Key only; wrong key 401; real dispatch via `WebhookService.trigger_webhook` delivered over HTTP to local receiver; receiver's independent `HMAC-SHA256(raw body, secret)` matched `X-Webhook-Signature` byte-for-byte; delivery visible in GET /{id}/deliveries. 3 defects found and fixed (see below) |

## Defects Found and Fixed (2026-07-14 live UAT)

1. `webhook_endpoints.py` create_webhook: motor mutated the response dict with ObjectId `_id` → 500 after insert; subscriber never received id/secret. Fixed (insert a copy).
2. `webhook_service.py` success branch: duplicate `"$set"` key in update dict — `lastResult` was never persisted on successful deliveries. Fixed (merged into one `$set`).
3. `webhook_service.py`: real dispatches were never recorded to `webhook_deliveries` (only test pings) — GET /deliveries and Zapier `performList` always empty. Fixed (dispatch now records deliveries).

Also verified: SSRF guard on webhook creation DNS-resolves the target and rejects loopback/private addresses (fail-closed).

## Verification Gaps

- Optional only: round trip against a hosted n8n instance / real Zapier account (external SaaS accounts). The wire contract those connectors depend on (X-API-Key auth, REST subscribe/unsubscribe/list, exact-byte HMAC signature) is now verified live.

## Test Run

- `backend/tests/test_api_key_auth.py` — 12 passed (2026-07-14)
- `backend/tests/test_webhook_signing.py` — 2 passed (2026-07-14)
- `integrations/zapier-omniagent` — `npm test` 4 passing (2026-07-14)
- `integrations/n8n-nodes-omniagent` — `npx tsc --noEmit` clean (2026-07-14)
