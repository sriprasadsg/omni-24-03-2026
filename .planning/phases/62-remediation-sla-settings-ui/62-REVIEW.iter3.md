---
phase: 62-remediation-sla-settings-ui
reviewed: 2026-08-11T00:48:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - components/RemediationSlaSettings.tsx
  - src/__tests__/RemediationSlaSettings.test.tsx
  - services/apiService.ts
  - components/SettingsDashboard.tsx
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: issues_found
---

# Phase 62: Code Review Report

**Reviewed:** 2026-08-11T00:48:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

This is iteration 2 of the fix/re-review loop. Iteration 1 (`62-REVIEW.md`, superseded by this report) found 9 issues (0 critical, 6 warning, 3 info). A fixer agent applied 6 of them across commits `88afb57`, `8296b6b`, `4415b02`, `7dbc26b`, `ed2f22f`, `49ba5f5`, and deliberately skipped 3 (WR-01, WR-05, IN-01) as contradicting locked design decisions in `62-CONTEXT.md` (D-04), `62-UI-SPEC.md`, and `62-PATTERNS.md`.

I re-read all four files fresh, traced the actual runtime behavior of the applied fixes (not just their diffs), ran the full test suite (`RemediationSlaSettings.test.tsx`, 9/9 passing), ran `tsc --noEmit` (no new errors attributable to these files — the two pre-existing `SettingsDashboard.tsx` errors are an unrelated `Permission` type gap on `'view:voice_bot'`, not touched by this phase), and diffed the component against its clone source `EvidenceSettings.tsx` to confirm no unintended drift.

**Verdict: all 6 claimed fixes are genuinely correct and complete.** All 3 skips are independently verified as correct per the cited locked-decision artifacts — I did not re-flag them. Two new, narrowly-scoped Info-level observations surfaced during this pass (below); neither blocks shipping.

## Fix Verification (Iteration 2)

- **WR-02 (controlled input corrupts retyped values) — VERIFIED FIXED.** `RemediationSlaSettings.tsx:30-44` now decouples the displayed text (`rawWindowDays`, string) from the committed clamped value (`windowDays`, number). Empty-string is passed through untouched on `onChange` (`rawWindowDays=''`, no snap-to-1), and `onBlur` (`handleWindowDaysBlur`, line 46-50) restores the last committed value only if the field was left empty. Traced the exact repro from the original finding (clear "200" via Backspace → type "5") by hand: `onChange('')` → `rawWindowDays=''`, `windowDays` untouched; `onChange('5')` → `parsed=5`, in range, both states become `"5"`. Bug is gone. The pre-existing out-of-range immediate-clamp behavior (e.g. typing toward "400" snaps to "365" mid-keystroke) is preserved and still covered by the existing `validat: clamps the input to [1, 365] on change` test — this was intentionally preserved, not part of the bug.
- **WR-03 (label/input not associated) — VERIFIED FIXED.** `id="sla-window-days"` / `htmlFor="sla-window-days"` pair present (lines 70, 78); `aria-invalid={!isValid}` and conditional `aria-describedby` pointing at `id="sla-window-days-error"` (only rendered, and only referenced, when `!isValid`) are wired correctly — no dangling `aria-describedby` reference when valid.
- **WR-04 (no runtime validation of network response shape) — VERIFIED FIXED, with one residual gap noted as IN-01 below.** `apiService.ts:4604-4614` now runs `Number(data?.windowDays)` through `Number.isFinite()` before trusting it, falling back to `REMEDIATION_SLA_WINDOW_DEFAULT_DAYS` (7) otherwise. Confirmed this satisfies the primary threat model (non-numeric strings, missing key, wrong type) and is covered by the `fetch: never renders blank when the resolved payload has no windowDays key` test.
- **WR-06 (missing `.catch()` on the `useEffect` chain) — VERIFIED FIXED.** `RemediationSlaSettings.tsx:14-26` now has an explicit `.catch(() => {})` with a comment explaining it's defensive against a future refactor of the callee. Correctly scoped as a no-op given `fetchRemediationSlaWindow` never rejects today.
- **IN-02 (magic numbers) — VERIFIED FIXED.** `SLA_WINDOW_MIN`/`SLA_WINDOW_MAX`/`SLA_WINDOW_DEFAULT` constants extracted in the component and `REMEDIATION_SLA_WINDOW_DEFAULT_DAYS` in `apiService.ts`, used at every call site checked (`useState` init, `isValid`, JSX `min`/`max`, clamp expression, both fetch/save fallbacks).
- **IN-03 (misleading test name) — VERIFIED FIXED.** The renamed test (`src/__tests__/RemediationSlaSettings.test.tsx:76`) now accurately states it exercises an ordinary resolved value, not the module's internal soft-fail path, and explicitly notes `apiService.ts`'s real `catch` block is not exercised because the module is mocked. This is an honest, accurate test name; no false confidence risk remains.

## Skipped Items — Reviewer Concurrence

Independently re-verified all three skip rationales against the cited source documents rather than taking the fixer's word for it:

- **WR-01** (no client-side capability gate on Save): `62-CONTEXT.md` D-04 explicitly locks "the Save button has no client-side role check... follows the phase's own 'clone verbatim' instruction." `62-UI-SPEC.md` line 115 independently confirms. Current code (`SettingsDashboard.tsx:292-294, 361-363`) still renders the tab/panel unconditionally, matching the locked decision and the sibling "evidence" tab's pattern. Concur with skip.
- **WR-05** (silent fetch-fallback indistinguishable from a real value of 7): `62-UI-SPEC.md`'s "silently falls back to the default and lets the user proceed" is cited verbatim and independently confirmed as a locked contract. Concur with skip; the robustness half of this concern (missing `.catch()`) was legitimately addressed via WR-06 without touching the locked user-visible behavior.
- **IN-01** (duplicate of `EvidenceSettings.tsx`): `62-PATTERNS.md` explicitly documents this phase as "a verbatim clone with locked copy substitutions." Diffed the two files directly — confirmed they remain structurally identical apart from copy/identifier substitutions, and confirmed `EvidenceSettings.tsx` was *not* touched by this iteration's fixes (it still has the original WR-02 clamping bug and WR-03 a11y gap, as the fixer's own report states). Concur with skip.

None of these three are re-flagged as new findings.

## Info

### IN-01: WR-04's runtime validation still lets `null` (and other non-string falsy-but-coercible values) through as `0` instead of falling back to the documented safe default

**File:** `services/apiService.ts:4604-4614`
**Issue:** `Number(data?.windowDays)` is checked with `Number.isFinite()`, which correctly rejects `undefined`, non-numeric strings, objects, and arrays — but `Number(null)` evaluates to `0`, which *is* finite, so an explicit `windowDays: null` in the response silently becomes `windowDays: 0` rather than falling back to `REMEDIATION_SLA_WINDOW_DEFAULT_DAYS` (7). Downstream, `RemediationSlaSettings.tsx`'s `d.windowDays ?? SLA_WINDOW_DEFAULT` (line 17) does not catch this either, because `0` is neither `null` nor `undefined` — `??` only substitutes on nullish values, not falsy-but-defined ones. The component would then render `0` in the input, `isValid` would be `false` (0 < `SLA_WINDOW_MIN`), and Save would be disabled with the "Must be between 1 and 365 days." message — a confusing degraded state (looks like a validation error, not a load failure) instead of the "always soft-fail to a safe default" behavior the fix's own commit message describes.
**Risk is low in practice**: `backend/compliance_remediation_sla_endpoints.py:96` always returns `{"windowDays": window}` where `window` comes from `get_sla_at_risk_window()`, which enforces `max(1, raw_val)` server-side (`compliance_remediation_sla_service.py:130-133`) and never returns `null`. This is a defense-in-depth gap in the boundary-validation code itself, not an exploitable path given the current backend contract, so it doesn't rise to Warning.
**Fix:** Treat `null`/non-positive values as invalid explicitly, rather than relying on `Number.isFinite()` alone:
```ts
const raw = Number(data?.windowDays);
const windowDays = Number.isFinite(raw) && raw > 0 ? raw : REMEDIATION_SLA_WINDOW_DEFAULT_DAYS;
return { windowDays };
```

### IN-02: No regression test added for the specific WR-02 bug scenario (clear-then-retype)

**File:** `src/__tests__/RemediationSlaSettings.test.tsx`
**Issue:** The fix for WR-02 (empty-field mid-edit corruption) is verified by hand-tracing the code, and the existing 9 tests all still pass, but none of them exercise the exact sequence that produced the original bug: an `onChange` to `''` (simulating Backspace-clearing the field) followed by a second `onChange` to a new digit, asserting the result is the new digit and not a corrupted concatenation (e.g. `"15"` instead of `"5"`). The current `validat: clamps the input to [1, 365] on change` test only fires single, complete-value `fireEvent.change` calls (e.g. straight to `'999'` or `'0'`), which — as the original finding itself noted — never exercises the incremental-typing path. Without a dedicated test, a future refactor could silently reintroduce this exact bug and the suite would stay green.
**Fix:** Add a small regression test:
```tsx
it('validat: clearing the field then typing a new digit does not corrupt the value', async () => {
  fetchRemediationSlaWindow.mockResolvedValue({ windowDays: 200 });
  render(<RemediationSlaSettings />);
  const input = screen.getByRole('spinbutton') as HTMLInputElement;
  await waitFor(() => expect(input.value).toBe('200'));

  fireEvent.change(input, { target: { value: '' } });
  expect(input.value).toBe('');

  fireEvent.change(input, { target: { value: '5' } });
  expect(input.value).toBe('5');
});
```

---

_Reviewed: 2026-08-11T00:48:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
