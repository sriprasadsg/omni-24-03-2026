# Phase 62: Remediation SLA Settings UI - Pattern Map

**Mapped:** 2026-08-10
**Files analyzed:** 4 (1 new component, 1 modified component, 1 modified service file, 1 new test file)
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `components/RemediationSlaSettings.tsx` (new) | component | CRUD (single-value fetch + patch) | `components/EvidenceSettings.tsx` | exact (verbatim clone target) |
| `components/SettingsDashboard.tsx` (modified) | component / router-tab-shell | request-response (tab switch) | itself, `'evidence'` tab block (same file, different lines) | exact |
| `services/apiService.ts` (modified) | service (API client) | request-response (fetch wrapper) | `fetchStalenessThreshold`/`saveStalenessThreshold` (same file, lines 4583-4600) | exact |
| `src/__tests__/RemediationSlaSettings.test.tsx` (new) | test | request-response (mocked fetch/patch) | `src/__tests__/ITAMCatalogPanel.test.tsx` | role-match (mock-shape only; component shape differs) |

## Pattern Assignments

### `components/RemediationSlaSettings.tsx` (component, CRUD)

**Analog:** `components/EvidenceSettings.tsx` (full file, 70 lines) — this is a byte-for-byte structural clone target per CONTEXT.md/UI-SPEC.md; only variable names, API calls, and copy strings change (plus one documented className deviation).

**Full source to clone from** (`components/EvidenceSettings.tsx:1-70`):
```typescript
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

    return (
        <div className="space-y-6">
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 p-4">
                <p className="text-sm font-semibold text-gray-900 dark:text-white mb-4">Evidence Quality</p>
                <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Staleness Threshold
                    </label>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                        Automated evidence older than this many days is flagged as stale.
                    </p>
                    <div className="flex items-center">
                        <input
                            type="number"
                            min={1}
                            max={365}
                            value={threshold}
                            onChange={e =>
                                setThreshold(Math.min(365, Math.max(1, parseInt(e.target.value, 10) || 1)))
                            }
                            className="w-24 px-3 py-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-gray-100"
                        />
                        <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">days</span>
                    </div>
                    {!isValid && (
                        <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                            Must be between 1 and 365 days.
                        </p>
                    )}
                </div>
                <div className="mt-4">
                    <button
                        onClick={handleSave}
                        disabled={!isValid || saving}
                        className="px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {saving ? 'Saving...' : 'Save Threshold'}
                    </button>
                </div>
            </div>
        </div>
    );
};
```

**Required substitutions when cloning (per 62-UI-SPEC.md Component-Level Build Notes, all locked, none discretionary):**

| In clone source | Replace with |
|---|---|
| `EvidenceSettings` (component name) | `RemediationSlaSettings` |
| `threshold` / `setThreshold` (state var) | `windowDays` / `setWindowDays` |
| `api.fetchStalenessThreshold().then(d => setThreshold(d.thresholdDays ?? 7))` | `api.fetchRemediationSlaWindow().then(d => setWindowDays(d.windowDays ?? 7))` |
| `api.saveStalenessThreshold(threshold)` | `api.saveRemediationSlaWindow(windowDays)` |
| `'Evidence Quality'` (section label) | `'Remediation SLA'` — **and** its `<p>` className must be `text-sm font-medium` NOT `text-sm font-semibold` (UI-SPEC's declared 2-weight-ceiling typography deviation — this is the only className change in the whole clone) |
| `'Staleness Threshold'` (field label) | `'At-Risk Window'` |
| `'Automated evidence older than this many days is flagged as stale.'` (helper text) | `Tasks with fewer than this many days until their due date are flagged "at risk".` |
| `'Staleness threshold updated'` (success toast) | `'SLA window updated'` |
| `'Failed to save threshold — please try again'` (error toast) | unchanged — identical string, intentional per D-04 |
| `'Save Threshold'` / `'Saving...'` (button label) | `'Save SLA Window'` / `'Saving...'` (unchanged) |
| `'Must be between 1 and 365 days.'` (validation msg) | unchanged — identical string |
| `days` suffix, `min={1}`/`max={365}` clamp, `isValid` expression | unchanged — copy verbatim |

No other lines change. Imports (`React, { useState, useEffect }`, `* as api`, `showToast`) stay identical in shape.

---

### `components/SettingsDashboard.tsx` (component, request-response — tab shell, 3 edits)

**Analog:** the file's own `'evidence'` tab wiring (self-referential — same file, three separate touch points).

**Edit 1 — `SettingsView` union type** (`components/SettingsDashboard.tsx:65`):
```typescript
type SettingsView = 'users' | 'roles' | 'apiKeys' | 'integrations' | 'alerts' | 'infrastructure' | 'dataSources' | 'subscription' | 'appearance' | 'email' | 'maintenance' | 'voiceBot' | 'security' | 'evidence';
```
Append `| 'remediation'`.

**Edit 2 — icon import** (`components/SettingsDashboard.tsx:4`):
```typescript
import { CogIcon, UsersIcon as Users2Icon, ShieldLockIcon, KeyIcon, AlertTriangleIcon, DatabaseIcon, BrainCircuitIcon, PaintbrushIcon, MailIcon, CalendarIcon, ClockIcon } from './icons';
```
Add `ClipboardListIcon` to this import list (confirmed present at `components/icons.tsx:76`).

**Edit 3 — tab button, insert immediately after the "evidence" button** (`components/SettingsDashboard.tsx:288-290`):
```typescript
<button onClick={() => setActiveView('evidence')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'evidence' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
    <ClockIcon size={18} className="mr-2" /> Evidence
</button>
```
New button (unrestricted — outside any `canManageSettings`/`isSuperAdmin` gate, per D-01):
```typescript
<button onClick={() => setActiveView('remediation')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'remediation' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
    <ClipboardListIcon size={18} className="mr-2" /> Remediation
</button>
```

**Edit 4 — panel mount, insert immediately after** (`components/SettingsDashboard.tsx:354-356`):
```typescript
{activeView === 'evidence' && (
    <EvidenceSettings />
)}
```
New mount:
```typescript
{activeView === 'remediation' && (
    <RemediationSlaSettings />
)}
```
Plus a new named import of `RemediationSlaSettings` from `./RemediationSlaSettings` alongside `EvidenceSettings`'s own import line (grep for `import { EvidenceSettings }` or similar near top of file to find exact placement).

---

### `services/apiService.ts` (service, request-response)

**Analog:** `fetchStalenessThreshold`/`saveStalenessThreshold` (`services/apiService.ts:4583-4600`).

**Full pattern to mirror:**
```typescript
export const fetchStalenessThreshold = async (): Promise<{ thresholdDays: number }> => {
    try {
        const res = await authFetch(`${API_BASE}/settings/evidence-staleness`);
        if (!res.ok) return { thresholdDays: 7 };
        return await res.json();
    } catch {
        return { thresholdDays: 7 };
    }
};

export const saveStalenessThreshold = async (thresholdDays: number): Promise<void> => {
    const res = await authFetch(`${API_BASE}/settings/evidence-staleness`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thresholdDays }),
    });
    if (!res.ok) throw new Error('Failed to save staleness threshold');
};
```

**New functions to append near this location** (note asymmetric error handling — GET soft-fails, PATCH throws — do not homogenize):
```typescript
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

`authFetch` (the auth-aware fetch wrapper both functions depend on) is defined at `services/apiService.ts:202`; `API_BASE = '/api'` is defined at `services/apiService.ts:39`. Both are already imported/in-scope within the same file — no new import needed, these are module-level consts/functions already available.

---

### `src/__tests__/RemediationSlaSettings.test.tsx` (test, request-response)

**Analog:** `src/__tests__/ITAMCatalogPanel.test.tsx` — for the **mock shape only** (component internals differ; ITAMCatalogPanel is a list/CRUD panel, RemediationSlaSettings is a single-field settings form matching `EvidenceSettings.tsx`'s shape instead).

**Mock-shape pattern to copy** (`src/__tests__/ITAMCatalogPanel.test.tsx:1-19`):
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const fetchCatalogEntities = vi.fn();
const createCatalogEntity = vi.fn().mockResolvedValue({ id: 'mf-1', name: 'Dell', tenantId: 't1' });
const deleteCatalogEntity = vi.fn().mockResolvedValue(undefined);

vi.mock('../../services/apiService', () => ({
  fetchCatalogEntities: (...args: unknown[]) => fetchCatalogEntities(...args),
  createCatalogEntity: (...args: unknown[]) => createCatalogEntity(...args),
  deleteCatalogEntity: (...args: unknown[]) => deleteCatalogEntity(...args),
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { CatalogPanel } from '../../components/itam/CatalogPanel';
```

**Adapt for RemediationSlaSettings** — mock only the two new API functions and `showToast`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const fetchRemediationSlaWindow = vi.fn();
const saveRemediationSlaWindow = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchRemediationSlaWindow: (...args: unknown[]) => fetchRemediationSlaWindow(...args),
  saveRemediationSlaWindow: (...args: unknown[]) => saveRemediationSlaWindow(...args),
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { RemediationSlaSettings } from '../../components/RemediationSlaSettings';
```

Required assertions per RESEARCH.md's Wave 0 test map: renders with label/icon, pre-fills fetched `windowDays`, Save calls PATCH wrapper + success toast on 2xx, save failure (any, including 403) shows the generic error toast, client clamp disables Save / shows validation message outside 1-365.

Note: no `SettingsDashboard*.test.tsx` file exists in the repo (confirmed via search) — this phase does not need to add SettingsDashboard-level integration tests to satisfy SLA-03; a targeted assertion in the new component's own test file is sufficient per RESEARCH.md.

---

## Shared Patterns

### Auth-aware fetch wrapper
**Source:** `services/apiService.ts:202` (`authFetch`), `services/apiService.ts:39` (`API_BASE = '/api'`)
**Apply to:** `fetchRemediationSlaWindow`/`saveRemediationSlaWindow` — use `authFetch` exactly as `fetchStalenessThreshold`/`saveStalenessThreshold` do; never a bare `fetch`.

### Toast notifications
**Source:** `utils/toast.ts` (`showToast`, global CustomEvent bus — already wired via `ToastContainer` app-wide)
**Apply to:** `RemediationSlaSettings.tsx`'s `handleSave` try/catch, identical call shape to `EvidenceSettings.tsx:20,22`:
```typescript
showToast('SLA window updated', 'success');
// ...
showToast('Failed to save threshold — please try again', 'error');
```

### Unrestricted settings tab (no client-side admin gate)
**Source:** `components/SettingsDashboard.tsx:288-290` (the `'evidence'` button, rendered outside the `canManageSettings` block)
**Apply to:** the new `'remediation'` tab button and its panel mount — per D-01/D-04, do NOT wrap either in `canManageSettings`/`isSuperAdmin`/any permission conditional. The backend's `_require_admin` gate (PATCH-only, in `backend/compliance_remediation_sla_endpoints.py`) is the sole access-control boundary; the frontend deliberately shows the tab/button to every authenticated user and lets a non-admin's PATCH 403 surface as the generic error toast.

### Numeric range clamp (1-365)
**Source:** `components/EvidenceSettings.tsx:13,45-47` (`isValid` expression + `onChange` clamp)
**Apply to:** `RemediationSlaSettings.tsx` verbatim — same bounds, same clamp expression:
```typescript
const isValid = windowDays >= 1 && windowDays <= 365;
// ...
onChange={e => setWindowDays(Math.min(365, Math.max(1, parseInt(e.target.value, 10) || 1)))}
```

## No Analog Found

None — all 4 files have a strong, verified, byte-for-byte-clonable analog. This phase is a verbatim clone with locked copy substitutions; there is no genuinely novel pattern requiring a fallback to RESEARCH.md's synthesized examples.

## Metadata

**Analog search scope:** `components/` (root), `services/apiService.ts`, `src/__tests__/`
**Files read in full:** `components/EvidenceSettings.tsx` (70 lines), `components/SettingsDashboard.tsx` (lines 1-360, targeted), `services/apiService.ts` (lines 4583-4600, targeted via grep), `components/icons.tsx` (line 76, targeted via grep), `src/__tests__/ITAMCatalogPanel.test.tsx` (lines 1-50)
**Pattern extraction date:** 2026-08-10
</content>
