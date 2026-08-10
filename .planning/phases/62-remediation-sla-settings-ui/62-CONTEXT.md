# Phase 62: Remediation SLA Settings UI - Context

**Gathered:** 2026-08-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the UI consumer for the already-live `GET/PATCH /api/settings/remediation-sla` endpoint (shipped in Phase 44-03, ITAM-unrelated — part of the v3.2 Remediation SLA & Escalation feature). Backend has worked since 2026-07 with zero UI; two consecutive UI audits (`44-UI-REVIEW.md`) flagged the orphaned endpoint so it wouldn't be mistaken for an oversight. This phase is pure UI — no backend changes.

</domain>

<decisions>
## Implementation Decisions

### Settings Placement
- **D-01:** New "Remediation" tab in `components/SettingsDashboard.tsx`, sibling to the existing "evidence" tab — same unrestricted-visibility pattern (not gated behind `canManageSettings`, matching how the GET endpoint has no admin gate).
- **D-02:** Tab label: exactly "Remediation" (one word, matches the codebase's existing terse tab labels like "Evidence"/"Security", not "Remediation SLA").
- **D-03:** Tab icon: `ClipboardListIcon` (from `components/icons.tsx`, already used elsewhere e.g. Sidebar's "Jobs" entry) — chosen over reusing `ClockIcon` to stay visually distinct from the adjacent Evidence tab.

### Access & Traceability
- **D-04:** Non-admin behavior matches `EvidenceSettings.tsx` exactly: the Save button has no client-side role check. It's visible and clickable to every authenticated user; a non-admin who clicks Save gets the backend's 403 surfaced as the generic "Failed to save threshold — please try again" error toast. No new permission-check logic — this follows the phase's own "clone verbatim" instruction from `44-UI-SPEC.md`.
- **D-05:** Add requirement **SLA-03** to `.planning/REQUIREMENTS.md`, extending the SLA-01/SLA-02 family from Phase 44 (this is literally that feature's deferred third piece, not a new capability). Update `.planning/ROADMAP.md`'s Phase 999.1 entry from "Requirements: TBD" to "Requirements: SLA-03" once planned.

### Claude's Discretion
- Exact placement of the "Remediation" tab within the tab bar's left-to-right order (near "Evidence" is natural given the shared "time-threshold setting" family, but exact position wasn't specified).
- Component file name (`RemediationSlaSettings.tsx` is the obvious match to `EvidenceSettings.tsx`'s naming, but not explicitly locked).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked design contract
- `.planning/phases/44-remediation-sla-escalation/44-UI-SPEC.md` — the discretionary "Settings surface" row (final row of the Copywriting Contract table) locks every string this phase needs verbatim: section label "Remediation SLA", field label "At-Risk Window", helper text "Tasks with fewer than this many days until their due date are flagged \"at risk\".", suffix "days", validation copy "Must be between 1 and 365 days.", button label "Save SLA Window", success toast "SLA window updated", error toast "Failed to save threshold — please try again" (identical to `EvidenceSettings.tsx`'s error copy). None of this is open for re-discussion.
- `.planning/phases/44-remediation-sla-escalation/44-UI-REVIEW.md` — confirms the backend endpoint has existed with no UI consumer since 44-03, flagged twice across two audit passes as a deliberate, tracked deferral (not a bug).

### Backend contract (do not modify)
- `backend/compliance_remediation_sla_endpoints.py` — `GET /api/settings/remediation-sla` returns `{windowDays: number}`, no auth gate beyond authentication. `PATCH /api/settings/remediation-sla` accepts `{windowDays: int, 1<=x<=365}` (422 on out-of-range), admin-only via `_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin", "Tenant Admin"}`, returns `{windowDays}`.
- `backend/compliance_remediation_sla_service.py` — `get_sla_at_risk_window(db, tenant_id)` is the read-side helper the GET endpoint calls; per-tenant doc with a global fallback (`{type: "remediation_sla_at_risk"}` with/without `tenantId`).

### Frontend clone source and mount point
- `components/EvidenceSettings.tsx` — the literal, verbatim clone source (state shape, validation clamp, save/error/success flow, layout classes). Only the copy strings and the two `apiService` calls change.
- `components/SettingsDashboard.tsx` — the `SettingsView` union type (line ~65) needs a new `'remediation'` member; the tab-button list (~line 285-296) needs a new button following the "evidence" tab's exact JSX shape; the panel-mount block (~line 354) needs `{activeView === 'remediation' && <RemediationSlaSettings />}`.

### Requirements
- `.planning/REQUIREMENTS.md` — where SLA-03 gets added, alongside the existing SLA-01/SLA-02 entries from Phase 44.
- `.planning/ROADMAP.md` §Backlog "### Phase 999.1: Remediation SLA Settings UI (BACKLOG)" — the phase entry itself, currently `Requirements: TBD`, `Plans: 0 plans`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `components/EvidenceSettings.tsx`: entire component structure is the clone template — `useState` for the numeric value, `useEffect` fetch-on-mount, `isValid` clamp check (1-365), `handleSave` with try/catch + `showToast`.
- `utils/toast.ts`'s `showToast` — already used identically in the clone source.
- Likely-needed `apiService.ts` client functions `fetchStalenessThreshold`/`saveStalenessThreshold` (used by `EvidenceSettings.tsx`) are the pattern to mirror for new `fetchRemediationSlaWindow`/`saveRemediationSlaWindow` functions wrapping the `/api/settings/remediation-sla` GET/PATCH.

### Established Patterns
- `SettingsDashboard.tsx`'s tab-based view switching: a `SettingsView` string-union type, `activeView` state, a row of tab `<button>`s each calling `setActiveView(...)`, and a conditional panel mount per view. Some tabs are gated behind `canManageSettings`/`canManageRBAC`/`isSuperAdmin`; others (like "evidence") are unrestricted — "remediation" follows the unrestricted group per D-01/D-04.
- Backend's "read open, write admin-gated" convention (`_SETTINGS_ADMIN_ROLES` on PATCH only) is already established across multiple settings endpoints in this codebase — this phase's frontend intentionally does not add a client-side mirror of that gate (D-04).

### Integration Points
- New component file: `components/RemediationSlaSettings.tsx` (Claude's discretion on exact name, see `<decisions>`).
- `components/SettingsDashboard.tsx`: new `SettingsView` union member, new tab button, new panel mount.
- `services/apiService.ts`: two new client functions for the GET/PATCH calls.

</code_context>

<specifics>
## Specific Ideas

The entire visual/copy design was already specified in a prior phase's UI-SPEC (see canonical refs) — this discussion only resolved *where* it lives (new Settings tab) and two behavioral details (non-admin Save behavior, requirement traceability) that the prior spec left open.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 62-remediation-sla-settings-ui (promoted from backlog item 999.1 on 2026-08-10)*
*Context gathered: 2026-08-10*
