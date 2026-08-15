---
phase: 62-remediation-sla-settings-ui
fixed_at: 2026-08-10T19:15:15Z
review_path: .planning/phases/62-remediation-sla-settings-ui/62-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 6
skipped: 3
status: partial
---

# Phase 62: Code Review Fix Report

**Fixed at:** 2026-08-10T19:15:15Z
**Source review:** .planning/phases/62-remediation-sla-settings-ui/62-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (fix_scope: all — 0 critical, 6 warning, 3 info)
- Fixed: 6
- Skipped: 3

All fixes were applied and verified in an isolated git worktree (`gsd-reviewfix/62-*` branch), then fast-forwarded onto `feat/rust-agent-2.1.0-and-fixes`. Each fix was verified against `npx tsc --noEmit` (no new errors in modified files) and the full `RemediationSlaSettings.test.tsx` suite (9/9 passing after every commit).

## Fixed Issues

### WR-02: Controlled number input re-clamps on every keystroke — corrupts a value being retyped after clearing the field

**Files modified:** `components/RemediationSlaSettings.tsx`
**Commit:** `88afb57`
**Applied fix:** Decoupled the input's displayed text (`rawWindowDays`, a string) from the committed clamped number (`windowDays`). The `onChange` handler now allows an empty string to pass through untouched (instead of coercing it to `1` via `parseInt(...) || 1`), so Backspace-clearing the field no longer corrupts the next keystroke. Any non-empty, parseable value is still clamped to `[1, 365]` synchronously on change, preserving the existing test suite's assertions (`fireEvent.change` → immediate clamp for out-of-range values). `onBlur` restores the last committed value if the field is left empty. All 9 pre-existing tests pass unmodified.

### WR-03: `<label>` is not programmatically associated with the input (accessibility)

**Files modified:** `components/RemediationSlaSettings.tsx`
**Commit:** `8296b6b`
**Applied fix:** Added `id="sla-window-days"` to the input and `htmlFor="sla-window-days"` to the label. Added `aria-invalid={!isValid}` and `aria-describedby` (pointing at a new `id="sla-window-days-error"` on the validation message, only when invalid) so screen readers announce the error state.

### WR-04: No runtime validation of the fetch/save network response shape

**Files modified:** `services/apiService.ts`
**Commit:** `4415b02`
**Applied fix:** `fetchRemediationSlaWindow` now runs the parsed JSON's `windowDays` through `Number(...)` and `Number.isFinite(...)` before trusting it, falling back to the default (`7`) if the field is missing, non-numeric, or malformed — consistent with the function's existing "always soft-fail to a safe default" contract.

### WR-06: `useEffect`'s fetch chain has no `.catch()` — correctness depends entirely on the callee's internal try/catch

**Files modified:** `components/RemediationSlaSettings.tsx`
**Commit:** `7dbc26b`
**Applied fix:** Added a local no-op `.catch(() => {})` to the `useEffect` fetch chain, with a comment explaining it's defensive (the callee currently never rejects) so a future refactor of `fetchRemediationSlaWindow` can't silently produce an unhandled rejection at this call site.

### IN-02: Magic numbers `1` / `365` / `7` duplicated across multiple call sites without shared constants

**Files modified:** `components/RemediationSlaSettings.tsx`, `services/apiService.ts`
**Commit:** `ed2f22f`
**Applied fix:** Extracted `SLA_WINDOW_MIN = 1`, `SLA_WINDOW_MAX = 365`, `SLA_WINDOW_DEFAULT = 7` as module-level constants in `RemediationSlaSettings.tsx`, used at every clamp/bounds/default call site. Extracted a local `REMEDIATION_SLA_WINDOW_DEFAULT_DAYS = 7` constant in `apiService.ts` for its three fallback occurrences.

### IN-03: Test name overstates what is actually being verified

**Files modified:** `src/__tests__/RemediationSlaSettings.test.tsx`
**Commit:** `49ba5f5`
**Applied fix:** Renamed the misleadingly-named test (previously `'fetch: soft-fails to the default of 7 when the wrapper resolves its own fallback'`, which actually just mocks an ordinary successful resolution) to accurately state that it verifies an ordinary resolved value and does not exercise `apiService.ts`'s real internal soft-fail `catch` block. Chose the rename option (over adding a new unmocked test file exercising the real `fetchRemediationSlaWindow`/`authFetch`/`fetch` chain) to keep the change minimal and avoid creating a new test file per CLAUDE.md's file-creation guidance.

## Skipped Issues

### WR-01: Save control has no capability check — non-admin users always get a generic, misleading failure toast

**File:** `components/SettingsDashboard.tsx:292-294`, `components/SettingsDashboard.tsx:361-363`, `components/RemediationSlaSettings.tsx:15-26`
**Reason:** The suggested fix (gate the Save action/tab on `canManageSettings`, give non-admins a distinct message) directly contradicts a locked design decision. `62-CONTEXT.md` **D-04** states verbatim: *"Non-admin behavior matches `EvidenceSettings.tsx` exactly: the Save button has no client-side role check. It's visible and clickable to every authenticated user; a non-admin who clicks Save gets the backend's 403 surfaced as the generic 'Failed to save threshold — please try again' error toast. No new permission-check logic — this follows the phase's own 'clone verbatim' instruction."* `62-UI-SPEC.md` line 116 independently confirms this is intentional per D-04, not an oversight. Applying the review's fix would revert an explicit, documented product decision from the phase's own planning artifacts, which the reviewer did not have visibility into. Left as-is; flagging for human decision if the product intent has since changed.
**Original issue:** The Remediation tab/panel render unconditionally with no `canManageSettings` guard, so non-admins can attempt Save and only ever see a generic failure toast that can't distinguish "you lack permission" from a transient network failure.

### WR-05: Silent fetch-failure fallback is indistinguishable from a genuine value of 7 — no error signal on load failure

**File:** `components/RemediationSlaSettings.tsx:9-11`; `services/apiService.ts:4602-4610`
**Reason:** The review itself flags this as "a documented, intentional design choice," citing `62-UI-SPEC.md`: *"the panel never renders blank or broken, it silently falls back to the default and lets the user proceed."* Verified this is a locked contract at `62-UI-SPEC.md` line 115. The suggested fix (surface a toast/inline notice on GET failure) would change this documented, intentional behavior. Left as-is; the underlying robustness concern (no `.catch()` at the call site) was addressed defensively via WR-06 without changing user-visible behavior.
**Original issue:** A transient GET failure during load is indistinguishable from a genuine configured value of `7`, creating a config-drift risk if an admin saves without noticing the fallback.

### IN-01: `RemediationSlaSettings.tsx` is a near line-for-line duplicate of `EvidenceSettings.tsx`

**File:** `components/RemediationSlaSettings.tsx` (whole file) vs `components/EvidenceSettings.tsx`
**Reason:** `62-PATTERNS.md` explicitly documents this phase as *"a verbatim clone with locked copy substitutions; there is no genuinely novel pattern requiring a fallback"* and lists `RemediationSlaSettings.tsx` as an *"exact (verbatim clone target)"* of `EvidenceSettings.tsx`. Extracting a shared component/hook, as the finding suggests, would contradict this explicit, locked design intent. The review itself marks this as "Low priority given the phase's explicit design intent to clone rather than share." Left as-is.
**Original issue:** Every future bug fix (e.g. this iteration's WR-02, WR-03) has to be applied to both `RemediationSlaSettings.tsx` and `EvidenceSettings.tsx` separately, and the two will silently drift apart over time. Note: this iteration's WR-02/WR-03 fixes were applied only to `RemediationSlaSettings.tsx` (the file in this phase's scope) — `EvidenceSettings.tsx` still has the original clamping bug and accessibility gap, consistent with WR-01's own note that fixing `EvidenceSettings.tsx` is "out of scope for this file list."

---

_Fixed: 2026-08-10T19:15:15Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
