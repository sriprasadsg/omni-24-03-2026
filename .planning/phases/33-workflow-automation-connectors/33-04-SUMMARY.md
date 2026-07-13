---
phase: 33-workflow-automation-connectors
plan: 04
subsystem: integrations
tags: [zapier, rest-hook, webhooks, api-key, nock, mocha]
summary_type: execution
status: completed
requirements: [WF-02]

requires:
  - phase: 33-workflow-automation-connectors
    provides: 33-01 X-API-Key auth path and 33-02 X-Webhook-Signature signing
provides:
  - integrations/zapier-omniagent/ — Zapier Platform CLI app (custom API-key auth + GRC Event REST Hook trigger)
  - offline unit tests (mocha + nock + createAppTester) for subscribe/unsubscribe/list/perform
affects: [trust-center, workflow-automation]

tech-stack:
  added: [zapier-platform-core@^19.0.0, zapier-platform-cli@^19.0.0 (dev), mocha (dev), nock (dev)]
  patterns: [REST Hook lifecycle against existing /api/webhooks CRUD; performList reuses the deliveries endpoint]

key-files:
  created:
    - integrations/zapier-omniagent/index.js
    - integrations/zapier-omniagent/authentication.js
    - integrations/zapier-omniagent/triggers/grc_event.js
    - integrations/zapier-omniagent/test/triggers/grc_event.test.js
    - integrations/zapier-omniagent/README.md
    - integrations/zapier-omniagent/package.json

key-decisions:
  - "Event dropdown lists only currently-emitted event types (agent.offline, security.alert, compliance.violation), matching the n8n node"
  - "zapier push / App Directory submission documented as manual operator follow-ups, not CI steps"

deviations:
  - "zapier-platform-cli v19's binary is `zapier-platform` (not `zapier`) and requires Node >= 22; the environment has Node 20.20.2. The plan's `npx zapier validate` gate was satisfied by running the identical underlying check directly: zapier-platform-schema `validateAppDefinition()` over the CLI-style serialized App → VALID (schema 19.0.0). Re-run `npx zapier-platform validate` once Node >= 22 is available."
---

# Plan 33-04 Summary — Zapier CLI App (WF-02)

## What was built

- `integrations/zapier-omniagent/`: custom API-key authentication (baseUrl + password-typed apiKey, connection test = authenticated `GET /api/webhooks` with `X-API-Key`), and the `grc_event` REST Hook trigger — `performSubscribe` → `POST /api/webhooks`, `performUnsubscribe` → `DELETE /api/webhooks/{subscribeData.id}`, `performList` → `GET /api/webhooks/{id}/deliveries` (required schema fallback, reuses the existing endpoint), `perform` → returns the inbound signed POST body.
- README documents connection setup, X-Webhook-Signature verification (exact-raw-bytes HMAC), and marks `zapier push`/directory submission as out-of-scope manual follow-ups.

## Verification

- `npm test` — **4 passing** (offline: nock-mocked HTTP, asserts X-API-Key header, request bodies, and returned ids; no live Zapier account).
- App definition **VALID** against `zapier-platform-schema` 19.0.0 (see deviation note re: CLI Node-version requirement).
- Live `zapier push` → subscribe → event → trigger round-trip remains human-verify only per 33-VALIDATION.md.
