# Phase 42 — UI Review (RE-AUDIT)

**Audited:** 2026-07-22 (re-audit — original audit 2026-07-22 scored 19/24; fixes applied in commit `66cb490`)
**Baseline:** `.planning/phases/42-comment-threads-on-compliance-controls/42-UI-SPEC.md` (design contract — note: contract's own "Checker Sign-Off" section remains entirely unchecked, `Approval: pending`; still never formally signed off)
**Screenshots:** not captured (no dev server on :3000 or :5173 — code-only audit)

---

## Prior Fixes — Verification

| # | Fix | Status | Evidence |
|---|-----|--------|----------|
| 1 | Add "Comment posted." success toast | **RESOLVED** | `components/ControlCommentsPanel.tsx:4` imports `showToast` from `../utils/toast`; line 81 calls `showToast('Comment posted.', 'success')` inside `handleSubmit`'s success path, immediately after `setComments`/`setText`. Matches UI-SPEC Copywriting Contract row verbatim. |
| 2 | Remove dead `ChevronDownIcon` from panel header | **RESOLVED** | Line 2 import list is now `import { MessageSquareIcon, SendIcon, ClockIcon } from './icons';` — `ChevronDownIcon` is absent from imports and `grep`-confirmed absent from the render tree (header at lines 91-97 contains only `MessageSquareIcon`, the "Comments" label, and the count span). No dead affordance remains. |
| 3 | Composer textarea `p-1.5` → `p-2` | **RESOLVED** | Line 148: `className="w-full text-xs p-2 border rounded dark:bg-gray-700 dark:border-gray-600"` — `p-1.5` no longer appears anywhere in the file; the textarea is now on the declared 4/8/16 spacing scale. |

All three prior findings are closed. No regressions introduced by the fix commit (toast placement is correct — after state updates, in the try block, not in `finally`, so it doesn't fire on error paths; chevron removal didn't touch the count-badge markup; textarea fix is a pure class-value swap with no other layout change).

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Every Copywriting Contract row now implemented verbatim, including the previously-missing success toast |
| 2. Visuals | 4/4 | Dead chevron affordance removed; header now only contains elements with real behavior/meaning |
| 3. Color | 4/4 | Unchanged from prior audit — accent blue still reserved exclusively for Post Comment button + `@mention` highlight; destructive red still error-text-only |
| 4. Typography | 4/4 | Unchanged from prior audit — only `text-xs`/`text-sm` and `font-normal`/`font-semibold` in use |
| 5. Spacing | 4/4 | The one off-scale value (`p-1.5`) is gone; all spacing in the file now sits on the declared 4/8/16 scale plus the single sanctioned `gap-1.5` header exception |
| 6. Experience Design | 4/4 | Post-success path now has an explicit, distinct feedback signal (toast) matching every comparable write flow in the codebase; loading/error/empty/role-gate/disabled states remain correctly implemented |

**Overall: 24/24**

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)
- Panel header label `Comments (N)` (lines 92-95), composer placeholder `Add a comment... (use @username to mention someone)` (line 150), button labels `Post Comment`/`Posting...` (line 164), empty state `No comments yet on this control.` (lines 114-116), load-error copy (line 63, 109-111), post-error copy (line 83, 155) — all verbatim, all previously verified and unchanged.
- **Newly resolved:** `showToast('Comment posted.', 'success')` at line 81 closes the previously-missing Copywriting Contract row. `grep -n "showToast" components/ControlCommentsPanel.tsx` now returns a match, and the import at line 4 confirms the utility is wired in, matching the exact mechanism used by sibling handlers in `FrameworkDetail.tsx`.
- No regressions: no new generic labels ("Submit", "OK", "Click Here") introduced by the fix commit.

### Pillar 2: Visuals (4/4)
- Header (lines 91-97) now contains exactly: icon (`MessageSquareIcon`), label ("Comments"), count badge — no orphaned affordance. This matches the UI-SPEC's Component Notes instruction ("icon + label + count") precisely; the chevron that implied non-existent collapse/expand behavior is gone.
- `SendIcon` retains `aria-hidden="true"` (line 163) with adjacent visible text (`Post Comment`/`Posting...`), so no icon-only-button accessibility gap.
- Visual hierarchy via weight/size differentiation (semibold author name vs. regular timestamp vs. regular body) unchanged and correct.
- Focal point remains clear: single panel, header bar + body, consistent with `ChainOfCustodyPanel.tsx`'s sibling structure.

### Pillar 3: Color (4/4)
- Unchanged from prior audit — re-verified against current file. `text-blue-600 dark:text-blue-400` appears exactly twice (mention-highlight span line 38, and nowhere else as text color); `bg-blue-600 hover:bg-blue-700` appears exactly once (submit button, line 161).
- `text-red-500` appears exactly twice, both error-message contexts (load error line 109, post error line 155).
- No hardcoded hex/`rgb()` values in the file. Dominant/secondary background split (`bg-white`/`dark:bg-gray-800` body, `bg-gray-100`/`dark:bg-gray-700/50` header) matches declared 60/30 split.

### Pillar 4: Typography (4/4)
- Unchanged from prior audit — only `text-xs` and `text-sm` present; only `font-semibold` and `font-normal`/default present. No new sizes/weights introduced by the fix commit (toast text and chevron removal are non-typographic changes; textarea class swap doesn't touch typography).

### Pillar 5: Spacing (4/4)
- `gap-1.5` still used correctly and only in the header (line 92), matching the contract's explicit single-use exception.
- `py-2` still used on the submit button (line 161).
- `px-4 py-2` (header), `px-4 py-3` (comment rows, composer), `px-4 py-4`/`py-6` (error/empty states), `mt-4` (panel wrapper) — all on the declared 4/8/16 scale.
- **Previously flagged violation resolved:** textarea now uses `p-2` (line 148), removing the only off-scale value in the file. `grep -n "p-1.5" components/ControlCommentsPanel.tsx` returns no matches. Spacing is now fully internally consistent with the contract.

### Pillar 6: Experience Design (4/4)
- Loading state: inline animated SVG spinner (lines 100-107), unchanged and correct.
- Error state (load): distinct message, correctly excludes empty-state/comment-list rendering while shown (lines 108-112).
- Error state (post): distinct message scoped to composer only, doesn't blow away existing comment list (lines 154-156).
- Empty state: correct italic/centered copy (lines 113-117).
- Role gate: composer only renders `{isReviewer && (...)}` (line 145) — matches D-01/contract, no disabled-input leak.
- Disabled state: submit button disabled while `submitting` or when text is empty/whitespace-only (line 160).
- **Previously flagged gap resolved:** the post-success path now fires `showToast('Comment posted.', 'success')` (line 81) immediately after the comment is appended to local state and the textarea is cleared — this is the same feedback pattern used by every comparable write action in `FrameworkDetail.tsx` (`Evidence deleted.`, `Control added successfully!`). The toast call sits inside the `try` block after the async `postControlComment` resolves, so it correctly does not fire on the error path (verified: `catch` block only sets `postError`, no toast call there).
- No confirmation-for-destructive-action gap exists — D-03 makes comments immutable, so there is no delete affordance to lack a confirmation for.

---

## Files Audited
- `components/ControlCommentsPanel.tsx` (full file, 172 lines — current state post-fix-commit `66cb490`)
- `.planning/phases/42-comment-threads-on-compliance-controls/42-UI-SPEC.md` (design contract baseline)
- `.planning/phases/42-comment-threads-on-compliance-controls/42-UI-REVIEW.md` (prior audit, findings verified against)
- `.planning/phases/42-comment-threads-on-compliance-controls/42-CONTEXT.md`
- `.planning/phases/42-comment-threads-on-compliance-controls/42-01-SUMMARY.md`, `42-02-SUMMARY.md`, `42-03-SUMMARY.md`
</content>
