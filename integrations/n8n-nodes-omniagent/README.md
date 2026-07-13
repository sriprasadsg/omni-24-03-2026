# n8n-nodes-omniagent

n8n community node for the **OmniAgent GRC platform**. The **OmniAgent Trigger** node starts a workflow whenever your OmniAgent instance emits a subscribed GRC event.

## Supported events

These are the event types the platform emits today:

| Event | Value |
|-------|-------|
| Agent Offline | `agent.offline` |
| Security Alert | `security.alert` |
| Compliance Violation | `compliance.violation` |

## Installation (into your own n8n instance)

1. Build the package: `npm install && npm run build`
2. In n8n: **Settings → Community Nodes → Install**, or copy/link the package into your n8n custom-nodes directory (`~/.n8n/custom/`).
3. Restart n8n.

## Credentials

Create an **OmniAgent API** credential:

- **Base URL** — your OmniAgent platform URL, e.g. `https://portal.example.com` (no trailing slash).
- **API Key** — generate one in OmniAgent under **Tenant Settings → API Keys**. The key is shown once; it is stored hashed on the platform. It is sent as the `X-API-Key` header and carries a narrow, tenant-scoped `api-integration` role.

To revoke access, delete the key in the same Tenant Settings screen.

## How it works

When you activate a workflow containing the OmniAgent Trigger, the node registers a webhook subscription via `POST /api/webhooks` on your platform (and removes it with `DELETE /api/webhooks/{id}` on deactivation). Re-activation is idempotent — the node remembers its subscription and will not create duplicates.

## Verifying inbound authenticity (X-Webhook-Signature)

Every delivery from the platform is signed when the webhook has a secret (auto-generated at subscription time, visible in the platform's webhook settings):

```
X-Webhook-Signature: sha256=<hex digest>
```

The digest is `HMAC-SHA256(secret, raw_request_body)` computed over the **exact raw body bytes**. To verify in a downstream Function node:

```javascript
const crypto = require('crypto');
const expected = 'sha256=' + crypto
  .createHmac('sha256', SECRET)
  .update(rawBody) // the raw, unparsed request body string
  .digest('hex');
const ok = crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signatureHeader));
```

Reject any request whose signature does not match.

## Publishing (manual follow-up — out of scope)

`npm publish` to the public npm registry is a **manual operator step** and is intentionally not performed by the platform's build or CI. Before publishing: bump the version, run `npm run prepublishOnly`, and publish from an account with 2FA enabled.

## Live verification checklist (manual)

1. Install the built node into a local n8n instance.
2. Add OmniAgent API credentials (base URL + API key).
3. Activate a workflow with the OmniAgent Trigger; confirm a subscription appears under `/api/webhooks` on the platform.
4. Emit a test event (e.g. trigger a security alert) and confirm the workflow fires.
5. Deactivate the workflow; confirm the subscription is removed.
