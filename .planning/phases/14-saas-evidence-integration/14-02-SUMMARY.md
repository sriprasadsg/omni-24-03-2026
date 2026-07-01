---
phase: 14-saas-evidence-integration
plan: "02"
subsystem: saas-integration
tags: [saas, oauth, evidence, compliance, react, typescript, dashboard]
dependency_graph:
  requires:
    - backend/saas_integration_endpoints.py (router at /api/saas — wave 1 output)
    - backend/saas_integration_service.py (SaaSIntegrationService — wave 1 output)
    - backend/router_registry.py (saas_integration_endpoints already registered in wave 1)
    - services/apiService.ts (authFetch)
    - utils/toast.ts (showToast)
  provides:
    - components/SaaSIntegrationsDashboard.tsx (provider cards, OAuth popup, Pull Evidence Now)
  affects:
    - Any page/nav that imports SaaSIntegrationsDashboard
tech_stack:
  added: []
  patterns:
    - OAuth 2.0 popup flow (window.open + postMessage + cleanup polling)
    - Per-item loading state via Record<string, boolean>
    - useCallback for stable fetch references in useEffect deps
    - Tailwind responsive grid (1-col mobile, 2-col md+)
key_files:
  created:
    - components/SaaSIntegrationsDashboard.tsx
  modified: []
decisions:
  - "router_registry.py already had saas_integration_endpoints registered (line 142) from wave 1 — no change needed in this wave"
  - "pollClosed interval cleans up the postMessage listener if the popup is closed without completing OAuth — prevents listener accumulation"
  - "pulling and disconnecting tracked as Record<string, boolean> keyed by connection ID — supports concurrent ops on different providers without shared boolean"
  - "confirm() dialog for Disconnect matches existing platform patterns (no modal needed for single-action confirm)"
  - "PROVIDER_CATALOG is a module-level constant (not state) — static data, never changes at runtime"
metrics:
  duration: ~2m
  completed: "2026-06-23T17:51:43Z"
  tasks_completed: 2
  files_created: 1
  files_modified: 0
status: complete
---

# Phase 14 Plan 02: SaaS Integrations Dashboard Summary

**One-liner:** React dashboard with 5 provider cards (GitHub, Jira, Okta, Google Workspace, Slack) wiring the OAuth popup flow, evidence pull, and disconnect to the wave-1 backend API.

## What Was Built

### components/SaaSIntegrationsDashboard.tsx (368 lines)

Provider catalog with 5 entries mapped to their compliance controls:

| Provider | ID | Controls |
|----------|----|---------|
| GitHub | `github` | Secure Development & Coding, Access to Source Code, Security Patch Status |
| Jira | `jira` | Change Management |
| Okta | `okta` | MFA for All Users, Identity & Authentication |
| Google Workspace | `google_workspace` | Account Security, Data Leakage Prevention |
| Slack | `slack` | Audit Logging Extension |

**Data flow:**
- `useEffect` → `fetchConnections()` → `GET /api/saas/connections` → maps provider IDs to connection state
- `connectProvider(providerId)` → `window.open(/api/saas/connect/{provider}, 'oauth', ...)` → postMessage listener for `'saas_connected'` → popup.close() + refresh
- `pullEvidence(connectionId)` → `POST /api/saas/connections/{id}/pull-evidence` → shows count in success toast
- `disconnectProvider(connectionId, providerName)` → `window.confirm()` → `DELETE /api/saas/connections/{id}` → removes from local state

**UI states:**
- Loading skeleton: 5 `animate-pulse` grey blocks during initial fetch
- Not connected: single "Connect" button (full width)
- Connected: shows last_synced, evidence_count, "Pull Evidence Now" + "Disconnect" buttons
- Pulling in-progress: SVG spinner inside "Pulling…" button, disabled state
- Disconnecting: button shows "Removing…", disabled

**Layout:** Responsive 2-column grid (`grid-cols-1 md:grid-cols-2`), each card is a white/dark-mode rounded box with header (logo + name + description + status badge), controls tags, and action row.

## Task Status

| Task | Description | Status | Commit |
|------|-------------|--------|--------|
| 1 | Register saas_integration_endpoints in router_registry.py | Pre-complete (wave 1) | cf9ad13 (wave 1) |
| 2 | Create SaaSIntegrationsDashboard.tsx | Complete | 49fd9ad |

**Note on Task 1:** Wave 1 (14-01) already added `_load(app, "saas_integration_endpoints", "router")` at line 142 of router_registry.py, after `compliance_score_endpoints`. The plan says to add it after `cookie_consent_endpoints` (line 135); lines 136-141 sit between them (access_review, cloud_checks, compliance_remediation, evidence_lifecycle, bulk_evidence, score). The registration is correct and functional.

## Deviations from Plan

None — plan executed as written. The router registration was pre-completed in wave 1 (documented in 14-01-SUMMARY.md under `key_files.modified`). The dashboard component was created fresh in this wave.

## Known Stubs

None — all 5 provider cards fetch live data from the wave-1 backend. OAuth popup, pull-evidence, and disconnect actions call real backend endpoints. Error and loading states are fully handled.

## Threat Flags

None new. The OAuth callback CSRF state-parameter gap noted in 14-01-SUMMARY (threat_flag: oauth_callback) remains open — state-nonce verification deferred to a future hardening phase. The dashboard itself introduces no new threat surface; it uses `authFetch` (bearer token) for all API calls.

## Self-Check: PASSED

- components/SaaSIntegrationsDashboard.tsx: FOUND (368 lines, under 500)
- commit 49fd9ad: FOUND
- router_registry.py line 142: saas_integration_endpoints registered (pre-existing from wave 1)
- All 5 providers present in PROVIDER_CATALOG: CONFIRMED
- Connect → window.open popup: CONFIRMED (line 109)
- Pull Evidence Now → POST with spinner: CONFIRMED (lines 139-163)
- Disconnect → DELETE with confirm: CONFIRMED (lines 167-188)
