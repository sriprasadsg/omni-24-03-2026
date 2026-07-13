---
phase: 33-workflow-automation-connectors
plan: 03
subsystem: integrations
tags: [n8n, community-node, trigger, webhooks, api-key, eslint]
summary_type: execution
status: completed
requirements: [WF-01]

requires:
  - phase: 33-workflow-automation-connectors
    provides: 33-01 X-API-Key auth path and 33-02 X-Webhook-Signature signing
provides:
  - integrations/n8n-nodes-omniagent/ — n8n community-node package (OmniAgent API credential + OmniAgent Trigger node)
  - compile-clean (tsc --noEmit), lint-clean (eslint-plugin-n8n-nodes-base), dist/ build matching the package.json n8n block
affects: [trust-center, workflow-automation]

tech-stack:
  added: [n8n-workflow@^2.16.0 (peer/dev), eslint-plugin-n8n-nodes-base@^1.16.7 (dev), "@typescript-eslint/parser (dev)", typescript@^5.7.3 (dev)]
  patterns: [webhookMethods create/delete/checkExists lifecycle against existing /api/webhooks CRUD with X-API-Key auth; workflow static data stashes webhookId for idempotency]

key-files:
  created:
    - integrations/n8n-nodes-omniagent/package.json
    - integrations/n8n-nodes-omniagent/credentials/OmniAgentApi.credentials.ts
    - integrations/n8n-nodes-omniagent/nodes/OmniAgentTrigger/OmniAgentTrigger.node.ts
    - integrations/n8n-nodes-omniagent/eslint.config.mjs
    - integrations/n8n-nodes-omniagent/README.md

key-decisions:
  - "Task 1 SUS checkpoint resolved: user explicitly approved installing eslint-plugin-n8n-nodes-base@^1.16.7 (SUS was recency-heuristic only; maintainer ivov, ~40k weekly downloads, public repo, named in n8n official docs)"
  - "npm install run with --ignore-scripts: isolated-vm (transitive dep of n8n-workflow) fails node-gyp compile against Node 20.20.2 v8 headers (SourceLocation API mismatch); isolated-vm is an n8n runtime concern, not needed for tsc/eslint/build gates"
  - "n8n-nodes-base/cred-class-field-documentation-url-miscased disabled: rule is main-repo-only per its own docs; community packages use a real HTTP documentationUrl (enforced by cred-class-field-documentation-url-not-http-url)"
  - "Event selector lists only currently-emitted event types (agent.offline, security.alert, compliance.violation), matching the Zapier app"

deviations:
  - "@typescript-eslint/parser added as an explicit devDependency — flat eslint.config.mjs needs a TS parser wired via languageOptions; the plan's config omitted it and eslint's default espree parser cannot parse TS"

human-verify:
  - "Live n8n round-trip (install built node into local n8n, add credential, activate workflow, confirm subscription appears in /api/webhooks) — documented in README; cannot run in this repo's CI"
  - "npm publish is a manual operator follow-up, out of scope per plan"
---

# Plan 33-03 Summary — n8n Community Node (WF-01)

Completed the previously gated install/lint/build verification of the n8n community-node package after explicit user approval of the SUS-flagged dev dependency (2026-07-14).

- `npm install --ignore-scripts` (isolated-vm native build incompatible with Node 20; not needed for gates)
- `npx tsc --noEmit` — clean
- `npx eslint . --ext .ts` — clean after wiring @typescript-eslint/parser and fixing documentationUrl to a real HTTP URL
- `npm run build` — emits dist/credentials/OmniAgentApi.credentials.js and dist/nodes/OmniAgentTrigger/OmniAgentTrigger.node.js, exactly the paths declared in the package.json `n8n` block
