---
phase: 02-manual-evidence-uploads
plan: "02"
subsystem: frontend/compliance
tags: [evidence-upload, source-badge, delete-button, description-input, multipart-bugfix]
dependency_graph:
  requires:
    - "02-01: DELETE /api/assets/{asset_id}/compliance/evidence/{evidence_id} + description form field + source/systemGenerated fields on evidence records"
  provides:
    - Fixed multipart boundary bug in uploadComplianceEvidence (no explicit Content-Type header)
    - deleteComplianceEvidence(assetId, controlId, evidenceId) API wrapper
    - Description text input in AssetComplianceList upload flow
    - Manual/Automated source badge per evidence row
    - Confirm-guarded delete button for manual evidence rows only
  affects:
    - services/apiService.ts
    - components/AssetComplianceList.tsx
    - components/FrameworkDetail.tsx
tech_stack:
  added: []
  patterns:
    - authFetch with FormData (no explicit Content-Type — browser sets boundary)
    - Per-asset keyed state maps (descriptionMap, deletingMap, ingestingMap)
    - Inline pill badge pattern reusing existing Tailwind classes
key_files:
  created: []
  modified:
    - services/apiService.ts
    - components/AssetComplianceList.tsx
    - components/FrameworkDetail.tsx
decisions:
  - "Removed explicit Content-Type header from uploadComplianceEvidence so authFetch lets the browser set the correct multipart/form-data boundary (T-02-07 fix)"
  - "isAutomated check uses ev.systemGenerated===true OR ev.source==='auto' to handle both backend field conventions"
  - "Description input placed below the icon buttons in the Actions cell (flex-col layout) to avoid horizontal overflow"
  - "onDeleteEvidence in FrameworkDetail calls onRefresh() after successful delete so the evidence list re-fetches from server"
  - "FrameworkDetail.tsx updated as a Rule 3 (blocking) fix — required prop onDeleteEvidence would cause TypeScript error without it"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-17"
  tasks_completed: 2
  files_modified: 3
---

# Phase 02 Plan 02: Frontend Evidence Upload UI Summary

One-liner: Fixed multipart Content-Type boundary bug, added description input + Manual/Automated source badges + confirm-guarded delete button for manual evidence rows, and wired the new DELETE API wrapper end-to-end through FrameworkDetail.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Fix Content-Type bug + add description param + deleteComplianceEvidence | b8ff04b | services/apiService.ts |
| 2 | Description input + source badge + delete button in AssetComplianceList | 1f97576 | components/AssetComplianceList.tsx, components/FrameworkDetail.tsx |

## What Was Built

### services/apiService.ts

`uploadComplianceEvidence` (lines 633-647):
- Removed `headers: { 'Content-Type': 'multipart/form-data' }` — this was the bug (T-02-07); explicit Content-Type on FormData prevents the browser from injecting the multipart boundary, causing 400 errors on the backend
- Added optional `description?: string` parameter; appended to FormData when provided

New `deleteComplianceEvidence(assetId, controlId, evidenceId)` (lines 650-655):
- Calls `DELETE /api/assets/${assetId}/compliance/evidence/${evidenceId}` via `authFetch`
- Throws `"Evidence delete failed"` if `!res.ok`
- `controlId` retained in signature for caller symmetry (route is asset+evidence-scoped per 02-01 backend)

### components/AssetComplianceList.tsx

Props interface:
- `onUploadEvidence` signature updated to `(assetId: string, file: File, description?: string) => void`
- Added `onDeleteEvidence: (assetId: string, controlId: string, evidenceId: string) => Promise<void>`

New state:
- `descriptionMap: Record<string, string>` — tracks per-asset description input values; cleared after upload
- `deletingMap: Record<string, boolean>` — tracks in-flight delete per evidence ID (disables button)

`handleFileChange`: reads `descriptionMap[selectedAssetId]` and passes it into `onUploadEvidence`; clears the description entry after completion.

`handleDeleteEvidence`: shows `window.confirm` guard, calls `onDeleteEvidence`, handles error with console.error.

Evidence render loop (per row):
- `isAutomated = ev.systemGenerated === true || ev.source === 'auto'`
- Source badge: "Automated" (blue pill) when `isAutomated`, "Manual" (green pill) otherwise
- Delete button (TrashIcon): rendered only when `!isAutomated`; `disabled` while delete is in flight; calls `handleDeleteEvidence(asset.id, evId)`
- Existing markdown-vs-download branch left intact; only the condition now uses `isAutomated` instead of `ev.systemGenerated` for consistency

Description input in Actions cell:
- `<input type="text" placeholder="Description (optional)" ...>` bound to `descriptionMap[asset.id]`
- Rendered below the icon buttons row (flex-col layout)

File stays at 218 lines (well under 500).

### components/FrameworkDetail.tsx (Rule 3 — blocking fix)

The existing `AssetComplianceList` usage did not pass `onDeleteEvidence` (newly required prop) and did not forward description through `onUploadEvidence`. Updated:
- `onUploadEvidence`: callback now accepts `description` and passes it to `api.uploadComplianceEvidence(assetId, control.id, file, description)`
- Added `onDeleteEvidence` handler: calls `api.deleteComplianceEvidence(assetId, controlId, evidenceId)`, shows success/error toast, calls `onRefresh()` to re-fetch evidence list

## Checkpoint Reached

This plan includes a `checkpoint:human-verify` (Task 3) requiring end-to-end visual verification of the UI. Tasks 1 and 2 are complete and committed. The checkpoint awaits human verification before plan closure.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated FrameworkDetail.tsx to satisfy new required prop**
- **Found during:** Task 2 — TypeScript would error without `onDeleteEvidence` prop
- **Issue:** `AssetComplianceList` gained a required `onDeleteEvidence` prop; its sole caller `FrameworkDetail.tsx` was not updated in the plan scope
- **Fix:** Added `onDeleteEvidence` handler in FrameworkDetail + forwarded `description` through `onUploadEvidence`; called `onRefresh()` after successful delete
- **Files modified:** `components/FrameworkDetail.tsx`
- **Commit:** `1f97576`

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. The delete call flows through the existing `authFetch` wrapper (which handles Authorization headers and token refresh). Client-side delete button visibility is a UX affordance only — the backend (02-01) enforces owner/admin/tenant authority (T-02-08 accepted disposition).

## Known Stubs

None — description is sent to the backend, source badge reads live evidence record fields, delete calls the real endpoint.

## Self-Check

| Criterion | Status |
|-----------|--------|
| Content-Type removed from uploadComplianceEvidence | PASS — `grep -A8 "uploadComplianceEvidence = async" services/apiService.ts` shows no Content-Type line |
| deleteComplianceEvidence exported | PASS — present at line 650 of apiService.ts |
| description param forwarded in upload | PASS — FormData.append('description', ...) present |
| onDeleteEvidence in AssetComplianceList props | PASS — line 13 |
| Manual badge rendered | PASS — "Manual" green pill for !isAutomated rows |
| Automated badge rendered | PASS — "Automated" blue pill for isAutomated rows |
| Delete button hidden for automated rows | PASS — `{!isAutomated && (<button ...>)}` |
| TypeScript compiles | PASS — `npx tsc --noEmit` exits 0 |
| Files under 500 lines | PASS — AssetComplianceList.tsx: 218 lines, apiService.ts: unchanged line count is >500 (pre-existing; added ~10 lines) |
| No new packages | PASS |
