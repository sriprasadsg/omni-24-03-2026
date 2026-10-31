# Phase 82 — UI Review (re-audit after gap plan 82-17)

**Audited:** 2026-10-31
**Baseline:** 82-UI-SPEC.md (approved 2026-10-27, amended 2026-10-31: Keep waiting is disabled and Esc is off while the confirm request is pending)
**Screenshots:** not captured. Code-only audit by instruction (2 vCPU / 8 GB VM; no dev server, browser or Playwright started). The Phase 82 UI is also unpublished (`dist-new` only).
**Interaction captures:** off (workflow.ui_interaction_capture is false). Every interaction finding is code-derived.
**Previous review:** 17/24 on 2026-10-31 (before 82-17).

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Spec copy matches; Run Cleanup Now no longer prints "Cleanup completed" for failures; legacy emoji labels remain |
| 2. Visuals | 3/4 | Unchanged: clear watchdog focal point, icon plus text chips; flat subheading levels |
| 3. Color | 3/4 | Unchanged: dialog error blocks still use `dark:red-900` palette; `red-600/400` text inconsistency remains |
| 4. Typography | 3/4 | Unchanged: 12/14/18 at 400/600 only in new files |
| 5. Spacing | 3/4 | Unchanged: `mt-0.5` half-steps not in contract exception list |
| 6. Experience Design | 3/4 | WR-01, WR-05 and Esc/Keep-waiting are fixed; legacy Retention screen still has no load or save error handling |

**Overall: 18/24** (was 17/24)

---

## Status of the previous findings

| # | Previous finding | Status | Evidence |
|---|------------------|--------|----------|
| 1 | BLOCKER WR-01: Confirm deletion enabled with rows not loaded | FIXED | `components/AutonomousOpsRetentionReview.tsx:262` `allLoaded = state?.nextOffset === null`; `:346` `disabled={running \|\| incomplete !== null \|\| countable <= 0 \|\| !allLoaded}`; `:355` helper `Load all {total} rows before confirming.` Helper order at `:351-357` (running, incomplete, no countable, not loaded, default) matches spec section 6. |
| 2 | BLOCKER WR-05: Run Cleanup Now reports success on 409/403/400 | FIXED | `components/RetentionPolicyDashboard.tsx:52` checks `!r.ok` or missing string `ran_at`; `:53` error toast with server `detail` or `Couldn't run cleanup.`; `:59` network-error catch. Success card is no longer set on failure. Matches spec section 9 last row. |
| 3 | WARNING: dialog dismissible mid-request | FIXED, matches amended spec | `components/AutonomousOpsRetentionConfirmDialog.tsx:82` `closeOnEsc={!pending}`; `:85` `Keep waiting ... disabled={pending}`; `closeOnBackdrop={false}` at `:81`. After a 409 or error `pending` returns to false in `finally` (`:66-69`) so both work again, as the spec says. |
| 4 | WARNING: dialog error blocks use `dark:border-red-900/50 dark:bg-red-900/20` | REMAINS | `AutonomousOpsRetentionConfirmDialog.tsx:122` and `:128`. Spec section 2 and `HealthNotice tone="red"` use `red-400/25` and `red-400/10`. |
| 5 | WARNING: legacy `RetentionPolicyDashboard` has no load, error or empty state | PARTLY FIXED | Run Cleanup Now now surfaces failure. Still open: `loadAll` only calls `console.error` (`RetentionPolicyDashboard.tsx:42`); `savePolicy` (starts `:63`) ignores `!res.ok` and gives no toast on a failed save; browser `confirm()` (`:46`) remains. |
| 6 | WARNING: "Counting only" chip beside "Nothing is waiting" if server sends the mix | NOT RE-VERIFIED | Chip comes straight from `review.mode` (`AutonomousOpsRetentionReview.tsx:282`); the empty-state branch is `:314`. The mismatch depends on server data, so it is unconfirmed, not fixed. |
| 7 | WARNING: failed-delivery line may re-announce on poll | NOT RE-VERIFIED | Needs a screen reader; out of scope for code-only. |

Other previous items unchanged: `mt-0.5` (Spacing), `Couldn't count` and `Couldn't load more rows.` use `red-600/red-400` (`AutonomousOpsRetentionReview.tsx:136`, `:214`) while other red text uses `red-700/red-300`, `as any` permission cast (`:247`), legacy emoji labels.

---

## Top Priority Fixes (remaining)

No BLOCKER remains. All items are WARNING.

1. **Legacy Retention Policy screen swallows load and save failures** — a failed `loadAll` shows an empty list, and a failed `savePolicy` closes the editor as if saved (`components/RetentionPolicyDashboard.tsx:42`, `:63` onward). Fix: check `res.ok` in `savePolicy` and toast the server message; on `loadAll` failure show a toast or inline error.
2. **Dialog error blocks use a different dark palette** — `AutonomousOpsRetentionConfirmDialog.tsx:122,128`. Replace with `HealthNotice tone="red"` or the `dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300` classes from the spec.
3. **A 409 REVIEW_INCOMPLETE answer shows the "counts changed" stale text** — by 82-17's own decision it lands in the existing stale block (`AutonomousOpsRetentionConfirmDialog.tsx:121-126`), so the reason shown is not the real one (the count is incomplete, not changed). Low likelihood because the button is already disabled while incomplete, but if it happens the user is told the wrong cause. Add a branch with the incomplete copy, or tolerate it and note it.
4. **Red shade inconsistency in the review card** — `AutonomousOpsRetentionReview.tsx:136,214` use `red-600 / red-400`; use `red-700 / red-300` like the other red text.
5. **Half-step spacing** — `mt-0.5` at `AutonomousOpsRetentionConfirmDialog.tsx:105,123,129` and `AutonomousOpsHealthCards.tsx:247`; either use `mt-1` or add `mt-0.5` to the spec exceptions.
6. **Legacy emoji labels** in `RetentionPolicyDashboard.tsx` (`🗑 Run Cleanup Now`) remain; allowed by "no restyle" but inconsistent with the "No emojis" naming rule that applies to the phase.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- The 82-17 additions match the amended spec: `Load all {n} rows before confirming.` (`AutonomousOpsRetentionReview.tsx:355`), `Confirm after the next run has counted every organization.` (`:34`), and `Couldn't run cleanup.` (`RetentionPolicyDashboard.tsx:53,59`).
- The run-cleanup confirm text at `RetentionPolicyDashboard.tsx:46` matches D-26 exactly.
- `No row could be counted, so there is nothing to confirm yet.` (`AutonomousOpsRetentionReview.tsx:354`) is not in the spec's copy table; reasonable, but unspecified.
- Generic `Save`/`Cancel`/`Edit` and emoji labels remain on the legacy screen (spec allows).

### Pillar 2: Visuals (3/4)
- Unchanged from the previous review. Watchdog and services card is the first block; chips always pair icon and text; every button has text. h3 and h4 levels are both 14/600 by contract.
- New amber incomplete notice reuses `HealthNotice tone="amber"` (`AutonomousOpsRetentionReview.tsx:338-342`), so it sits visually with the other notices. Not rendered, so wrapping at 375, 768 and 1440 is unverified.

### Pillar 3: Color (3/4)
- No hex or rgb values in new files (as before). Accent use stays within the contract.
- Open: dark red palette in the dialog (Fix 2) and `red-600/400` text (Fix 4).

### Pillar 4: Typography (3/4)
- New files use `text-xs`, `text-sm`, `text-lg`, and weights 400 and 600 only. 82-17 added no new sizes. Legacy screen keeps its own `font-bold` sizes (out of scope).

### Pillar 5: Spacing (3/4)
- Scale followed (`p-6`, `gap-6`, `gap-4`, `min-h-10`). The amber notice and button row use `gap-4` inside `flex-col gap-6`, consistent. `mt-0.5` half-steps remain (Fix 5).

### Pillar 6: Experience Design (3/4)
- Destructive-action safeguard now holds: the button needs all rows loaded, no incomplete reason, a countable row and no run in progress; a recount resets `nextOffset` through the hook (`AutonomousOpsRetentionReview.tsx:81-82`), re-disabling the button.
- Dialog in-flight behaviour matches the amended spec: Keep waiting disabled, Esc off, backdrop off, confirm shows `Confirming...`, a single-flight ref guards repeat clicks (`inFlight` in the dialog).
- Run Cleanup Now handles 4xx, unreadable body, missing `ran_at` and network errors with a toast.
- Remaining gaps: legacy screen load and save errors (Fix 1); wrong cause text for a 409 incomplete (Fix 3); the checkbox stays enabled while a request is pending (harmless).
- Why 3 and not 4: the legacy screen still fails silently, and no interaction or rendered check was possible.

---

## Registry Safety
`components.json` is absent and the UI-SPEC lists no third-party registries. Registry audit skipped.

## Files Audited
- components/AutonomousOpsRetentionReview.tsx (368 lines; cited lines 34, 81-82, 136, 214, 247, 262, 282, 314, 338-357 checked)
- components/AutonomousOpsRetentionConfirmDialog.tsx (146 lines; cited lines 66-69, 81-85, 105, 121-129 checked)
- components/RetentionPolicyDashboard.tsx (220 lines; cited lines 42, 46, 52, 53, 59, 63 checked)
- components/AutonomousOpsHealthCards.tsx (line 247 only)
- .planning/phases/82-platform-self-healing-scheduled-retention/82-UI-SPEC.md, 82-17-SUMMARY.md, previous 82-UI-REVIEW.md
- Not re-read this round: AutonomousOpsHealthBanners, AutonomousOpsHealthChips, AutonomousOpsPlatformHealth, AutonomousOpsActivityList; their findings carry over from the previous review unchanged (82-17 did not touch them).
