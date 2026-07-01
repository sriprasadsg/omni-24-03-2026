---
phase: 07-evidence-lifecycle-staleness-chain-of-custody
plan: "03"
subsystem: frontend-evidence-lifecycle
tags: [staleness, chain-of-custody, frontend, settings, react, tsx]
dependency_graph:
  requires:
    - services/apiService.ts::fetchStalenessThreshold
    - services/apiService.ts::saveStalenessThreshold
    - services/apiService.ts::fetchControlAuditLog
    - services/apiService.ts::fetchEvidenceAuditLog
    - backend/compliance_evidence_lifecycle_endpoints.py::router (07-02)
    - backend/compliance_evidence_endpoints.py::get_control_evidence stale fields (07-02)
  provides:
    - components/ChainOfCustodyPanel.tsx::ChainOfCustodyPanel
    - components/EvidenceSettings.tsx::EvidenceSettings
    - components/AssetComplianceList.tsx (stale badge + days-old parenthetical)
    - components/SettingsDashboard.tsx (evidence tab wiring)
    - components/FrameworkDetail.tsx (ChainOfCustodyPanel mount gated on view:audit_log)
    - services/apiService.ts (fetchStalenessThreshold, saveStalenessThreshold, fetchEvidenceAuditLog, fetchControlAuditLog)
  affects:
    - components/FrameworkDetail.tsx
    - components/SettingsDashboard.tsx
tech_stack:
  added: []
  patterns:
    - lazy-fetch on panel expand (not on mount) with cancelled-flag cleanup
    - controlled number input with clamp to 1-365 on onChange
    - toast feedback on save success/error (showToast)
    - ChevronDownIcon with rotate-180 class instead of non-existent ChevronUpIcon
    - dynamic aria-label for accessibility on collapsible toggle
    - React.details/summary for snapshot diff display (XSS-safe via React text escaping)
key_files:
  created:
    - components/ChainOfCustodyPanel.tsx
  modified:
    - services/apiService.ts
    - components/AssetComplianceList.tsx
    - components/EvidenceSettings.tsx
    - components/SettingsDashboard.tsx
    - components/FrameworkDetail.tsx
decisions:
  - "ChainOfCustodyPanel lazily fetches on expand (not mount) using a 'fetched' sentinel flag to avoid re-fetching on collapse/re-expand"
  - "ChevronDownIcon with rotate-180 used instead of non-existent ChevronUpIcon (not exported from icons.tsx)"
  - "Stale badge uses AlertCircleIcon (already imported in AssetComplianceList) per plan instruction — avoids new import"
  - "Task 1 and Task 2 were already committed from prior session (11e7cbe and 54a24db); only Task 3 was implemented in this run"
  - "'view:audit_log' used in FrameworkDetail (not 'audit:read') per research finding #1 and PATTERNS.md"
metrics:
  duration: "~5m"
  completed: "2026-06-22"
  tasks: 3
  files: 6
status: complete
---

# Phase 07 Plan 03: Frontend Evidence Lifecycle Components Summary

**One-liner:** Stale amber badge on automated evidence, staleness threshold settings UI with 1-365 validation + toast, and a collapsible Chain-of-Custody log panel with lazy fetch gated on view:audit_log — all wired to the 07-02 backend contract.

## What Was Built

### Task 1 — services/apiService.ts + AssetComplianceList.tsx (committed 11e7cbe)

Four exported API functions added to `services/apiService.ts` after `fetchLlmSettings`:

- `fetchStalenessThreshold()` → GET `/api/settings/evidence-staleness`; returns `{ thresholdDays: 7 }` on error.
- `saveStalenessThreshold(thresholdDays)` → PATCH `/api/settings/evidence-staleness` with `Content-Type: application/json`; throws on non-ok.
- `fetchEvidenceAuditLog(evidenceId)` → GET `/api/compliance/evidence/{id}/audit-log`; returns `{ entries: [] }` on error.
- `fetchControlAuditLog(controlId)` → GET `/api/compliance/controls/{id}/audit-log`; returns `{ entries: [] }` on error.

`AssetComplianceList.tsx` stale badge (STALE-01):
- Amber pill (`bg-amber-100 text-amber-700 text-xs`) after Automated/Manual badge, rendered only when `isAutomated && ev.stale`.
- Evidence name shows ` ({ev.stale_days} days old)` parenthetical when `isAutomated && ev.stale`.
- Manual evidence never shows badge or parenthetical.
- `AlertCircleIcon` at size 10 used (already imported, avoids new import).

### Task 2 — components/EvidenceSettings.tsx + SettingsDashboard.tsx (committed 54a24db)

`EvidenceSettings.tsx` (70 lines, new file):
- Section heading "Evidence Quality" with "Staleness Threshold" label.
- Exact copywriting: "Automated evidence older than this many days is flagged as stale."
- Number input clamped to 1-365 on onChange; inline error "Must be between 1 and 365 days." when out of range.
- "Save Threshold" button (disabled when invalid or saving); "Saving..." label while in-flight.
- Calls `api.fetchStalenessThreshold()` on mount; `api.saveStalenessThreshold()` on save with `showToast` feedback.

`SettingsDashboard.tsx` minimal mount:
- `'evidence'` added to `SettingsView` type union (line 65).
- `EvidenceSettings` imported; `{activeView === 'evidence' && <EvidenceSettings />}` render guard added.
- Evidence tab nav button with `ClockIcon` positioned after Security tab.

### Task 3 — components/ChainOfCustodyPanel.tsx + FrameworkDetail.tsx (committed 694eafd)

`ChainOfCustodyPanel.tsx` (134 lines, new file):

- Props: `{ controlId: string }`.
- State: `isExpanded`, `entries`, `loading`, `error`, `fetched`.
- Lazy fetch: calls `api.fetchControlAuditLog(controlId)` only on first expand; re-collapse/re-expand does not re-fetch.
- Header always visible: `ClockIcon` + "Chain of Custody" + `(N events)`. `ChevronDownIcon` with `rotate-180` for expanded state.
- Dynamic `aria-label`: "Collapse chain of custody panel" / "Expand chain of custody panel".
- Body only when expanded: loading spinner, error message, empty state, or entry rows.
- Per-entry: action icon (PlusIcon green / RefreshCwIcon blue / TrashIcon red), actor + action label, UTC timestamp + evidence ID.
- Update entries with snapshot show `<details><summary>Show change</summary><pre>...</pre></details>` (React text, XSS-safe).

`FrameworkDetail.tsx` minimal mount:
- `import { ChainOfCustodyPanel } from './ChainOfCustodyPanel'` added.
- `const canViewCoC = hasPermission('view:audit_log')` added next to `canManageEvidence`.
- `{canViewCoC && <ChainOfCustodyPanel controlId={control.id} />}` mounted below `<AssetComplianceList />` in expanded control row.
- Permission string `'view:audit_log'` used (not `'audit:read'`).

## Verification Results

```
$ grep -c 'fetchStalenessThreshold\|saveStalenessThreshold\|fetchEvidenceAuditLog\|fetchControlAuditLog' services/apiService.ts
4

$ grep -c 'evidence-staleness' services/apiService.ts
2

$ grep -c 'ev.stale' components/AssetComplianceList.tsx
2

$ grep -c 'EvidenceSettings' components/SettingsDashboard.tsx
2

$ grep -c 'Chain of Custody' components/ChainOfCustodyPanel.tsx
1

$ grep -c 'fetchControlAuditLog' components/ChainOfCustodyPanel.tsx
1

$ grep -c 'ChevronUpIcon' components/ChainOfCustodyPanel.tsx
0

$ grep -c "hasPermission('view:audit_log')" components/FrameworkDetail.tsx
1

$ grep -c "audit:read" components/FrameworkDetail.tsx
0

$ grep -c 'ChainOfCustodyPanel' components/FrameworkDetail.tsx
2

$ wc -l components/EvidenceSettings.tsx components/ChainOfCustodyPanel.tsx components/AssetComplianceList.tsx
70 components/EvidenceSettings.tsx
134 components/ChainOfCustodyPanel.tsx
237 components/AssetComplianceList.tsx
```

TypeScript: one pre-existing error in FrameworkDetail.tsx (line 67, `'warning'` toast type — existed before this plan). No new errors introduced.

## Deviations from Plan

### Continuation: Tasks 1 and 2 pre-committed

Tasks 1 (API functions + stale badge) and Task 2 (EvidenceSettings + SettingsDashboard wiring) were already committed from a prior session:
- `11e7cbe` — Task 1 (apiService.ts + AssetComplianceList.tsx)
- `54a24db` — Task 2 (EvidenceSettings.tsx + SettingsDashboard.tsx)

This plan run executed only Task 3. Functionality is complete and identical to plan.

No other deviations — plan executed as written.

## Commits

| Hash | Task | Description |
|------|------|-------------|
| 11e7cbe | Task 1 | feat(07-03): add staleness/CoC API functions and stale badge in AssetComplianceList |
| 54a24db | Task 2 | feat(07-03): add EvidenceSettings component and Evidence tab in SettingsDashboard |
| 694eafd | Task 3 | feat(07-03): add ChainOfCustodyPanel and mount in FrameworkDetail behind view:audit_log |

## Known Stubs

None — all components are fully wired to real API endpoints from 07-02.

## Threat Surface Scan

No new network endpoints introduced in this plan (frontend only). All trust boundaries already documented in the plan's threat model:

- T-07-10 (CoC panel to unauthorized user): Mitigated — `hasPermission('view:audit_log')` gate in FrameworkDetail.tsx. Server enforces tenant isolation independently.
- T-07-11 (wrong permission string): Mitigated — `'view:audit_log'` used; `audit:read` absent (grep returns 0).
- T-07-12 (threshold client clamp bypass): Mitigated — client clamp is convenience; server enforces Field(ge=1, le=365).
- T-07-13 (XSS via snapshot JSON): Mitigated — rendered as `{JSON.stringify(...)}` inside `<pre>` (React escapes by default; no dangerouslySetInnerHTML).

## Self-Check: PASSED

- [x] components/ChainOfCustodyPanel.tsx exists (134 lines, under 500)
- [x] components/EvidenceSettings.tsx exists (70 lines, under 500)
- [x] components/AssetComplianceList.tsx stale badge present (237 lines, under 500)
- [x] SettingsDashboard.tsx has 2 refs to EvidenceSettings (import + mount)
- [x] FrameworkDetail.tsx has 2 refs to ChainOfCustodyPanel (import + mount)
- [x] FrameworkDetail.tsx uses 'view:audit_log', 0 refs to 'audit:read'
- [x] All 3 commits exist: 11e7cbe, 54a24db, 694eafd
- [x] No new TypeScript errors in touched files
- [x] Stale badge uses text-xs (WCAG-safe, not text-[10px])
