# Phase 76 - UI Review

**Audited:** 2026-10-15
**Baseline:** abstract 6-pillar standards (no UI-SPEC.md)
**Screenshots:** not captured (code-only audit; no dev server started, per orchestrator notes)
**Interaction captures:** off

Scope: Phase 76 frontend is limited to `utils/catalogueAccess.ts` (manifest reader), `components/Sidebar.tsx` and `App.tsx` (nav and hash routes read `shared/catalogue-access.json`). Everything else is backend. Spec C6 tenant-switch code in the same files is later work and is not scored here.

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 2/4 | Rejected navigation and 403s have no user-facing message |
| 2. Visuals | 3/4 | No visual change; sidebar built from the manifest in manifest order |
| 3. Color | 3/4 | Not touched by this phase; no regression found |
| 4. Typography | 3/4 | Not touched by this phase; no regression found |
| 5. Spacing | 3/4 | Not touched by this phase; no regression found |
| 6. Experience Design | 2/4 | Backend now returns 403 to roles whose UI still requests or shows the data |

**Overall: 16/24** (visual pillars 2-5 are inferred from an unchanged surface, not measured, since no screenshots were taken)

## Top 3 Priority Fixes

1. **Startup fetches ignore the new read rules** - Roles that lose a read (viewer on agents and patches, non-admins on integrations and infrastructure) get 403s on every app load. `App.tsx:495-515` `ifOn(...)` only checks tenant feature switches, and the view permission is only passed through `switchedOnFor`. Fix: skip each fetch unless `holds(viewPermission(view))`, and have the fallback return an empty value. Do not toast.
2. **Dead sidebar items and tabs for roles without the manifest read** - The 76-06..12 summaries list nav items still visible to roles that now get 403 (PAM needs `manage:settings` even for reads, Subscription/Invoices/Payment/Knowledge Base, FinOps, jobs, agent detail tabs). Sidebar filters by `item.permission` (`Sidebar.tsx:244`), but several catalogues have `read` lists differing from `permission`. Fix: have the reader expose the read permission (`CatalogueEntry.read`) and filter by it. Hide the agent detail tabs for roles without `view:agents`.
3. **Silent denial in `handleSetCurrentView`** - `App.tsx:1172-1186` only calls `console.warn` and leaves the user on the same page, so a hash or deep-link to a blocked view looks like a broken link. Also `viewPermission(view) as Permission` casts away an undefined result. Fix: show a "You do not have access to X" toast or an access-denied panel, and fail closed when no permission resolves.

## Detailed Findings

### Pillar 1: Copywriting (2/4)
- WARNING `App.tsx:1182`: the only feedback to a denied view is `console.warn`; the code comment says "Optionally show an error message". No user-facing copy exists for permission denial.
- WARNING: summaries note ITAM `RequestsPanel`/`LifecyclePanel` treat a 403 on `/api/ticketing/config` as "ticketing unavailable", and `PrivacyDashboard` shows the default location-tracking value instead of the tenant's. Both show misleading copy/state rather than "you lack permission".
- Nav labels come from the manifest (`label`); no generic labels introduced.

### Pillar 2: Visuals (3/4)
- `NAV_GROUPS` in `utils/catalogueAccess.ts` keeps manifest array order, so the sidebar order is stable; drift is checked by `findNavDrift` and tests (`src/__tests__/catalogueAccess.test.ts`).
- WARNING: items that lead only to 403 content appear as normal, active-looking items (see Experience Design).
- Not verified visually (no screenshots).

### Pillar 3: Color (3/4)
- No color changes in this phase's files. Not measured.

### Pillar 4: Typography (3/4)
- No typography changes in this phase's files. Not measured.

### Pillar 5: Spacing (3/4)
- No spacing changes in this phase's files. Not measured.

### Pillar 6: Experience Design (2/4)
- BLOCKER-level for quality of the roles affected, not for the flows of admins: `App.tsx:508-510` startup loads (`fetchIntegrations`, `fetchInfrastructure`, `fetchDataSources`, `fetchAgents`, `fetchAgentUpgradeJobs`, `fetchPatches`) are gated by tenant feature switches, not by the guarded read permission, so restricted roles hit 403s each load. They fall back through `Promise.allSettled`/`getResult` with `console.warn`, so nothing crashes, but this is noise and wasted requests.
- WARNING: `Sidebar.tsx:244` filters by the single `permission` string, while the backend guard uses `read`/`write` lists. Mismatched items stay visible: certificates (view:assets read, manage:settings write, so every change 403s), PAM (manage:settings for reads), billing/payments/knowledge/finops pages, viewer on agent/patch/jobs catalogues.
- WARNING: agent detail tabs (telemetry, detections, scans, instruction history, agentic decisions) call guarded reads and should be hidden for roles without `view:agents`.
- WARNING: support chat admin-to-user picker 403s for non-admins; should be hidden.
- WARNING: ITAM asset columns (purchase/warranty) are stripped for roles without `view:itam`; UI should hide the columns rather than render blanks.
- WARNING: `viewPermission(view) as Permission` (`App.tsx:1172`) casts an undefined permission; deliberately deferred to Phase 77 but remains fail-open-ish in the UI (backend is the real gate).
- Positive: hash routing now resolves case-insensitively through `viewForHash` (`App.tsx:444`), and a drift test pins nav vs presentation keys.
- Finding that belongs to later work: the `screenAllowed` and `switchedOnFor` tenant-switch logic (spec C6) in Sidebar/App is not part of this phase.

## Files Audited
- /home/azureuser/enterprise-omni-agent-ai-platform/utils/catalogueAccess.ts
- /home/azureuser/enterprise-omni-agent-ai-platform/components/Sidebar.tsx (lines 5, 181-254)
- /home/azureuser/enterprise-omni-agent-ai-platform/App.tsx (lines 239, 444, 495-515, 1160-1190)
- /home/azureuser/enterprise-omni-agent-ai-platform/shared/catalogue-access.json (existence and shape only)
- Phase 76 SUMMARY files (Phase 77 UX notes sections)
