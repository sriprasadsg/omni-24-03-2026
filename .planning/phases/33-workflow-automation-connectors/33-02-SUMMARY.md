---
phase: 33-workflow-automation-connectors
plan: 02
subsystem: api
tags: [hmac, sha256, webhooks, httpx, signing]
summary_type: execution
status: completed
requirements: [WF-01, WF-02]

requires:
  - phase: 33-workflow-automation-connectors
    provides: plan 33-01 API-key auth path (same wave, independent)
provides:
  - HMAC-SHA256 X-Webhook-Signature header on every outbound generic webhook delivery with a secret
  - exact-wire-bytes signing (json.dumps body passed to content=)
affects: [33-03-n8n-node, 33-04-zapier-app]

tech-stack:
  added: []
  patterns: [sign the same json.dumps string sent via content= — never httpx json= (T-33-BYTES)]

key-files:
  created:
    - backend/tests/test_webhook_signing.py
  modified:
    - backend/webhook_service.py

key-decisions:
  - "Hooks without a secret still deliver unsigned (additive, backward-compatible)"
  - "Signing pattern cloned from ticket_webhook_service.py for consistency"

patterns-established:
  - "X-Webhook-Signature: sha256=<hmac(secret, exact body bytes)> on generic webhook deliveries"
---

# Plan 33-02 Summary — Outbound Webhook HMAC Signing

## What was built

- `webhook_service.py::_send_single_webhook` now serializes the payload once (`body = json.dumps(payload)`), signs it with the hook's stored `whsec_...` secret when present (`X-Webhook-Signature: sha256=<hmac>`), and sends the identical string via `content=body`. Delivery tracking (`lastResult`, `failureCount`) and the SSRF guard are untouched.
- `backend/tests/test_webhook_signing.py` — TDD RED→GREEN: exact-bytes signature assertion (HMAC computed independently over the captured `content=` kwarg) and no-secret backward-compat case.

## Verification

- `venv/bin/python -m pytest tests/test_webhook_signing.py tests/test_api_key_auth.py -q` — **14 passed**.
