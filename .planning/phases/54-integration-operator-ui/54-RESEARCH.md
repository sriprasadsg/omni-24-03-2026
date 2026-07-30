# Phase 54 — Integration & Operator UI — RESEARCH

Codebase-grounded. Refs verified 2026-07-30.

## 1. Existing-surface audit

| Surface | State | Use in 54 |
|---------|-------|-----------|
| Backend endpoints from 50-53 | scan verdict POST (`agent_security_scan_endpoints`, 50-04); vuln GET (`vuln_endpoints`, 51); fim-events GET/POST (`agent_security_endpoints`, 52); remediation approve/deny + audit GET (`remediation_control_endpoints`, 53-04); playbook CRUD (`enhanced_playbook_endpoints`) | Consume. Add only the gaps: GET scan-findings list, GET remediation-queue, POST trigger-scan, GET fim-status (D-03). |
| `agent_instructions` queue | Phase-53 dispatch inserts `{type, agent_id, payload, status:"pending"}`; the agent polls it; scan/action arms exist (50-05/53-02) | trigger-scan inserts a `scan_file`/`vuln-scan`/`fim` instruction here (reuse). |
| `components/PlaybookManager.tsx` / `PlaybookBuilder.tsx` / `ExecutePlaybookModal.tsx` | existing playbook library UI | Reuse in the Playbooks tab (D-04). |
| `components/RemediationDashboard.tsx`, vuln list components | existing remediation/vuln UI | Reference/reuse patterns; do not rebuild. |
| `types.ts` AppView + permissions | has `vulnerabilities`, `playbooks`, `remediationWorkflow`; perms `manage:active_response`, `view:vulnerabilities` | Add `nativeSecurity` AppView; gate on `manage:active_response` (D-02). |
| App.tsx / Sidebar.tsx registration (49-05 pattern) | lazy import (line ~166) + `viewPermissionMap` (line ~236/369) + switch (~1916) + Sidebar entry (~417) | Clone for `nativeSecurity` (54-04). |
| `services/apiService.ts` | `authFetch` + `API_BASE`; existing fetchers (fetchFleetGeo etc.) | Add the native-security clients (54-02). |

**Net:** INT-03 is ~80% delivered by 50-53. Phase 54 adds the thin ops endpoints + the unified console UI + nav registration.

## 2. Backend ops endpoints (INT-03) — D-03

`security_ops_endpoints.py`, `APIRouter(prefix="/api/security-ops")`:
- `GET /findings` — merge/list scan verdicts (`security_scan_results`) [+ optionally reference vuln/fim counts]; tenant-scoped, paginated.
- `GET /remediation-queue` — pending/in-flight remediations (pending_approval + dispatched-not-verified), tenant-scoped.
- `POST /trigger-scan` — body `{agent_id, type: file|vuln|fim, target?}` → insert an `agent_instructions` doc `{type: "scan_file"|..., agent_id, payload}` (reuse the Phase-53 dispatch shape); check agent connectivity; return `{queued: true}`.
- `GET /fim-status` — per-agent FIM watcher status (from `agent.meta.capabilities` fim summary) + recent `fim_events` counts.
- `GET /summary` — small tenant rollup (findings by verdict, open remediations, drift count).
All gated `manage:active_response`, wrapped db, never `db._db`.

## 3. Frontend console (INT-01/02) — D-01

`NativeSecurityConsole.tsx` — a tabbed shell (reuse the tab pattern from an existing multi-tab dashboard):
- **Findings**: table/feed of scan verdicts + vuln findings + FIM events (from `/security-ops/findings`, `vuln_endpoints`, `fim-events`), filterable, paginated; a "Scan now" action (`POST /trigger-scan`).
- **Remediation Queue**: pending_approval + in-flight (from `/remediation-queue`), each with Approve/Deny buttons (`POST /api/remediation/{id}/approve|deny`, 53-04).
- **Playbooks**: embed `PlaybookManager` (D-04).
- **Audit**: the `remediation_audit` trail (`GET /api/remediation/audit`, 53-04), read-only, paginated.
Keep < 500 lines — one child component per tab.

## 4. apiService clients (54-02) — D-05

`fetchScanFindings`, `fetchRemediationQueue`, `triggerScan(agentId, type, target)`, `fetchRemediationAudit`, `approveRemediation(id)` / `denyRemediation(id)`, `fetchFimStatus`, `fetchSecuritySummary` — all `authFetch` with the standard error shape. Types for each response.

## 5. Nav registration (54-04) — D-02

Clone 49-05: `nativeSecurity` in the AppView union + `viewPermissionMap` (`nativeSecurity: 'manage:active_response'`) + App.tsx lazy import + switch case + a Sidebar entry (icon e.g. `ShieldZapIcon`/`ShieldAlertIcon` already imported). Gate `manage:active_response`.

## 6. Risk

- **Mostly integration** — low new-tech risk; main effort is the console + wiring.
- **Async scan verdicts** — trigger returns queued; refresh/poll findings (don't block).
- **Pagination** — feed + audit must be bounded.
- No new deps (backend or frontend). Reuse existing components + `authFetch`.
