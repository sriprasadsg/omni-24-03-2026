---
phase: 62-remediation-sla-settings-ui
reviewed: 2026-08-11T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - components/RemediationSlaSettings.tsx
  - src/__tests__/RemediationSlaSettings.test.tsx
  - services/apiService.ts
  - components/SettingsDashboard.tsx
findings:
  critical: 0
  warning: 6
  info: 3
  total: 9
status: issues_found
---

# Phase 62: Code Review Report

**Reviewed:** 2026-08-11T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the new Remediation SLA settings panel (`RemediationSlaSettings.tsx`), its two `apiService.ts` wrappers (`fetchRemediationSlaWindow` / `saveRemediationSlaWindow`), the `SettingsDashboard.tsx` tab wiring that mounts it, and the accompanying test suite. The component is a close structural clone of the existing `EvidenceSettings.tsx` panel (same state shape, same clamp logic, same soft-fail-on-GET / throw-on-PATCH asymmetry), which is documented in `62-PATTERNS.md` as an intentional "verbatim clone with locked copy substitutions." Backend authorization was spot-checked: `GET /api/settings/remediation-sla` is intentionally open to any authenticated user (non-sensitive read), and `PATCH /api/settings/remediation-sla` calls `_require_admin(current_user)` before writing, so there is no server-side authorization bypass. No hardcoded secrets, `eval`, `innerHTML`, or empty catch blocks were found in the reviewed files.

No Critical-severity issues were found. The findings below are: a UX/authorization-signaling gap (frontend never distinguishes "you lack permission" from "network blip"), a real controlled-input bug that can corrupt manually-typed values, an accessibility gap, a missing input-validation boundary on the network response, and some quality/duplication notes.

## Warnings

### WR-01: Save control has no capability check — non-admin users always get a generic, misleading failure toast

**File:** `components/SettingsDashboard.tsx:292-294`, `components/SettingsDashboard.tsx:361-363`, `components/RemediationSlaSettings.tsx:15-26`
**Issue:** The "Remediation" tab button (line 292-294) and its panel (line 361-363) render unconditionally — no `canManageSettings`/`hasPermission` guard, unlike the sibling `email`/`integrations`/`dataSources`/`alerts`/`maintenance` tabs which are wrapped in `{canManageSettings && (...)}`. The backend `PATCH /api/settings/remediation-sla` is admin-gated (`_require_admin` in `backend/compliance_remediation_sla_endpoints.py:118`, 403 for non-admins), but `RemediationSlaSettings`'s `Save SLA Window` button is only disabled by `!isValid || saving` (line 61) — never by permission. A non-admin user can freely edit the field and click Save; every attempt fails with the same generic toast (`'Failed to save threshold — please try again'`, line 22) that is also shown for genuine transient/network failures. The user has no way to learn they simply lack permission — "try again" will never succeed for them.
**Fix:** Gate the Save action (or the whole tab) on `canManageSettings`, consistent with the sibling admin-only tabs:
```tsx
{activeView === 'remediation' && (
    <RemediationSlaSettings canEdit={canManageSettings} />
)}
```
and disable/hide the input and button (or show a permission-specific message) when `canEdit` is false, so the error path is reserved for genuine failures. This same gap pre-exists in `EvidenceSettings.tsx` and is worth fixing there too, but is out of scope for this file list.

### WR-02: Controlled number input re-clamps on every keystroke — corrupts a value being retyped after clearing the field

**File:** `components/RemediationSlaSettings.tsx:44-47`
```tsx
value={windowDays}
onChange={e =>
    setWindowDays(Math.min(365, Math.max(1, parseInt(e.target.value, 10) || 1)))
}
```
**Issue:** The input is fully controlled and coerces every keystroke's value through `parseInt(...) || 1` then clamps to `[1, 365]`. If a user clears the field first (e.g. clicks into it and presses Backspace repeatedly to remove `200` before typing a new value — a very common editing pattern), the intermediate empty string `""` produces `parseInt("", 10)` → `NaN` → `NaN || 1` → `1`, so `windowDays` is immediately forced to `1` and the input re-renders showing `"1"` instead of staying empty. The user's next keystroke (e.g. `5`) is then inserted into `"1"` by the browser's cursor position rather than into an empty field, producing `"15"` or `"51"` instead of the intended `"5"`, and further digits compound the corruption. `fireEvent.change` in the test suite sets `target.value` directly to a final string and therefore never exercises this incremental-typing path, so the existing tests do not catch it.
**Fix:** Decouple the raw text the user is typing from the clamped numeric value — track a string in local state during editing and only clamp on blur/save, e.g.:
```tsx
const [raw, setRaw] = useState(String(windowDays));
// onChange: setRaw(e.target.value)  (no coercion here — allow "" mid-edit)
// onBlur: const n = clamp(parseInt(raw, 10)); setWindowDays(n); setRaw(String(n));
```

### WR-03: `<label>` is not programmatically associated with the input (accessibility)

**File:** `components/RemediationSlaSettings.tsx:33-35, 40-49`
**Issue:** `<label className="...">At-Risk Window</label>` has no `htmlFor`, and the following `<input type="number" ...>` has no matching `id`. They are siblings, not nested, so there is no implicit association either. Screen readers (and `getByLabelText`-style test queries) cannot derive an accessible name for the spin button from the visible label text — assistive-tech users only hear "spin button" with no context. The validation message at lines 52-56 is likewise not wired to the input via `aria-describedby`/`aria-invalid`, so a screen-reader user editing an out-of-range value gets no announcement of the error.
**Fix:**
```tsx
<label htmlFor="sla-window-days" className="...">At-Risk Window</label>
...
<input
    id="sla-window-days"
    aria-invalid={!isValid}
    aria-describedby={!isValid ? 'sla-window-days-error' : undefined}
    ...
/>
...
{!isValid && <p id="sla-window-days-error" ...>Must be between 1 and 365 days.</p>}
```

### WR-04: No runtime validation of the fetch/save network response shape

**File:** `services/apiService.ts:4602-4619`
**Issue:** `fetchRemediationSlaWindow` returns `await res.json()` typed as `Promise<{ windowDays: number }>` with no runtime check that the parsed JSON actually has a numeric `windowDays` field. If the backend ever returns a malformed or differently-shaped payload (e.g. `windowDays` as a string, or a different key), the type annotation only affects compile-time checking of *callers*, not the actual runtime value — `RemediationSlaSettings.tsx:10`'s `d.windowDays ?? 7` will happily pass through a non-numeric value into `useState<number>`, and every downstream comparison (`windowDays >= 1`) silently coerces rather than failing loudly. CLAUDE.md requires validating input "at system boundaries"; a network response is exactly such a boundary and currently has zero validation here.
**Fix:** Validate the shape before trusting it, e.g.:
```ts
export const fetchRemediationSlaWindow = async (): Promise<{ windowDays: number }> => {
    try {
        const res = await authFetch(`${API_BASE}/settings/remediation-sla`);
        if (!res.ok) return { windowDays: 7 };
        const data = await res.json();
        const windowDays = Number(data?.windowDays);
        return { windowDays: Number.isFinite(windowDays) ? windowDays : 7 };
    } catch {
        return { windowDays: 7 };
    }
};
```

### WR-05: Silent fetch-failure fallback is indistinguishable from a genuine value of 7 — no error signal on load failure

**File:** `components/RemediationSlaSettings.tsx:9-11`; `services/apiService.ts:4602-4610`
**Issue:** `fetchRemediationSlaWindow` swallows all GET failures (network error or non-2xx) and resolves `{ windowDays: 7 }`. This is a documented, intentional design choice (`62-UI-SPEC.md`: "silently falls back to the default and lets the user proceed"), so it is not flagged as incorrect behavior per se — but the component gives the user zero indication that the displayed `7` might be a fallback rather than their tenant's actual configured window. If an admin opens the tab during a transient backend hiccup, sees `7`, and clicks "Save SLA Window" without realizing the real (possibly very different, e.g. `30`) configured value was never loaded, the tenant's real SLA window is silently overwritten with the default — a real config-drift/data-integrity risk, even though it requires an explicit Save click to materialize.
**Fix:** At minimum, surface a distinguishable state when the GET fails (e.g. a toast or inline notice: "Could not load current SLA window — showing default"), so a save-without-noticing scenario can't silently clobber the real value:
```tsx
useEffect(() => {
    api.fetchRemediationSlaWindow()
        .then(d => setWindowDays(d.windowDays ?? 7))
        .catch(() => showToast('Could not load current SLA window', 'error'));
}, []);
```
(This also requires `fetchRemediationSlaWindow` to actually reject on failure instead of catching internally, which is a larger change — see WR-06.)

### WR-06: `useEffect`'s fetch chain has no `.catch()` — correctness depends entirely on the callee's internal try/catch

**File:** `components/RemediationSlaSettings.tsx:9-11`
**Issue:** `api.fetchRemediationSlaWindow().then(d => setWindowDays(d.windowDays ?? 7))` has no `.catch()`. This works today only because `fetchRemediationSlaWindow` happens to catch all its own errors internally and always resolves. If that internal try/catch is ever removed, refactored, or the function is swapped for a variant that can reject (a real possibility if WR-05 is fixed by making the fetch reject on failure), this call site will produce an unhandled promise rejection with zero user-facing feedback and the input will stay stuck at the default `7` state initializer.
**Fix:** Add a local `.catch()` regardless of what the callee does, so the component's correctness doesn't silently depend on an implementation detail two files away:
```tsx
useEffect(() => {
    api.fetchRemediationSlaWindow()
        .then(d => setWindowDays(d.windowDays ?? 7))
        .catch(() => {});
}, []);
```

## Info

### IN-01: `RemediationSlaSettings.tsx` is a near line-for-line duplicate of `EvidenceSettings.tsx`

**File:** `components/RemediationSlaSettings.tsx` (whole file, 70 lines) vs `components/EvidenceSettings.tsx` (70 lines)
**Issue:** The two components are identical except for the state variable name (`windowDays` vs `threshold`), copy strings, and the two API function names. This is confirmed as an intentional "clone" pattern per `62-PATTERNS.md`, but it means every future bug fix (e.g. WR-02's clamping bug, WR-03's a11y gap) has to be applied twice, and the two will silently drift apart over time.
**Fix:** Extract a shared `NumericDayThresholdSetting` component/hook parameterized by label text, helper text, fetch/save functions, and button label, then have both `EvidenceSettings` and `RemediationSlaSettings` render it. Low priority given the phase's explicit design intent to clone rather than share.

### IN-02: Magic numbers `1` / `365` / `7` duplicated across multiple call sites without shared constants

**File:** `components/RemediationSlaSettings.tsx:6, 13, 42-43, 46`; `services/apiService.ts:4602, 4605, 4608`
**Issue:** The bounds `1`/`365` and default `7` are repeated as inline literals in the initial `useState`, the `isValid` check, the JSX `min`/`max` props, the clamp expression, and twice in the apiService fallback — six occurrences for three values. They also need to stay in sync with the backend's `Field(ge=1, le=365)` constraint. There is no compiler/lint mechanism tying these together.
**Fix:** Extract module-level constants (`SLA_WINDOW_MIN = 1`, `SLA_WINDOW_MAX = 365`, `SLA_WINDOW_DEFAULT = 7`) and reuse them at every call site.

### IN-03: Test name overstates what is actually being verified

**File:** `src/__tests__/RemediationSlaSettings.test.tsx:76-82`
**Issue:** The test `'fetch: soft-fails to the default of 7 when the wrapper resolves its own fallback'` mocks `fetchRemediationSlaWindow` with `mockResolvedValue({ windowDays: 7 })` — an ordinary successful resolution, not a simulated failure. Because `apiService` is mocked at the module boundary (`vi.mock('../../services/apiService', ...)`), this test never actually exercises `fetchRemediationSlaWindow`'s real internal `try/catch` fallback (`services/apiService.ts:4602-4610`) that WR-05 depends on. It is effectively a duplicate of the `'fetch: settles the input to the resolved windowDays value'` test immediately above it, differing only in the asserted number (7 vs 14), and could give false confidence that the soft-fail path is covered.
**Fix:** Either rename the test to reflect what it verifies (rendering on a successful fetch of `7`), or add a separate test that exercises `apiService.fetchRemediationSlaWindow` directly (unmocked, with the underlying `authFetch`/`fetch` failing) to genuinely cover the fallback contract.

---

_Reviewed: 2026-08-11T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
