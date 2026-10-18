---
status: testing
phase: 76-catalogue-manifest-backend-route-enforcement
source: [76-VERIFICATION.md]
started: 2026-10-18T18:04:21Z
updated: 2026-10-18T18:04:21Z
---

## Current Test

number: 1
name: Enrolled agent still works after deploy (agent route group)
expected: |
  After the backend is restarted on this checkout, an enrolled Rust agent registers, heartbeats, polls /api/agentic-tasks and /api/response/tasks/{agent_id}, downloads an installer from /api/software/download/{filename}, and posts telemetry/scan results with no 401/403; the UI agent list is unchanged.
awaiting: user response

## Tests

### 1. Enrolled agent still works after deploy (agent route group)
expected: After the backend is restarted on this checkout, an enrolled Rust agent registers, heartbeats, polls /api/agentic-tasks and /api/response/tasks/{agent_id}, downloads an installer from /api/software/download/{filename}, and posts telemetry/scan results with no 401/403; the UI agent list is unchanged.
result: [pending]

### 2. Tenant admin and platform staff reads of the five gated tenant GETs
expected: Signed in as a tenant admin, then as Platform Support and Platform Billing, GET /api/tenants/{id}/allowlist, /enrollment-keys, /license (and, for tenant admin only, /email/config and /email/preferences) return 200 with data and the Tenant Management and Settings screens render them.
result: [pending]

### 3. Viewer, itam_viewer and analyst refusals on live data
expected: These roles receive 403 from the same five tenant GETs, the installer download, GET /api/response/tasks/{agent_id} and GET /api/agent-chat/sessions, and no screen they can still reach shows a blank page or crash because of it.
result: [pending]

### 4. Tenant shell still renders after the GET /api/tenants/me projection (CR-01)
expected: Logged in as viewer and tenant admin, the app shell shows tenant name, tier and branding; no screen is missing a field. The endpoint now returns only id, name, subscriptionTier and branding.
result: [pending]

### 5. Registration key exposure decision (CR-01)
expected: Decide whether tenant registrationKey values were exposed to non-admin roles while the old GET /api/tenants/me was live (the backend running now still serves the old response until restart) and rotate them if so.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
