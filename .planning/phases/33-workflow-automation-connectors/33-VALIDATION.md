---
phase: 33
slug: workflow-automation-connectors
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-08
---

# Phase 33 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Backend framework** | pytest (`pytest.ini` at repo root, `asyncio_mode = auto`) |
| **Backend quick run** | `cd backend && python -m pytest tests/test_api_key_auth.py tests/test_webhook_signing.py -x` |
| **Backend full suite** | `cd backend && python -m pytest tests/ -q` |
| **n8n node check** | `cd integrations/n8n-nodes-omniagent && npx tsc --noEmit && npx eslint . --ext .ts` |
| **Zapier app check** | `cd integrations/zapier-omniagent && npx zapier validate && npm test` |

---

## Sampling Rate

- **After every task commit:** the relevant quick-run command for the file(s) touched (backend pytest subset, or `tsc`/`eslint`/`zapier validate` for the touched package)
- **After every plan wave:** full backend suite + both package build/lint/validate commands
- **Before `/gsd-verify-work`:** full backend suite green, both packages compile/lint/validate clean; live n8n/Zapier round-trips are explicitly human-verify only (per research Pitfall 4 — deliverables run outside this repo's runtime)
- **Max feedback latency:** 60 seconds (package installs excluded)

---

## Per-Task Verification Map

Task IDs are assigned by the planner; requirement-level rows below are the contract the planner must map tasks onto (per `33-RESEARCH.md` § Validation Architecture).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | 1 | WF-01/02 (prereq) | T-33-KEY | API key stored as hash (never plaintext), verifies correctly, rejects wrong/revoked keys | unit | `pytest tests/test_api_key_auth.py -k hash_verify -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | WF-01/02 (prereq) | T-33-KEY | `X-API-Key`-authenticated request to `/api/webhooks` resolves the correct tenant, carries only the narrow `api-integration` role, and is rejected for a revoked key | integration | `pytest tests/test_api_key_auth.py -k webhook_route -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | WF-01/02 (prereq) | T-33-SIGN | Outbound webhook payload carries a correct HMAC-SHA256 `X-Webhook-Signature` header verifiable against `hook['secret']` (cloning `ticket_webhook_service.py`'s existing signing) | unit | `pytest tests/test_webhook_signing.py -k signature -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 2 | WF-01 | — | n8n node package compiles clean | build | `cd integrations/n8n-nodes-omniagent && npx tsc --noEmit` | ❌ W0 | ⬜ pending |
| TBD | TBD | 2 | WF-01 | — | n8n node passes `eslint-plugin-n8n-nodes-base` community-node rules | lint | `cd integrations/n8n-nodes-omniagent && npx eslint . --ext .ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | 2 | WF-02 | — | Zapier app definition passes schema validation | validate | `cd integrations/zapier-omniagent && npx zapier validate` | ❌ W0 | ⬜ pending |
| TBD | TBD | 2 | WF-02 | — | `performSubscribe`/`performUnsubscribe`/`performList` correctly call `/api/webhooks` (mocked HTTP, offline) | unit | `cd integrations/zapier-omniagent && npm test` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_api_key_auth.py` — new file; clone the `_col`/`_db`/`_user`/`_app` helper block from `backend/tests/test_automation_and_baa.py`
- [ ] `backend/tests/test_webhook_signing.py` — new file, same helper convention
- [ ] `integrations/n8n-nodes-omniagent/` — entire package scaffold (package.json, tsconfig, eslint config, credentials file, node file)
- [ ] `integrations/zapier-omniagent/` — entire package scaffold (package.json, index.js, authentication.js, trigger file, test file)
- [ ] Package install: `n8n-workflow` (peer dep), `eslint-plugin-n8n-nodes-base` (SUS-flagged false-positive — carry the `checkpoint:human-verify` per the research's Package Legitimacy Audit), `zapier-platform-core`/`-schema`/`-cli` (all verdict OK)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| n8n node's `webhookMethods.create/delete/checkExists` work against a live platform instance | WF-01 | No offline harness exists for n8n's `IHookFunctions` execution | Install the node into a local n8n instance, add credentials (API key + base URL), activate a workflow with the trigger, confirm a webhook subscription appears in `/api/webhooks` and events flow |
| Zapier app round-trip (subscribe → event → trigger fires) | WF-02 | Requires Zapier developer account + deployed app — publishing is explicitly out of this phase's DoD | Follow the README's `zapier push` instructions with a developer account, wire a test Zap, confirm the trigger fires on a GRC event |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (2 test files + 2 package scaffolds created before assertions run)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner, 2026-07-08)
