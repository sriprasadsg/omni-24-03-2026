# Phase 33: Workflow Automation Connectors - Research

**Researched:** 2026-07-08
**Domain:** Building external, out-of-repo-runtime integration packages (an n8n community node npm package; a Zapier Platform CLI app) that consume this platform's existing generic webhook system (`webhook_service.py`/`webhook_endpoints.py`), plus the in-repo backend prerequisites (a real, verifiable API-key auth path) both connectors need to authenticate.
**Confidence:** HIGH (in-repo webhook/auth architecture — all confirmed by direct reads this session) / MEDIUM (n8n/Zapier package conventions — official docs via WebSearch, not Context7; no local n8n/Zapier install to execute against)

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase. This project runs in yolo/auto mode this milestone — no `/gsd-discuss-phase` was run for Phase 33 (or most other v3.0 phases). This research and the resulting plan must proceed from `.planning/REQUIREMENTS.md` + `.planning/ROADMAP.md` + direct codebase inspection only. There are no locked decisions, discretion notes, or deferred ideas to copy verbatim — everything below is this agent's own research-derived recommendation, and items needing a human product decision are called out explicitly in **Open Questions**.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WF-01 | A dedicated n8n community node for the platform's webhook events | See Architecture Patterns → Pattern 1 (n8n trigger node with `webhookMethods` create/delete/checkExists, cloning the platform's existing `webhook_service.py` CRUD) and Pattern 3 (the API-key auth prerequisite the node's credential type needs) |
| WF-02 | A dedicated Zapier integration ("Zap" template) for the platform's webhook events | See Architecture Patterns → Pattern 2 (Zapier REST Hook trigger with `performSubscribe`/`performUnsubscribe`/`performList`, same underlying webhook CRUD) and Pattern 3 |
</phase_requirements>

## Summary

This is an unusual phase: its two deliverables (an n8n community node, a Zapier integration) are **npm packages that run outside this repo's runtime** — one inside a user's n8n instance, one on Zapier's infrastructure — calling this platform's REST API as an external client. Neither can be executed end-to-end in this repo's CI (no live n8n instance, no Zapier developer account to `zapier push` against). The realistic, verifiable-in-CI deliverable shape for both is: **a real, complete, lint-clean/type-checked source package committed to this repo**, verified by TypeScript compilation + the standard community-node linter (n8n) or `zapier validate` + unit tests against the app definition (Zapier) — not a live round-trip through either platform's UI.

**The good news: the event source both connectors need already exists and needs no new event infrastructure.** `webhook_service.py` + `webhook_endpoints.py` (router prefix `/api/webhooks`) is a working, tenant-scoped webhook subscription CRUD (`POST/GET/PUT/DELETE /api/webhooks`) with SSRF-guarded URL validation and per-webhook delivery history (`webhook_deliveries`). This is exactly the shape both n8n's and Zapier's "instant trigger" (REST Hook) patterns expect: a `create`/`subscribe` call that registers a callback URL, a `delete`/`unsubscribe` call that tears it down. **No new backend event infrastructure needs to be built — the connectors are clients of an API that already exists.**

**The bad news, and the load-bearing finding of this research: there is no working machine-to-machine auth path for that API today.** `tenant_endpoints.py` has `generate_api_key`/`revoke_api_key` (confirmed, full read this session), but they are **write-only** — `generate_api_key` stores only a truncated display prefix (`plaintext[:12] + "••••••••••••"`), never a verifiable hash of the full key, and **no middleware or FastAPI dependency anywhere in this codebase accepts an API key on an incoming request** (`authentication_service.py`'s `get_current_user` is hard-wired to `OAuth2PasswordBearer` / JWT only — confirmed by full read). n8n credentials and Zapier's authentication config are both built around a static API key or OAuth2 client-credentials flow, not an interactive username/password JWT login. **Neither connector can authenticate to this platform's webhook API until a real, verifiable API-key auth path is added — this is a Wave-0/Wave-1 prerequisite for this phase, the same class of finding as Phase 30's ChromaDB tenant-scoping gap:** research surfaced a real, load-bearing gap the phase brief's framing didn't anticipate.

**A second finding that materially affects both connectors' design:** `webhook_service.py`'s `_send_single_webhook` does **not** sign outbound payloads, even though `webhook_endpoints.py`'s `create_webhook` auto-generates a per-webhook `secret` (`whsec_{uuid4().hex[:24]}`) — that secret is stored but never used. This is a **real, pre-existing bug** made visible by this phase, not something this phase invented: the sibling `ticket_webhook_service.py` *does* correctly HMAC-sign its outbound webhooks (`X-Webhook-Signature: sha256=...`, confirmed by direct read) — proving the pattern already exists in this codebase and simply wasn't applied to the generic webhook system. n8n's and Zapier's own webhook-trigger conventions both expect an HMAC signature header so the receiving platform can verify authenticity; without it, an n8n Webhook node or Zapier catch-hook has no way to confirm a POST actually came from this platform. **Fixing `_send_single_webhook` to sign with `hook["secret"]` (cloning `ticket_webhook_service.py`'s exact pattern) is a small, in-scope backend fix this phase should make**, and both connectors' credential/setup instructions should document the signature header for users who want to verify it.

**A third, smaller finding:** this codebase has at least three non-integrated notification/webhook subsystems — `webhook_service.py` (generic, tenant-configured, the one the phase brief names), `notification_service.py` (a separate `notification_channels`/`notification_rules` system with its own fixed `VALID_EVENTS = {finding_created, control_failed, evidence_expired, review_overdue, cert_expiring}`), and `ticket_webhook_service.py` (ticketing-specific, its own `SUPPORTED_EVENTS`). **The phase brief is explicit that `webhook_service.py` is the event source to consume — this research confirms that scoping and recommends not touching the other two.** There is no single canonical "list of all GRC event types" constant anywhere in the codebase; event-type strings (`"agent.offline"`, `"security.alert"`, `"compliance.violation"`, etc.) are emitted ad hoc from ~5 call sites into `notification_manager.send_notification`, which fans out to `webhook_service.trigger_webhook`. The plan should document the actual set of event types currently emitted (grep results below) as the initial "Event" selector values for both connectors, not invent a larger catalog.

**Primary recommendation:** (1) As a backend prerequisite, add a real API-key verification dependency — hash-and-lookup, not the current display-prefix-only storage — and fix `generate_api_key` to store a SHA-256 hash of the full key; wire it as an alternative auth path (`X-API-Key` header) accepted by `POST/DELETE /api/webhooks` (and any new polling endpoint) alongside the existing JWT path. (2) Fix `_send_single_webhook` to HMAC-sign outbound payloads with the webhook's existing `secret`, cloning `ticket_webhook_service.py`'s pattern. (3) Build `integrations/n8n-nodes-omniagent/` — a standard n8n community-node package with a trigger node implementing `webhookMethods.create/delete/checkExists` against `/api/webhooks`, verified in CI via `tsc --noEmit` + `eslint-plugin-n8n-nodes-base`. (4) Build `integrations/zapier-omniagent/` — a Zapier Platform CLI app with a REST Hook trigger (`performSubscribe`/`performUnsubscribe`/`performList`) against the same endpoints, verified in CI via `zapier validate` + `zapier-platform-core`'s local test harness (no `zapier push`, no live account).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| GRC event emission (agent.offline, security.alert, compliance.violation, etc.) | API / Backend | Database / Storage | Unchanged — existing call sites into `notification_manager.send_notification`; this phase does not add new event types |
| Webhook subscription CRUD (the API both connectors call) | API / Backend | Database / Storage | Already exists (`webhook_endpoints.py` / `db.webhooks`); this phase adds an API-key auth path to it, not new CRUD logic |
| Outbound webhook delivery + signing | API / Backend | — | `webhook_service.py`; this phase's in-scope fix adds HMAC signing (currently missing) |
| API-key issuance, hashing, verification | API / Backend | Database / Storage | New verification dependency needed — `tenant_endpoints.py`'s existing issuance is write-only today |
| n8n community node (trigger + credential) | External runtime (n8n instance) — outside this repo's process boundary | — | Ships as an npm package a user installs into their own n8n; calls this platform's REST API as a client. Source lives in this repo; execution does not |
| Zapier integration (trigger) | External runtime (Zapier infrastructure) — outside this repo's process boundary | — | Ships as a Zapier Platform CLI app deployed via `zapier push` to Zapier's infra; calls this platform's REST API as a client. Source lives in this repo; execution does not |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `n8n-workflow` | `2.16.0` [ASSUMED — package name/role from WebSearch of official n8n docs, not yet verified via Context7; registry existence confirmed via `npm view`, see Package Legitimacy Audit] | Peer dependency providing n8n's node/credential TypeScript interfaces (`INodeType`, `IHookFunctions`, etc.) | The only way to type an n8n node against the n8n runtime API; never bundled, always a peerDependency per n8n's own convention |
| `eslint-plugin-n8n-nodes-base` | `1.16.7` [ASSUMED — see Package Legitimacy Audit, flagged SUS for recency] | Lints community-node `package.json` shape and node-file conventions | The standard, n8n-team-recommended CI gate for community nodes; runs without a live n8n instance |
| `zapier-platform-core` | `19.0.0` [ASSUMED — see Package Legitimacy Audit] | Runtime + schema for a Zapier Platform CLI app definition | Required dependency for any Zapier CLI-built integration; `zapier-platform-schema` validates the exported App object structurally, usable offline |
| `zapier-platform-cli` | `19.0.0` [ASSUMED — see Package Legitimacy Audit] | `zapier scaffold`, `zapier validate`, `zapier push` tooling | Official Zapier developer tool; `validate` and the bundled test harness run fully offline, only `push`/`deploy` need a live account |
| `typescript` | (repo already uses `5.7.3` [VERIFIED: `npx tsc --version`, this session]) | Compiling the n8n node source | Matches this repo's existing frontend TS toolchain; n8n community nodes are conventionally authored in TypeScript |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| stdlib `hashlib` (Python) | n/a | SHA-256 hashing of API keys at rest | Backend prerequisite fix — see Architecture Patterns → Pattern 3. Not bcrypt/Argon2: those are for low-entropy human passwords needing deliberately-slow hashing; a 256-bit random API key already has enough entropy that a fast, deterministic hash (enabling an indexed equality lookup) is the correct and standard tool [CITED: WebSearch synthesis of FastAPI API-key auth best-practice guidance, this session] |
| `hmac`/`hashlib` (Python, stdlib) | n/a | Signing outbound webhook payloads | Already used correctly by `ticket_webhook_service.py` — clone verbatim for `webhook_service.py`'s fix, do not introduce a new signing library |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| n8n REST-Hook-style trigger node (`webhookMethods.create/delete/checkExists`, recommended) | An n8n **polling trigger** (interval-based `GET`) | Simpler to build (no subscribe/unsubscribe lifecycle), but materially worse UX (delay up to the poll interval, extra load) for something this platform's webhook system already delivers in real time. No existing precedent reason to prefer polling here — recommended only as a fallback if a live GRC-events-list endpoint is needed anyway for Zapier's `performList` (see Pattern 2) |
| Zapier REST Hook trigger (`performSubscribe`/`performUnsubscribe`, recommended) | A Zapier **polling trigger** (`perform` only, Zapier polls on an interval) | Zapier's own guidance treats REST Hooks as the preferred pattern when the target API supports webhook subscription (which this one does); polling is the fallback for platforms with no webhook API — not this platform's situation |
| Full `zapier-platform-core` CLI app scaffold in this repo (recommended for WF-02, given the literal wording "a dedicated Zapier integration") | "Zapier-friendly" REST endpoints only, relying on Zapier's generic Webhooks/REST app for users to wire up manually | The generic-webhook-app path requires zero new code in this repo (the existing `/api/webhooks` API can already be pointed at any URL, which is explicitly what the phase brief says is already possible today) — but it does not satisfy WF-02's literal ask for "a dedicated Zapier integration ('Zap' template)", which implies a named, published app users find in Zapier's app directory, not a manual HTTP config. Recommending the real CLI app scaffold because the requirement text asks for more than what already exists |
| SHA-256 hash-and-lookup for API-key verification (recommended) | bcrypt/Argon2 (as used for user passwords in this codebase) | Slow-hash algorithms are designed to resist brute-force guessing of low-entropy human passwords; a randomly generated 256-bit API key has no guessing-attack surface a slow hash defends against, and a slow hash makes a per-request O(n) or even indexed lookup impractical at any real request volume. GitHub, Stripe, and similar API-key systems use fast deterministic hashing (SHA-256) for this exact reason [CITED: WebSearch synthesis, FastAPI/API-key auth best practices, this session] |

**Installation:**
```bash
# n8n node package (new directory: integrations/n8n-nodes-omniagent/)
cd integrations/n8n-nodes-omniagent && npm install --save-peer n8n-workflow@^2.16.0
npm install --save-dev eslint-plugin-n8n-nodes-base@^1.16.7 typescript@^5.7.3

# Zapier app (new directory: integrations/zapier-omniagent/)
cd integrations/zapier-omniagent && npm install zapier-platform-core@^19.0.0
npm install --save-dev zapier-platform-cli@^19.0.0
```

**Version verification:** `n8n-workflow` 2.16.0, `n8n-core` 2.16.1, `eslint-plugin-n8n-nodes-base` 1.16.7, `zapier-platform-core`/`zapier-platform-schema`/`zapier-platform-cli` all 19.0.0 — all confirmed present on the npm registry via `npm view <pkg> version` [VERIFIED: npm registry, this session]. Package **names** themselves were discovered via WebSearch/training knowledge, not an authoritative source, so per this project's provenance rule they remain tagged `[ASSUMED]` in the Standard Stack table above despite passing registry lookup — see Package Legitimacy Audit below for the full legitimacy check.

## Package Legitimacy Audit

| Package | Registry | Age (latest publish) | Downloads/wk | Source Repo | Verdict | Disposition |
|---------|----------|----------------------|--------------|-------------|---------|-------------|
| `n8n-workflow` | npm | 2026-04-07 | 299,931 | github.com/n8n-io/n8n | OK | Approved |
| `eslint-plugin-n8n-nodes-base` | npm | 2026-06-16 | 40,706 | github.com/ivov/eslint-plugin-n8n-nodes-base | SUS (`too-new` signal) | Flagged — see note below |
| `zapier-platform-core` | npm | 2026-05-18 | 100,890 | github.com/zapier/zapier-platform | OK | Approved |
| `zapier-platform-schema` | npm | 2026-05-18 | 101,491 | github.com/zapier/zapier-platform | OK | Approved |
| `zapier-platform-cli` | npm | 2026-05-18 | 55,743 | github.com/zapier/zapier-platform | OK | Approved |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `eslint-plugin-n8n-nodes-base` — the legitimacy gate flagged its latest-version publish date (2026-06-16, ~3 weeks before this research) as `too-new`. This reads as a **false positive from a recency heuristic, not a real slopsquatting signal**: the package has 40,706 weekly downloads, a real GitHub org/maintainer (`ivov`, a known n8n community contributor) with a public repo history, and it is the package n8n's own official documentation names as the standard node linter — but per this project's protocol, `[SUS]` verdicts must still be surfaced with a checkpoint, not silently waved through. `` `eslint-plugin-n8n-nodes-base` [WARNING: flagged as suspicious by the legitimacy gate — recency-only signal, high download count and known maintainer make this very likely a benign recent version bump, but the planner must add a `checkpoint:human-verify` task before this package is installed.] ``

## Architecture Patterns

### System Architecture Diagram

```
 GRC EVENT SOURCE (existing, unchanged)              BACKEND API SURFACE (existing + this phase's fix)
 ┌──────────────────────────────┐                    ┌───────────────────────────────────────────────┐
 │ ~5 call sites emit events:    │                    │  webhook_endpoints.py  (router: /api/webhooks) │
 │ agent.offline, security.alert,│                    │                                                 │
 │ compliance.violation, etc.    │──notification_──►  │  POST/GET/PUT/DELETE /api/webhooks             │
 │ (agent_metrics_endpoints.py,  │  manager.send_     │    auth: JWT (existing) OR X-API-Key (NEW —    │
 │  jit_access_service.py, ...)  │  notification()    │    this phase's prerequisite fix)              │
 └──────────────────────────────┘                    │                                                 │
                                                       │  webhook_service.py::trigger_webhook()          │
                                                       │    finds active webhooks matching event_type   │
                                                       │    POSTs payload to hook['url']                │
                                                       │    NEW: signs with HMAC-SHA256(hook['secret'])  │
                                                       │    (this phase's fix — currently missing,       │
                                                       │    cloning ticket_webhook_service.py's pattern) │
                                                       └──────────────────┬──────────────────────────────┘
                                                                          │ HTTPS POST (signed)
                        ┌─────────────────────────────────────────────────┴──────────────────────────────────┐
                        │                                                                                      │
                        ▼                                                                                      ▼
   ┌───────────────────────────────────────────┐                          ┌───────────────────────────────────────┐
   │  n8n community node                        │                          │  Zapier Platform CLI app                │
   │  integrations/n8n-nodes-omniagent/          │                          │  integrations/zapier-omniagent/         │
   │  (runs inside a USER'S n8n instance —       │                          │  (runs on ZAPIER'S infrastructure —     │
   │   outside this repo's runtime)              │                          │   outside this repo's runtime)          │
   │                                              │                          │                                          │
   │  Credential: OmniAgent API (X-API-Key)       │                          │  Authentication: API Key field          │
   │  Trigger node webhookMethods:                │                          │  Trigger (REST Hook):                   │
   │   create()  → POST /api/webhooks             │                          │   performSubscribe()  → POST /api/webhooks │
   │   delete()  → DELETE /api/webhooks/{id}      │                          │   performUnsubscribe()→ DELETE /api/webhooks/{id} │
   │   checkExists() → GET /api/webhooks          │                          │   perform()  → receives the signed POST │
   │  Node execution: receives the signed POST    │                          │   performList() → GET /api/webhooks/{id}/deliveries │
   │   body as the trigger's output data          │                          │    (sample data fallback, offline-testable) │
   └───────────────────────────────────────────┘                          └───────────────────────────────────────┘

 VERIFICATION BOUNDARY (what CI in THIS repo can actually check):
   n8n node:  tsc --noEmit  +  eslint-plugin-n8n-nodes-base lint   (no live n8n instance)
   Zapier app: zapier validate  +  zapier-platform-core unit test harness   (no zapier push, no live account)
   Backend:   pytest — API-key hash/verify roundtrip, HMAC signature roundtrip, /api/webhooks auth (JWT + API-key paths)
```

### Recommended Project Structure
```
backend/
├── tenant_endpoints.py             # MODIFIED — generate_api_key stores a SHA-256 hash of the full key (not display-prefix only)
├── api_key_auth.py                 # NEW — hash-and-lookup verification dependency (get_current_user_or_api_key)
├── webhook_service.py              # MODIFIED — _send_single_webhook signs outbound payload with hook['secret'] (HMAC-SHA256)
├── webhook_endpoints.py            # MODIFIED — POST/DELETE /api/webhooks accept the new API-key auth path alongside JWT
├── tests/
│   ├── test_api_key_auth.py        # NEW — hash storage, verification, revocation, wrong-key rejection
│   └── test_webhook_signing.py     # NEW — HMAC signature present + correct on outbound delivery

integrations/
├── n8n-nodes-omniagent/            # NEW — n8n community node package (WF-01)
│   ├── package.json                #   name: n8n-nodes-omniagent, n8n block, n8n-workflow peerDependency
│   ├── credentials/
│   │   └── OmniAgentApi.credentials.ts
│   ├── nodes/
│   │   └── OmniAgentTrigger/
│   │       └── OmniAgentTrigger.node.ts   # webhookMethods.create/delete/checkExists
│   ├── tsconfig.json / tsconfig.build.json
│   ├── eslint.config.mjs
│   └── README.md
├── zapier-omniagent/                # NEW — Zapier Platform CLI app (WF-02)
│   ├── index.js                     # App definition export
│   ├── authentication.js            # API key field
│   ├── triggers/
│   │   └── grc_event.js             # performSubscribe / performUnsubscribe / performList
│   ├── test/
│   │   └── triggers/grc_event.test.js
│   └── package.json                 # zapier-platform-core dependency
```

### Pattern 1: n8n trigger node — clone `webhookMethods` lifecycle against the existing `/api/webhooks` CRUD
**What:** n8n community trigger nodes implement `webhookMethods.create`/`delete`/`checkExists` (running in `IHookFunctions` context) to manage a REST-Hook-style subscription with an external API when a user activates/deactivates the workflow. This maps directly onto this platform's already-shipped webhook CRUD.
**When to use:** WF-01.
**Example:**
```typescript
// Pattern source: n8n community-node docs (WebSearch, this session — see Sources)
// Backend calls target this repo's existing webhook_endpoints.py, unmodified except for the new API-key auth path.
export class OmniAgentTrigger implements INodeType {
  description: INodeTypeDescription = {
    displayName: 'OmniAgent Trigger',
    name: 'omniAgentTrigger',
    group: ['trigger'],
    version: 1,
    credentials: [{ name: 'omniAgentApi', required: true }],
    webhooks: [{ name: 'default', httpMethod: 'POST', responseMode: 'onReceived', path: 'webhook' }],
    properties: [
      { displayName: 'Event', name: 'event', type: 'options',
        options: [
          { name: 'Agent Offline', value: 'agent.offline' },
          { name: 'Security Alert', value: 'security.alert' },
          { name: 'Compliance Violation', value: 'compliance.violation' },
          // full option list = the actual event_type strings emitted today — see Sources
        ], default: 'security.alert' },
    ],
  };

  webhookMethods = {
    default: {
      async checkExists(this: IHookFunctions): Promise<boolean> {
        const webhookData = this.getWorkflowStaticData('node');
        return !!webhookData.webhookId;
      },
      async create(this: IHookFunctions): Promise<boolean> {
        const webhookUrl = this.getNodeWebhookUrl('default');
        const event = this.getNodeParameter('event') as string;
        const credentials = await this.getCredentials('omniAgentApi');
        const response = await this.helpers.httpRequest({
          method: 'POST', url: `${credentials.baseUrl}/api/webhooks`,
          headers: { 'X-API-Key': credentials.apiKey as string },
          body: { name: 'n8n trigger', url: webhookUrl, events: [event] }, json: true,
        });
        this.getWorkflowStaticData('node').webhookId = response.id;
        return true;
      },
      async delete(this: IHookFunctions): Promise<boolean> {
        const webhookData = this.getWorkflowStaticData('node');
        const credentials = await this.getCredentials('omniAgentApi');
        await this.helpers.httpRequest({
          method: 'DELETE', url: `${credentials.baseUrl}/api/webhooks/${webhookData.webhookId}`,
          headers: { 'X-API-Key': credentials.apiKey as string },
        });
        return true;
      },
    },
  };
}
```

### Pattern 2: Zapier REST Hook trigger — `performSubscribe`/`performUnsubscribe`/`performList` against the same CRUD
**What:** Zapier's REST Hook pattern is the equivalent lifecycle: `performSubscribe` registers Zapier's callback URL, `performUnsubscribe` tears it down, `perform` handles the inbound payload, and `performList` is a required fallback (Zapier's `BasicHookOperationSchema` validation requires it) that returns sample/recent data for the Zap editor's "test trigger" UI even when the trigger is hook-based.
**When to use:** WF-02.
**Example:**
```javascript
// Pattern source: Zapier Platform CLI REST Hook docs (WebSearch, this session — see Sources)
const subscribeHook = (z, bundle) =>
  z.request({
    url: `${bundle.authData.baseUrl}/api/webhooks`,
    method: 'POST',
    headers: { 'X-API-Key': bundle.authData.apiKey },
    body: { name: 'Zapier trigger', url: bundle.targetUrl, events: [bundle.inputData.event] },
  }).then((response) => response.json);

const unsubscribeHook = (z, bundle) =>
  z.request({
    url: `${bundle.authData.baseUrl}/api/webhooks/${bundle.subscribeData.id}`,
    method: 'DELETE',
    headers: { 'X-API-Key': bundle.authData.apiKey },
  });

const performList = (z, bundle) =>
  z.request({
    url: `${bundle.authData.baseUrl}/api/webhooks/${bundle.subscribeData?.id}/deliveries`,
    headers: { 'X-API-Key': bundle.authData.apiKey },
  }).then((response) => response.json);

module.exports = {
  key: 'grc_event',
  noun: 'GRC Event',
  display: { label: 'New GRC Event', description: 'Triggers when a GRC event (agent offline, security alert, compliance violation, ...) fires.' },
  operation: { type: 'hook', performSubscribe: subscribeHook, performUnsubscribe: unsubscribeHook, perform: (z, bundle) => [bundle.cleanedRequest], performList },
};
```

### Pattern 3: Backend prerequisite — real API-key verification (the gap both connectors need fixed first)
**What:** `tenant_endpoints.py::generate_api_key` currently stores only a truncated display prefix (`plaintext[:12] + "••••••••••••"`) — the full key is returned once and never persisted in any verifiable form, and no dependency anywhere accepts an `X-API-Key` header. This must be fixed before either connector can authenticate.
**When to use:** Wave-0/Wave-1 prerequisite for both WF-01 and WF-02.
**Example:**
```python
# backend/tenant_endpoints.py — generate_api_key, modified to also store a verifiable hash
import hashlib
plaintext = f"omni_sk_{secrets.token_urlsafe(32)}"
key_hash = hashlib.sha256(plaintext.encode()).hexdigest()   # NEW — SHA-256, not bcrypt (see Standard Stack rationale)
key_doc = {
    "id": key_id,
    "name": data.get("name", "API Key"),
    "key": plaintext[:12] + "••••••••••••",   # unchanged — display prefix only
    "keyHash": key_hash,                       # NEW — enables verification
    "createdAt": now,
    "userId": data.get("userId") or getattr(current_user, "username", ""),
}

# backend/api_key_auth.py — NEW verification dependency
async def get_current_user_or_api_key(
    api_key: Optional[str] = Security(APIKeyHeader(name="X-API-Key", auto_error=False)),
    token: Optional[str] = Depends(_oauth2_optional),
):
    if api_key:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        tenant = await mongodb.db.tenants.find_one({"apiKeys.keyHash": key_hash}, {"id": 1, "apiKeys.$": 1})
        if not tenant:
            raise HTTPException(status_code=401, detail="Invalid API key")
        set_tenant_id(tenant["id"])   # per Phase 29's Pattern 2 precedent — explicit context set, not middleware
        return TokenData(tenant_id=tenant["id"], role="api-integration", username="api-key")
    if token:
        return await verify_token_async(token)
    raise HTTPException(status_code=401, detail="Authentication required")
```
`webhook_endpoints.py`'s `POST`/`GET`/`DELETE`/`PUT /api/webhooks` routes swap `Depends(get_current_user)` for `Depends(get_current_user_or_api_key)`. Note this follows the **same manual `set_tenant_id()` pattern Phase 29's research already established** for non-JWT-authenticated requests against `TenantIsolatedCollection` — see that phase's Pitfall 1 for why this is mandatory, not optional.

### Pattern 4: Outbound webhook signing fix — clone `ticket_webhook_service.py`, do not invent a new scheme
**What:** `webhook_service.py::_send_single_webhook` builds `headers` from `hook.get('headers', {})` plus `Content-Type`/`User-Agent` only — it never touches `hook['secret']`, despite that secret being auto-generated on every webhook (`webhook_endpoints.py::create_webhook`). `ticket_webhook_service.py` already does this correctly.
**When to use:** Backend prerequisite fix, in scope for this phase since both connectors' credential setup should be able to tell users "verify the `X-Webhook-Signature` header using your webhook's secret."
**Example:**
```python
# Source: backend/ticket_webhook_service.py lines 70-77 (existing, correct — the pattern to clone)
import json, hmac, hashlib
body = json.dumps(payload)
sig = hmac.new(hook["secret"].encode(), body.encode(), hashlib.sha256).hexdigest()
headers["X-Webhook-Signature"] = f"sha256={sig}"
# Apply the same two lines inside webhook_service.py::_send_single_webhook, using `hook.get('secret')`.
```

### Anti-Patterns to Avoid
- **Building a full custom "public event polling" endpoint before checking whether the REST-Hook (subscribe/unsubscribe) shape already covers the requirement:** Both n8n and Zapier prefer REST Hooks when the target API supports webhook subscriptions, which this one already does. A polling endpoint is only needed as Zapier's `performList` sample-data fallback (a small, cheap addition — the existing `GET /api/webhooks/{id}/deliveries` already serves this purpose) — do not build a second, larger "recent GRC events" feed unless a human confirms it's actually wanted (see Open Questions).
- **Reusing bcrypt/Argon2 (this codebase's existing password-hashing tool) for API-key verification:** Wrong tool for high-entropy random tokens — see Standard Stack → Alternatives Considered. Use SHA-256 (Pattern 3).
- **Treating `notification_service.py`'s `VALID_EVENTS` or `ticket_webhook_service.py`'s `SUPPORTED_EVENTS` as the event catalog for these connectors:** The phase brief is explicit that `webhook_service.py` is the event source; those two are separate, non-integrated subsystems (see Summary). Do not merge or "unify" them as part of this phase — out of scope.
- **Attempting a live round-trip test against a real n8n instance or Zapier account inside this repo's CI:** Neither is available in this environment and both require external accounts/infrastructure this repo does not control. Verification is source-correctness (compile + lint + `zapier validate` + offline unit tests), not a live integration test — document this explicitly so the plan's verification steps don't chase an impossible CI target.
- **Publishing either package to npm / Zapier's public directory as part of this phase's automated execution:** Publishing is an operator action requiring credentials/accounts this phase's execution should not assume access to. Build and verify the package; leave `npm publish`/`zapier push`/Zapier's app-review submission as a documented manual follow-up step, not an automated task.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Webhook subscription storage/CRUD for the connectors to call | A second, connector-specific webhook table/API | The existing `/api/webhooks` CRUD (`webhook_service.py`/`webhook_endpoints.py`) | Already tenant-scoped, SSRF-guarded, has delivery history — exactly what both connector patterns need; a second implementation fragments the event source the phase brief explicitly names |
| API-key verification | A bespoke token scheme or reusing JWT with an artificially long expiry | SHA-256 hash-and-lookup dependency (Pattern 3), the standard shape for third-party/automation-platform auth | JWTs are designed to expire and be refreshed by an interactive user session — automation platforms need a static, revocable credential; API keys are the correct primitive, they just need real verification added |
| Outbound webhook payload authenticity | A new signing library or bespoke verification instructions per connector | HMAC-SHA256 with the existing per-webhook `secret`, cloning `ticket_webhook_service.py` (Pattern 4) | Already a proven, shipped pattern in this exact codebase for exactly this problem — it was simply never applied to the generic webhook path |
| n8n node linting / Zapier app schema validation | Custom TypeScript/JSON Schema validators | `eslint-plugin-n8n-nodes-base` / `zapier-platform-schema`'s built-in `zapier validate` | Both are the platform-owner's own official verification tooling — reinventing them risks missing the exact checks each platform's real review process runs |

**Key insight:** Every piece of backend infrastructure both connectors need already exists in some form in this codebase (webhook CRUD, an HMAC-signing pattern, an API-key issuance UI) — the actual gap is that two of those three pieces were built to only half their job (API keys are issued but never verified; webhook secrets are generated but never used). This phase's real backend work is closing those two gaps, not building new infrastructure — closely mirroring Phase 29's and Phase 30's research findings that this codebase's competitive-parity gaps are usually "finish what's half-built," not "build from scratch."

## Runtime State Inventory

> This phase is not a rename/refactor/migration — it adds new capability (API-key hash storage, webhook signing, two new external packages). Included for completeness per the trigger criteria, since it does modify an existing stored-data shape (`tenants.apiKeys[]`).

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Existing `tenants.apiKeys[]` array entries (created before this phase) have no `keyHash` field — any API key generated prior to this phase's fix cannot be verified under the new scheme. | Code edit, not a silent migration: document that pre-existing API keys must be regenerated after this phase ships (their plaintext was never stored, so no automatic backfill is possible). Surface this in the plan's release notes / admin-facing messaging, not just quietly in code. |
| Live service config | None found — no n8n/Zapier configuration lives outside this repo yet (greenfield for this phase). | None. |
| OS-registered state | None found. | None. |
| Secrets/env vars | Webhook `secret` fields (`whsec_...`) already exist per-webhook in `db.webhooks`; this phase starts using them (Pattern 4) but does not rename or relocate them. | None — additive use of an existing stored field. |
| Build artifacts | None found — `integrations/n8n-nodes-omniagent/` and `integrations/zapier-omniagent/` are new directories with no prior build output to clean up. | None. |

## Common Pitfalls

### Pitfall 1: API keys generated before this phase's fix cannot be verified, and there is no way to recover them
**What goes wrong:** If the plan assumes `keyHash` can be backfilled onto existing `tenants.apiKeys[]` entries, it will discover that the plaintext key was never stored (by design, correctly) — only a display prefix. There is no cryptographic way to derive a hash from a prefix.
**Why it happens:** `generate_api_key` returns the plaintext exactly once and never persists it in recoverable form — correct security practice, but it means this phase's schema change cannot be retroactively applied to old keys.
**How to avoid:** Treat this as a breaking change for existing API keys, not a migration. The plan should include a step that documents (in an admin-facing changelog or the API-keys UI itself) that keys created before this phase must be regenerated.
**Warning signs:** A task that says "backfill `keyHash` for existing keys" — this is not achievable and signals the plan misunderstood the storage model.

### Pitfall 2: Adding `X-API-Key` support to `/api/webhooks` without also scoping what an API-key-authenticated request is allowed to do
**What goes wrong:** The existing JWT-authenticated `get_current_user` carries a `role` used elsewhere in this codebase for RBAC checks (`_WEBHOOK_SUPER_ROLES` in `webhook_endpoints.py`, for instance). A naive API-key dependency that fabricates a `TokenData` with an arbitrary role could accidentally grant an automation credential more (or less) access than intended, or trip an RBAC check written assuming only interactive-user roles exist.
**Why it happens:** RBAC role checks in this codebase were written before any non-interactive credential type existed.
**How to avoid:** Give API-key-authenticated requests an explicit, narrow role (e.g. `"api-integration"`, as in Pattern 3's example) and audit every RBAC branch `webhook_endpoints.py` (and any new polling endpoint) touches to confirm that role is handled correctly — not silently treated as `SUPER_ROLES` or silently rejected.
**Warning signs:** An API-key-authenticated request either bypasses tenant scoping (too permissive) or 403s on routes it should be allowed to call (too restrictive) — both are signs the role wasn't threaded through the existing RBAC checks correctly.

### Pitfall 3: Building the n8n node's `create()`/Zapier's `performSubscribe()` without handling the case where the subscription already exists (workflow re-activated, Zap re-enabled)
**What goes wrong:** n8n's linting rule and Zapier's REST-Hook convention both expect `checkExists`/idempotent subscribe behavior; without it, re-activating a workflow or re-enabling a Zap can silently create duplicate webhook subscriptions in `db.webhooks`, each independently posting the same event — the user sees duplicate trigger executions.
**Why it happens:** It's easy to implement `create`/`performSubscribe` as unconditional "always POST a new webhook" without checking for an existing one tied to the same workflow/Zap instance.
**How to avoid:** n8n: implement `checkExists` against `this.getWorkflowStaticData('node').webhookId` (Pattern 1). Zapier: `bundle.subscribeData` already carries the prior subscription id across activate/deactivate cycles — Zapier's own lifecycle handles this if `performUnsubscribe` is implemented correctly and always called before a re-subscribe.
**Warning signs:** Multiple `db.webhooks` documents for the same tenant with URLs pointing at the same n8n/Zapier callback host.

### Pitfall 4: Assuming this repo's CI can meaningfully "verify" either connector end-to-end
**What goes wrong:** A verification step written as "confirm the n8n node fires when a real webhook is received" or "confirm the Zap triggers in production" cannot be automated in this repo — there is no live n8n instance or Zapier developer account available in this environment.
**Why it happens:** Every other phase in this codebase verifies against a real, in-repo running backend; these two deliverables are genuinely external.
**How to avoid:** Scope automated verification to source correctness only (compile, lint, `zapier validate`, unit tests against the app definition/node file using each platform's own offline test harness) — see Validation Architecture. Manual/human verification (installing the node into a real n8n instance, or `zapier push` to a developer account) is a documented, explicitly out-of-CI step, not something the plan should claim is "tested."
**Warning signs:** A plan task with an automated verification command that requires network access to a live n8n/Zapier instance — this will fail or silently be skipped in CI.

## Code Examples

### Existing webhook CRUD the connectors call unmodified (backend, already shipped)
```python
# Source: backend/webhook_endpoints.py lines 111-140 (existing, read in full this session)
@router.post("")
async def create_webhook(webhook_data: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    url = webhook_data.get("url", "")
    if not _is_safe_webhook_url(url):
        raise HTTPException(status_code=400, detail="Invalid or disallowed webhook URL")
    new_webhook = {
        "id": f"wh-{uuid.uuid4().hex[:12]}", "name": webhook_data.get("name"), "url": url,
        "events": webhook_data.get("events", []), "status": "Active",
        "secret": f"whsec_{uuid.uuid4().hex[:24]}",   # generated, but never used for signing today — Pattern 4 fixes this
        "tenantId": current_user.tenant_id, "createdBy": current_user.username,
        "createdAt": datetime.now(timezone.utc).isoformat(), "failureCount": 0, "lastResult": None,
    }
    await db.webhooks.insert_one(new_webhook)
    return new_webhook
```

### The existing, correct signing pattern to clone (from a sibling webhook system)
```python
# Source: backend/ticket_webhook_service.py lines 70-77 (existing, read this session)
sig = hmac.new(hook["secret"].encode(), body.encode(), hashlib.sha256).hexdigest()
headers["X-Webhook-Signature"] = f"sha256={sig}"
```

### The write-only API-key issuance this phase must complete (backend, existing)
```python
# Source: backend/tenant_endpoints.py lines 271-305 (existing, read in full this session)
plaintext = f"omni_sk_{secrets.token_urlsafe(32)}"
key_doc = {
    "id": key_id, "name": data.get("name", "API Key"),
    "key": plaintext[:12] + "••••••••••••",   # display prefix only — no verifiable form stored today
    "createdAt": now, "userId": data.get("userId") or getattr(current_user, "username", ""),
}
await mongodb.db.tenants.update_one({"id": tenant_id}, {"$push": {"apiKeys": key_doc}})
return {"id": key_id, "name": key_doc["name"], "key": plaintext, "createdAt": now}
# Nothing in this codebase ever reads apiKeys back for request verification — confirmed by full-repo grep this session.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|-------------------|---------------|--------|
| Generic webhook system usable only via hand-built HTTP config pointed at an n8n/Zapier-provided URL (phase brief's stated starting point) | A real n8n community node (subscribe/unsubscribe lifecycle) + a real Zapier REST Hook trigger, both authenticating via a newly-verifiable API key, both riding the now-signed existing webhook delivery path | This phase | First time this platform ships packages that run as clients of its own API from outside this repo's runtime — establishes the API-key-auth + HMAC-signing pattern any future third-party integration (e.g. a future Make.com/Workato connector) would also need |

**Deprecated/outdated:** None — this phase is purely additive; the existing generic-webhook "point it at a URL" path remains available for users who don't want a dedicated connector.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | WF-02's "dedicated Zapier integration ('Zap' template)" means a real `zapier-platform-core` CLI app scaffold committed to this repo (buildable/validatable, not deployed), not merely "REST endpoints shaped for Zapier's generic Webhooks app" | Standard Stack → Alternatives Considered | If the actual intent was the lighter-weight REST-endpoints-only interpretation, this phase over-builds; the CLI-app work is still valid (a superset), just larger than strictly required — flagged as Open Question 1 |
| A2 | A new `X-API-Key` auth path should be added to the *existing* `/api/webhooks` CRUD endpoints, rather than building a parallel, connector-specific API surface | Architecture Patterns → Pattern 3 | If a human wants a narrower, purpose-built "integrations API" separate from the general webhook-management API (e.g. for a smaller RBAC blast radius), this recommendation would need revisiting — low risk, as scoping the API-key role narrowly (Pitfall 2) achieves a similar isolation without a second API surface |
| A3 | Fixing `webhook_service.py`'s missing HMAC signing is in-scope for this phase (since it directly affects both connectors' credential/security story), not a separate bug-fix phase | Summary, Pattern 4 | Low risk — it's a small, contained, two-line fix cloning an already-proven in-codebase pattern; even if a human disagrees it belongs in this phase, deferring it doesn't block WF-01/WF-02 functionally (connectors would just document "signature verification not yet available") |
| A4 | The initial "Event" selector for both connectors should be the actual event-type strings found emitted in this codebase today (`agent.offline`, `security.alert`, `compliance.violation`, plus others found in the call-site grep), not a larger, aspirational catalog | Summary | Low risk — additive; more event types can be added to the selector list later without breaking either connector's architecture |
| A5 | Publishing either package to npm (`npm publish`) / submitting the Zapier app for platform review is an out-of-scope, manual, post-phase operator action, not something this phase's execution should attempt | Architecture Patterns → Anti-Patterns | If a human expects the connectors to be live/discoverable on npm or in Zapier's app directory by the end of this phase, this assumption under-delivers — flagged as Open Question 2 |

## Open Questions

1. **Does WF-02 require the full `zapier-platform-core` CLI app scaffold (this research's recommendation, Assumption A1), or would "Zapier-friendly" REST endpoints plus documentation for wiring up Zapier's generic Webhooks app satisfy the requirement at lower effort?**
   - What we know: The requirement text says "a dedicated Zapier integration ('Zap' template)" — the phrase "Zap template" specifically implies a named, discoverable integration a user finds and connects to by name, not a manual HTTP-config walkthrough.
   - What's unclear: Whether "dedicated" requires the integration to actually be published/discoverable in Zapier's app directory, or whether a locally-buildable, unpublished CLI app satisfies the phase's Definition of Done.
   - Recommendation: Build the full CLI app scaffold (superset of the lighter option); leave `zapier push`/app-directory submission as a documented manual follow-up.

2. **Should this phase's execution actually publish `n8n-nodes-omniagent` to npm and submit the Zapier app for platform review, or is "source exists, compiles, lints/validates clean" the actual Definition of Done?**
   - What we know: Both publishing actions require external accounts/credentials (an npm publish token with permission to publish under whatever org/scope is chosen; a Zapier developer account) that this execution environment has no confirmed access to.
   - What's unclear: Whether a human has (or wants to set up) those credentials as part of this phase, or treats publishing as a separate, manual release step.
   - Recommendation: Scope this phase to "source, compiled/linted/validated clean, committed to this repo" — treat publishing as an explicit manual follow-up documented in each package's README, not an automated task.

3. **Should the API-key auth prerequisite (Pattern 3) be scoped narrowly to `/api/webhooks` only, or should it become a general-purpose auth path other future integrations can also use?**
   - What we know: The immediate need is `/api/webhooks`; a general-purpose `get_current_user_or_api_key` dependency (as designed in Pattern 3) is trivially reusable by any future route without extra cost.
   - What's unclear: Whether product wants API-key scopes/permissions (e.g. "webhooks:write" vs. full tenant access) from day one, or whether tenant-wide access via API key is acceptable for v1.
   - Recommendation: Implement the dependency generally (any route can `Depends()` it), but grant API-key-authenticated requests only the `"api-integration"` role scoped to the webhook routes for v1 — expanding scope granularity is a natural, low-risk follow-up if needed.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Building/compiling both new packages | ✓ [VERIFIED: `node --version`, this session] | v20.20.2 | — |
| npm | Installing n8n-workflow / zapier-platform-core deps | ✓ [VERIFIED: `npm --version`, this session] | 10.8.2 | — |
| TypeScript (`tsc`) | Compiling the n8n node | ✓ [VERIFIED: `npx tsc --version`, this session] | 5.7.3 | — |
| A live n8n instance | Manual/human verification of WF-01 (not automatable in this repo) | ✗ | — | Source-level verification only (compile + lint); document live-instance testing as a manual follow-up |
| A Zapier developer account | Manual/human verification + `zapier push` for WF-02 (not automatable in this repo) | ✗ | — | Source-level verification only (`zapier validate` + offline unit tests); document account setup + push as a manual follow-up |
| MongoDB (via Motor) | API-key hash storage, webhook CRUD | ✓ (assumed running — used by every other phase this milestone) [ASSUMED — not independently re-probed this session] | — | — |

**Missing dependencies with no fallback:** none block the automatable portion of this phase's work.
**Missing dependencies with fallback:** live n8n instance and Zapier developer account — both fall back to source-level (compile/lint/validate) verification; live end-to-end testing is explicitly out of this repo's CI reach (Pitfall 4).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Backend framework | pytest [VERIFIED: `pytest.ini` read this session — `testpaths = . backend`, `asyncio_mode = auto`] |
| Backend config file | `pytest.ini` (repo root) |
| Backend quick run | `cd backend && python -m pytest tests/test_api_key_auth.py tests/test_webhook_signing.py -x` |
| Backend full suite | `cd backend && python -m pytest tests/ -q` |
| n8n node "test" | `cd integrations/n8n-nodes-omniagent && npx tsc --noEmit && npx eslint . --ext .ts` (no dedicated unit-test framework needed for a thin trigger node; compile + lint is the standard bar for community nodes) |
| Zapier app test | `cd integrations/zapier-omniagent && npx zapier validate && npm test` (mocha/jest-based unit tests against the exported App object, per `zapier-platform-cli`'s scaffold convention) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WF-01 (prereq) | API key hashes correctly, verifies correctly, rejects a wrong key | unit | `pytest tests/test_api_key_auth.py -k hash_verify -x` | ❌ Wave 0 |
| WF-01 (prereq) | `X-API-Key`-authenticated request to `/api/webhooks` resolves the correct tenant and is rejected for a revoked key | integration | `pytest tests/test_api_key_auth.py -k webhook_route -x` | ❌ Wave 0 |
| WF-01 (prereq) | Outbound webhook payload carries a correct `X-Webhook-Signature` header verifiable against `hook['secret']` | unit | `pytest tests/test_webhook_signing.py -k signature -x` | ❌ Wave 0 |
| WF-01 | n8n node package compiles with no TypeScript errors | build | `cd integrations/n8n-nodes-omniagent && npx tsc --noEmit` | ❌ Wave 0 (new package) |
| WF-01 | n8n node package passes `eslint-plugin-n8n-nodes-base` community-node rules | lint | `cd integrations/n8n-nodes-omniagent && npx eslint . --ext .ts` | ❌ Wave 0 |
| WF-01 | `webhookMethods.create`/`delete`/`checkExists` correctly call `/api/webhooks` (mocked HTTP) | unit | manual/human-verify against a real n8n instance — no offline harness for `IHookFunctions` execution exists; document as human-verify | n/a |
| WF-02 | Zapier app definition passes schema validation | validate | `cd integrations/zapier-omniagent && npx zapier validate` | ❌ Wave 0 (new package) |
| WF-02 | `performSubscribe`/`performUnsubscribe`/`performList` correctly call `/api/webhooks` (mocked HTTP, offline) | unit | `cd integrations/zapier-omniagent && npm test` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the relevant quick-run command for the file(s) touched (backend pytest subset, or `tsc`/`eslint`/`zapier validate` for the touched package)
- **Per wave merge:** full backend suite (`pytest tests/ -q`) + both package build/lint/validate commands
- **Phase gate:** full backend suite green, both packages compile/lint/validate clean, before `/gsd-verify-work`; live n8n/Zapier verification is explicitly scoped to human-verify (Pitfall 4), not part of the automated gate

### Wave 0 Gaps
- [ ] `backend/tests/test_api_key_auth.py` — new file; clone the `_col`/`_db`/`_user`/`_app` helper block from `backend/tests/test_automation_and_baa.py` per this repo's per-file test-helper convention (as Phase 29's research also did)
- [ ] `backend/tests/test_webhook_signing.py` — new file, same helper convention
- [ ] `integrations/n8n-nodes-omniagent/` — entire package scaffold (package.json, tsconfig, eslint config, credentials file, node file)
- [ ] `integrations/zapier-omniagent/` — entire package scaffold (package.json, index.js, authentication.js, trigger file, test file)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|-------------------|
| V2 Authentication | yes — central to this phase | New `X-API-Key` path (Pattern 3) must hash-and-verify, never compare plaintext; existing JWT path unchanged |
| V3 Session Management | no | API keys are stateless per-request credentials, not sessions |
| V4 Access Control | yes | API-key-authenticated requests must resolve tenant via explicit `set_tenant_id()` (cloning Phase 29's established pattern) and carry a narrowly-scoped role (Pitfall 2), not silently inherit broad RBAC |
| V5 Input Validation | yes | Webhook `events` array values, n8n/Zapier-supplied callback URLs continue through the existing `_is_safe_webhook_url` SSRF guard, unchanged |
| V6 Cryptography | yes | SHA-256 for API-key hash-and-lookup (Pattern 3); HMAC-SHA256 for outbound webhook signing (Pattern 4) — both cloning proven in-codebase patterns, no new crypto primitives introduced |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| API key leaked (committed to a public n8n workflow export, logged, or pasted into a support ticket) is usable indefinitely with no way to detect misuse | Spoofing / Information Disclosure | Revocation already exists (`revoke_api_key`) — ensure the plan surfaces revocation prominently in each connector's setup docs; consider (as a documented follow-up, not required for this phase) last-used-at tracking on `apiKeys[]` so a tenant admin can spot a stale/compromised key |
| Cross-tenant webhook-subscription creation via a mis-scoped API-key auth dependency | Elevation of Privilege / Information Disclosure | Pattern 3's `set_tenant_id()` resolution + Pitfall 2's narrow role scoping — the API-key dependency must never grant `SUPER_ROLES`-equivalent access |
| Forged inbound POSTs to an n8n Webhook node or Zapier catch-hook claiming to be from this platform | Spoofing / Tampering | Pattern 4's HMAC signing fix — document the `X-Webhook-Signature` verification step in both connectors' README/setup instructions so users who need it can verify authenticity |
| SSRF via a malicious webhook URL supplied through the n8n/Zapier credential flow (attacker-controlled n8n instance pointing the subscription at an internal address) | Tampering / Information Disclosure | Already mitigated — `_is_safe_webhook_url`'s private/link-local/loopback CIDR blocklist applies unconditionally to every `POST /api/webhooks` call regardless of auth method; this phase does not weaken or bypass it |
| API key brute-forcing / credential stuffing against the new `X-API-Key` header path | Spoofing | `secrets.token_urlsafe(32)` already yields 256 bits of entropy — no additional rate-limiting beyond what `webhook_endpoints.py`'s routes already have is strictly required, but adding `slowapi` rate-limiting to the auth-failure path is a reasonable low-cost hardening the plan should consider |

## Sources

### Primary (HIGH confidence)
- `backend/webhook_service.py` (full file read, this session) — confirmed `trigger_webhook`/`_send_single_webhook`, confirmed no HMAC signing applied despite `hook['secret']` existing
- `backend/webhook_endpoints.py` (full file read, this session) — confirmed full CRUD shape, SSRF guard, delivery-history endpoint, auto-generated `secret` field never used
- `backend/tenant_endpoints.py` lines 269-437 (read in full this session) — confirmed `generate_api_key`/`revoke_api_key` are write-only, no verification path exists
- `backend/authentication_service.py` lines 1-200 (read this session) — confirmed `get_current_user` is `OAuth2PasswordBearer`-only, no API-key auth dependency anywhere
- `backend/database.py` `TenantIsolatedCollection` (read this session, cross-referenced with Phase 29's research) — confirms the fail-closed tenant-isolation mechanism the new API-key auth path must respect via explicit `set_tenant_id()`
- `backend/ticket_webhook_service.py` (read this session) — confirmed the correct, already-shipped HMAC-signing pattern to clone
- `backend/notification_service.py` lines 460-510 (read this session) — confirmed a second, non-integrated `VALID_EVENTS`/notification-rules subsystem, distinct from `webhook_service.py`
- `backend/notification_manager.py` (full file read, this session) — confirmed the fan-out from event emission to `webhook_service.trigger_webhook`
- `backend/router_registry.py` (grepped this session) — confirmed `webhook_endpoints`/`tenant_endpoints` router registration pattern
- Repo-wide grep for `event_type=`/`send_notification(` call sites (this session) — confirmed the actual, current set of emitted event-type strings
- `.planning/REQUIREMENTS.md` lines 200-204 (read this session) — confirmed WF-01/WF-02's exact, minimal requirement text
- `.planning/phases/29-public-trust-center/29-RESEARCH.md` (read in full this session) — structural template and the `set_tenant_id()`-for-non-JWT-auth precedent this research extends to API-key auth
- `npm view <pkg> version` for `n8n-workflow`, `n8n-core`, `eslint-plugin-n8n-nodes-base`, `zapier-platform-core`, `zapier-platform-schema`, `zapier-platform-cli` (this session) — confirmed current registry versions
- `gsd-tools query package-legitimacy check` (this session) — confirmed OK/SUS verdicts, see Package Legitimacy Audit
- `node --version` / `npm --version` / `npx tsc --version` (this session) — confirmed local build-toolchain availability

### Secondary (MEDIUM confidence)
- [Building community nodes — n8n Docs](https://docs.n8n.io/integrations/community-nodes/building-community-nodes) (WebSearch, this session) — package structure, naming convention, `n8n` package.json block
- [n8n webhookMethods discussion — n8n Community](https://community.n8n.io/t/checkexists-create-delete-webhookmethods-for-trigger-based-nodes-itriggerfunctions/16565) (WebSearch, this session) — `checkExists`/`create`/`delete` lifecycle
- [eslint-plugin-n8n-nodes-base — GitHub/npm](https://github.com/ivov/eslint-plugin-n8n-nodes-base) (WebSearch, this session) — community-node lint rule set
- [Build with CLI — Zapier Platform Docs](https://docs.zapier.com/platform/build-cli/overview) (WebSearch, this session) — CLI app project structure
- [Add an instant trigger using REST Hooks — Zapier Platform Docs](https://platform.zapier.com/build/cli-hook-trigger) (WebSearch, this session) — `performSubscribe`/`performUnsubscribe`/`performList` pattern
- WebSearch synthesis of FastAPI API-key authentication best practices (multiple blog/tutorial sources, this session) — SHA-256-over-bcrypt rationale for high-entropy tokens
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html), [OWASP ASVS V2/V6 (GitHub)](https://github.com/OWASP/ASVS) (WebSearch, this session) — general API-key/secret-management guidance

### Tertiary (LOW confidence)
- None used as authoritative for any Standard Stack or Architecture recommendation — package **names** (`n8n-workflow`, `zapier-platform-core`, etc.) are tagged `[ASSUMED]` throughout per this project's provenance rule (discovered via WebSearch/training knowledge, not Context7), despite passing registry/legitimacy checks.

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — package identities came from WebSearch of official docs (not Context7), all cross-checked against the npm registry and a legitimacy scan; the one flagged package (`eslint-plugin-n8n-nodes-base`, SUS/too-new) is very likely a benign false positive but is carried as a checkpoint per protocol
- Architecture: HIGH for the in-repo backend findings (API-key write-only gap, missing HMAC signing, tenant-isolation mechanics — all confirmed by direct full-file reads this session); MEDIUM for the exact n8n/Zapier package conventions (sourced from official documentation via WebSearch, not independently executed against a live n8n/Zapier environment)
- Pitfalls: HIGH — Pitfalls 1 and 2 are drawn directly from this codebase's actual data model and RBAC structure, confirmed by direct reads; Pitfalls 3 and 4 are standard, well-documented patterns for each external platform's own trigger lifecycle and this repo's genuine CI boundary

**Research date:** 2026-07-08
**Valid until:** 30 days for the in-repo architecture findings (stable); 7-14 days for the exact n8n/Zapier package versions cited (both platforms ship frequent point releases — re-verify versions via `npm view` immediately before scaffolding either package if planning is delayed)
