---
phase: 62-remediation-sla-settings-ui
reviewed: 2026-08-10T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - components/RemediationSlaSettings.tsx
  - services/apiService.ts
  - components/SettingsDashboard.tsx
  - src/__tests__/RemediationSlaSettings.test.tsx
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: issues_found
---

# Phase 62: Code Review Report

**Reviewed:** 2026-08-10T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the new Remediation SLA settings UI (`RemediationSlaSettings.tsx`), its two `apiService.ts` fetch/save wrappers, the `SettingsDashboard.tsx` tab wiring, and the accompanying test suite. The diff for this phase is small and closely modeled on the existing `EvidenceSettings.tsx` component. No critical bugs or security vulnerabilities were found in this component: the backend PATCH endpoint (`compliance_remediation_sla_endpoints.py`) independently enforces admin-only writes and range validation via Pydantic, and the frontend never leaks status codes or role details in its error toast (verified against `saveRemediationSlaWindow`'s generic `Error` and the component's bare `catch`).

The findings below are authorization/UX gaps and a controlled-input quirk that should be fixed, plus minor accessibility and test-quality notes. Note: `apiService.ts`'s diff for this phase also includes a large, unrelated block of ITAM catalog/license/consumable/component API wrappers (`fetchCatalogEntities` … `detachComponent`, lines ~5211-5411). These are out of scope for the "Remediation SLA Settings UI" phase description; I spot-checked them for obvious defects (all `itamThrow` failure paths are reachable/typed correctly, `attachComponent`/`detachComponent` don't `encodeURIComponent` their path params unlike most of the sibling ITAM functions in the same block, but they carry internally-generated IDs so this is low-risk) and did not find blocking issues, but flag that this file mixes two phases' worth of changes in one diff.

## Warnings

### WR-01: "Remediation" tab is visible and interactive for users who can never save it

**File:** `components/SettingsDashboard.tsx:292-294`, `components/RemediationSlaSettings.tsx:15-26`
**Issue:** The new "Remediation" tab button is rendered unconditionally (no `canManageSettings`/`hasPermission` guard), same as the pre-existing `security`/`evidence` tabs it sits next to. The backend PATCH `/api/settings/remediation-sla` is admin-gated (`_require_admin` in `backend/compliance_remediation_sla_endpoints.py:31-34`, returns 403 for non-admin roles), but the frontend `Save SLA Window` button is only disabled by `!isValid || saving` — never by permission. A non-admin user can open the tab, edit the value, click Save, and will always get the generic toast `"Failed to save threshold — please try again"` (from the bare `catch` in `RemediationSlaSettings.tsx:21-22`), which is indistinguishable from a transient network failure. The user has no way to learn they simply lack permission, and repeated "try again" clicks will always fail.
**Fix:** Either gate the tab/button behind `canManageSettings` (consistent with the `email`/`integrations`/`dataSources`/`alerts`/`maintenance` tabs that already do this), or have `RemediationSlaSettings` accept a `readOnly`/`canEdit` prop and render the input disabled with an explanatory message for non-admins, e.g.:
```tsx
{activeView === 'remediation' && (
    <RemediationSlaSettings canEdit={canManageSettings} />
)}
```
This is a pre-existing pattern copied from `EvidenceSettings.tsx` (same gap there), so fixing it here is a good opportunity to also flag/fix the sibling component.

### WR-02: Controlled number input clamps on every keystroke, corrupting multi-digit edits

**File:** `components/RemediationSlaSettings.tsx:44-47`
**Issue:**
```tsx
value={windowDays}
onChange={e =>
    setWindowDays(Math.min(365, Math.max(1, parseInt(e.target.value, 10) || 1)))
}
```
Because the input is fully controlled and re-clamps to `[1, 365]` (with `|| 1` for `NaN`) on every `onChange`, clearing the field mid-edit to type a new value forces the displayed value back to `1` before the next keystroke lands. E.g. a user editing `200` down to `50` by selecting-all and typing `5` then `0` will see the field snap to `1` the instant the field is empty, then the next digit is inserted into `"1"` rather than into an empty field, producing `"15"` or `"51"` instead of `50`. This is a real, user-facing input-fighting bug that unit tests don't catch because `fireEvent.change` sets `target.value` directly to a final string rather than emulating incremental typing.
**Fix:** Track the raw string in local state and only clamp/coerce on blur or on save, e.g.:
```tsx
const [inputValue, setInputValue] = useState(String(windowDays));
// onChange: setInputValue(e.target.value)  — no clamping here
// onBlur: clamp inputValue into windowDays and re-sync inputValue
```
or use `type="number"` with `onBlur`-only clamping while allowing free typing via `onChange` without forcing a resolved numeric value each keystroke.

### WR-03: `<label>` not programmatically associated with the input (accessibility)

**File:** `components/RemediationSlaSettings.tsx:33-49`
**Issue:** The `<label>At-Risk Window</label>` has no `htmlFor`, and the `<input>` has no matching `id`. Screen readers and `getByLabelText`-style queries cannot associate the label with the control, so assistive-tech users hear "spin button" with no accessible name context from the visual label (only from DOM order, which is unreliable). This mirrors the same gap in `EvidenceSettings.tsx`.
**Fix:**
```tsx
<label htmlFor="sla-window-days" className="...">At-Risk Window</label>
...
<input id="sla-window-days" type="number" ... />
```

## Info

### IN-01: Redundant test does not exercise what its name claims

**File:** `src/__tests__/RemediationSlaSettings.test.tsx:76-82`
**Issue:** The test `'fetch: soft-fails to the default of 7 when the wrapper resolves its own fallback'` mocks `fetchRemediationSlaWindow` to `mockResolvedValue({ windowDays: 7 })` — an ordinary successful resolution, not a rejection or an error path. It is functionally identical to the `'fetch: settles the input to the resolved windowDays value'` test just above it (lines 68-74), differing only in the numeric value asserted (7 vs 14). Neither test actually simulates the apiService-level fallback behavior (`fetchRemediationSlaWindow`'s internal `catch { return { windowDays: 7 } }` in `services/apiService.ts:4602-4610`), since the real implementation is mocked out entirely at the module boundary. The test name overstates coverage of the "soft-fail" contract.
**Fix:** Either remove this test as a duplicate, or actually exercise the fallback path by testing `apiService.fetchRemediationSlaWindow` directly (unmocked, with `authFetch` failing) in a separate apiService-focused test, or rename the test to reflect what it verifies (rendering the default value 7 on success).

### IN-02: Magic numbers `1`/`365`/`7` duplicated across frontend and backend without a shared constant

**File:** `components/RemediationSlaSettings.tsx:6,13,42-43,46`; `services/apiService.ts:4602-4619`
**Issue:** The bounds `1` and `365` and the default `7` appear as inline literals in multiple places (initial `useState`, `isValid`, `min`/`max` JSX props, the clamp expression, and the apiService fallback). They also mirror the backend's `Field(ge=1, le=365)` in `compliance_remediation_sla_endpoints.py:38`. This is consistent with the sibling `EvidenceSettings.tsx` component's existing style, so it's not a regression, but any future change to the valid range requires updating 5+ call sites by hand with no compiler/lint safety net tying them together.
**Fix:** Extract `const SLA_WINDOW_MIN = 1`, `SLA_WINDOW_MAX = 365`, `SLA_WINDOW_DEFAULT = 7` constants (module-level) for reuse across the clamp logic and JSX attributes; low priority given the existing duplicated pattern in the codebase.

---

_Reviewed: 2026-08-10T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
