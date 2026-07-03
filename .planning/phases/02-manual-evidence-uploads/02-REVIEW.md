---
phase: 02-manual-evidence-uploads
reviewed: 2026-07-03T09:54:49Z
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
  critical: 4
  warning: 4
  info: 3
  total: 11
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-07-03T09:54:49Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

This is a from-scratch re-review of the manual-evidence-upload feature after a prior fix pass claimed to resolve 15 findings (6 critical, incl. stored-XSS via unsafe upload allowlist). Several of the previously-described fix patterns (narrowed extension allowlists, magic-byte validation, path-traversal guards on download/delete, ownership/tenant checks) are present and correctly implemented in `compliance_evidence_endpoints.py`. However, this pass surfaces **new, unfixed, exploitable issues**, the most serious being:

1. `compliance_artifacts_endpoints.py`'s manual-artifact upload endpoint uses an inverted conditional that lets a caller **bypass the extension allowlist entirely** by omitting the file extension — reopening exactly the class of vulnerability ("stored-XSS via unsafe upload allowlist") the prior pass claims to have fixed. The sibling evidence-upload endpoints got this right; this one did not.
2. All evidence/artifact files are stored under `backend/static/evidence/`, which is mounted **publicly and without authentication** at `/static` in `app.py`. This completely bypasses the RBAC- and tenant-scoped `/api/compliance/evidence/download/{evidence_id}` endpoint and every ownership check built into the delete endpoints — anyone who obtains a stored filename (via referrer leakage, logs, or the tenant-isolation bug below) can fetch the raw file with zero authorization.
3. `get_control_evidence` silently drops its tenant filter (returning evidence across **all tenants**) whenever a non-super-admin caller has a falsy `tenant_id`, instead of failing closed like every other endpoint in the same file.
4. `upload_manual_artifact`'s asset-tenant-ownership check is skipped outright when the caller's `tenant_id` is falsy, instead of failing closed.

These are provable, not hypothetical: I traced each through the actual conditional logic and cross-referenced `app.py`'s static mount and the RBAC helper (`rbac_utils.py`) to confirm tenant/role plumbing.

## Critical Issues

### CR-01: Extension allowlist bypass via omitted file extension in manual artifact upload

**File:** `backend/compliance_artifacts_endpoints.py:127-140`
**Issue:** The extension check uses an inverted-guard conditional that only rejects a file when an extension is *present and disallowed*:

```python
file_ext = os.path.splitext(original_name)[1].lower()

# Whitelist extension and MIME type — reject executables and scripts
if file_ext and file_ext not in _ALLOWED_UPLOAD_EXTENSIONS:
    raise HTTPException(status_code=400, detail=f"File type '{file_ext}' is not allowed.")
```

If the client omits a filename (or uses a filename with no dot, e.g. `"artifact"`), `file_ext` is `""`, which is falsy, so `file_ext and ...` short-circuits to `False` and **no exception is raised** — the request sails through the allowlist check entirely. The same request then only needs a `Content-Type` that starts with an allowed prefix (`"text/"`, `"image/"`, `"application/pdf"`, etc. — note `"text/"` matches *any* `text/*` subtype, including `text/html`). `_check_magic(content, "")` looks up `_MAGIC_SIGNATURES.get("")`, finds nothing, and returns `True` (documented pass-through for "extensions with no defined signature") — so the magic-byte check is defeated too. The result: a file with attacker-controlled bytes and an attacker-controlled `Content-Type` can be stored with **no extension and no content validation whatsoever**, as long as the filename has no dot.

Contrast with the two upload handlers in `compliance_evidence_endpoints.py` (`upload_compliance_evidence` line 61, `upload_control_direct_evidence` line 342), which correctly use:
```python
if not file_ext or file_ext not in _EVIDENCE_ALLOWED_EXTENSIONS:
```
This fails closed on empty extension. `compliance_artifacts_endpoints.py` was not brought in line with that pattern.

**Fix:**
```python
if not file_ext or file_ext not in _ALLOWED_UPLOAD_EXTENSIONS:
    raise HTTPException(status_code=400, detail=f"File type '{file_ext or '(none)'}' is not allowed.")
```

### CR-02: Uploaded evidence/artifact files are served publicly with no authentication, bypassing all RBAC/tenant checks

**File:** `backend/compliance_artifacts_endpoints.py:18-19` (and `backend/compliance_evidence_endpoints.py:12` which imports the same `UPLOAD_DIR`); root cause visible at `backend/app.py:81-82`
**Issue:** `UPLOAD_DIR = "static/evidence"` and files are written under `backend/static/evidence/...`. `app.py` mounts that same `static/` tree publicly and unauthenticated:
```python
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
```
Every evidence/artifact record's `url` field (`/static/evidence/<uuid>.<ext>`) is therefore directly fetchable by anyone — no JWT, no tenant check, no ownership check — completely bypassing:
- The tenant/role checks in `download_compliance_evidence` (`compliance_evidence_endpoints.py:160-219`),
- The "only owner or admin can delete" logic (irrelevant to *reads*, but shows the intended access model),
- The tenant-scoping in `list_manual_artifacts` / `get_control_evidence`.

Filenames are UUID4 hex (hard to brute-force), but they are not designed to be secrets — they are returned verbatim in API responses to any user who can see the record, they'll appear in browser history/devtools/network logs, and (per CR-03 below) can even leak cross-tenant through `get_control_evidence`. Once a filename is known by any means, the file is fully exposed regardless of tenant, role, or whether the uploading control/asset is even accessible to the requester anymore.
**Fix:** Do not serve the evidence directory through the public static mount. Either:
1. Store uploads outside of `backend/static/` (e.g. `backend/private_uploads/evidence/`) so nothing under `/static` maps to them, and route all reads exclusively through the authenticated download endpoints, or
2. If they must live under `static/`, exclude that subpath from the `StaticFiles` mount (e.g., mount only `static/public` at `/static`) and require every read to go through `download_compliance_evidence`.

### CR-03: `get_control_evidence` returns cross-tenant evidence when a non-super caller has no `tenant_id`

**File:** `backend/compliance_evidence_endpoints.py:408-458`
**Issue:**
```python
manual_query: dict = {"controlId": control_id}
if not is_super and tenant_id:
    manual_query["tenantId"] = tenant_id
...
asset_query: dict = {"controlId": control_id}
if not is_super and tenant_id:
    asset_query["tenantId"] = tenant_id
```
If `tenant_id` is `None`/empty for a non-super-admin caller (malformed token, mis-provisioned account, service-to-service caller, etc.), the `and tenant_id` guard is falsy, so **the tenant filter is never applied** — both `manual_query` and `asset_query` collapse to `{"controlId": control_id}`, returning every tenant's manual and system evidence for that control. This is the *only* place in the file that behaves this way; every other endpoint in the same module fails closed on a missing tenant (e.g. `download_compliance_evidence:171-174` raises 403 "Tenant context required"; `get_asset_compliance:233` uses `tenant_id or ""` which can never match a real tenant; `delete_control_direct_evidence:479` compares `record.get("tenantId") != caller_tenant` which is `!= None` and fails safe).
**Fix:** Fail closed like the sibling endpoints:
```python
if not is_super:
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    manual_query["tenantId"] = tenant_id
    asset_query["tenantId"] = tenant_id
```

### CR-04: Asset-tenant ownership check silently skipped when caller has no `tenant_id`

**File:** `backend/compliance_artifacts_endpoints.py:143-149`
**Issue:**
```python
if asset_id:
    _caller_tenant = getattr(current_user, "tenant_id", None)
    if _caller_tenant:
        _db = get_database()
        _asset = await _db.assets.find_one({"id": asset_id, "tenantId": _caller_tenant})
        if not _asset:
            raise HTTPException(status_code=403, detail="Asset not found in your tenant")
```
When `current_user.tenant_id` is falsy for a non-super-admin caller, the entire ownership check (`if _caller_tenant:`) is skipped, and the artifact is happily associated with an arbitrary `asset_id` belonging to any tenant — no 403 is raised. This mirrors the same fail-open pattern as CR-03, just in the sibling module.
**Fix:** Fail closed instead of skipping the check:
```python
if asset_id:
    _caller_tenant = getattr(current_user, "tenant_id", None)
    _user_role = getattr(current_user, "role", "")
    if _user_role not in _SUPER_ROLES:
        if not _caller_tenant:
            raise HTTPException(status_code=403, detail="Tenant context required")
        _db = get_database()
        _asset = await _db.assets.find_one({"id": asset_id, "tenantId": _caller_tenant})
        if not _asset:
            raise HTTPException(status_code=403, detail="Asset not found in your tenant")
```

## Warnings

### WR-01: Evidence-upload endpoints lack the dedicated rate limit applied to the sibling artifact-upload endpoint

**File:** `backend/compliance_evidence_endpoints.py:36-131` (`upload_compliance_evidence`), `:324-405` (`upload_control_direct_evidence`)
**Issue:** `upload_manual_artifact` in `compliance_artifacts_endpoints.py:100-101` is explicitly throttled with `@limiter.limit("10/hour")`. Neither `upload_compliance_evidence` nor `upload_control_direct_evidence` carry any endpoint-specific limit, so they fall back to the much more permissive app-wide default (`200/minute`, `2000/hour`, from `rate_limiter.py:13`, wired in via `SlowAPIMiddleware` in `app_middleware.py`). Both endpoints accept up to 25 MB per request and write to disk; at the default global limit a single caller can write roughly 5 GB/minute, dramatically more than the artifact-upload path allows for functionally identical file-write operations. `upload_compliance_evidence` even declares unused `request: Request, response: Response` parameters, suggesting a limiter decorator was intended but never added.
**Fix:** Add a comparable per-endpoint limit, e.g. `@limiter.limit("30/hour")`, to both handlers, consistent with the artifact-upload endpoint's posture.

### WR-02: Distinguishable 403 vs 404 responses allow cross-tenant existence probing in `delete_compliance_evidence`

**File:** `backend/compliance_evidence_endpoints.py:249-321`
**Issue:** The aggregation lookup (`:264-269`) matches purely on `{"assetId": asset_id, "evidence.id": evidence_id}` with no tenant filter. Only *after* a match is found does the code check `doc_tenant != caller_tenant` and return 403 (`:284-285`); if no match is found at all, it returns 404 (`:270-271`). A caller can therefore distinguish "this asset/evidence pair doesn't exist" (404) from "it exists but belongs to another tenant" (403) — a tenant/asset/evidence-existence oracle. Severity is limited because evidence IDs are UUID4 hex and hard to guess, but it is nonetheless a real information leak that a defense-in-depth posture should close.
**Fix:** Scope the initial aggregation match by tenant for non-super callers (when `caller_tenant` is known) so a mismatch collapses into the same 404 as "not found," e.g. add `"tenantId": caller_tenant` to the `$match` stage before the aggregation for non-super callers, then return a single 404 for both "doesn't exist" and "exists in another tenant."

### WR-03: `_MAGIC_SIGNATURES` pass-through combines with the extension-bypass in CR-01 to fully defeat content validation

**File:** `backend/compliance_artifacts_endpoints.py:66-84`
**Issue:** This is a secondary contributor to CR-01: `_check_magic` intentionally passes through (`return True`) for any extension without a registered signature (`.csv`, `.txt`, `.zip`, `.tar`, `.gz`, `.webp`, `.gif`, `.doc`, `.xls`, and — critically — the empty string `""`). This is a reasonable trade-off for those legitimate extensions individually, but because `_check_magic("", content)` also passes through, it removes the last line of defense once CR-01's extension check is bypassed. Once CR-01 is fixed (extension can no longer be empty), this is no longer independently exploitable, but it's worth tightening for genuinely-unsigned extensions like `.txt`/`.csv` too, since arbitrary bytes (including HTML/script payloads) can currently be stored under those extensions without any content check.
**Fix:** After CR-01 is fixed this is low-risk, but consider adding a lightweight sanity check for text-based unsigned extensions (e.g., reject NUL bytes or `<script`/`<html` prefixes) as defense-in-depth, and explicitly reject `_check_magic` calls with an empty `ext` rather than silently passing them through.

### WR-04: Stale "RED phase" framing left in test module docstring understates actual coverage gaps

**File:** `backend/tests/test_evidence_uploads.py:1-7`
**Issue:** The module docstring still reads "RED phase: tests are written against the INTENDED post-fix behavior. They will FAIL until ... updated in Tasks 1 and 2," implying these are pre-fix, expected-to-fail tests from an earlier TDD cycle. Left in place post-fix, this is misleading to future readers about the current state of the suite and, notably, none of these tests exercise `upload_manual_artifact` in `compliance_artifacts_endpoints.py` at all (only its shared `_check_magic` helper is unit-tested) — so CR-01 and CR-04, both in that same file, have zero test coverage.
**Fix:** Update the docstring to reflect current (green) state, and add tests for `upload_manual_artifact` covering: extension omitted entirely, extension omitted with a spoofed allowed `Content-Type`, and the asset/tenant-ownership check with a caller lacking `tenant_id`.

## Info

### IN-01: Leftover debug `console.log` calls in evidence-ingestion path

**File:** `components/FrameworkDetail.tsx:409, 416`
**Issue:** `console.log(\`Ingesting evidence for asset ${assetId}: ${fileName}\`);` and `console.log('Ingested into RAG');` are debug artifacts left in the shipped `onIngestEvidence` handler.
**Fix:** Remove, or route through a proper logging utility gated behind a debug flag.

### IN-02: Commented-out `alert(...)` call left in place

**File:** `components/FrameworkDetail.tsx:415`
**Issue:** `// alert(\`Successfully ingested ${fileName} into RAG Knowledge Base!\`); // Reduced noise` is dead, commented-out code.
**Fix:** Delete the line; the intent ("reduced noise") is already served by the toast/console-log calls around it.

### IN-03: `RenderedEvidence.model_used` access has no runtime guard despite being read via `.split('/')`

**File:** `components/AssetComplianceList.tsx:248`
**Issue:** `statusRecord.ai_evaluation.model_used.split('/').pop()` will throw if `model_used` is ever `undefined`/`null` at runtime (the TS type in `types.ts:476` marks it required, but this is backend-supplied JSON with no runtime validation at the boundary, per CLAUDE.md's "Validate input at system boundaries" guidance). A malformed `ai_evaluation` payload would crash this row's render.
**Fix:** `{(statusRecord.ai_evaluation.model_used || '').split('/').pop() || 'unknown'}` or a small helper that tolerates a missing value.

---

_Reviewed: 2026-07-03T09:54:49Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
