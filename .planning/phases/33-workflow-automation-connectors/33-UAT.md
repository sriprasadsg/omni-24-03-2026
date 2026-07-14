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
| 9 | End-to-end against live n8n instance and Zapier account | Pending | Human verification — needs real n8n install + Zapier developer account |

## Verification Gaps
- Item 9 only: live-connector round trip (subscribe from real n8n/Zapier, receive a signed GRC event, verify HMAC on the receiving side). All automated coverage passes.

## Test Run
- `backend/tests/test_api_key_auth.py` — 12 passed (2026-07-14)
- `backend/tests/test_webhook_signing.py` — 2 passed (2026-07-14)
- `integrations/zapier-omniagent` — `npm test` 4 passing (2026-07-14)
- `integrations/n8n-nodes-omniagent` — `npx tsc --noEmit` clean (2026-07-14)
