# zapier-omniagent

Zapier Platform CLI app for the **OmniAgent GRC platform**. The **GRC Event** REST Hook trigger starts a Zap whenever your OmniAgent instance emits a subscribed event.

## Supported events

| Event | Value |
|-------|-------|
| Agent Offline | `agent.offline` |
| Security Alert | `security.alert` |
| Compliance Violation | `compliance.violation` |

## Connection setup

The app uses custom API-key authentication:

- **Base URL** — your OmniAgent platform URL, e.g. `https://portal.example.com` (no trailing slash).
- **API Key** — generate one in OmniAgent under **Tenant Settings → API Keys**. The key is shown once; it is stored hashed on the platform. It is sent as the `X-API-Key` header and carries a narrow, tenant-scoped `api-integration` role.

The connection test calls `GET /api/webhooks` with your key. To revoke access, delete the key in the same Tenant Settings screen.

## How the trigger works

- **Subscribe** (Zap turned on): `POST /api/webhooks` registers Zapier's catch-hook URL for the selected event; the returned subscription `id` is persisted by Zapier.
- **Unsubscribe** (Zap turned off): `DELETE /api/webhooks/{id}` removes the subscription — this is what prevents duplicates across re-enables.
- **Test trigger** (Zap editor): `GET /api/webhooks/{id}/deliveries` returns recent deliveries as sample data.

## Verifying inbound authenticity (X-Webhook-Signature)

Every delivery from the platform is signed when the webhook has a secret (auto-generated at subscription time):

```
X-Webhook-Signature: sha256=<hex digest>
```

The digest is `HMAC-SHA256(secret, raw_request_body)` over the **exact raw body bytes**. In a Code step you can verify:

```javascript
const crypto = require('crypto');
const expected = 'sha256=' + crypto
  .createHmac('sha256', SECRET)
  .update(rawBody)
  .digest('hex');
const ok = crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signatureHeader));
```

Reject any request whose signature does not match.

## Local development

```bash
npm install
npm test            # offline unit tests (mocked HTTP — no Zapier account needed)
npx zapier validate # schema validation of the exported App object
```

## Deployment (manual follow-up — out of scope)

`zapier push` and Zapier App Directory submission are **manual operator steps** performed with a Zapier developer account; they are intentionally not part of the platform's build or CI. After pushing, wire a test Zap with the GRC Event trigger and confirm it fires on a real platform event.
