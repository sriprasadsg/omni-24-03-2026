---
phase: 02-manual-evidence-uploads
reviewed: 2026-07-03T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/compliance_artifacts_endpoints.py
  - backend/compliance_evidence_endpoints.py
  - backend/tests/test_evidence_uploads.py
  - components/AssetComplianceList.tsx
  - components/FrameworkDetail.tsx
  - services/apiService.ts
findings:
  critical: 6
  warning: 7
  info: 2
  total: 15
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-07-03T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

This is a re-review of the manual-evidence-upload surface against its current
state. An earlier review round (`02-REVIEW.md` history) fixed several serious
issues in `compliance_evidence_endpoints.py` and `apiService.ts` — the tenant
isolation bypass on DELETE, header-injection via evidence filename, the
`controlId`/`control_id` mismatch, the missing `tenantId` on artifact records,
and the artifact record's ID collision are all correctly fixed in the code
read for this review. Good — that hardening held.

However, `compliance_artifacts_endpoints.py` still lags well behind
`compliance_evidence_endpoints.py`'s security bar, and a new critical issue
emerges from how the two interact with the rest of the app. It defines the
same magic-byte helper (`_check_magic`) the evidence module uses but never
calls it in its own upload endpoint; its extension allowlist still includes
`.html`/`.xml`; and its MIME-check has an "only validate if a Content-Type
was actually sent" bug that fails *open* instead of closed. Because
`backend/app.py` mounts `static/evidence` directly as a static file server,
the `.html` allowance is not theoretical — it is a working stored-XSS path for
any authenticated user, of any role, since none of the upload endpoints
enforce a permission check beyond "is logged in." The artifact upload's
generated *filename* (as opposed to its `id`, which was already fixed to use
a UUID) is still built from a second-granularity timestamp with no random
component, so two same-second, same-category uploads still silently
overwrite each other's file on disk — the ID collision was fixed, but an
adjacent, functionally identical collision in the filename was not.

On the frontend, the file-picker `accept` mismatch flagged in the prior
review was only half-fixed: the missing image/office formats were added
back, but the extra text formats (`.txt`/`.md`/`.json`/`.csv`) that the
backend's narrow evidence allowlist has never accepted are still offered,
so picking one of those still always fails the primary upload. The
"Pending_Review" status string set by both upload endpoints still isn't
recognized by the frontend's status-badge styling (which only special-cases
`Compliant` and `Pending_Evidence`), so freshly uploaded evidence awaiting
review renders with the "Non-Compliant" red badge.

## Critical Issues

### CR-01: Unrestricted `.html`/`.xml` upload + same-origin static serving enables stored XSS

**File:** `backend/compliance_artifacts_endpoints.py:19-24` (allowlist), `:92-180` (endpoint); exploitability confirmed via `backend/app.py:82`

**Issue:** `_ALLOWED_UPLOAD_EXTENSIONS` includes `.md`, `.json`, `.xml`, and `.html`. Uploaded files are written under `UPLOAD_DIR = "static/evidence"` and returned with `url: f"/static/evidence/{safe_filename}"`. `backend/app.py:82` mounts that same directory directly: `app.mount("/static", StaticFiles(directory=static_dir), name="static")`. Any authenticated user (no permission check — see CR-06) can upload an `.html` file containing `<script>...</script>` as a "manual artifact" and have it served same-origin at `/static/evidence/artifact_other_<timestamp>.html`, executing in the browser of anyone who opens that link (a reviewer, auditor, or Super Admin — possibly from another tenant). `sessionStorage` holds the JWT `token`/`refresh_token` (`services/apiService.ts:108-109`), so this is a session-hijack vector, not just defacement.

**Fix:** Drop `.html`/`.xml` (and reconsider `.md`/`.json`, which some browsers still sniff) from `_ALLOWED_UPLOAD_EXTENSIONS`, and/or stop serving `static/evidence` through the raw static mount — route all evidence downloads exclusively through the existing `download_compliance_evidence` handler, which can force `Content-Disposition: attachment` and a locked content type:
```python
_ALLOWED_UPLOAD_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".zip", ".tar", ".gz",
    # ".md", ".json", ".xml", ".html" removed — servable, script-capable formats
})
```

---

### CR-02: MIME-type check silently no-ops when `Content-Type` is blank

**File:** `backend/compliance_artifacts_endpoints.py:124-126`

**Issue:**
```python
content_type = (file.content_type or "").split(";")[0].strip()
if content_type and not any(content_type.startswith(p) for p in _ALLOWED_UPLOAD_MIME_PREFIXES):
    raise HTTPException(status_code=400, detail=f"MIME type '{content_type}' is not allowed.")
```
When `content_type` is empty (client omits `Content-Type`, or a scripted API call sends an empty value), `if content_type and ...` short-circuits to `False` and the check is skipped entirely — the file is accepted with no MIME validation at all. Contrast with the correct pattern already used two files over, in `compliance_evidence_endpoints.py:68` and `:348`:
```python
if not content_type or not any(content_type.startswith(p) for p in _EVIDENCE_ALLOWED_MIME_PREFIXES):
```
which fails closed instead of open.

**Fix:**
```python
content_type = (file.content_type or "").split(";")[0].strip()
if not content_type or not any(content_type.startswith(p) for p in _ALLOWED_UPLOAD_MIME_PREFIXES):
    raise HTTPException(status_code=400, detail=f"MIME type '{content_type}' is not allowed.")
```

---

### CR-03: Magic-byte validation (`_check_magic`) is defined but never called in the artifact upload endpoint

**File:** `backend/compliance_artifacts_endpoints.py:68-76` (definition), `:92-180` (endpoint — no call site)

**Issue:** `_check_magic()` exists specifically to catch content/extension mismatches (e.g. an HTML/script payload saved with a `.pdf` name and a forged `Content-Type: application/pdf`). `compliance_evidence_endpoints.py` correctly calls it (`compliance_evidence_endpoints.py:79`, `:354`) after reading the file. `upload_manual_artifact`, in the module that *defines* `_check_magic`, reads `file_content`, checks extension and MIME, and writes straight to disk — the helper is dead code in its own home module and is only ever invoked by the sibling module that imports it. Combined with CR-01/CR-02, this removes the last layer of defense against spoofed uploads on the broader artifact-upload path.

**Fix:** Call it right after reading the content, mirroring `compliance_evidence_endpoints.py`:
```python
file_content = await file.read()
if len(file_content) > 50 * 1024 * 1024:
    raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

original_name = os.path.basename(file.filename or "artifact")
file_ext = os.path.splitext(original_name)[1].lower()
...
if not _check_magic(file_content, file_ext):
    raise HTTPException(status_code=400, detail="File content does not match extension")
```

---

### CR-04: Non-unique, low-resolution filename generation corrupts evidence integrity on the artifact upload path

**File:** `backend/compliance_artifacts_endpoints.py:136-138`

**Issue:**
```python
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
...
safe_filename = f"artifact_{category}_{timestamp}{file_ext}"
```
This has only second-level resolution and no random/unique component. Two uploads of the same category within the same wall-clock second (concurrent requests, a double-clicked submit, or scripted bulk imports) collide on `safe_filename`, and the second `_write_binary` call silently overwrites the first upload's bytes on disk. Because `sha256 = _sha256_file(file_path)` re-reads the file *after* writing it, the first record's stored `sha256` will end up describing the *second* file's content the moment a collision occurs — silently breaking the chain-of-custody/integrity guarantee this endpoint exists to provide. A prior review round already fixed the *record's* `id` field to use `uuid.uuid4().hex` (avoiding a Mongo duplicate-key error) — but that fix was never applied to `safe_filename`, so the on-disk collision this review found is a distinct, still-open instance of the same root cause. Every other upload path in this codebase (`compliance_evidence_endpoints.py:82`, `:357`) uses `uuid.uuid4().hex` in the filename for exactly this reason.

**Fix:**
```python
import uuid  # promote the existing local `import uuid as _uuid` to module scope (see IN-01)
...
safe_filename = f"artifact_{category}_{uuid.uuid4().hex}{file_ext}"
```

---

### CR-05: Non-unique MongoDB filter can silently attach evidence to (and flip the status of) an unrelated asset

**File:** `backend/compliance_artifacts_endpoints.py:169-178`

**Issue:**
```python
for control_id in control_list:
    scope = {"assetId": asset_id, "controlId": control_id} if asset_id else {"controlId": control_id}
    await db.asset_compliance.update_one(
        scope,
        {
            "$set": {"status": "Pending_Review", "lastUpdated": record["uploaded_at"]},
            "$push": {"evidence": record},
        },
        upsert=True,
    )
```
When `asset_id` is not supplied (the "org-wide control, no specific asset" case that field's docstring describes), `scope` is `{"controlId": control_id}` — with no `assetId` constraint. `asset_compliance` normally holds one document per `(assetId, controlId)` pair, so for any control tracked across multiple assets there will be several documents matching that filter. `update_one` only updates the **first** document Mongo happens to match (order is not guaranteed) — this silently pushes the artifact's evidence into, and flips the `status` of, one arbitrary asset's compliance record instead of the intended "no particular asset" target, corrupting that asset's compliance state as a side effect of an unrelated upload. If no document matches, `upsert=True` instead creates an orphaned record with no `assetId`, which `get_asset_compliance` (filtered by `assetId`) will never surface, but `get_control_evidence`'s asset-agnostic query (`compliance_evidence_endpoints.py:429`, `asset_query: dict = {"controlId": control_id}`) will pick up and mislabel as `system`-sourced evidence (it has neither `systemGenerated` nor `source: "auto"`, so it's silently misclassified rather than merely hidden).

**Fix:** Route control-level (no-asset) manual artifacts to the dedicated `control_evidence` collection that already exists for exactly this case (see `upload_control_direct_evidence` in `compliance_evidence_endpoints.py:326-407`), instead of upserting into `asset_compliance` with an ambiguous filter:
```python
if asset_id:
    await db.asset_compliance.update_one(
        {"assetId": asset_id, "controlId": control_id},
        {"$set": {"status": "Pending_Review", "lastUpdated": record["uploaded_at"]},
         "$push": {"evidence": record}},
        upsert=True,
    )
else:
    await db.control_evidence.insert_one({**record, "controlId": control_id})
```

---

### CR-06: No server-side authorization check on evidence/artifact upload endpoints

**File:** `backend/compliance_artifacts_endpoints.py:92-103` (`upload_manual_artifact`); `backend/compliance_evidence_endpoints.py:38-47` (`upload_compliance_evidence`), `:326-333` (`upload_control_direct_evidence`)

**Issue:** All three upload endpoints depend only on `Depends(get_current_user)`, which (per `authentication_service.py:169`) verifies the JWT but performs no role/permission check. Tenant isolation is enforced correctly where it applies, but *any* authenticated user of *any* role — including a read-only `Viewer` — can call these endpoints directly (they're plain REST routes, unrelated to what the client UI chooses to render). The frontend's own gating is inconsistent, which is evidence server-side enforcement is actually needed: `FrameworkDetail.tsx:167-176` hides "Bulk Upload Evidence" behind `canManageEvidence = hasPermission('manage:compliance_evidence')`, but the per-control "Upload" button (`FrameworkDetail.tsx:357-367`) that opens `ControlEvidenceUploadModal` is not gated by that permission at all — and neither button's protection would matter to an attacker calling the API directly regardless.

**Fix:** Add an explicit permission dependency to each upload/create route, mirroring whatever mechanism gates other write endpoints elsewhere in the backend (e.g. a `require_permission("manage:compliance_evidence")` dependency), rather than relying on the frontend to hide the control.

## Warnings

### WR-01: Backend validation `detail` messages are discarded by the frontend evidence API wrappers

**File:** `services/apiService.ts:639-660, 677-701`

**Issue:** `uploadComplianceEvidence`, `deleteComplianceEvidence`, `uploadControlEvidence`, `getControlEvidence`, and `deleteControlEvidence` all throw a fixed generic string on `!res.ok` (e.g. `throw new Error("Evidence upload failed")`), discarding the response body. The backend returns several distinct, specific reasons for a 4xx (wrong extension, wrong MIME, size cap exceeded, tenant mismatch, content/extension mismatch) — all of that detail is thrown away, so `FrameworkDetail.tsx:401-404`'s catch block can only ever show "Failed to upload evidence." regardless of cause. `uploadBulkEvidence` a few lines below (`apiService.ts:715-731`) handles this correctly (`err.detail = body.detail`), showing this is an inconsistency rather than a deliberate simplification.

**Fix:**
```typescript
export const uploadComplianceEvidence = async (assetId: string, controlId: string, file: File, description?: string) => {
    ...
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Evidence upload failed");
    }
    return await res.json();
};
```
Apply the same pattern to the other four functions listed above.

---

### WR-02: Super-admin role sets have drifted between the two compliance-upload modules

**File:** `backend/compliance_artifacts_endpoints.py:197`, `backend/compliance_evidence_endpoints.py:20-22`

**Issue:** `compliance_evidence_endpoints.py` now correctly uses a single shared `_SUPER_ROLES = frozenset({"Super Admin", "super_admin", "superadmin", "admin", "platform-admin"})` everywhere inside that file. `compliance_artifacts_endpoints.py`'s `list_manual_artifacts`, however, independently inlines `is_super_admin = user_role in ("Super Admin", "superadmin", "super_admin")` — missing `"admin"` and `"platform-admin"`. A user with role `"admin"` therefore gets unrestricted, cross-tenant visibility in `get_all_compliance_evidence`/`download_compliance_evidence` but is tenant-scoped in `list_manual_artifacts`. The earlier fix for this class of drift was applied only within `compliance_evidence_endpoints.py`, not shared with the sibling module.

**Fix:** Export `_SUPER_ROLES` from one shared location (or from `compliance_artifacts_endpoints.py` and import it into `compliance_evidence_endpoints.py`, the way `_check_magic`/`UPLOAD_DIR` already are) and use that single definition everywhere.

---

### WR-03: Inconsistent error handling/logging — some endpoints wrap and log, siblings don't

**File:** `backend/compliance_artifacts_endpoints.py:92-180` (`upload_manual_artifact`); `backend/compliance_evidence_endpoints.py:463-498` (`delete_control_direct_evidence`)

**Issue:** `upload_compliance_evidence`, `delete_compliance_evidence`, and `upload_control_direct_evidence` all wrap their bodies in `try/except HTTPException: raise / except Exception as e: logger.error(...); raise HTTPException(500, ...)`. `upload_manual_artifact` and `delete_control_direct_evidence` have no such wrapper — an unexpected exception (DB error, disk full, etc.) will still produce a 500 via FastAPI's default handler, but it won't go through this module's structured `logger`, making production diagnosis harder and leaving the file internally inconsistent.

**Fix:** Wrap both functions the same way as their siblings, logging via `logger.error(...)` before re-raising as a generic 500.

---

### WR-04: Frontend evidence file picker still advertises formats the backend always rejects

**File:** `components/AssetComplianceList.tsx:287` vs `backend/compliance_evidence_endpoints.py:25-27`

**Issue:** The hidden `<input type="file">` for "Upload Evidence & Ingest" sets `accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.txt,.md,.json,.csv"`, but `upload_compliance_evidence`'s `_EVIDENCE_ALLOWED_EXTENSIONS` only permits `{".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx"}`. A previous review round flagged this mismatch and the fix added the missing image/office formats back — but the extra text formats were left in place. Selecting `.txt`, `.md`, `.json`, or `.csv` (all explicitly offered) still always fails the primary upload with a 400, while the parallel ingestion path (`handleFileChange:76-83`, which runs for exactly those "ingestible text" MIME types) can still succeed — leaving the file ingested into the RAG knowledge base with no corresponding evidence record ever attached to the control, and a "Failed to upload evidence" toast the user has no obvious way to resolve.

**Fix:** Narrow the `accept` attribute to match the backend allowlist (or widen the backend allowlist, only if `.txt`/`.md`/`.json`/`.csv` are genuinely meant to be accepted as evidence and not just ingestion input):
```tsx
accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx"
```

---

### WR-05: Dead/misleading MIME-prefix entries with no corresponding allowed extension

**File:** `backend/compliance_evidence_endpoints.py:25-35`

**Issue:** `_EVIDENCE_ALLOWED_MIME_PREFIXES` includes `"application/msword"` and `"application/vnd.ms-excel"` (legacy `.doc`/`.xls` MIME types), but `_EVIDENCE_ALLOWED_EXTENSIONS` only allows `.docx`/`.xlsx` — the legacy extensions are rejected before the MIME check is ever reached. These entries are unreachable and misleading to future maintainers who might reasonably assume `.doc`/`.xls` are supported.

**Fix:** Remove the unreachable MIME prefixes, or add `.doc`/`.xls` to the extension allowlist if legacy Office formats should genuinely be supported (in which case add magic signatures for them too — `_MAGIC_SIGNATURES` in `compliance_artifacts_endpoints.py` currently has none for `.doc`/`.xls`).

---

### WR-06: `onUploadEvidence` is invoked without `await`, relying entirely on its caller's try/catch

**File:** `components/AssetComplianceList.tsx:71`

**Issue:**
```tsx
onUploadEvidence(selectedAssetId, file, description);
```
This async call is fired without `await` or a `.catch`. It currently avoids becoming an unhandled promise rejection only because the sole current caller (`FrameworkDetail.tsx:394-405`) happens to wrap its own body in `try/catch`. That is an implicit contract on the `onUploadEvidence` prop that this component has no way to verify or enforce.

**Fix:** Either `await` it before proceeding to the ingestion step, or explicitly mark the fire-and-forget intent with a trailing `.catch(() => {})` and a comment, so a future caller that omits its own error handling can't produce an unhandled rejection.

---

### WR-07: `Pending_Review` status still isn't recognized by the frontend status badge (renders as "Non-Compliant" red)

**File:** `components/AssetComplianceList.tsx:137-141` vs `backend/compliance_evidence_endpoints.py:109` and `backend/compliance_artifacts_endpoints.py:174`

**Issue:** Both upload endpoints set `"status": "Pending_Review"` after a successful upload. The status badge styling is:
```tsx
${status === 'Compliant' ? 'bg-green-100 ...' :
    status === 'Pending_Evidence' ? 'bg-yellow-100 ...' :
        'bg-red-100 ...'}
```
`"Pending_Review"` matches neither `'Compliant'` nor `'Pending_Evidence'`, so it falls through to the red "Non-Compliant" styling. A user who just uploaded evidence for review sees the control flip to red immediately, which reads as a regression/failure rather than "awaiting review." This was flagged in a prior review pass and does not appear to have been addressed for this status value.

**Fix:**
```tsx
${status === 'Compliant' ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300' :
    (status === 'Pending_Evidence' || status === 'Pending_Review') ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300' :
        'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300'}
```

## Info

### IN-01: Local `import uuid as _uuid` inside a function body

**File:** `backend/compliance_artifacts_endpoints.py:146`

**Issue:** `upload_manual_artifact` does `import uuid as _uuid` mid-function instead of importing `uuid` at module scope (as `compliance_evidence_endpoints.py:6` does). The module has no top-level `uuid` import at all, so this local import is the only source of unique IDs in the file — worth promoting to a normal top-level import for consistency and so the dependency is obvious at a glance, especially once CR-04's fix also needs `uuid` for the filename.

**Fix:**
```python
import uuid  # top of file, alongside os, hashlib, etc.
...
record = {
    "id": f"artifact-{uuid.uuid4().hex}",
    ...
```

### IN-02: "Upload" button for control-level evidence isn't gated by the same permission as "Bulk Upload Evidence"

**File:** `components/FrameworkDetail.tsx:167-176` vs `:357-367`

**Issue:** `canManageEvidence` gates the "Bulk Upload Evidence" button but not the per-control "Upload" button that opens `ControlEvidenceUploadModal`. Whether or not this is intentional (e.g. any tenant member may attach single pieces of evidence, but only privileged users may bulk-import), the asymmetry is worth a second look given CR-06 — since there's no backend enforcement either, this button is currently the only place the intended access boundary is expressed at all, and it doesn't match the sibling control right next to it.

**Fix:** Decide the intended policy and either gate both buttons on `canManageEvidence` or document why single-item upload is intentionally open to all roles.

---

_Reviewed: 2026-07-03T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
