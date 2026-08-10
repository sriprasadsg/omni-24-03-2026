---
phase: 62-remediation-sla-settings-ui
fixed_at: 2026-08-10T19:24:40Z
review_path: .planning/phases/62-remediation-sla-settings-ui/62-REVIEW.md
iteration: 2
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 62: Code Review Fix Report

**Fixed at:** 2026-08-10T19:24:40Z
**Source review:** .planning/phases/62-remediation-sla-settings-ui/62-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 2 (fix_scope: all — 0 critical, 0 warning, 2 info)
- Fixed: 2
- Skipped: 0

This is iteration 2 of the fix/re-review loop. Iteration 1's `62-REVIEW-FIX.md` (fixed 6, skipped 3 as contradicting locked design decisions) is superseded by this report, which addresses the two new Info-level findings the iteration-2 re-review surfaced. All 6 prior fixes and all 3 prior skips were independently re-verified as correct by the reviewer and are not revisited here.

All fixes were applied and verified in an isolated git worktree (`gsd-reviewfix/62-*` branch), then fast-forwarded onto `feat/rust-agent-2.1.0-and-fixes`. Each fix was verified against the full `RemediationSlaSettings.test.tsx` suite (10/10 passing, including the new regression test) and a scoped `npx tsc --noEmit` (no new errors in either modified file).

## Fixed Issues

### IN-01: WR-04's runtime validation still lets `null` through as `0` instead of falling back to the documented safe default

**Files modified:** `services/apiService.ts`
**Commit:** `44b82a3`
**Applied fix:** Changed `fetchRemediationSlaWindow`'s validation from `Number.isFinite(windowDays) ? windowDays : DEFAULT` to explicitly require `raw > 0` in addition to `Number.isFinite(raw)`, exactly per the review's suggested fix:
```ts
const raw = Number(data?.windowDays);
const windowDays = Number.isFinite(raw) && raw > 0 ? raw : REMEDIATION_SLA_WINDOW_DEFAULT_DAYS;
return { windowDays };
```
This closes the gap where an explicit `windowDays: null` (or `0`/negative) in the response previously coerced to `0` — which is finite but falls outside the valid `[1, 365]` range — and silently produced a confusing "validation error, Save disabled" state on load instead of the intended soft-fail to the default of `7`. Verified the existing `fetch: never renders blank when the resolved payload has no windowDays key` test (mocks `{}`, i.e. `windowDays: undefined` → `NaN` → still falls back) and all other fetch-path tests still pass unmodified.

### IN-02: No regression test for the WR-02 clear-then-retype repro scenario

**Files modified:** `src/__tests__/RemediationSlaSettings.test.tsx`
**Commit:** `f647226`
**Applied fix:** Added the review's suggested regression test immediately after the existing `validat: clamps the input to [1, 365] on change` test, exercising the exact incremental-typing sequence that produced the original WR-02 bug (clear the field via a `''` `onChange`, then type a new digit) and asserting the result is the new digit alone, not a corrupted concatenation:
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
This guards against a future refactor silently reintroducing the WR-02 bug without the suite catching it. Full suite now 10/10 passing.

## Skipped Issues

None — both in-scope findings were fixed.

---

_Fixed: 2026-08-10T19:24:40Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
