---
phase: 42-comment-threads-on-compliance-controls
plan: 03
subsystem: ui
tags: [react, typescript, tailwind, xss-safe-rendering, rbac]

# Dependency graph
requires:
  - phase: 42-comment-threads-on-compliance-controls
    plan: 01
    provides: control_comments_service.add_comment/list_comments + control_comments_endpoints.post_control_comment/get_control_comments (persistence + role gating)
  - phase: 42-comment-threads-on-compliance-controls
    plan: 02
    provides: extract_mention_tokens/resolve_mentions + in-app-only @mention notification dispatch (channels=[])
provides:
  - "services/apiService.ts: fetchControlComments(controlId) / postControlComment(controlId, text)"
  - "components/ControlCommentsPanel.tsx: fetch-on-mount comment thread with XSS-safe @mention rendering and role-gated composer"
  - "components/FrameworkDetail.tsx: ControlCommentsPanel mounted unconditionally after ChainOfCustodyPanel in the expanded control row"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "renderCommentText: split(/(@[\\w.-]+)/g) + map, never dangerouslySetInnerHTML — all comment text flows through React's default JSX child escaping"
    - "_REVIEWER_ROLES hand-synced literal (admin/super_admin/compliance_reviewer) mirroring EvidenceReviewPanel's existing UX-only frontend role gate; backend _COMMENT_AUTHOR_ROLES is the authoritative enforcement"
    - "Composer wrapped in a whole-block {isReviewer && (...)} conditional — no disabled input rendered for non-reviewers"

key-files:
  created:
    - components/ControlCommentsPanel.tsx
  modified:
    - services/apiService.ts
    - components/FrameworkDetail.tsx

key-decisions:
  - "42-03: fetchControlComments is non-throwing (returns [] on error/non-ok), matching the existing fetchControlAuditLog convention; postControlComment throws on non-ok so the composer can surface a post-error"
  - "42-03: ControlCommentsPanel mount is NOT wrapped in the canViewCoC guard — read access is available to all authenticated tenant users (A2); composer visibility is gated inside the panel via isReviewer"
  - "42-03: Rule 1 auto-fix — reworded the anti-XSS code comment in ControlCommentsPanel.tsx (originally spelled out the literal forbidden-prop name) so it no longer trips the plan's own grep-based dangerouslySetInnerHTML acceptance gate; no behavior change"

patterns-established:
  - "renderCommentText's safe split/map @mention-highlighting pattern is reusable by any future free-text field that needs inline @token highlighting without raw-HTML injection"

requirements-completed: [CMT-01]

coverage:
  - id: D1
    description: "fetchControlComments/postControlComment API wrappers added to apiService.ts, matching the authFetch convention"
    requirement: "CMT-01"
    verification:
      - kind: other
        ref: "grep -Eq 'export const fetchControlComments' services/apiService.ts && grep -Eq 'export const postControlComment' services/apiService.ts"
        status: pass
    human_judgment: false
  - id: D2
    description: "ControlCommentsPanel renders a fetch-on-mount thread with XSS-safe @mention rendering and a role-gated composer"
    requirement: "CMT-01"
    verification:
      - kind: other
        ref: "grep -q 'export const ControlCommentsPanel' components/ControlCommentsPanel.tsx && ! grep -q 'dangerouslySetInnerHTML' components/ControlCommentsPanel.tsx"
        status: pass
    human_judgment: false
  - id: D3
    description: "ControlCommentsPanel mounted in FrameworkDetail.tsx's expanded control row, immediately after ChainOfCustodyPanel"
    requirement: "CMT-01"
    verification:
      - kind: other
        ref: "grep -q 'import { ControlCommentsPanel }' components/FrameworkDetail.tsx && grep -q '<ControlCommentsPanel controlId={control.id} />' components/FrameworkDetail.tsx"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live browser verification: panel renders below Chain of Custody, post+persist works, @mention notification delivery works, non-reviewer sees read-only thread with no composer, comment text renders escaped"
    requirement: "CMT-01"
    verification: []
    human_judgment: true
    rationale: "Task 4 was an explicit checkpoint:human-verify blocking gate requiring a live browser session (render, post, cross-user @mention notification, RBAC visibility, escaped-text rendering) — not automatable via source-grep or unit test. Human confirmed all 6 steps pass ('approved')."

# Metrics
duration: ~4min (Tasks 1-3 code); checkpoint approval elapsed separately
completed: 2026-07-21
status: complete
---

# Phase 42 Plan 03: Frontend Comment Thread (ControlCommentsPanel) Summary

**Two thin `apiService.ts` wrappers, a fetch-on-mount `ControlCommentsPanel` with XSS-safe @mention highlighting and a role-gated composer, mounted unconditionally in `FrameworkDetail.tsx`'s expanded control row right after the Chain of Custody panel — confirmed live in a browser (render, post+persist, cross-user @mention notification delivery, non-reviewer read-only view, escaped comment text).**

## Performance

- **Duration:** ~4 min (Tasks 1-3 code execution); Task 4 (human-verify checkpoint) elapsed separately across the session pause
- **Started:** 2026-07-21T14:05:31+05:30
- **Completed:** 2026-07-21 (checkpoint approved)
- **Tasks:** 4 (3 auto + 1 checkpoint:human-verify)
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- `fetchControlComments(controlId)` / `postControlComment(controlId, text)` added to `services/apiService.ts`, cloning the existing `fetchControlAuditLog` non-throwing-GET / throwing-POST conventions.
- `components/ControlCommentsPanel.tsx` — fetch-on-mount (`useEffect` keyed on `controlId`) comment thread: `Comments (N)` header, italic empty state, oldest-first rendering, `renderCommentText` safely splits on `@token` and wraps mentions in an accent-blue span (never `dangerouslySetInnerHTML`), composer rendered only inside `{isReviewer && (...)}` using the hand-synced `_REVIEWER_ROLES` literal.
- `components/FrameworkDetail.tsx` mounts `<ControlCommentsPanel controlId={control.id} />` unconditionally (no `canViewCoC` guard) immediately after the existing `ChainOfCustodyPanel` mount — closes Pitfall 5 (built-but-unmounted).
- Live browser verification (Task 4, human-approved): comment panel renders below Chain of Custody; posting a comment appears immediately and survives collapse/re-expand; an `@mention` in a posted comment delivers a "You were mentioned" notification to the mentioned user; a non-reviewer sees the read-only thread with no composer; `<b>`-style text in a comment renders as literal escaped text, not HTML.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add fetch/post API wrappers** - `d98fc13` (feat)
2. **Task 2: Build ControlCommentsPanel.tsx** - `28eff7b` (feat)
3. **Task 3: Mount ControlCommentsPanel in FrameworkDetail.tsx** - `ca1fc52` (feat)
4. **Task 4: Human-verify live render, post, persistence, @mention delivery** - checkpoint:human-verify, gate=blocking — no code changes; human responded "approved" confirming all 6 verification steps pass

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `services/apiService.ts` - `fetchControlComments`/`postControlComment` wrappers
- `components/ControlCommentsPanel.tsx` - fetch-on-mount comment thread, XSS-safe @mention rendering, role-gated composer
- `components/FrameworkDetail.tsx` - imports and mounts `ControlCommentsPanel` after `ChainOfCustodyPanel` in the expanded control row

## Decisions Made
- `fetchControlComments` is non-throwing (returns `[]` on error) so a load failure degrades to an empty-state-shaped error message rather than crashing the panel; `postControlComment` throws so the composer can surface a distinct post-error.
- The new mount is deliberately NOT wrapped in the `canViewCoC` guard — per A2, comment-thread reads are available to all authenticated tenant users; only the composer is role-gated, and only inside the panel itself.
- Rule 1 auto-fix: the anti-XSS code comment above `renderCommentText` originally spelled out the literal forbidden prop name, which tripped the plan's own `grep -q 'dangerouslySetInnerHTML'` acceptance gate against the comment text itself, not real usage. Reworded to describe the rule without repeating the literal string ("NEVER use the raw-HTML injection prop..."). No behavior change — the component still never calls that prop; confirmed by `grep -c 'dangerouslySetInnerHTML' components/ControlCommentsPanel.tsx` returning 0.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Anti-XSS code comment tripped its own grep-based acceptance gate**
- **Found during:** Task 2 (Build ControlCommentsPanel.tsx), while running the task's own automated verify command
- **Issue:** The initial explanatory comment above `renderCommentText` spelled out the literal forbidden prop name (`dangerouslySetInnerHTML`) as prose, which the plan's `! grep -q "dangerouslySetInnerHTML" components/ControlCommentsPanel.tsx` verify check matched against — a false positive on a comment, not real usage.
- **Fix:** Reworded the comment to describe the rule ("NEVER use the raw-HTML injection prop...") without repeating the literal identifier. No functional/behavioral change; the component still never invokes that prop.
- **Files modified:** `components/ControlCommentsPanel.tsx`
- **Verification:** `grep -c 'dangerouslySetInnerHTML' components/ControlCommentsPanel.tsx` returns 0; task's automated verify command passes.
- **Committed in:** `28eff7b` (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1)
**Impact on plan:** Comment-only wording fix required to make the plan's own acceptance gate pass; no behavior change, no scope creep.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Phase 42 (Comment Threads on Compliance Controls) is now fully complete across all 3 plans: 42-01 (backend persistence + role gating), 42-02 (@mention extraction/resolution + in-app-only notification dispatch), 42-03 (frontend panel + mount, live-verified). CMT-01 is functionally complete end-to-end and live-browser-verified. No blockers for subsequent v3.2 phases (43, 44).

---
*Phase: 42-comment-threads-on-compliance-controls*
*Completed: 2026-07-21*
