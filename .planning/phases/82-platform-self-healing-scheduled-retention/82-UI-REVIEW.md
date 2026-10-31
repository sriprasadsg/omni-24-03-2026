# Phase 82 — UI Review

**Audited:** 2026-10-31
**Baseline:** 82-UI-SPEC.md (approved 2026-10-27)
**Screenshots:** not captured. The Phase 82 UI is unpublished and no mocked-API preview of `dist-new` was practical, so no screenshots were taken. The live site at port 443 was not driven. The audit is code-only (components, services, existing tests).
**Interaction captures:** off (workflow.ui_interaction_capture is false). Every interaction finding below is code-derived.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Spec copy is reproduced almost verbatim; the legacy Run Cleanup Now screen prints "Cleanup completed" for failures (WR-05) |
| 2. Visuals | 3/4 | Watchdog and services card is a clear focal point; chips always pair icon and text; the legacy screen still uses emoji icons |
| 3. Color | 3/4 | Tone vocabulary is reused with no hex or rgba values; the dialog error blocks use a different dark palette than the contract |
| 4. Typography | 3/4 | New files use only 12, 14 and 18px at weights 400 and 600; subheading levels (h3, h4) are flat |
| 5. Spacing | 3/4 | Follows the 4/8/16/24 scale; a few half-step `mt-0.5` nudges that the contract does not list |
| 6. Experience Design | 2/4 | WR-01 lets a reviewer attest to rows never shown; WR-05; Esc can close the confirm dialog mid-request; legacy screen has no error or load states |

**Overall: 17/24**

---

## Top 3 Priority Fixes

1. **BLOCKER (WR-01, cited from 82-REVIEW.md): Confirm deletion is enabled while only the first 25 rows are loaded** — The checkbox says "I have reviewed the counts for every organization listed", but the token confirms every waiting row. With about 160 rows, a reviewer can authorize roughly 135 deletions they never saw. Fix in `components/AutonomousOpsRetentionReview.tsx:315`: add `|| state?.nextOffset !== null` to `disabled` and show "Load all {n} rows before confirming." in the helper line. Alternatively, have the dialog state how many rows are not yet displayed.
2. **BLOCKER (WR-05, cited from 82-REVIEW.md): Run Cleanup Now reports success on 409, 403 and 400** — `components/RetentionPolicyDashboard.tsx:48-50` calls `r.json()` and `setLastResult(d)` without checking `r.ok`. A busy lock or a non-admin gets the green "Cleanup completed at Invalid Date" card with no tiles. Fix: check `r.ok`, otherwise `showToast(d.detail || "Couldn't run cleanup.", 'error')` and return. The same screen's `savePolicy` (line 58-71) and `loadAll` (line 41) also swallow failures, so a failed save or load shows nothing.
3. **WARNING: The Confirm deletion dialog can be dismissed while the request is in flight** — `Modal` closes on Esc by default and `Keep waiting` stays enabled during `Confirming...` (`components/AutonomousOpsRetentionConfirmDialog.tsx:74-82`). The user sees the dialog close as if nothing was deleted, while the request may still succeed and show the success toast. Fix: pass `closeOnEsc={!pending}` and `disabled={pending}` on `Keep waiting`, or confirm that the contract intends "Keep waiting stays enabled" and then add a visible "request already sent" line.

Further items:
4. WARNING: dialog error blocks use `dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300` (`AutonomousOpsRetentionConfirmDialog.tsx:119,125`). The spec and `HealthNotice` use `dark:border-red-400/25 dark:bg-red-400/10`. Reuse `HealthNotice tone="red"` so dark mode matches.
5. WARNING: the legacy `RetentionPolicyDashboard` has no loading, error or empty state. `loadAll` only calls `console.error`, so a failed fetch renders a header and an empty list.
6. WARNING: when the review is empty and `review.mode === 'counting_only'` but `notCountedYet` is false, the card shows the "Counting only" chip beside "Nothing is waiting for confirmation" (`AutonomousOpsRetentionReview.tsx:291`). The contract maps "Nothing waiting" to Deleting nightly, so the two lines can disagree if the server sends that mix.
7. WARNING: `ResultLine` for the pending test and for the amber "not picked up" message is inside `role="status"`, but the failed-delivery line (`AutonomousOpsHealthCards.tsx:364`) is outside it with its own `role="alert"`. This is correct, but the 5 s poll can re-mount the line when `quiet` flips, which may re-announce it. Verify with a screen reader.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- Banner, section, watchdog, certificate, disk, on-call, retention, dialog, toast and error strings match the Copywriting Contract line for line (`AutonomousOpsHealthBanners.tsx:72-97`, `AutonomousOpsPlatformHealth.tsx:43-48,213-233,301,314`, `AutonomousOpsHealthCards.tsx`, `AutonomousOpsRetentionConfirmDialog.tsx`).
- Unspecified copy was added: `No row could be counted, so there is nothing to confirm yet.` (`AutonomousOpsRetentionReview.tsx:321`). It is reasonable, but it is not in the contract and not covered by a spec line.
- The fallback text `no reason was given` is inserted after `Last attempt {HH:MM}:` and `not delivered:` without a closing period (`AutonomousOpsHealthCards.tsx`). Server errors are rendered as sent, so the sentence may end without a stop. The spec text for those two lines also has no closing period, so this matches.
- `RetentionPolicyDashboard.tsx:45,122`: the confirm and notice copy matches D-26 and D-19, but the success card still says "Cleanup completed" for failed runs (WR-05). Generic labels remain (`Save`, `Cancel`, `Edit`), which the spec allows ("no restyle").
- The legacy screen keeps emoji in labels (`🗑 Run Cleanup Now`, `✓`, `⚠`). The spec said no restyle, so this is not a Phase 82 regression, but it is in a file Phase 82 edited.
- `autonomous-ops-banned-terms.json` lists all five new component files. `RetentionPolicyDashboard.tsx` is not in it, which is correct because it is not Autonomous Ops copy.

### Pillar 2: Visuals (3/4)
- Focal point: the watchdog and services card is the first block after the heading (`AutonomousOpsPlatformHealth.tsx:325`) and the only block with per-service chips. Hierarchy follows H3.
- Every chip has a 12px `aria-hidden` icon and visible text (`AutonomousOpsHealthChips.tsx`). The disk meter has `role="meter"`, an `aria-label`, visible percent text and decorative ticks (`AutonomousOpsHealthCards.tsx:149`).
- The one icon-only affordance (none found); every button has text.
- Hierarchy gap: h3 card titles, the h4 "Waiting for your confirmation" and card body subheads are all 14/600, so the retention card has no distinct level between title and table heading. This is by contract, but it flattens scanning.
- The disk meter fill uses `bg-amber-500` for the Warning rung; the amber chip text is `amber-800`. Fine, but the spec's fill list says amber without a shade, so this is unverified against the Phase 81 palette.
- No screenshots, so wrapping at 375 and 768 widths is verified only from classes (`grid-cols-1 sm:grid-cols-2 xl:grid-cols-4`, `basis-full sm:basis-auto` on `View details`).

### Pillar 3: Color (3/4)
- No hard-coded hex or rgb values in the audited Autonomous Ops files (grep returned none). All tones come from the six constants in `AutonomousOpsHealthChips.tsx`.
- Accent is not used on any Phase 82 element except the pill reused from Phase 81 (`Platform health` filter), matching the contract. `Confirm deletion` is `bg-red-600`; `Send test alert` is secondary.
- Deviation: dialog error blocks use `dark:border-red-900/50 dark:bg-red-900/20` instead of the contract's red-400 alpha tokens (`AutonomousOpsRetentionConfirmDialog.tsx:119,125`), so the same error looks different in dark mode between the card and the dialog.
- `Couldn't count` uses `text-red-600 dark:text-red-400` (`AutonomousOpsRetentionReview.tsx:116`) while the other red text uses `red-700 / red-300`. Contrast is acceptable on white, but the red shades are inconsistent within one file.
- Legacy `RetentionPolicyDashboard.tsx` uses blue, purple, green, yellow and red tiles. Out of scope by the spec ("no restyle") but it is the least consistent screen in the phase.

### Pillar 4: Typography (3/4)
- The new files use only `text-xs`, `text-sm` and `text-lg`, which map to 12, 14 and 18px. Weights are `font-semibold` and the default 400. No `font-medium` or `font-bold` in any new file (grep). Mono is limited to units, paths, collection ids and `omni-watchdog.timer`.
- `tabular-nums` is applied to percents, counts and the footer.
- Weak differentiation between subheadings (see Visuals).
- `RetentionPolicyDashboard.tsx` uses `text-2xl font-bold`, `text-3xl font-bold`, `font-medium` and `text-lg font-bold`. The spec scoped the changes to text and small blocks there, so this is not marked as a Phase 82 failure.

### Pillar 5: Spacing (3/4)
- Cards use `p-6` and `gap-6`; readout grids use `gap-4`; table cells use `px-4 py-4`; the section uses `space-y-6`. These match the scale.
- `min-w-[200px]` on two table headers is an arbitrary value, but it is the contract's "min 200px". `mt-0.5` (2px) on icons in `HealthNotice`, `ResultLine` and the dialog blocks is not a multiple of 4 and not in the contract's exception list. The contract lists only `h-2` and `w-px` as exceptions.
- Button heights: `Send test alert`, `Confirm deletion`, `Load more rows` all use `min-h-10`.
- Viewport behavior at 375, 768 and 1440 was not rendered.

### Pillar 6: Experience Design (2/4)
- **WR-01 (cited, not re-derived):** `AutonomousOpsRetentionReview.tsx:315` enables Confirm deletion whenever `countable > 0`, while the checkbox attests to every organization listed. This breaks a destructive-action safeguard the contract relies on.
- **WR-05 (cited, not re-derived):** `RetentionPolicyDashboard.tsx:48-50` treats every answer as success.
- Dialog: the checkbox is first focusable and gates the button; no keyboard submit; stale 409 resets the checkbox and swaps to `Reload review`; 403 toasts and closes. These all match the contract. The gap is that Esc and `Keep waiting` stay live during `Confirming...` (see Fix 3).
- Loading, error, empty and background-poll rules are implemented for the health section (`aria-busy`, skeletons, `Reload platform health`, last data kept on poll failure) and for the retention card (`Reload retention review`, `Couldn't load more rows.` with retry).
- The test-alert state machine covers requesting, waiting (spinner, 5 s poll), no answer after 90 s, delivered, failed, request failed, not installed and silent. A silent watchdog disables the button, consistent with the contract's contradictory row.
- The silent-watchdog in-app notification exists server-side (`backend/autonomous_ops/selfheal.py`); not verified end to end.
- Legacy `RetentionPolicyDashboard.tsx`: no loading state, no error state on `loadAll`, `savePolicy` ignores `!res.ok` (no toast on failure), the browser `confirm()` is used for the destructive action. Server-held waiting state and the shortened notice are implemented correctly.
- Permission gating: the section, banners and Confirm button are driven by `hasPermission('control:platform_autonomous_ops')`. The cast `as any` at `AutonomousOpsRetentionReview.tsx:227` hides a type gap but does not change behavior.

---

## Registry Safety
`components.json` is absent and the UI-SPEC lists no third-party registries. Registry audit skipped.

## Files Audited
- components/AutonomousOpsHealthBanners.tsx
- components/AutonomousOpsHealthChips.tsx
- components/AutonomousOpsHealthCards.tsx
- components/AutonomousOpsPlatformHealth.tsx
- components/AutonomousOpsRetentionReview.tsx
- components/AutonomousOpsRetentionConfirmDialog.tsx
- components/AutonomousOpsActivityList.tsx (platform_health filter, guard, empty state: grep only)
- components/AutonomousOpsStopBanner.tsx (health banner slot: grep only)
- components/RetentionPolicyDashboard.tsx
- shared/autonomous-ops-banned-terms.json
- .planning/phases/82-platform-self-healing-scheduled-retention/82-UI-SPEC.md, 82-REVIEW.md

> Citation check 2026-10-31: every file:line above was compared with the source after the audit. Two were corrected in the Top Fixes and 7 more were corrected or reduced to the file name. The findings themselves were not changed.
