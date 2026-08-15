# Phase 62: Remediation SLA Settings UI - Research

**Researched:** 2026-08-10
**Domain:** React/TypeScript settings-tab UI clone against an already-live, already-documented backend endpoint
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** New "Remediation" tab in `components/SettingsDashboard.tsx`, sibling to the existing "evidence" tab — same unrestricted-visibility pattern (not gated behind `canManageSettings`, matching how the GET endpoint has no admin gate).
- **D-02:** Tab label: exactly "Remediation" (one word, matches the codebase's existing terse tab labels like "Evidence"/"Security", not "Remediation SLA").
- **D-03:** Tab icon: `ClipboardListIcon` (from `components/icons.tsx`, already used elsewhere e.g. Sidebar's "Jobs" entry) — chosen over reusing `ClockIcon` to stay visually distinct from the adjacent Evidence tab.
- **D-04:** Non-admin behavior matches `EvidenceSettings.tsx` exactly: the Save button has no client-side role check. It's visible and clickable to every authenticated user; a non-admin who clicks Save gets the backend's 403 surfaced as the generic "Failed to save threshold — please try again" error toast. No new permission-check logic — this follows the phase's own "clone verbatim" instruction from `44-UI-SPEC.md`.
- **D-05:** Add requirement **SLA-03** to `.planning/REQUIREMENTS.md`, extending the SLA-01/SLA-02 family from Phase 44. Update `.planning/ROADMAP.md`'s Phase 999.1 entry from "Requirements: TBD" to "Requirements: SLA-03" once planned.

### Claude's Discretion

- Exact placement of the "Remediation" tab within the tab bar's left-to-right order (near "Evidence" is natural given the shared "time-threshold setting" family, but exact position wasn't specified).
- Component file name (`RemediationSlaSettings.tsx` is the obvious match to `EvidenceSettings.tsx`'s naming, but not explicitly locked).

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SLA-03 | The remediation SLA at-risk window (`GET/PATCH /api/settings/remediation-sla`, live since v3.2 Phase 44-03) is exposed in the Settings UI — extends SLA-01/SLA-02. | Confirmed against live code: backend endpoint contract (`backend/compliance_remediation_sla_endpoints.py`), clone source (`components/EvidenceSettings.tsx`), mount point (`components/SettingsDashboard.tsx`), and copywriting contract (`44-UI-SPEC.md`) all verified byte-for-byte below. See Architecture Patterns and Code Examples sections for the exact diff shape. |
</phase_requirements>

## Summary

This phase has almost no open technical questions — it is a verbatim UI clone of an existing, working component (`EvidenceSettings.tsx`) against an already-shipped, already-tested backend endpoint (`compliance_remediation_sla_endpoints.py`, registered in `router_registry.py` since Phase 44-03). All copy strings are pre-locked in `44-UI-SPEC.md`'s Copywriting Contract table. This research's job was therefore verification, not exploration: every claim in `62-CONTEXT.md`'s `<canonical_refs>` and `<code_context>` sections was checked directly against the live files rather than trusted at face value, and every one of them checked out exactly as documented — line numbers, function signatures, string literals, and behavior all match.

No new npm packages are needed. No new architectural pattern is introduced. The only genuine engineering work is: (1) two new `apiService.ts` functions mirroring `fetchStalenessThreshold`/`saveStalenessThreshold`'s exact shape but pointed at `/settings/remediation-sla` with a `windowDays` field instead of `/settings/evidence-staleness` with `thresholdDays`, (2) a new `RemediationSlaSettings.tsx` component that is `EvidenceSettings.tsx` with copy/field-name swaps only, and (3) three small edits to `SettingsDashboard.tsx` (union type, tab button, panel mount) in the exact shape the "evidence" tab already uses.

**Primary recommendation:** Clone `components/EvidenceSettings.tsx` → `components/RemediationSlaSettings.tsx` verbatim (state shape, `useEffect` fetch-on-mount, `isValid` 1-365 clamp, `handleSave` try/catch/finally, layout classes), swapping only: state variable name/copy strings per `44-UI-SPEC.md`'s locked table, and the two `apiService` function names/URLs. Wire it into `SettingsDashboard.tsx` as a third unrestricted tab (alongside "security" and "evidence") using the exact JSX shape of the "evidence" button/panel-mount pair.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Render "Remediation" tab + at-risk-window field | Browser / Client (React component) | — | Pure presentational + form-state concern; no server logic added |
| Fetch current `windowDays` on mount | Frontend Server → API / Backend | — | `apiService.fetchRemediationSlaWindow()` calls the already-live `GET /api/settings/remediation-sla`; no backend change |
| Persist updated `windowDays` | Frontend Server → API / Backend | — | `apiService.saveRemediationSlaWindow()` calls the already-live `PATCH /api/settings/remediation-sla`; no backend change |
| Enforce admin-only write | API / Backend | — | Already enforced server-side by `_require_admin` / `_SETTINGS_ADMIN_ROLES` in `compliance_remediation_sla_endpoints.py`. Per D-04, the client deliberately does **not** duplicate this check — it lets the 403 surface as a toast. |
| Client-side range validation (1-365) | Browser / Client | API / Backend (belt-and-braces) | UX-only clamp mirroring the backend's `Field(ge=1, le=365)` Pydantic validation; backend remains the source of truth (422 on violation) |
| Persistence of the window value | Database / Storage | — | `system_settings` collection, per-tenant doc with global fallback — already implemented in `compliance_remediation_sla_service.py`, untouched by this phase |

## Package Legitimacy Audit

**Not applicable — this phase installs zero new packages.** All dependencies used (`react`, `react-dom`, `typescript`, `vitest`, `@testing-library/react`) are already installed and already used by the exact files being cloned (`EvidenceSettings.tsx`, `SettingsDashboard.tsx`) and by the most recent precedent test file (`src/__tests__/ITAMCatalogPanel.test.tsx`, Phase 61). Confirmed via `package.json`:

| Package | Installed Version | Confirmed via |
|---------|-------------------|----------------|
| react / react-dom | ^19.2.0 | `package.json` [VERIFIED: package.json] |
| typescript | ~5.7 | `package.json` [VERIFIED: package.json] |
| vitest | ^3.2.4 | `package.json` [VERIFIED: package.json] |
| @testing-library/react | ^16.3.0 | `package.json` [VERIFIED: package.json] |
| tailwindcss | ^3.4.17 | `package.json` [VERIFIED: package.json] |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Standard Stack

### Core

No new libraries. This phase reuses, unchanged:

| Asset | Purpose | Confirmed |
|-------|---------|-----------|
| `React.useState`/`useEffect` | Local component state + fetch-on-mount | [VERIFIED: components/EvidenceSettings.tsx:1,6-11] |
| `utils/toast.ts`'s `showToast` | Success/error toast (CustomEvent bus, no context/prop-drilling) | [VERIFIED: utils/toast.ts:1-3,18-30] |
| `services/apiService.ts`'s `authFetch`/`API_BASE` convention | Authenticated fetch wrapper used by every existing settings call | [VERIFIED: services/apiService.ts:4583-4600] |
| Tailwind utility classes | Layout/theming, identical dark-mode class pairs used across all settings tabs | [VERIFIED: components/EvidenceSettings.tsx, SettingsDashboard.tsx] |

### Alternatives Considered

None — CONTEXT.md's `<decisions>` section locked "clone verbatim" as the explicit approach; researching or proposing an alternative UI pattern would contradict the user's Decisions and the phase's own scope framing ("this discussion only resolved *where* it lives... the entire visual/copy design was already specified").

**Installation:** None required — zero new packages.

## Architecture Patterns

### System Architecture Diagram

```
[User] --clicks "Remediation" tab--> [SettingsDashboard.tsx: activeView='remediation']
                                              |
                                              v
                              [RemediationSlaSettings.tsx mounts]
                                              |
                        useEffect on mount -> apiService.fetchRemediationSlaWindow()
                                              |
                                              v
                        authFetch(GET /api/settings/remediation-sla)
                                              |
                                              v
              [compliance_remediation_sla_endpoints.py: get_remediation_sla_settings]
                        (no admin gate) --> get_sla_at_risk_window(db, tenant_id)
                                              |
                                              v
                        {windowDays: N} <-- system_settings collection
                                              |
                                              v
                        setState(windowDays) -> renders <input> pre-filled

[User] --edits value, clicks Save--> handleSave()
                        isValid = 1 <= value <= 365  (client clamp, UX only)
                                              |
                                    apiService.saveRemediationSlaWindow(value)
                                              |
                                              v
                        authFetch(PATCH /api/settings/remediation-sla, {windowDays})
                                              |
                                              v
              [compliance_remediation_sla_endpoints.py: patch_remediation_sla_settings]
                        _require_admin(user) --> non-admin: raise 403
                                |                        |
                          admin: upsert                  v
                          system_settings doc      authFetch throws (res.ok === false)
                                |                        |
                                v                        v
                  {windowDays} returned      handleSave() catch block
                        |                     showToast('Failed to save threshold —
                        v                       please try again', 'error')
              showToast('SLA window updated', 'success')
```

### Recommended Project Structure

No new directories. Single new file at the existing flat `components/` root, matching `EvidenceSettings.tsx`'s placement (not the nested `components/itam/` pattern used by Phase 61's ITAM console — that nesting was specific to a 6-tab sub-console, not a single settings panel):

```
components/
├── EvidenceSettings.tsx           # clone source (unchanged)
├── RemediationSlaSettings.tsx     # NEW — this phase's only new component file
└── SettingsDashboard.tsx          # 3 edits: union type, tab button, panel mount
services/
└── apiService.ts                  # 2 new exported functions appended near line 4600
src/__tests__/
└── RemediationSlaSettings.test.tsx  # NEW — follows ITAMCatalogPanel.test.tsx's mock shape
```

### Pattern 1: Verbatim Settings-Panel Clone

**What:** A self-contained settings panel component: local `useState` for the numeric value + a `saving` flag, `useEffect(() => { fetch().then(setState) }, [])` on mount, a derived `isValid` boolean, a `handleSave` async function with try/catch/finally calling `showToast` on both paths.

**When to use:** Exactly this phase — adding a UI consumer for an existing single-value tenant setting that already has a GET/PATCH pair.

**Example (confirmed live, `components/EvidenceSettings.tsx` in full):**
```typescript
// Source: components/EvidenceSettings.tsx (verified live 2026-08-10)
import React, { useState, useEffect } from 'react';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';

export const EvidenceSettings: React.FC = () => {
    const [threshold, setThreshold] = useState<number>(7);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        api.fetchStalenessThreshold().then(d => setThreshold(d.thresholdDays ?? 7));
    }, []);

    const isValid = threshold >= 1 && threshold <= 365;

    const handleSave = async () => {
        if (!isValid) return;
        setSaving(true);
        try {
            await api.saveStalenessThreshold(threshold);
            showToast('Staleness threshold updated', 'success');
        } catch {
            showToast('Failed to save threshold — please try again', 'error');
        } finally {
            setSaving(false);
        }
    };
    // ...JSX: labeled numeric input (min=1 max=365, clamped onChange),
    // validation message when !isValid, Save button disabled when !isValid || saving
};
```

For `RemediationSlaSettings.tsx`, the only substantive edits are: rename `threshold`→a similarly-named state var (e.g. `windowDays`), swap the two `api.*` calls, and swap every copy string per the locked Copywriting Contract (see Code Examples below). The `isValid` range (1-365) is identical in both features — do not re-derive it, copy it.

### Pattern 2: Unrestricted Settings Tab (no `canManageSettings` gate)

**What:** Some `SettingsDashboard.tsx` tabs (`security`, `evidence`) render as standalone `<button>`s outside the `{canManageSettings && (...)}` block, meaning every authenticated user sees the tab and its content — the admin gate lives entirely server-side (PATCH-only).

**When to use:** This phase, per D-01/D-04 — the GET endpoint has no admin gate, so the tab itself must not be gated either.

**Example (confirmed live, `components/SettingsDashboard.tsx:285-290`):**
```typescript
// Source: components/SettingsDashboard.tsx (verified live 2026-08-10)
<button onClick={() => setActiveView('security')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'security' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
    <ShieldLockIcon size={18} className="mr-2" /> Security
</button>
<button onClick={() => setActiveView('evidence')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'evidence' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
    <ClockIcon size={18} className="mr-2" /> Evidence
</button>
```
Insert a third button of this exact shape immediately after the "evidence" button (natural placement per CONTEXT.md's discretion note — same "time-threshold setting" family), using `ClipboardListIcon` and `activeView === 'remediation'`.

Panel mount (confirmed live, `SettingsDashboard.tsx:354-356`):
```typescript
{activeView === 'evidence' && (
    <EvidenceSettings />
)}
```
Add `{activeView === 'remediation' && <RemediationSlaSettings />}` immediately after.

`SettingsView` union type (confirmed live, `SettingsDashboard.tsx:65`):
```typescript
type SettingsView = 'users' | 'roles' | 'apiKeys' | 'integrations' | 'alerts' | 'infrastructure' | 'dataSources' | 'subscription' | 'appearance' | 'email' | 'maintenance' | 'voiceBot' | 'security' | 'evidence';
```
Append `| 'remediation'`.

### Anti-Patterns to Avoid

- **Adding a client-side role check before Save:** Explicitly forbidden by D-04. Every other unrestricted tab (`evidence`) has no such check; adding one for `remediation` alone would be an inconsistent, unrequested scope addition and would diverge from the locked "clone verbatim" instruction.
- **Reusing `fetchStalenessThreshold`/`saveStalenessThreshold` directly with a different URL parameter:** Don't parameterize the existing Evidence functions to serve two purposes — write two new, separately-named functions (`fetchRemediationSlaWindow`/`saveRemediationSlaWindow`) mirroring their shape. This keeps the two features' client code independently evolvable, matching how `EvidenceSettings.tsx` and other settings panels already each own their own fetch/save pair rather than sharing a generic "settings value" abstraction.
- **Nesting the new component under `components/itam/`:** That subdirectory is Phase 61's ITAM-console-specific pattern (a 6-tab sub-console with its own internal routing). This is a single flat settings panel; it belongs at `components/` root next to `EvidenceSettings.tsx`, its direct sibling.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Numeric range validation UX | A new validation library/hook | The existing inline `isValid = x >= 1 && x <= 365` + clamped `onChange` pattern from `EvidenceSettings.tsx` | Already proven, already matches the backend's exact bound (`Field(ge=1, le=365)`); introducing a validation library for one field would be pure overhead |
| Toast notifications | A new toast state/portal | `utils/toast.ts`'s `showToast()` (global CustomEvent bus) | Already wired app-wide via `ToastContainer`; every existing settings panel uses this exact call |
| Auth-aware fetch | A new fetch wrapper | `services/apiService.ts`'s `authFetch`/`API_BASE` | Every other `apiService.ts` function (4600+ lines of precedent) uses this; a bespoke fetch call would break token-refresh/auth-header consistency |
| Admin-only write enforcement | Any client-side `hasPermission`/`canManageSettings` check on the Save button | The backend's existing `_require_admin`/`_SETTINGS_ADMIN_ROLES` gate, surfaced as a caught 403 → error toast | D-04 explicitly forbids client-side duplication of this check for this feature; the backend is already the sole source of truth |

**Key insight:** There is no genuinely novel problem in this phase. Every "don't hand-roll" item here is really "don't deviate from the already-established sibling pattern" — the risk in this phase is scope creep (adding validation, permission logic, or structural patterns not present in the clone source), not missing capability.

## Common Pitfalls

### Pitfall 1: Forgetting to update all three `SettingsDashboard.tsx` touch points
**What goes wrong:** Adding the component and the `apiService` functions but missing one of the three required edits (union type / tab button / panel mount) — most commonly the `SettingsView` union type, since TypeScript will only catch this as a type error at the `setActiveView('remediation')` call site, not silently at runtime.
**Why it happens:** The three edits are non-adjacent (lines ~65, ~285-296, ~354 per CONTEXT.md, confirmed accurate against the live file this session) and easy to do two-of-three during a quick edit pass.
**How to avoid:** Grep for `'evidence'` in `SettingsDashboard.tsx` after editing — it should return exactly the same number of matches as `'remediation'` (union member, button `onClick`/comparison, panel-mount comparison — 3+ occurrences each, exact count depends on how many string literal comparisons vs template usages exist).
**Warning signs:** `npx tsc --noEmit` failing on `Argument of type '"remediation"' is not assignable to parameter of type 'SettingsView'`, or the tab rendering but clicking it does nothing (panel-mount conditional missing).

### Pitfall 2: Copy string drift from the locked Copywriting Contract
**What goes wrong:** Paraphrasing or "improving" the locked strings (e.g., "At Risk Window" instead of "At-Risk Window", or a different helper-text wording) instead of copying them verbatim from `44-UI-SPEC.md`.
**Why it happens:** The strings live in a different phase's directory (`44-remediation-sla-escalation/44-UI-SPEC.md`), one hop away from this phase's own CONTEXT.md, which only reproduces them in one already-quoted block — easy to work from memory on a second pass instead of re-checking the source.
**How to avoid:** Copy the exact table row from `44-UI-SPEC.md` line 105 (also duplicated verbatim in `62-CONTEXT.md`'s `<canonical_refs>` section) character-for-character: section label "Remediation SLA", field label "At-Risk Window", helper text `Tasks with fewer than this many days until their due date are flagged "at risk".`, suffix "days", validation copy "Must be between 1 and 365 days.", button label "Save SLA Window", success toast "SLA window updated", error toast "Failed to save threshold — please try again".
**Warning signs:** A plan-checker or code-review pass flagging string mismatches against the UI-SPEC.

### Pitfall 3: `fetchRemediationSlaWindow` throwing instead of soft-failing on GET errors
**What goes wrong:** Writing the new GET wrapper to `throw` on a non-ok response, unlike its clone source.
**Why it happens:** `saveStalenessThreshold` (PATCH) *does* throw on failure (`if (!res.ok) throw new Error(...)`), which is the version most people reach for by pattern-matching "API call → throw on failure." But `fetchStalenessThreshold` (GET) does the opposite — it swallows both HTTP-not-ok and network-exception cases and returns a hardcoded default (`{ thresholdDays: 7 }`), confirmed live at `services/apiService.ts:4583-4591`.
**How to avoid:** Mirror each function's error-handling shape independently: `fetchRemediationSlaWindow` should soft-fail with a sane default (e.g. `{ windowDays: 7 }`, matching `44-UI-REVIEW.md`/`compliance_remediation_sla_service.py`'s documented default), `saveRemediationSlaWindow` should throw on `!res.ok` so `handleSave`'s catch block can produce the error toast.
**Warning signs:** A non-admin (or a user hitting a transient network blip) sees a broken/blank settings panel on load instead of a pre-filled default value, because the GET call threw with no caller-side catch.

## Code Examples

### `apiService.ts` — new functions (mirror `fetchStalenessThreshold`/`saveStalenessThreshold` exactly)

```typescript
// Source: services/apiService.ts:4583-4600 (verified live 2026-08-10) — pattern to mirror
// New functions to add near this location, following the identical shape:
export const fetchRemediationSlaWindow = async (): Promise<{ windowDays: number }> => {
    try {
        const res = await authFetch(`${API_BASE}/settings/remediation-sla`);
        if (!res.ok) return { windowDays: 7 };
        return await res.json();
    } catch {
        return { windowDays: 7 };
    }
};

export const saveRemediationSlaWindow = async (windowDays: number): Promise<void> => {
    const res = await authFetch(`${API_BASE}/settings/remediation-sla`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ windowDays }),
    });
    if (!res.ok) throw new Error('Failed to save remediation SLA window');
};
```
Note: the default fallback value (7) is a UI-only placeholder shown before the real fetch resolves or on soft-fail; it does not need to match the backend's own default exactly (that default lives in `compliance_remediation_sla_service.get_sla_at_risk_window` and is not documented in this phase's scope — do not hardcode assumptions about it beyond "a reasonable placeholder").

### Backend contract being consumed (unchanged, confirmed live)

```python
# Source: backend/compliance_remediation_sla_endpoints.py (verified live 2026-08-10) — DO NOT MODIFY
class SlaWindowUpdate(BaseModel):
    windowDays: int = Field(ge=1, le=365)

@router.get("/api/settings/remediation-sla")
async def get_remediation_sla_settings(current_user=Depends(get_current_user)):
    # No admin gate — returns {"windowDays": window}

@router.patch("/api/settings/remediation-sla")
async def patch_remediation_sla_settings(body: SlaWindowUpdate, current_user=Depends(get_current_user)):
    # _require_admin(current_user) raises HTTPException(403) for non-admin roles
    # Pydantic returns 422 for windowDays outside [1, 365]
    # Returns {"windowDays": body.windowDays} on success
```

## State of the Art

Not applicable in the "framework evolved" sense — this is an internal-consistency clone, not a library-currency question. The one relevant "state of the art" fact is internal: Phase 61 (the most recently shipped phase, 2026-08-09) introduced a *nested* `components/itam/` directory pattern for a multi-tab sub-console. That pattern is **not** applicable here — this phase's single settings panel belongs at the flat `components/` root next to its direct clone source, matching every other `SettingsDashboard.tsx` tab (`EvidenceSettings.tsx`, `SecuritySettings.tsx`, etc., all flat).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The GET wrapper's soft-fail default value should be `{ windowDays: 7 }` (matching Evidence's `thresholdDays: 7` placeholder) rather than some other number | Pitfall 3 / Code Examples | Low — this is a UI-only placeholder shown for a fraction of a second before the real fetch resolves, or on a network error; any reasonable in-range default (1-365) is functionally equivalent and does not affect the persisted backend value. Confirm with the planner/implementer if a different placeholder is preferred, but do not block on it. |

**If this table is empty:** N/A — see A1 above. All other claims (file contents, line numbers, function signatures, locked copy strings) were directly verified against the live repository this session, not assumed.

## Open Questions

None. CONTEXT.md's canonical_refs and code_context sections were each checked against the live files this session (`components/EvidenceSettings.tsx`, `components/SettingsDashboard.tsx`, `services/apiService.ts`, `backend/compliance_remediation_sla_endpoints.py`, `backend/router_registry.py`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `44-UI-SPEC.md`) and all matched exactly as documented — line numbers, string literals, function signatures, and the admin-role set. There is no gap between what CONTEXT.md claims and what the code actually contains.

## Environment Availability

Skipped — this phase has no new external tool/service/runtime dependencies. It uses only already-installed npm packages (verified in Package Legitimacy Audit above) against an already-registered, already-running backend router entry (`router_registry.py:181`, confirmed live).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Vitest ^3.2.4 + @testing-library/react ^16.3.0 [VERIFIED: package.json] |
| Config file | `vite.config.ts` (`test:` block at line 83) |
| Quick run command | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx` |
| Full suite command | `npm test` (`vitest run`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SLA-03 | Remediation tab renders with correct label/icon and is reachable by every user | unit (render) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "renders"` | ❌ Wave 0 |
| SLA-03 | Tab shows the fetched `windowDays` value pre-filled on mount | unit (render + mocked fetch) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "fetch"` | ❌ Wave 0 |
| SLA-03 | Save calls the PATCH wrapper with the current value and shows a success toast on 2xx | unit (interaction) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "save"` | ❌ Wave 0 |
| SLA-03 | A 403 (or any save failure) surfaces the generic error toast, not a permission-specific message | unit (interaction, mocked rejected promise) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "error"` | ❌ Wave 0 |
| SLA-03 | Client-side clamp rejects values outside 1-365 (Save disabled, validation message shown) | unit (interaction) | `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx -t "validat"` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `npx vitest run src/__tests__/RemediationSlaSettings.test.tsx`
- **Per wave merge:** `npm test` (full `src/__tests__` + `components/ui/__tests__` suite — 172 passed as of the Phase 61 session baseline)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `src/__tests__/RemediationSlaSettings.test.tsx` — covers SLA-03 (new file; follow `src/__tests__/ITAMCatalogPanel.test.tsx`'s mock shape: `vi.mock('../../services/apiService', ...)` + `vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }))`)
- [ ] No shared fixtures needed — the component is self-contained (no props, no context dependency beyond the two mocked modules)
- [ ] Framework install: none — Vitest/@testing-library/react already installed and already configured for this exact class of component test (`ITAMCatalogPanel.test.tsx`, `ITAMConsole.test.tsx` precedents)

Optionally, extend `SettingsDashboard.tsx`'s own test coverage (none currently exists — confirmed via search, no `SettingsDashboard*.test.tsx` file present) to assert the new tab button renders and switches `activeView`, but this is not required to satisfy SLA-03 since `SettingsDashboard.tsx` currently has zero test coverage of any tab and adding full coverage for the whole file is out of this phase's scope — a targeted assertion in the new component's own test file (rendering `SettingsDashboard` and clicking the "Remediation" tab) is sufficient if the planner wants integration-level coverage.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Unchanged — `get_current_user` dependency already gates both routes; this phase adds no auth logic |
| V3 Session Management | No | Not touched by this phase |
| V4 Access Control | Yes | Already enforced server-side: `_require_admin`/`_SETTINGS_ADMIN_ROLES` on PATCH only, GET intentionally ungated (non-sensitive config). This phase's frontend must NOT add a client-side mirror of this gate per D-04 — the correct control is "let the 403 surface," not "hide the button." |
| V5 Input Validation | Yes | Backend Pydantic `Field(ge=1, le=365)` is the authoritative validator (422 on violation); the new client-side clamp is a UX convenience only, never the source of truth |
| V6 Cryptography | No | Not applicable — no secrets/crypto touched |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Non-admin bypassing the write gate via a crafted client request | Elevation of Privilege | Already mitigated server-side (`_require_admin` checked before any DB write, independent of what the UI shows/hides) — this phase does not weaken or duplicate that control |
| Cross-tenant read/write of another tenant's SLA window | Tampering / Information Disclosure | Already mitigated: `get_sla_at_risk_window(db, tenant_id)` and the PATCH handler both scope by `current_user.tenant_id`; per-tenant `system_settings` doc with `{type: "remediation_sla_at_risk"}` + `tenantId` filter, global fallback only when `tenantId` is absent from the auth context (not client-suppliable) |
| Out-of-range value injection | Tampering | Backend Pydantic `Field(ge=1, le=365)` returns 422; client clamp is defense-in-depth UX only, not the security boundary |

**Note:** No new threat surface is introduced by this phase — it consumes an existing, already-hardened API contract with no changes to backend authorization, tenant scoping, or validation logic. The above table documents the *existing* controls this UI must not accidentally weaken (e.g., by adding a client-side "if admin" conditional that could be mistaken for the real gate).

## Sources

### Primary (HIGH confidence)

- `components/EvidenceSettings.tsx` — read in full, clone source [VERIFIED: live file, 2026-08-10]
- `components/SettingsDashboard.tsx` — read in full, mount point [VERIFIED: live file, 2026-08-10]
- `services/apiService.ts:4583-4600` — `fetchStalenessThreshold`/`saveStalenessThreshold` pattern [VERIFIED: live file, 2026-08-10]
- `backend/compliance_remediation_sla_endpoints.py` — read in full, backend contract [VERIFIED: live file, 2026-08-10]
- `backend/router_registry.py:181` — confirms the router is registered (`_load(app, "compliance_remediation_sla_endpoints", "router")`) [VERIFIED: live file, 2026-08-10]
- `components/icons.tsx:76` — `ClipboardListIcon` definition confirmed present [VERIFIED: live file, 2026-08-10]
- `.planning/phases/44-remediation-sla-escalation/44-UI-SPEC.md:18,105` — locked Copywriting Contract row [VERIFIED: live file, 2026-08-10]
- `.planning/REQUIREMENTS.md:44` — SLA-03 already present in the Gap Closures section [VERIFIED: live file, 2026-08-10]
- `.planning/ROADMAP.md:805-825` — Phase 62 entry already present with Requirements: SLA-03 [VERIFIED: live file, 2026-08-10]
- `package.json` — dependency versions [VERIFIED: live file, 2026-08-10]
- `src/__tests__/ITAMCatalogPanel.test.tsx`, `src/__tests__/ITAMConsole.test.tsx` — test-mocking pattern precedent [VERIFIED: live file, 2026-08-10]

### Secondary (MEDIUM confidence)

None — no external documentation lookups were needed for this phase; every claim was verifiable directly against the live codebase.

### Tertiary (LOW confidence)

None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies; all versions confirmed directly from `package.json`
- Architecture: HIGH — verbatim clone pattern confirmed against live source and mount-point files, all line numbers and string literals verified this session
- Pitfalls: HIGH — each pitfall derived from an actual behavioral asymmetry found in the live code (e.g., GET soft-fails while PATCH throws), not speculative

**Research date:** 2026-08-10
**Valid until:** No expiry concern — this research is tied to a specific already-shipped, stable internal API and component, not a fast-moving external dependency. Re-verify only if `EvidenceSettings.tsx`, `SettingsDashboard.tsx`, or `compliance_remediation_sla_endpoints.py` change before this phase is planned/executed.
