# External Integrations

**Analysis Date:** 2026-08-12

## APIs & External Services

**WebSocket Communication:**
- Socket.io - Used for real-time bidirectional communication.
  - Client: `socket.io-client`

**Authentication:**
- SimpleWebAuthn - For WebAuthn/FIDO2 authentication.
  - SDK/Client: `@simplewebauthn/browser`

## Data Storage

**Databases:**
- Not directly exposed in the frontend code. Likely handled via backend APIs accessed via `axios`.

**File Storage:**
- Local filesystem/browser storage used via Vite during build.

**Caching:**
- Not detected.

## Authentication & Identity

**Auth Provider:**
- Custom approach using `UserContext` (`src/contexts/UserContext.tsx`).
- WebAuthn integration via `@simplewebauthn/browser`.

## Monitoring & Observability

**Error Tracking:**
- Not explicitly detected in the dependency list.

**Logs:**
- Not detected.

## CI/CD & Deployment

**Hosting:**
- Not specified.

**CI Pipeline:**
- Not specified.

## Environment Configuration

**Required env vars:**
- None identified in the provided file list (typically in `.env` files which are not read).

**Secrets location:**
- Not exposed.

## Webhooks & Callbacks

**Incoming:**
- WebSocket events via Socket.io.

**Outgoing:**
- API calls via `axios`.

---

*Integration audit: 2026-08-12*
