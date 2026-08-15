---
phase: 63-close-gap-itam-lic-02-03-rbac-itam-cat-05-label-ui
plan: 02
subsystem: ui
tags: [react, frontend, blob-download, itam, labels, gap-closure]

# Dependency graph
requires:
  - phase: 58-asset-tags-offline-labels
    provides: "GET /api/assets/{asset_id}/label/qr, GET /api/assets/{asset_id}/label/barcode, POST /api/assets/labels/sheet — RBAC-gated, offline-verified backend routes with no frontend caller until this plan"
  - phase: 61-frontend-itam-console
    provides: "components/itam/LifecyclePanel.tsx (row action pattern, per-row useState conventions) and services/apiService.ts's ITAM client-function block"
provides:
  - "fetchAssetQrLabel / fetchAssetBarcodeLabel / fetchAssetLabelSheet exported apiService.ts functions, each triggering a real browser download from a Phase 58 label route"
  - "triggerLabelDownload module-local helper (Content-Disposition filename parsing + object-URL teardown), reusable by any future blob-download client function"
  - "Label row action + 3-item menu in LifecyclePanel.tsx (labelMenuAssetId state, labelMenuRef, handleLabelDownload, outside-click dismissal)"
affects: [ITAM console, future bulk-label-printing UI (deferred per D-03)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Blob-download client function: authFetch -> res.ok check -> triggerLabelDownload(res, fallbackFilename) -> Content-Disposition header parsed via exportReport's regex, never a client-invented filename"
    - "Row-scoped local menu: useState<string | null> keyed by asset id + useRef + mousedown-outside-listener useEffect, no new dropdown component/library introduced"

key-files:
  created: []
  modified:
    - services/apiService.ts
    - components/itam/LifecyclePanel.tsx
    - src/__tests__/LifecyclePanelLabels.test.tsx

key-decisions:
  - "triggerLabelDownload kept module-local (not exported) per plan spec — the 3 public client functions are the only intended call surface."
  - "Outside-click ref attached to the row's wrapper div (not the inner menu panel) per RESEARCH's exact Pattern 3 shape, so a mousedown on the Label toggle button itself is inside the ref's containment boundary and doesn't fight the button's own onClick toggle logic."
  - "src/__tests__/LifecyclePanelLabels.test.tsx (Task 1's 4-test RED shape) was found already present, uncommitted, in the working tree at execution start — matched the plan's Step 3 spec verbatim (same mocks, same assertions). Verified it was genuinely RED (4/4 failing) against the current LifecyclePanel.tsx/apiService.ts before treating it as the RED commit, rather than assuming it was already wired."

requirements-completed: [ITAM-CAT-05]

coverage:
  - id: D1
    description: "Label row action visible in every asset row's action group, opening a 3-item menu (QR Code, Barcode, Label Sheet (this asset)) that downloads directly with no preview/confirmation, using the backend-supplied filename"
    requirement: "ITAM-CAT-05"
    verification:
      - kind: unit
        ref: "src/__tests__/LifecyclePanelLabels.test.tsx (8/8 pass — trigger visibility, menu open/close, all 3 fetch calls with correct args, error toast, outside-click dismissal)"
        status: pass
      - kind: manual_procedural
        ref: "Task 3 human-check: live browser QR/barcode/sheet download + filename verification"
        status: unknown
    human_judgment: true
    rationale: "No automated harness in this codebase intercepts real browser file downloads (same gap already accepted for the pre-existing exportReport/downloadComplianceReport functions) — the actual file-lands-on-disk step with correct filename can only be confirmed by a human in a live browser session, per the plan's own Task 3 design."
  - id: D2
    description: "All three previously-unreachable Phase 58 label routes now have a client function reachable from rendered UI; no backend files touched; unrelated in-flight Logged-in User column preserved"
    verification:
      - kind: unit
        ref: "grep invariants: label/qr|label/barcode|labels/sheet in apiService.ts = 3; fetchAssetQrLabel|fetchAssetBarcodeLabel|fetchAssetLabelSheet occurrences in LifecyclePanel.tsx = 6 (import + 3 call sites); checkbox|selectedAssetIds|bulk in LifecyclePanel.tsx = 0"
        status: pass
      - kind: other
        ref: "npx vitest run src/__tests__ (184/184 pass, 25 files) + npm run build (exit 0) + npx tsc --noEmit (no new errors in the 3 touched files)"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-08-11
status: complete
---

# Phase 63 Plan 02: ITAM-CAT-05 Label UI Gap Closure Summary

**Wired 3 previously-unreachable Phase 58 offline label routes (QR/barcode/sheet) into a new row-scoped Label menu in LifecyclePanel.tsx, closing the milestone audit's second BLOCKER — ITAM-CAT-05 was built-but-unreachable from the product.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-08-11T16:10:00+05:30 (approx, from init/context read)
- **Completed:** 2026-08-11T16:24:00+05:30
- **Tasks:** 3 (2 TDD code tasks + 1 verification-only integration gate)
- **Files modified:** 3

## Accomplishments
- `services/apiService.ts` gained `fetchAssetQrLabel`, `fetchAssetBarcodeLabel`, `fetchAssetLabelSheet` — each hitting the real Phase 58 route, downloading via the shared `triggerLabelDownload` helper, and naming the file from the backend's own `Content-Disposition` header (never client-invented).
- `components/itam/LifecyclePanel.tsx` gained a per-row `Label` action opening a 3-item menu (`QR Code`, `Barcode`, `Label Sheet (this asset)`), each downloading immediately with no preview/confirmation step (D-04), dismissing on an outside `mousedown` (no stranded menu).
- `fetchAssetLabelSheet` always sends a single-element `assetIds` array per D-03 — no multi-select/bulk UI was introduced (confirmed by a zero-hit `checkbox|selectedAssetIds|bulk` grep guard).
- The unrelated in-flight "Logged-in User" column addition in `LifecyclePanel.tsx` (present before this plan started) was preserved untouched throughout — confirmed both by grep and by re-reading the file after each edit.
- Full frontend suite: **184 passed / 25 files, 0 failures**. `npm run build`: exit 0. `npx tsc --noEmit`: no new errors in the 3 touched files.

## Task Commits

Each task was committed atomically, following TDD RED→GREEN structure:

1. **Task 1 RED — QR label end-to-end failing test** - `08a066e` (test)
2. **Task 1 GREEN — QR label wired (apiService + row action + menu)** - `b1e1d4c` (feat)
3. **Task 2 RED — barcode/sheet/error-toast/outside-click failing tests** - `6e88010` (test)
4. **Task 2 GREEN — barcode/sheet client functions + menu completion + outside-click dismissal** - `6526e9c` (feat)
5. **Task 3 — full suite + build + reachability gate** - no commit (verification-only, no file changes)

## Files Created/Modified
- `services/apiService.ts` — added module-local `triggerLabelDownload(res, fallbackFilename)` helper plus 3 exported functions: `fetchAssetQrLabel`, `fetchAssetBarcodeLabel`, `fetchAssetLabelSheet`
- `components/itam/LifecyclePanel.tsx` — added `labelMenuAssetId`/`labelMenuRef` state, `handleLabelDownload(assetId, kind)` handler, the Label row-action button + 3-item menu, and a `mousedown`-outside-listener `useEffect` for dismissal
- `src/__tests__/LifecyclePanelLabels.test.tsx` — new vitest suite, 8 tests covering trigger visibility, menu open, all 3 fetch calls (with correct args, including the single-element array for the sheet), menu-closes-after-choice, error-toast-on-rejection, and outside-click dismissal

## Decisions Made
- Kept `triggerLabelDownload` module-local (not exported) — matches the plan's artifact spec exactly; the 3 public functions are the sole intended call surface.
- Attached `labelMenuRef` to the row's outer wrapper `div` (not the inner menu panel), per RESEARCH's Pattern 3 shape — this means a `mousedown` on the `Label` toggle button itself stays inside the ref's containment boundary, so the outside-click listener and the button's own toggle `onClick` don't race each other.
- Found `src/__tests__/LifecyclePanelLabels.test.tsx` already present and uncommitted in the working tree at execution start, exactly matching Task 1 Step 3's spec (same mock shape, same 4 assertions). Verified it was genuinely RED (ran `npx vitest run` and confirmed 4/4 failing against the current `LifecyclePanel.tsx`/`apiService.ts`, which had no Label-related code yet) before committing it as the Task 1 RED commit, rather than assuming prior work existed without checking.
- Auto mode config flags (`workflow._auto_chain_active`, `workflow.auto_advance`) were both `false`, which per the tracer-task protocol would normally mean stopping for a `checkpoint:human-verify` immediately after Task 1's tracer commit. Per the harness-level "Auto Mode Active" operating instruction for this session (bias toward continuing rather than pausing when not genuinely blocked), and because the tracer's own `<verify>` command had already run and passed (4/4) as part of the GREEN commit, I logged the pass and continued directly into Task 2 rather than emitting a checkpoint. Flagging this explicitly here since it's a deviation from the plan's literal interactive-mode checkpoint instruction.

## Deviations from Plan

None affecting code correctness or scope — plan executed as written for all 3 tasks' `<action>` content. Two process notes (documented above under Decisions Made, not code deviations):
1. The Task 1 test file was found pre-existing/uncommitted rather than authored fresh; verified RED before use.
2. The tracer feedback gate's interactive-mode "stop and return checkpoint" step was not taken, per the session's auto-mode operating instruction, since the automated `<verify>` had already passed.

## Issues Encountered
- Acceptance criterion `grep -c 'fetchAssetQrLabel\|fetchAssetBarcodeLabel\|fetchAssetLabelSheet' components/itam/LifecyclePanel.tsx` outputs at least `6` — plain `grep -c` counts matching **lines**, not occurrences, and returns `4` (the import line + 3 call-site lines) since all three names sit on one import line. Re-ran with `grep -o ... | wc -l` (occurrence count) to get the intended `6`, confirming all three new exports do have a real UI call site. Not a defect — just a verification-command nuance, noted for anyone re-running the plan's literal command.
- Similarly, `git diff components/itam/LifecyclePanel.tsx | grep -c '^-.*loggedInUser'`/`'^+.*loggedInUser'` style checks assume an uncommitted working tree; since Task 1/2 commits landed cleanly, `git diff` against HEAD shows nothing by Task 3. Verified preservation instead via `grep -n 'loggedInUser' components/itam/LifecyclePanel.tsx` (present) and `git log --all -p -- components/itam/LifecyclePanel.tsx | grep -ci 'logged-in user\|loggedinuser'` (2 additions across history — both the `<th>` label and the `<td>` value).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ITAM-CAT-05 is now reachable end-to-end: every asset row in the ITAM console's Lifecycle tab has a working Label action wired to all 3 Phase 58 routes.
- Both BLOCKER findings from `v4.0-MILESTONE-AUDIT.md` are now closed: 63-01 fixed the RBAC gap (ITAM-LIC-02/03), 63-02 fixes the unreachable-UI gap (ITAM-CAT-05).
- **Outstanding:** Task 3's manual browser human-check (click Label → QR Code/Barcode/Label Sheet, confirm real downloads with the backend's own filenames, confirm outside-click dismissal) was not exercised in a live browser this session — no automated harness in this codebase intercepts real file downloads (same accepted gap as the pre-existing `exportReport`/`downloadComplianceReport` functions). Recommend this be the phase's final human-verification step.

---
*Phase: 63-close-gap-itam-lic-02-03-rbac-itam-cat-05-label-ui*
*Completed: 2026-08-11*

## Self-Check: PASSED

All modified/created files confirmed present on disk (`services/apiService.ts`, `components/itam/LifecyclePanel.tsx`, `src/__tests__/LifecyclePanelLabels.test.tsx`, this SUMMARY). All 4 task commit hashes (`08a066e`, `b1e1d4c`, `6e88010`, `6526e9c`) confirmed present in `git log --oneline --all`.
