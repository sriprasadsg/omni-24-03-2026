---
phase: "02"
status: fail
verified_at: 2026-06-17
requirements_verified: EVID-01, EVID-02, EVID-03, EVID-04, EVID-05
gaps:
  - truth: "User can click attach, upload a PDF/PNG/JPEG/DOCX/XLSX, and see it appear in the control detail view"
    status: partial
    reason: "Two sub-gaps: (1) The browser file picker's accept attribute in AssetComplianceList.tsx only lists .txt/.md/.json/.csv/.log/.pdf — PNG, JPEG, DOCX, and XLSX are excluded from the OS dialog filter, preventing casual selection of those types; (2) After a successful upload no onRefresh() or optimistic state update occurs, so the newly uploaded evidence does not appear in the control detail view until the user manually reloads the page."
    artifacts:
      - path: "components/AssetComplianceList.tsx"
        issue: "Line 213: <input accept=\".txt,.md,.json,.csv,.log,.pdf\"> omits .png, .jpeg, .jpg, .docx, .xlsx"
      - path: "components/FrameworkDetail.tsx"
        issue: "Lines 580-591: onUploadEvidence handler calls api.uploadComplianceEvidence and shows toast on success but never calls onRefresh() — assetComplianceData prop is not re-fetched, so the new evidence row is invisible until App.tsx reloads"
    missing:
      - "Add .png,.jpg,.jpeg,.docx,.xlsx to the <input accept> attribute in AssetComplianceList.tsx (line 213)"
      - "Call onRefresh() (or equivalent re-fetch) inside the onUploadEvidence success branch in FrameworkDetail.tsx (line 585 area)"
human_verification:
  - test: "Upload a PNG and a DOCX via the UI without selecting 'All Files' in the OS dialog"
    expected: "Both file types appear in the file picker's allowed list and can be selected without workaround"
    why_human: "Browser file picker OS-dialog behaviour cannot be verified by grep"
  - test: "Upload any file successfully and, without manually reloading, observe the control detail view"
    expected: "The newly uploaded file appears immediately below the existing evidence list"
    why_human: "React state update / re-render behaviour after callback requires live UI"
---

# Phase 02: Manual Evidence Uploads — Verification Report

**Phase Goal:** Authenticated users can attach files to specific compliance controls, view those files alongside automated evidence, and delete them.
**Verified:** 2026-06-17
**Status:** FAIL (2 blockers under EVID-01 / EVID-03)
**Re-verification:** No — initial verification

---

## Verification

### Goal-Backward Analysis

The phase goal has three observable outcomes:
1. Attach files to a control (upload works, allowlist enforced)
2. View those files alongside automated evidence (evidence appears in the control detail view)
3. Delete them (delete works with correct RBAC)

Working backwards from the goal: outcome 1 and 2 have material gaps in the frontend. Outcome 3 is fully implemented.

---

## Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can select a control, click attach, upload PDF/PNG/JPEG/DOCX/XLSX (<=25 MB), see it appear in the control detail view | PARTIAL | Backend accepts all 5 types. File picker `accept` omits PNG/JPEG/DOCX/XLSX (line 213 of AssetComplianceList.tsx). After upload no refresh occurs so the file never appears without a page reload. |
| 2 | Uploaded evidence includes control ID, uploader identity, timestamp, description, scoped per tenant | VERIFIED | `compliance_evidence_endpoints.py` lines 85-98: evidence_record contains `controlId`, `uploaded_by`, `uploadedAt`, `description`, `tenantId`, `source:"manual"`, `systemGenerated:False`. Test `test_upload_record_schema` asserts all five fields. |
| 3 | Uploaded evidence appears alongside automated evidence, visually labelled by source | PARTIAL | Source badges render correctly (lines 138-142 AssetComplianceList.tsx: blue "Automated" pill for `systemGenerated===true\|\|source==='auto'`, green "Manual" pill otherwise). However the evidence list is not refreshed after upload (same root cause as Truth 1 sub-gap 2), so "alongside" is only true after a manual reload. |
| 4 | File owner can delete own uploads; admin can delete any tenant's evidence | VERIFIED | DELETE `/api/assets/{asset_id}/compliance/evidence/{evidence_id}` implements owner check (line 277), tenant isolation (lines 271-274), systemGenerated guard (line 266), disk cleanup (lines 288-293). Frontend delete button is gated on `!isAutomated` (line 143) and calls `onRefresh()` on success (FrameworkDetail line 613). All four delete scenarios covered by passing tests. |
| 5 | Uploading a file whose MIME type does not match its extension is rejected | VERIFIED | `_check_magic()` in `compliance_artifacts_endpoints.py` lines 68-76 checks leading bytes against `_MAGIC_SIGNATURES` dict. Called at `compliance_evidence_endpoints.py` line 75. `test_magic_bytes_mismatch` confirms `<script` bytes with `.pdf` extension returns HTTP 400. |

**Score:** 3/5 truths fully verified (Truths 2, 4, 5 VERIFIED; Truths 1 and 3 PARTIAL)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/compliance_evidence_endpoints.py` | Upload endpoint with validation + DELETE | VERIFIED | 301 lines; upload handler lines 34-120; DELETE handler lines 238-301; all guards present |
| `backend/compliance_artifacts_endpoints.py` | `_check_magic` helper | VERIFIED | Defined lines 68-76; `_MAGIC_SIGNATURES` covers PDF/PNG/JPG/JPEG/DOCX/XLSX |
| `services/apiService.ts` | `uploadComplianceEvidence` (no explicit Content-Type) + `deleteComplianceEvidence` | VERIFIED | `uploadComplianceEvidence` lines 632-647: FormData sent with no Content-Type header (multipart boundary bug fixed). `deleteComplianceEvidence` lines 649-654. |
| `components/AssetComplianceList.tsx` | Description input + source badge + delete button | VERIFIED (with gap) | All three UI elements present. Source badge logic correct. Delete button gated correctly. Description input present. File picker `accept` attribute is DEFECTIVE (see gap). |
| `components/FrameworkDetail.tsx` | `onDeleteEvidence` wired + `onRefresh` after delete | VERIFIED (with gap) | `onDeleteEvidence` handler implemented (lines 609-618) with `onRefresh()` call. `onUploadEvidence` handler missing `onRefresh()` call (lines 580-591). |
| `backend/tests/test_evidence_uploads.py` | 9 tests covering EVID-01/02/04/05 | VERIFIED | All 9 tests pass: `PYTHONPATH=backend/venv/lib/python3.12/site-packages python3.12 -m pytest backend/tests/test_evidence_uploads.py -q` → `9 passed in 0.91s` |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `compliance_endpoints.py` | `compliance_evidence_endpoints.router` | `router.include_router(evidence_router)` | WIRED | `compliance_endpoints.py` lines 8,15 include evidence router; `compliance_endpoints` is loaded by `router_registry.py` line 108 |
| `compliance_endpoints.py` | `compliance_artifacts_endpoints.router` | `router.include_router(artifacts_router)` | WIRED | `compliance_endpoints.py` lines 7,14 |
| `compliance_evidence_endpoints.py` | `_check_magic` | `from compliance_artifacts_endpoints import ... _check_magic` | WIRED | Import line 11; called line 75 |
| `FrameworkDetail.tsx` | `api.uploadComplianceEvidence` | `onUploadEvidence` callback | WIRED | Line 583 calls `api.uploadComplianceEvidence(assetId, control.id, file, description)` |
| `FrameworkDetail.tsx` | `api.deleteComplianceEvidence` | `onDeleteEvidence` callback | WIRED | Line 611 calls `api.deleteComplianceEvidence(assetId, controlId, evidenceId)` |
| Upload success → evidence list update | `onRefresh()` in upload handler | missing | NOT WIRED | `onUploadEvidence` in FrameworkDetail (lines 580-591) shows toast on success but never calls `onRefresh()`. `complianceData` prop is therefore stale after upload. |
| File picker | PNG/JPEG/DOCX/XLSX | `accept=` attribute | NOT WIRED | AssetComplianceList.tsx line 213: `accept=".txt,.md,.json,.csv,.log,.pdf"` — four of the five required file types missing from browser filter |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| EVID-01 | 02-01, 02-02 | Upload PDF/PNG/JPEG/DOCX/XLSX ≤25 MB | PARTIAL | Backend validates all 5 types and size. Frontend file picker excludes PNG/JPEG/DOCX/XLSX. Evidence not shown post-upload without reload. |
| EVID-02 | 02-01 | Evidence stored per-tenant with full metadata | VERIFIED | All 5 metadata fields present in evidence record and asserted by test |
| EVID-03 | 02-02 | Uploaded evidence appears alongside automated evidence, labelled | PARTIAL | Badges render correctly; data not refreshed after upload so "appears" is deferred until reload |
| EVID-04 | 02-01, 02-02 | Owner delete own; admin delete any tenant | VERIFIED | RBAC enforced in backend; delete button gated on !isAutomated in frontend; post-delete refresh works |
| EVID-05 | 02-01 | MIME/extension mismatch rejected | VERIFIED | `_check_magic` validates first bytes; 400 on mismatch confirmed by test |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `components/AssetComplianceList.tsx` | 213 | `accept=".txt,.md,.json,.csv,.log,.pdf"` — four required types missing | BLOCKER | Users cannot easily select PNG/JPEG/DOCX/XLSX files via OS file dialog; they must choose "All Files" as a workaround |
| `components/FrameworkDetail.tsx` | 580-591 | Upload success handler has no `onRefresh()` call | BLOCKER | Newly uploaded evidence is invisible in the control detail view until page is manually reloaded |

No `TBD`, `FIXME`, `XXX`, or `HACK` markers in any phase-modified file.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 9 evidence upload tests pass | `PYTHONPATH=backend/venv/lib/python3.12/site-packages python3.12 -m pytest backend/tests/test_evidence_uploads.py -q` | `9 passed in 0.91s` | PASS |
| `_check_magic` is callable and imported | `grep "from compliance_artifacts_endpoints import.*_check_magic" backend/compliance_evidence_endpoints.py` | Line 11 matches | PASS |
| DELETE endpoint registered | `compliance_endpoints.py` includes `evidence_router`; `router_registry.py` loads `compliance_endpoints` at line 108 | Routing chain verified | PASS |
| File picker accepts required types | `grep 'accept=' components/AssetComplianceList.tsx` | `accept=".txt,.md,.json,.csv,.log,.pdf"` — PNG/JPEG/DOCX/XLSX absent | FAIL |
| Evidence list refreshes after upload | Inspect `onUploadEvidence` handler in FrameworkDetail.tsx lines 580-591 | No `onRefresh()` call after `res.success` | FAIL |

---

## Human Verification Required

### 1. File picker allows PNG, JPEG, DOCX, XLSX

**Test:** Navigate to a compliance framework control and click the upload icon. Observe the OS file picker dialog without enabling "All Files".
**Expected:** PNG, JPEG, DOCX, and XLSX appear in the allowed types list alongside PDF.
**Why human:** Browser OS-dialog filtering behaviour cannot be asserted by grep.

### 2. Uploaded evidence appears immediately after upload (no reload required)

**Test:** Upload a valid PDF to a control and, without clicking reload, observe the Evidence column for that control.
**Expected:** The newly uploaded file appears immediately in the evidence list with a green "Manual" badge.
**Why human:** React state update and re-render after async callback cannot be confirmed without running the UI.

---

## Gaps Summary

Two related gaps block the phase goal. Both are in the frontend:

**Gap 1 — File picker `accept` attribute (EVID-01, EVID-03)**
`components/AssetComplianceList.tsx` line 213 has `accept=".txt,.md,.json,.csv,.log,.pdf"`. The four remaining required types (`.png`, `.jpg`/`.jpeg`, `.docx`, `.xlsx`) are absent. The backend correctly validates and accepts them, but the user cannot select them from the default OS file dialog without switching to "All Files". This is a friction blocker on EVID-01 and weakens EVID-03.

**Gap 2 — No evidence list refresh after upload (EVID-01, EVID-03)**
The `onUploadEvidence` handler in `FrameworkDetail.tsx` (lines 580-591) calls `api.uploadComplianceEvidence`, shows a success toast, but never calls `onRefresh()`. As a result, `assetComplianceData` (managed in `App.tsx`, passed down as a prop) is not re-fetched, and the newly uploaded file does not appear in the control detail view until the user manually reloads the page. The delete flow correctly calls `onRefresh()` (line 613) — the same pattern is simply missing from the upload flow.

Both gaps require one-line or small fixes. They are not architectural problems; the backend, routing, RBAC, and badge rendering are all correct.

---

_Verified: 2026-06-17_
_Verifier: Claude (gsd-verifier)_
