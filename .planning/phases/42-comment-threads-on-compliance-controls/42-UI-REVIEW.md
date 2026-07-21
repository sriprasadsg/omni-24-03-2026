# Phase 42 — UI Review

**Audited:** 2026-07-22
**Baseline:** `.planning/phases/42-comment-threads-on-compliance-controls/42-UI-SPEC.md` (design contract — note: contract's own "Checker Sign-Off" section is entirely unchecked, `Approval: pending`; this was never formally signed off before build)
**Screenshots:** not captured (no dev server on :3000 or :5173 — code-only audit)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 2/4 | Required "Comment posted." success toast is entirely absent from the implementation despite being an explicit contract line item and an established codebase pattern (`showToast`) used everywhere else in this same file's sibling handlers |
| 2. Visuals | 3/4 | `ChevronDownIcon` rendered in the header implies a collapse/expand affordance that does not exist — the panel is always open, and the chevron has no `onClick`/rotation state, misleading the user |
| 3. Color | 4/4 | Accent blue reserved exclusively for Post Comment button and `@mention` highlight, exactly as specified; no hardcoded hex; destructive red reserved for error text only |
| 4. Typography | 4/4 | Only `text-xs`/`text-sm` and `font-normal`/`font-semibold` used, matching the contract's declared two-size/two-weight vocabulary exactly |
| 5. Spacing | 3/4 | One undeclared off-scale value (`p-1.5` on the textarea) not sanctioned anywhere in the spacing scale — the contract's only approved 6px exception (`gap-1.5`) is scoped explicitly to the header only |
| 6. Experience Design | 3/4 | Loading/empty/error states all present and correctly gated; but the post-success path has no distinct feedback beyond the comment silently appearing in the list — no toast, no visual "just posted" cue, weaker signal than every comparable action in this codebase |

**Overall: 19/24**

---

## Top 3 Priority Fixes

1. **Missing "Comment posted." success toast** — Users who post a comment get no positive confirmation beyond the comment appearing inline (easy to miss if the panel isn't in view or the list is long); every other write action in `FrameworkDetail.tsx` (`Evidence deleted.`, `Control added successfully!`, `Evidence ${decision}`) uses `showToast(..., 'success')`. Fix: import `showToast` from `../utils/toast` in `ControlCommentsPanel.tsx` and call `showToast('Comment posted.', 'success')` on successful `postControlComment`, matching the UI-SPEC Copywriting Contract row verbatim.

2. **Dead chevron affordance in the panel header** — `ChevronDownIcon` is rendered next to "Comments (N)" with zero click handler or rotation logic, implying the panel can be collapsed/expanded when it cannot; this trains users to click a non-interactive element. Fix: either remove the chevron entirely (the UI-SPEC's own "Component Notes" only calls for "the same header-bar visual chrome... icon + label + count," not a chevron with no behavior) or wire it to an actual collapse toggle.

3. **Off-scale spacing value (`p-1.5`) on the composer textarea** — the UI-SPEC's spacing scale exceptions explicitly restrict the one approved 6px value (`gap-1.5`) to the panel header only, and no `p-1.5` value appears anywhere in the declared scale (4/8/16px). Fix: change `p-1.5` on the `<textarea>` to `p-2` (8px, the nearest value on the declared scale) to keep the component's spacing internally consistent with the rest of the panel.

---

## Detailed Findings

### Pillar 1: Copywriting (2/4)
- `components/ControlCommentsPanel.tsx` implements every other Copywriting Contract row correctly: panel header `Comments (N)` (line 92-93), placeholder `Add a comment... (use @username to mention someone)` (line 149), button labels `Post Comment`/`Posting...` (line 163), empty state `No comments yet on this control.` italic/centered/`text-gray-400` (line 113-115), load-error copy verbatim (line 62, 108-110), post-error copy verbatim (line 81, 154).
- **Missing entirely:** the contract's `Success toast (post): "Comment posted."` row (42-UI-SPEC.md, Copywriting Contract table). `grep -n "showToast" components/ControlCommentsPanel.tsx` returns zero matches — the component doesn't even import the utility. This is not a stylistic nit; it's a declared contract line that was silently dropped, and the codebase already has the exact mechanism used by every comparable handler in the same parent file (`services/apiService.ts` / `FrameworkDetail.tsx` lines 425, 58, 146 all call `showToast(..., 'success')` on successful writes).
- 42-03-SUMMARY.md's own Task 4 human-verify checklist (six items) never asked the human to confirm the success toast fired — the gap slipped through both the plan's acceptance criteria and the manual checkpoint.

### Pillar 2: Visuals (3/4)
- Clear focal point: single panel, header bar + body, consistent with `ChainOfCustodyPanel.tsx`'s sibling structure.
- `SendIcon` inside the submit button carries visible text (`Post Comment`/`Posting...`) alongside it, so no aria-label gap there.
- `ChevronDownIcon` (line 95) is rendered with no `onClick`, no rotation state, and no accompanying collapse logic anywhere in the component — it is pure decoration that visually promises interactivity `ChainOfCustodyPanel.tsx` actually has (click-to-expand) but this panel does not (per the UI-SPEC's own Interaction note, it fetches on mount instead of on click). Carrying the chevron over without carrying over the behavior it signals is a hierarchy/affordance mismatch.
- Visual hierarchy via weight/size differentiation (semibold author name vs. regular timestamp vs. regular body) is present and matches spec.

### Pillar 3: Color (4/4)
- `grep` confirms `text-blue-600`/`dark:text-blue-400` appears exactly twice: the mention-highlight span (line 37) and nowhere else as text color; `bg-blue-600 hover:bg-blue-700` appears exactly once, on the submit button (line 160) — matches the contract's "Reserved exclusively for" instruction precisely.
- `text-red-500` appears exactly twice, both error-message contexts (load error line 108, post error line 154) — matches "Reserved exclusively for" error text, no destructive action/button exists (correct, since D-03 makes comments immutable).
- No hardcoded hex/`rgb()` values found in the file.
- Dominant/secondary backgrounds (`bg-white`/`dark:bg-gray-800` for body, `bg-gray-100`/`dark:bg-gray-700/50` for header) match the declared 60/30 split.

### Pillar 4: Typography (4/4)
- Only two sizes present: `text-xs` (body, author, timestamp, empty/error states, textarea, button) and `text-sm` (header label) — matches the contract's declared two-size vocabulary exactly, no `text-lg`/`text-2xl`/etc. anywhere in the file.
- Only two weights present: `font-semibold` (header label, author name) and `font-normal`/default (timestamp, body text) — matches the contract's declared 400/600 vocabulary.

### Pillar 5: Spacing (3/4)
- `gap-1.5` used correctly and only in the header (line 90), matching the contract's explicit single-use exception.
- `py-2` used on the submit button (line 160) as required — the contract explicitly called out avoiding `py-3.5` here, and the executor complied.
- `px-4 py-2` (header), `px-4 py-3` (comment rows, composer), `px-4 py-4`/`py-6` (error/empty states), `mt-4` (panel wrapper) — all on the declared 4/8/16 scale.
- **Violation:** `p-1.5` (6px) on the `<textarea>` (line 147) is not on the declared scale (4/8/16) and is not the one sanctioned 6px exception (that exception is scoped to the header's `gap-1.5` only, per the UI-SPEC's explicit "carry forward for the new panel's header only, do not use elsewhere"). This is a small but real drift the executor introduced beyond what the contract authorized.

### Pillar 6: Experience Design (3/4)
- Loading state: inline animated SVG spinner cloned from `ChainOfCustodyPanel.tsx`, shown during initial fetch (lines 99-106).
- Error state (load): distinct message text (line 108-110), correctly excludes empty-state/comment-list rendering while shown.
- Error state (post): distinct message text scoped to the composer only, doesn't blow away the existing comment list (line 153-155).
- Empty state: correct italic/centered copy (lines 112-116).
- Role gate: composer only renders `{isReviewer && (...)}` (line 144) — no disabled input shown to non-reviewers, matching D-01/contract.
- Disabled state: submit button disabled while `submitting` or when text is empty/whitespace-only (line 159) — prevents empty-comment submission client-side (note: no client-side max-length guard mirroring the backend's `max_length=2000`, so a very long paste only fails after a round trip to the server — minor, not scored down further since backend enforces it).
- **Gap:** as noted under Copywriting, the post-success path provides only an implicit signal (comment appears in the list) with no toast — this is as much an Experience Design gap (a completed write action gives weaker feedback than every comparable write flow in the app) as a Copywriting one; scored down here for the missing feedback loop rather than double-penalizing the same root cause twice at full weight.
- No confirmation-for-destructive-action gap exists because D-03 makes comments immutable (no delete affordance to lack a confirmation for) — correctly scoped by omission.

---

## Files Audited
- `components/ControlCommentsPanel.tsx` (full file, 171 lines)
- `components/FrameworkDetail.tsx` (mount site, lines 1-40 imports/context, 415-436 render)
- `services/apiService.ts` (lines 4586-4626 — `fetchControlAuditLog`, `fetchControlComments`, `postControlComment`)
- `components/icons.tsx` (icon exports referenced: `ChevronDownIcon`, `ClockIcon`, `SendIcon`, `MessageSquareIcon`)
- `.planning/phases/42-comment-threads-on-compliance-controls/42-UI-SPEC.md` (design contract baseline)
- `.planning/phases/42-comment-threads-on-compliance-controls/42-01-PLAN.md`, `42-01-SUMMARY.md` (backend core)
- `.planning/phases/42-comment-threads-on-compliance-controls/42-02-PLAN.md`, `42-02-SUMMARY.md` (mention notifications)
- `.planning/phases/42-comment-threads-on-compliance-controls/42-03-PLAN.md`, `42-03-SUMMARY.md` (frontend panel)
- `.planning/phases/42-comment-threads-on-compliance-controls/42-CONTEXT.md`, `42-DISCUSSION-LOG.md`, `42-PATTERNS.md`
