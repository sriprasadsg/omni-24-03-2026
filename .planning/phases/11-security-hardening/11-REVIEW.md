---
phase: 11-security-hardening
reviewed: 2026-07-02T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - backend/compliance_bulk_evidence_endpoints.py
  - backend/tests/test_bulk_evidence_upload.py
findings:
  critical: 2
  warning: 7
  info: 2
  total: 11
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-07-02T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Reviewed the bulk evidence upload endpoint (`backend/compliance_bulk_evidence_endpoints.py`) and its
test suite for the phase 11 security-hardening closeout of SEC-01 (zip-bomb real-bytes accumulator)
and SEC-02 (DB rollback on partial commit failure). This is the first review pass for this file.

The SEC-01 accumulator itself is sound: it counts real decompressed bytes per-chunk (not
`ZipInfo.file_size`), bounds per-entry reads to `MAX_ENTRY_BYTES`, and bounds the cross-entry total to
`MAX_BULK_BYTES`, so no single entry or batch can force more than ~1.25 GB of actual decompression work
(50 files × 25 MB), and the tests correctly exercise the DEFLATE case that would defeat a
container-size-only guard.

However, the SEC-02 rollback path has two correctness gaps that undermine the "zero commits on
failure" guarantee the module's own docstring promises, plus several secondary robustness issues:

1. **The rollback is not atomic with the file cleanup it depends on** — if the compensating
   `delete_many` itself fails, the code still deletes the on-disk files for records that remain in the
   database, producing evidence entries with dangling `url` fields (Critical).
2. **The rollback can be skipped entirely** on cancellation (client disconnect / request timeout),
   because it is scoped to `except Exception` and `asyncio.CancelledError` does not subclass
   `Exception` in Python 3.8+, so a cancelled request can leave orphaned files and DB records with no
   cleanup at all (Critical).

Tenant isolation on the write path itself (role check, `tenantId` stamped on every inserted record) is
correctly enforced, but the compensating `delete_many` rollback filter is not scoped by `tenantId`,
which is a defense-in-depth gap worth closing even though it is not currently exploitable (see WR-01).

## Critical Issues

### CR-01: Rollback failure leaves DB records pointing at deleted files (broken evidence links)

**File:** `backend/compliance_bulk_evidence_endpoints.py:223-235`
**Issue:** In the exception handler for the commit loop, the compensating `delete_many` (line 227) and
the on-disk file cleanup (lines 230-234) are independent, unconditional steps. If `delete_many` raises
(e.g. transient Mongo error, network blip during the exact moment rollback is needed), the code logs
the failure at line 229 and then *still* proceeds to unlink every file in `written_paths` at lines
230-234. This means any record that failed to roll back in the DB now has a `url` pointing at a file
that no longer exists on disk — the evidence entry is silently corrupted (permanently broken download
link) while the client is told the whole batch failed with a 500 and zero commits, which is false: some
records survived, just with dead file references. This directly contradicts the module's own guarantee
("Any single failure ... zero commits"; BULK-02).
**Fix:** Do not delete files unconditionally once DB rollback has failed. Either skip file cleanup when
`delete_many` fails and leave both DB rows and files intact for manual reconciliation, or track a
per-record `(id, path)` pairing and only unlink the path for a record that was actually confirmed
deleted:
```python
except Exception:
    rollback_ok = True
    if inserted_ids:
        try:
            await db.control_evidence.delete_many({"id": {"$in": inserted_ids}})
        except Exception as rollback_exc:
            rollback_ok = False
            logger.error(
                "Bulk upload DB rollback failed for ids=%s: %s",
                inserted_ids, rollback_exc,
            )
    if rollback_ok:
        for p in written_paths:
            try:
                await asyncio.to_thread(os.unlink, p)
            except OSError as unlink_exc:
                logger.error("Bulk upload cleanup: failed to remove %s: %s", p, unlink_exc)
    else:
        logger.error(
            "Bulk upload: skipping file cleanup for batch because DB rollback failed; "
            "files=%s require manual reconciliation", written_paths,
        )
    raise HTTPException(status_code=500, detail="Internal server error")
```

### CR-02: Rollback can be bypassed entirely on request cancellation

**File:** `backend/compliance_bulk_evidence_endpoints.py:189-235`
**Issue:** The commit loop's compensating rollback is scoped to `except Exception:` (line 223). In
Python, `asyncio.CancelledError` inherits from `BaseException`, not `Exception` (since Python 3.8). If
the client disconnects, the request times out, or the server begins a graceful shutdown while the
`for v in validated:` loop is awaiting `_write_binary`, `insert_one`, or `_append_coc_entry`, the task
is cancelled and `CancelledError` propagates straight past this `except Exception:` (and past the outer
`except Exception as exc:` at line 250) without ever reaching the rollback logic. Any files already
written and any DB records already inserted for that partially-committed batch are permanently
orphaned — no compensating delete_many, no file cleanup, nothing logged. This is a realistic production
scenario (reverse-proxy timeouts, client aborting a large multipart upload) and it means "zero commits
on failure" (BULK-02) does not hold for the most common real-world failure mode of a long-running
upload.
**Fix:** Guard the loop with a `finally`-based success flag so rollback also executes on
`BaseException`-derived cancellation, not just `Exception`:
```python
committed_ok = False
try:
    for v in validated:
        ...
        committed.append(record)
    committed_ok = True
finally:
    if not committed_ok:
        if inserted_ids:
            try:
                await db.control_evidence.delete_many({"id": {"$in": inserted_ids}})
            except Exception as rollback_exc:
                logger.error("Bulk upload DB rollback failed: %s", rollback_exc)
        for p in written_paths:
            try:
                await asyncio.to_thread(os.unlink, p)
            except OSError:
                pass
if not committed_ok:
    raise HTTPException(status_code=500, detail="Internal server error")
```
Note this still won't run cleanup if the process itself is killed (SIGKILL), but it closes the common
`CancelledError`/timeout gap that the current `except Exception` cannot catch.

## Warnings

### WR-01: Compensating `delete_many` rollback filter is not tenant-scoped

**File:** `backend/compliance_bulk_evidence_endpoints.py:227`
**Issue:** `db.control_evidence.delete_many({"id": {"$in": inserted_ids}})` filters only on `id`, with
no `tenantId` clause. Every other query/write in this handler is tenant-scoped (`tenantId: tenant_id`
is stamped on each inserted record), but the rollback path is not. Today this is not exploitable — the
`id`s are server-generated `uuid.uuid4().hex` values inserted only for the current tenant within this
same request — but it is a defense-in-depth gap: if `id` generation ever changes (e.g. becomes
predictable, or a future refactor reuses `inserted_ids` from a different code path), this filter would
silently allow deleting another tenant's evidence records with a colliding id. It also contradicts the
phase's own SEC-02 description of the rollback as "tenant-scoped."
**Fix:** Add the tenant filter defensively:
```python
await db.control_evidence.delete_many({
    "id": {"$in": inserted_ids},
    "tenantId": tenant_id,
})
```

### WR-02: Encrypted/password-protected zip entries crash the request instead of producing a validation error

**File:** `backend/compliance_bulk_evidence_endpoints.py:123-151`
**Issue:** The per-entry read is wrapped in `except KeyError` (entry missing) and
`except (zipfile.BadZipFile, OSError, zlib.error)` (corrupt entry), but `zipfile.ZipExtFile.read()`
raises `RuntimeError` (e.g. `"File '...' is encrypted, password required for extraction"`) when a zip
entry is AES/ZipCrypto-protected. That `RuntimeError` is not caught here, so it propagates to the outer
generic `except Exception` (line 250) and returns an opaque 500 instead of the intended per-file 422
validation report. An unauthenticated-looking but otherwise well-formed encrypted zip entry can trigger
this on every upload attempt, which is a robustness gap for a code path that is explicitly documented
as "validate all entries ... any single failure returns 422 with per-file errors."
**Fix:** Add `RuntimeError` to the caught exceptions for the per-entry read (or catch it as an
"encrypted/unreadable" per-file validation error):
```python
except (zipfile.BadZipFile, OSError, zlib.error, RuntimeError) as exc:
    errors.append({"filename": raw_name, "error": f"Could not read entry: {exc}"})
    continue
```

### WR-03: Manifest entries are not validated for element type before use

**File:** `backend/compliance_bulk_evidence_endpoints.py:70-77, 104-109`
**Issue:** After `json.loads(manifest)`, the code checks `isinstance(items, list)` but never checks
that each `item` is itself a `dict`, nor that `item["filename"]` is a `str`. The membership checks
`"filename" not in item` / `"control_id" not in item` (lines 74-76) happen to work for strings (via
substring containment) but raise `TypeError: argument of type 'int' is not iterable` for a manifest
like `[1, 2, 3]`, and `raw_name.replace(...)` at line 109 raises `AttributeError` if `item["filename"]`
is e.g. an int or list. Neither exception is one of `(json.JSONDecodeError, ValueError)` caught at line
78, so a malformed-but-valid-JSON manifest produces an unhandled 500 instead of the expected 400 "Invalid
manifest" response — an input-validation gap at a system boundary (per project convention: "Validate
input at system boundaries").
**Fix:**
```python
for item in items:
    if not isinstance(item, dict):
        raise ValueError("each manifest entry must be a JSON object")
    if not isinstance(item.get("filename"), str) or not isinstance(item.get("control_id"), str):
        raise ValueError("'filename' and 'control_id' must be strings")
```

### WR-04: Orphaned file left on disk if `_write_binary` itself fails mid-write

**File:** `backend/compliance_bulk_evidence_endpoints.py:192-194`
**Issue:** `written_paths.append(file_path)` happens only *after*
`await asyncio.to_thread(_write_binary, file_path, v["bytes"])` returns successfully. If
`_write_binary` raises partway through (e.g. `OSError: No space left on device` after a partial
`fh.write`), the file may already exist on disk (partially written) but `file_path` was never added to
`written_paths`, so the exception handler's cleanup loop (lines 230-234) never attempts to remove it.
The partial file is orphaned on disk indefinitely.
**Fix:** Track the path before the write is attempted (and treat cleanup as idempotent for a file that
was never created):
```python
file_path = os.path.join(UPLOAD_DIR, stored_name)
written_paths.append(file_path)
await asyncio.to_thread(_write_binary, file_path, v["bytes"])
```

### WR-05: Post-commit cache invalidation failure returns a false 500 after a real, successful commit

**File:** `backend/compliance_bulk_evidence_endpoints.py:237-246`
**Issue:** `invalidate_cache(...)` (four calls) runs after the `with zf:` block, once the DB commit loop
has already fully succeeded and `committed` is populated. These calls are still inside the outer
`try` (line 60) and are not wrapped in their own error handling. If `cache.delete_pattern` raises (e.g.
Redis unavailable), the outer `except Exception as exc:` (line 250) converts it into a 500 response —
even though every record was already durably committed to `control_evidence`. The client sees a hard
failure for what was actually a successful write, and since there is no idempotency key on the batch
(each retry generates fresh `uuid4()` ids), a client that retries on 500 will create duplicate evidence
records for the same files.
**Fix:** Wrap cache invalidation so it cannot turn a successful commit into a reported failure:
```python
try:
    invalidate_cache(f"compliance:score:{tenant_id}")
    invalidate_cache("compliance:score:__super__")
    invalidate_cache(f"compliance:threat-score:{tenant_id}")
    invalidate_cache("compliance:threat-score:__super__")
except Exception as cache_exc:
    logger.error("Bulk upload: cache invalidation failed post-commit: %s", cache_exc)
return {"success": True, "committed": len(committed), "batch_id": batch_id, "evidence": committed}
```

### WR-06: Authorization check uses a brittle, hardcoded case-sensitive role allowlist

**File:** `backend/compliance_bulk_evidence_endpoints.py:34-36, 64-66`
**Issue:** `_WRITE_ROLES` enumerates specific case variants (`"admin"`, `"Admin"`, `"Super Admin"`,
`"superadmin"`, `"super_admin"`, `"platform-admin"`) and `user_role not in _WRITE_ROLES` is an exact
membership test. Any legitimate admin role string that doesn't match one of these exact casings/spacings
(e.g. `"ADMIN"`, `"SuperAdmin"`, `"Platform Admin"`) is silently denied with a 403, even though it may be
a valid admin role elsewhere in the system. This is fragile and will produce confusing false-negative
authorization failures as role naming conventions drift elsewhere in the codebase.
**Fix:** Normalize before comparing, e.g.:
```python
_WRITE_ROLES_NORMALIZED = frozenset(r.lower().replace(" ", "").replace("_", "").replace("-", "")
                                     for r in _WRITE_ROLES)
...
normalized_role = (user_role or "").lower().replace(" ", "").replace("_", "").replace("-", "")
if normalized_role not in _WRITE_ROLES_NORMALIZED:
    raise HTTPException(status_code=403, detail="Insufficient permissions to upload evidence")
```

### WR-07: File-cleanup failures during rollback are silently swallowed with no logging

**File:** `backend/compliance_bulk_evidence_endpoints.py:230-234`
**Issue:** `except OSError: pass` discards any failure to unlink a written file during rollback with no
log line, in contrast to the parallel DB-rollback branch two lines above it, which does log on failure
(line 229). If file deletion fails (permissions, filesystem full, file locked), the operator has no way
to know an orphaned file was left behind after a failed bulk upload — it will silently accumulate on
disk.
**Fix:**
```python
for p in written_paths:
    try:
        await asyncio.to_thread(os.unlink, p)
    except OSError as unlink_exc:
        logger.error("Bulk upload cleanup: failed to remove %s: %s", p, unlink_exc)
```

## Info

### IN-01: `tenant_id` silently defaults to empty string when missing from the authenticated user

**File:** `backend/compliance_bulk_evidence_endpoints.py:61`
**Issue:** `tenant_id = getattr(current_user, "tenant_id", None) or ""` masks a missing/None
`tenant_id` on an authenticated user by silently substituting `""` rather than rejecting the request.
Every subsequent record is then stamped with `tenantId: ""`, which could group evidence from
misconfigured accounts into a shared, un-scoped bucket. This matches an existing pattern elsewhere in
the codebase, so it's flagged as informational rather than a blocking finding for this phase, but is
worth hardening (e.g. `raise HTTPException(403, "Missing tenant context")` when tenant_id is falsy) the
next time this module is touched.
**Fix:** Consider failing closed instead of defaulting to `""` when `tenant_id` is missing.

### IN-02: `.docx` and `.xlsx` share an identical magic-byte signature, so content-type spoofing between the two is not detected

**File:** `backend/compliance_artifacts_endpoints.py:63-64` (imported and relied upon by
`compliance_bulk_evidence_endpoints.py:157`)
**Issue:** `_MAGIC_SIGNATURES` maps both `.docx` and `.xlsx` to the generic OOXML/zip signature
`b"PK\x03\x04"`. `_check_magic` therefore accepts any OOXML zip container for either extension — an
`.xlsx` file renamed to `.docx` (or vice versa) passes the magic-byte check. This file is outside this
phase's diff, so it is not scored as a blocking finding here, but it directly affects the correctness
guarantee this endpoint relies on ("File content does not match extension") and should be tightened
(e.g. inspect `[Content_Types].xml` inside the OOXML zip) in a future pass.
**Fix:** Out of scope for this phase; noted for future hardening of `_check_magic`.

---

_Reviewed: 2026-07-02T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
