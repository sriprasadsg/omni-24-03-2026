# Phase 08 — UI Review

**Audited:** 2026-07-05
**Baseline:** 08-UI-SPEC.md (design contract, approval: pending)
**Screenshots:** not captured (no dev server detected on :3000 or :5173 — code-only audit)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Every string in the spec's Copywriting Contract table is implemented verbatim. |
| 2. Visuals | 2/4 | Trigger button is visually indistinguishable from "Import Controls" — same icon, same classes, sitting side-by-side; no focal differentiation. |
| 3. Color | 3/4 | Indigo accent correctly scoped to submit button only; but the preview list's control-id text also uses `text-indigo-600`, a second accent usage not declared in the spec. |
| 4. Typography | 4/4 | Only the four declared sizes (`text-lg`, `text-sm`, `text-xs`, plus base) and two weights (`font-medium`/`font-semibold`, `font-bold`) are used; matches spec. |
| 5. Spacing | 4/4 | All spacing classes match the declared 8-point scale (`p-4`, `p-6`, `gap-2`, `gap-3`, `mt-4`, `mb-4`); no arbitrary values found. |
| 6. Experience Design | 3/4 | All 3 UI states implemented (form/422/success) with proper `role="alert"`/`role="status"`, but focus management and drag-and-drop from the spec are missing. |

**Overall: 20/24**

---

## Top 3 Priority Fixes

1. **Icon collision between "Import Controls" and "Bulk Upload Evidence" buttons** — Both buttons use `<UploadIcon size={14} className="mr-1.5" />` with identical container classes (`components/FrameworkDetail.tsx:159-166` vs `168-176`), sitting adjacent in the header row. Users cannot visually distinguish the two actions at a glance — this directly contradicts Pillar 2 (visual hierarchy) and increases mis-click risk on a data-mutating action. **Fix:** swap the bulk button's icon per the spec's OQ-1 fallback intent (spec anticipated `ArchiveIcon`, not a second `UploadIcon`); use a distinguishable icon (e.g. `FileTextIcon`/`FolderIcon`) or add a visual separator/grouping label.

2. **Focus management from UI-SPEC Section 8 is not implemented** — Spec requires: focus moves to first interactive element on modal open, focus returns to trigger button on close, and focus auto-moves to the "Close" button after success (`08-UI-SPEC.md` lines 487-492). None of `BulkEvidenceUploadModal.tsx` implements `useRef`/`.focus()` calls for any of these — only the `Escape` keydown handler exists (lines 23-27). Keyboard and screen-reader users have no programmatic focus entry point into the modal, and after success, focus is stranded. **Fix:** add a `useEffect` on mount to focus the zip drop zone, an `onClose` wrapper in `FrameworkDetail.tsx` that restores focus to the trigger button, and a `useEffect` on `successResult` to focus the Close button.

3. **Drag-and-drop not implemented on zip drop zone despite spec resolution (OQ-3)** — Spec explicitly resolves OQ-3 recommending drag-and-drop support on the zip zone for UX consistency with `ControlEvidenceUploadModal`. The implemented drop zone (`BulkEvidenceUploadModal.tsx:86-106`) only has `onClick`/`onKeyDown` handlers — no `onDrop`/`onDragOver` — despite copy explicitly stating "Drop zip here or click" (line 102), which is now a false affordance. **Fix:** either implement `onDrop`/`onDragOver` handlers or change the copy to "Click to select zip file" to avoid promising unsupported behavior.

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)
- All copy matches the contract exactly: "Bulk Evidence Upload" (line 73), "Upload a zip file and a JSON manifest to attach multiple evidence files to controls." (line 79), "1. Select zip file" / "2. Select manifest JSON" / "3. Preview — {N} files mapped" (lines 85, 111, 132), "Upload Batch"/"Uploading..." (line 192), "Cancel"/"Close" (line 187), format hint and file-type hint strings (lines 121, 144), "Batch rejected — {N} file(s) failed validation" (line 153), success copy (lines 177-180), and all four fatal-error strings mapped correctly in `handleSubmit` (lines 58-64).
- Minor deviation: manifest empty-state copy differs from spec. Spec declares "No manifest loaded. Select a JSON manifest file to preview the file list." but implementation shows "Click to select manifest JSON file" (line 119) — the declared empty-state string is never rendered anywhere in the component. This is a real, if minor, contract deviation (WARNING).

### Pillar 2: Visuals (2/4)
- BLOCKER-adjacent WARNING: "Bulk Upload Evidence" (`FrameworkDetail.tsx:168-176`) and "Import Controls" (`FrameworkDetail.tsx:159-166`) are adjacent buttons with byte-identical styling and the same `UploadIcon`. No hierarchy, color, or shape differentiates a bulk-mutating action from a simple import trigger.
- Icon-only close button (`XIcon`, line 74-76) correctly has `aria-label="Close bulk evidence upload modal"` — pass.
- Visual hierarchy inside the modal is otherwise good: heading (`text-lg font-bold`) > section labels (`text-sm font-medium`) > hints (`text-xs`) creates a clear reading order.
- Modal focal point (the form) is centered and dims the background correctly (`bg-black bg-opacity-50`).

### Pillar 3: Color (3/4)
- Accent (indigo) is used on the submit button (line 191) as declared.
- However, `entry.control_id` in the preview list also renders with `text-indigo-600 dark:text-indigo-400` (line 139) — this is a second, undeclared use of the accent color. The spec states: "Accent (indigo) reserved for: the 'Upload Batch' submit button. No other element uses indigo accent in this modal." This is a direct contract violation, however minor in visual impact.
- Warning/destructive/success colors (amber, red, green) are all correctly scoped to their respective error/success blocks and match declared hex-equivalent Tailwind classes.
- No hardcoded hex/rgb colors found in the component.

### Pillar 4: Typography (4/4)
- Distinct sizes used: `text-lg` (heading), `text-sm` (labels/body), `text-xs` (hints/sub-labels) — matches the spec's declared four roles (base text size for e.g. filenames uses `text-sm` too, consistent with spec's "Body/form labels" and "File list rows" both being 14px).
- Weights used: `font-bold` (heading), `font-medium` (labels), `font-semibold` (amber error heading, success count) — all match the two-weight contract (400/700 with 500 for labels); `font-semibold` for success/error headings is a reasonable emphasis choice within the existing weight vocabulary and not flagged as a violation since the spec's table lists file-list rows as 400 but batch-rejection headers correctly warrant the heavier weight already implied by "text-sm font-semibold" pattern used elsewhere in the codebase.

### Pillar 5: Spacing (4/4)
- Spacing classes observed: `p-4`, `p-6`, `mb-4`, `mb-1`, `mt-4`, `mt-6`, `mt-1`, `mt-0.5`, `mt-3`, `pt-4`, `gap-1`, `gap-2`, `gap-3`, `px-3`, `py-2`, `py-2.5`, `py-1.5` — all map cleanly onto the declared 8-point scale (4/8/16/24px) or half-steps documented as exceptions (e.g. `py-2.5` ≈ 10px for header rows, consistent with existing `ControlEvidenceUploadModal` patterns referenced in spec).
- No arbitrary bracket values (`[...px]`, `[...rem]`) found in the component except the pre-approved `max-h-[90vh]` on the modal panel, which is explicitly specified in the design contract (Section 3).

### Pillar 6: Experience Design (3/4)
- Loading state: `uploading` boolean disables submit and shows "Uploading..." with `aria-busy={uploading}` — present and correct (line 190-193).
- Error states: both per-file (422, amber, `role="alert"`) and fatal (400/413/500, red banner) are implemented and correctly mapped from `err.status`/`err.detail` (lines 57-65).
- Empty states: zip/manifest empty states render placeholder copy and icons — present.
- Missing: focus management (see Top Fix #2) — WARNING, degrades keyboard/screen-reader UX but doesn't block task completion since Tab order still reaches all elements eventually.
- Missing: drag-and-drop (see Top Fix #3) — WARNING, copy promises unsupported behavior.
- Destructive-action confirmation: correctly not required per spec (upload is additive-only) — pass.
- Registry audit: `components.json` not found in project root — shadcn not initialized, registry safety audit skipped per protocol.

---

## Files Audited

- `components/BulkEvidenceUploadModal.tsx` (202 lines)
- `components/FrameworkDetail.tsx` (lines 1-50, 155-190, 460-475 — trigger button, state, mount)
- `services/apiService.ts` (lines 715-750 — `uploadBulkEvidence`, `ManifestEntry`, `BulkUploadResult`)
- `components/icons.tsx` (icon availability check: `UploadIcon`, `CheckCircleIcon`, `XIcon`, `AlertTriangleIcon`)
- `.planning/phases/08-bulk-evidence-upload/08-UI-SPEC.md` (design contract)
- `.planning/phases/08-bulk-evidence-upload/08-01-SUMMARY.md`, `08-02-SUMMARY.md`
- `.planning/phases/08-bulk-evidence-upload/08-01-PLAN.md`, `08-02-PLAN.md`
</content>
