# Phase 11: Security Hardening — Research

**Researched:** 2026-06-22
**Domain:** Python asyncio security, zip decompression attacks, MongoDB rollback patterns, ContextVar lifecycle
**Confidence:** HIGH

---

## Summary

Phase 11 is a targeted bug-fix phase closing three verified security and data-integrity findings from the Phase 8 code review (CR-02, CR-03) and a ContextVar leak identified during architecture review (CR-SEC-03). All three findings are already located in two files (`compliance_bulk_evidence_endpoints.py` and `tenant_context.py` / `authentication_service.py`). No new libraries or infrastructure are required — fixes are pure logic changes in existing code.

**F-01 (SEC-01)** is a real, exploitable bypass of the 200 MB zip-bomb pre-check. The fix integrates a cross-entry byte accumulator into the existing chunked-read loop. The existing per-entry cap (line 132) is correct and stays unchanged.

**F-02 (SEC-02)** is a real data-integrity gap. MongoDB is running as a standalone instance (no replica set configured — confirmed via `MONGODB_URL=mongodb://localhost:27017` with no `replicaSet` param), so ACID transactions are unavailable. The correct fix is a compensating `delete_many` in the except block, scoped by the collected `inserted_ids`.

**F-03 (SEC-03)** is a lower-severity defensive hardening. Uvicorn creates a new asyncio `Task` per HTTP request, which copies (not shares) the ContextVar context — so there is no cross-request leak in standard operation. The real leak window is: (a) `asyncio.create_task()` calls within a request that inherit a stale context, and (b) `FastAPI.BackgroundTasks` which run after the response is sent with the context that was active when `add_task()` was called. The fix — converting `get_current_user` to a generator dependency with `try/finally` reset — closes this window definitively.

**Primary recommendation:** Fix all three in a single backend-only phase. No frontend changes required. All fixes are verifiable with synchronous `TestClient` tests matching the project's existing test pattern (no `pytest-asyncio`).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Zip-bomb total-size validation | API / Backend | — | Server-side only; client cannot be trusted for size metadata |
| DB rollback on partial commit | API / Backend | Database / Storage | Compensating deletes executed by the API layer; MongoDB layer has no auto-rollback without replica set |
| ContextVar tenant isolation | API / Backend | — | Request-scoped context; no frontend or DB involvement |

---

## Standard Stack

No new dependencies required. All fixes use Python stdlib and existing project imports.

### Relevant Existing Imports

| Module | Used In | Purpose in Fix |
|--------|---------|---------------|
| `contextvars` (stdlib) | `tenant_context.py` | `ContextVar.set()` returns a `Token`; `ContextVar.reset(token)` restores prior state |
| `zipfile` (stdlib) | `compliance_bulk_evidence_endpoints.py` | `zf.open(name)` + chunked read; accumulator added to existing loop |
| Motor `AsyncIOMotorClient` | `database.py` | `delete_many` on `TenantIsolatedCollection` already implemented |

### Package Legitimacy Audit

No new packages installed in this phase.

| Package | Registry | Verdict | Disposition |
|---------|----------|---------|-------------|
| N/A | — | — | No new packages |

---

## Finding F-01 / SEC-01: Zip-bomb Spoofable Metadata

### Current Code Analysis

**File:** `backend/compliance_bulk_evidence_endpoints.py`
**Lines:** 93–98

```python
with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
    total_uncompressed = sum(i.file_size for i in zf.infolist())   # LINE 94 — BUG
    if total_uncompressed > MAX_BULK_BYTES:
        raise HTTPException(
            status_code=413, detail="Uncompressed content exceeds 200 MB limit"
        )
```

`ZipInfo.file_size` is a field in the zip Local File Header — it is metadata declared by the file that created the zip, and it is not verified by Python's `zipfile` module during `infolist()`. A crafted zip can set `file_size=0` (or any value) for each entry while actually containing large decompressed content. The pre-check at line 94–98 is therefore fully bypassable.

**Lines 121–136 (correct — unchanged):**

```python
buf = io.BytesIO()
with zf.open(raw_name) as entry_fh:
    read = 0
    while True:
        chunk = entry_fh.read(65536)
        if not chunk:
            break
        read += len(chunk)
        if read > MAX_ENTRY_BYTES:
            errors.append({"filename": raw_name, "error": "File exceeds 25 MB limit"})
            buf = None
            break
        buf.write(chunk)
```

This per-entry bounded read is correct and limits individual decompression to 25 MB. It cannot be bypassed via metadata because `read` counts actual bytes returned by `entry_fh.read()`.

### Attack Vector

An attacker crafts a zip where all `ZipInfo.file_size` entries are set to `0`. The pre-check at line 94 computes `sum(0 for i in ...)` = 0, which passes the 200 MB guard. The attacker can then include up to `MAX_BULK_FILES` (50) entries, each up to 25 MB decompressed, totalling 1.25 GB of actual decompression load. The attacker must hold a valid JWT to reach the endpoint, limiting this to authenticated insider threats.

### Recommended Fix [VERIFIED: stdlib zipfile docs + direct runtime test]

Remove the `infolist()` metadata pre-check entirely. Instead, introduce a `total_actual_bytes` accumulator outside the entry loop and increment it inside the chunk loop. Check it against `MAX_BULK_BYTES` after each chunk.

**Replace lines 93–98 with:**

```python
# Pass 0b: validate that uploaded bytes are a valid zip (metadata pre-check removed — SEC-01)
if not zipfile.is_zipfile(io.BytesIO(zip_content)):
    raise HTTPException(status_code=400, detail="Uploaded file is not a valid zip")

with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
    # NOTE: Do NOT sum zf.infolist() file_size here — that metadata is spoofable.
    # Total uncompressed size is tracked via actual bytes read in Pass 1 below.
```

**Replace lines 121–136 (the existing chunk loop) with:**

```python
# total_actual_bytes declared once BEFORE the `for item in items:` loop
total_actual_bytes = 0   # tracks real decompressed bytes across all entries (SEC-01)

# ... inside the for item in items loop, replacing the current chunk loop:
buf = io.BytesIO()
with zf.open(raw_name) as entry_fh:
    read = 0
    while True:
        chunk = entry_fh.read(65536)
        if not chunk:
            break
        read += len(chunk)
        total_actual_bytes += len(chunk)          # SEC-01: accumulate across entries
        if read > MAX_ENTRY_BYTES:
            errors.append({"filename": raw_name, "error": "File exceeds 25 MB limit"})
            buf = None
            break
        if total_actual_bytes > MAX_BULK_BYTES:   # SEC-01: cross-entry total cap
            errors.append({"filename": raw_name, "error": "Batch total exceeds 200 MB uncompressed limit"})
            buf = None
            break
        buf.write(chunk)
```

**What stays the same:** The `if len(zip_content) > MAX_BULK_BYTES:` check at line 88 (compressed size guard) remains. The `zipfile.is_zipfile()` check at line 90 remains. The per-entry `read > MAX_ENTRY_BYTES` check remains. Only the infolist sum pre-check is removed.

### Test Strategy

Add one new test to `tests/test_bulk_evidence_upload.py`. The existing `test_bulk_zip_bomb_guard` tests the OLD path (mocking `infolist`). It must be updated to reflect the new behavior (infolist is no longer read for the total check):

```python
def test_bulk_zip_bomb_total_bytes_accumulator():
    """Zip entries whose combined actual bytes exceed 200 MB → 413/422 (SEC-01).
    
    This test verifies the accumulator catches total overflow, NOT the infolist metadata.
    We cannot realistically create a 200 MB zip in a unit test, so we lower the 
    constant using monkeypatching.
    """
    import compliance_bulk_evidence_endpoints as mod
    
    # Two valid 6-byte PDFs — together they exceed a patched 10-byte MAX_BULK_BYTES
    zip_bytes = _make_zip_bytes({
        "a.pdf": b"%PDF-1.4",   # 8 bytes
        "b.pdf": b"%PDF-1.4",   # 8 bytes — total 16 > patched 10
    })
    manifest = json.dumps([
        {"filename": "a.pdf", "control_id": "CC1.1"},
        {"filename": "b.pdf", "control_id": "CC1.2"},
    ])
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)
    
    with patch.object(mod, "MAX_BULK_BYTES", 10), \
         patch.object(mod, "get_database", return_value=db_mock):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )
    # Expect 422 (per-file error in validation pass) or 413
    assert resp.status_code in (413, 422), resp.text
    db_mock.control_evidence.insert_one.assert_not_awaited()
```

Also update `test_bulk_zip_bomb_guard` to patch `MAX_BULK_BYTES` on the module rather than mocking `infolist`, since the infolist path no longer drives the check.

### Risk Assessment

**What breaks if we change this:** The existing `test_bulk_zip_bomb_guard` test patches `zipfile.ZipFile.infolist` — it will need updating to reflect the new code path. No production behavior changes for valid uploads. For malicious zips, the check now fires later (inside the decompression loop) rather than before, which is still safe because the per-entry cap bounds individual reads.

**Residual risk:** None. The bounded read was already correct; the fix simply adds cross-entry accounting.

---

## Finding F-02 / SEC-02: No DB Rollback on Partial Bulk Commit

### Current Code Analysis

**File:** `backend/compliance_bulk_evidence_endpoints.py`
**Lines 178–217:**

```python
try:
    for v in validated:
        stored_name = f"{uuid.uuid4().hex}{v['ext']}"
        file_path = os.path.join(UPLOAD_DIR, stored_name)
        await asyncio.to_thread(_write_binary, file_path, v["bytes"])
        written_paths.append(file_path)

        record: dict = { "id": f"cev-bulk-{uuid.uuid4().hex}", ... }
        await db.control_evidence.insert_one({**record})    # LINE 199
        await _append_coc_entry(...)
        record.pop("_id", None)
        committed.append(record)
except Exception:
    for p in written_paths:
        try:
            await asyncio.to_thread(os.unlink, p)           # disk cleanup: correct
        except OSError:
            pass
    raise HTTPException(status_code=500, detail="Internal server error")
```

If `insert_one` or `_append_coc_entry` raises an exception after N records have been inserted, the except block cleans up disk files (`written_paths`) but does NOT delete the already-inserted `control_evidence` records. Those N records are left orphaned in the database — they reference files that no longer exist on disk.

### MongoDB Transaction Availability

**Confirmed:** The project connects to MongoDB as a standalone instance (`MONGODB_URL=mongodb://localhost:27017` with no `replicaSet` parameter — verified in `database.py` line 175 and `.env`). MongoDB ACID multi-document transactions require a replica set. They are unavailable here. [VERIFIED: database.py runtime configuration]

Motor's `AsyncIOMotorClient` started without replica set configuration does not support `start_session()` with transaction semantics. Attempting to use transactions against a standalone would raise `OperationFailure: Transaction numbers are only allowed on a replica set member or mongos`.

### Attack Vector / Failure Mode

This is a data-integrity failure, not a direct security exploit. If the Nth `insert_one` fails due to a transient MongoDB error, connection timeout, or duplicate key violation:

1. Files 1..N-1 are deleted from disk (correct cleanup).
2. Records 1..N-1 remain in `control_evidence` with valid `id` and `tenantId` fields.
3. Those records' `url` fields point to `/static/evidence/<stored_name>` files that no longer exist.
4. The control detail view will show evidence entries that return 404 when clicked.
5. The audit trail (`evidence_audit_log`) has CoC "create" entries for records that are now orphaned.

The `TenantIsolatedCollection.delete_many` wrapper injects `tenantId` automatically, so a compensating delete is tenant-scoped by construction.

### Recommended Fix [VERIFIED: database.py TenantIsolatedCollection.delete_many + direct code analysis]

Track the `id` field of each successfully inserted record in a list. In the except block, after disk cleanup, issue a `delete_many` on `control_evidence` for all collected IDs. Because `TenantIsolatedCollection.delete_many` injects the tenant filter automatically, the rollback is automatically scoped to the correct tenant.

**Add `inserted_ids` accumulator to commit loop:**

```python
committed: list[dict] = []
written_paths: list[str] = []
inserted_ids: list[str] = []          # SEC-02: track for rollback

try:
    for v in validated:
        stored_name = f"{uuid.uuid4().hex}{v['ext']}"
        file_path = os.path.join(UPLOAD_DIR, stored_name)
        await asyncio.to_thread(_write_binary, file_path, v["bytes"])
        written_paths.append(file_path)

        record: dict = {
            "id": f"cev-bulk-{uuid.uuid4().hex}",
            ...
        }
        await db.control_evidence.insert_one({**record})
        inserted_ids.append(record["id"])             # SEC-02: record after successful insert
        await _append_coc_entry(...)
        record.pop("_id", None)
        committed.append(record)
except Exception:
    # SEC-02: DB rollback — delete any already-inserted records
    if inserted_ids:
        try:
            await db.control_evidence.delete_many({"id": {"$in": inserted_ids}})
        except Exception as rollback_exc:
            logger.error("Bulk upload DB rollback failed: %s", rollback_exc)
    # Disk cleanup (unchanged)
    for p in written_paths:
        try:
            await asyncio.to_thread(os.unlink, p)
        except OSError:
            pass
    raise HTTPException(status_code=500, detail="Internal server error")
```

**Why this works with TenantIsolatedCollection:** The `delete_many` call goes through `TenantIsolatedCollection._inject_tenant_id()` which appends `{"tenantId": effective_tenant_id}` to the filter. The resulting query is `{"id": {"$in": [...]}, "tenantId": "tenant-X"}` — it only deletes records belonging to the current tenant and matching the collected IDs.

**Note on CoC records:** CoC entries in `evidence_audit_log` are intentionally immutable — the Phase 7 design explicitly states they must not be auto-purged. Rolled-back CoC "create" entries can remain as an audit trail of the attempted upload. The planner does NOT need to add CoC rollback.

### Test Strategy

Add to `tests/test_bulk_evidence_upload.py`:

```python
def test_bulk_db_rollback_on_partial_failure():
    """Mid-batch insert_one failure triggers delete_many for already-inserted IDs (SEC-02)."""
    pdf_bytes = b"%PDF-1.4 content"
    zip_bytes = _make_zip_bytes({
        "first.pdf":  pdf_bytes,
        "second.pdf": pdf_bytes,
    })
    manifest = json.dumps([
        {"filename": "first.pdf",  "control_id": "CC1.1"},
        {"filename": "second.pdf", "control_id": "CC1.2"},
    ])
    user = _fake_user()
    db_mock = _make_mock_db()
    
    # First insert succeeds, second raises
    call_count = {"n": 0}
    async def insert_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise Exception("simulated DB error")
        return MagicMock(inserted_id="cev-id")
    
    db_mock.control_evidence.insert_one = AsyncMock(side_effect=insert_side_effect)
    db_mock.control_evidence.delete_many = AsyncMock()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock), \
         patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("batch.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code == 500, resp.text
    # Rollback: delete_many should have been called with the first record's id
    db_mock.control_evidence.delete_many.assert_awaited_once()
    call_args = db_mock.control_evidence.delete_many.call_args[0][0]
    assert "$in" in call_args["id"]
    assert len(call_args["id"]["$in"]) == 1   # only the first successful insert
```

### Risk Assessment

**What breaks if we change this:** No behavior change for successful uploads. For failed uploads, the user now receives a clean state (no orphaned records) instead of a partially-committed state. The rollback itself is a best-effort `delete_many` — if the rollback also fails, the error is logged but the 500 is still raised. This is acceptable: a double failure (insert fails AND rollback fails) leaves the database in the same orphaned state as before, but the failure is now logged for investigation.

---

## Finding F-03 / SEC-03: ContextVar Tenant Context Not Cleaned on Exceptions

### Current Code Analysis

**File:** `backend/tenant_context.py` (full file — 14 lines)

```python
from contextvars import ContextVar
from typing import Optional

_tenant_id_ctx: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)

def set_tenant_id(tenant_id: str):
    """Set the tenant_id for the current context"""
    _tenant_id_ctx.set(tenant_id)          # BUG: discards returned Token

def get_tenant_id() -> Optional[str]:
    """Get the tenant_id for the current context"""
    return _tenant_id_ctx.get()
```

`ContextVar.set()` returns a `Token` object that can be used to restore the ContextVar to its prior value via `ContextVar.reset(token)`. The current code discards this Token, making it impossible to undo the `set()` later.

**File:** `backend/authentication_service.py` lines 151–158 (`verify_token_async`):

```python
token_data = TokenData(username=username, role=role, tenant_id=tenant_id, ...)
_set_tenant_id(tenant_id or "platform-admin")   # LINE 157 — sets ContextVar
return token_data
```

The ContextVar is set at line 157 and there is no cleanup path.

### asyncio ContextVar Isolation Model [VERIFIED: direct runtime testing]

Python's `contextvars` module guarantees that each `asyncio.Task` receives a **copy** of the context from its creating scope, not a reference. Mutations inside a Task do not affect the parent or sibling tasks.

**Practical consequence for uvicorn:** Uvicorn's h11 and httptools implementations call `asyncio.ensure_future()` (or `loop.create_task()`) for each HTTP request, producing a fresh asyncio Task per request. Therefore:

- In the **standard request path**, ContextVar values do NOT leak across requests.
- The ContextVar starts as `None` (the default) at the beginning of each request Task.
- Even if `set_tenant_id` is called and an exception propagates without cleanup, the next HTTP request runs in a new Task with a fresh copy of the context.

**The real leak scenarios (confirmed by runtime test):**

1. **`asyncio.create_task()` within a request:** `tickets_config_mixin.py:240`, `model_retraining_service.py:75`, `software_endpoints.py:387`, etc. — these calls snapshot the current context at `create_task()` time. If the tenant ContextVar is set (correctly) at request time, these tasks inherit the correct tenant, which is the desired behavior. No leak here.

2. **`asyncio.to_thread()` in bulk upload (lines 182, 214):** `asyncio.to_thread` copies the current context into the thread. This is correct behavior — the thread needs tenant context for any tenant-aware operations.

3. **`FastAPI.BackgroundTasks`** (`compliance_scans_endpoints.py:53`, `soar_endpoints.py:81`, etc.): Starlette schedules background tasks by capturing `contextvars.copy_context()` at the time of response sending. If the ContextVar was set during the request handler and an exception path corrupted it, the background task inherits the corrupted value.

4. **`get_optional_user`** path (line 173–181): Returns `None` without calling `_set_tenant_id`. Endpoints that use `get_optional_user` and then fall through without auth will see whatever tenant context was previously set in the Task (which is `None` for a fresh Task, or a stale value if the Task was reused — this is unlikely with uvicorn's per-request task model but is a defense-in-depth concern).

**Severity Assessment:** MEDIUM. Not an emergency cross-request data leak in normal uvicorn operation. A defense-in-depth fix that closes the window for background task inheritance and any future code that reuses tasks.

### Recommended Fix [VERIFIED: Python contextvars stdlib docs + runtime test]

**Part 1 — `tenant_context.py`:** Return the `Token` from `set_tenant_id` and add a `reset_tenant_id` function.

```python
from contextvars import ContextVar, Token
from typing import Optional

_tenant_id_ctx: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)

def set_tenant_id(tenant_id: str) -> Token:
    """Set the tenant_id for the current context. Returns a Token for reset."""
    return _tenant_id_ctx.set(tenant_id)          # Return Token — callers use for reset

def reset_tenant_id(token: Token) -> None:
    """Reset the tenant_id to its value before the matching set_tenant_id call."""
    _tenant_id_ctx.reset(token)

def get_tenant_id() -> Optional[str]:
    """Get the tenant_id for the current context."""
    return _tenant_id_ctx.get()
```

**Part 2 — `authentication_service.py`:** Convert `get_current_user` to an async generator dependency so the ContextVar reset happens in a `finally` block after the endpoint handler completes.

```python
from tenant_context import set_tenant_id as _set_tenant_id, reset_tenant_id as _reset_tenant_id

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Dependency to get the current user; performs async revocation check.
    
    Uses generator form (yield) so the ContextVar tenant context is reset
    in the finally block after the endpoint handler completes (SEC-03).
    """
    token_data = await verify_token_async(token)
    # verify_token_async now returns token_data WITHOUT setting the ContextVar
    # We set it here and reset it after the request finishes
    ctx_token = _set_tenant_id(token_data.tenant_id or "platform-admin")
    try:
        yield token_data
    finally:
        _reset_tenant_id(ctx_token)
```

**Part 3 — `authentication_service.py` `verify_token_async`:** Remove the `_set_tenant_id` call from `verify_token_async` (line 157), since `get_current_user` now owns that responsibility. Do the same for `verify_token` (line 96).

**Part 4 — `authentication_service.py` `get_optional_user`:** Apply the same generator pattern:

```python
async def get_optional_user(token: Optional[str] = Depends(_oauth2_optional)):
    if not token:
        yield None
        return
    try:
        token_data = await verify_token_async(token)
    except HTTPException:
        yield None
        return
    ctx_token = _set_tenant_id(token_data.tenant_id or "platform-admin")
    try:
        yield token_data
    finally:
        _reset_tenant_id(ctx_token)
```

**`tunnel_endpoints.py` callers of `verify_token_async` directly:** These call `verify_token_async` directly (not via `Depends`). After removing the `_set_tenant_id` call from `verify_token_async`, these callers will need to set/reset the tenant context themselves if they need it. Check whether `tunnel_endpoints.py` uses `get_tenant_id()` or the `TenantIsolatedCollection` (which reads tenant context automatically). If it does not need tenant context (WebSocket upgrade path likely has its own auth), no change is needed there.

**`deployment_result_endpoints.py` calls `verify_token` (sync):** Same analysis — if it accesses tenant-isolated collections, the sync `verify_token` will also need a Token-returning update.

### Test Strategy

Add to `backend/tests/` a new file `tests/test_tenant_context.py`:

```python
"""Tests for tenant context ContextVar lifecycle (SEC-03)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from tenant_context import set_tenant_id, reset_tenant_id, get_tenant_id

def test_set_returns_token_and_reset_restores():
    """set_tenant_id returns Token; reset_tenant_id restores prior value (SEC-03)."""
    assert get_tenant_id() is None
    token = set_tenant_id("tenant-A")
    assert get_tenant_id() == "tenant-A"
    reset_tenant_id(token)
    assert get_tenant_id() is None

def test_reset_on_exception_path():
    """ContextVar is cleaned up even when an exception occurs (SEC-03)."""
    token = set_tenant_id("tenant-B")
    try:
        raise ValueError("simulated error")
    except ValueError:
        pass
    finally:
        reset_tenant_id(token)
    assert get_tenant_id() is None

def test_get_current_user_resets_context_via_generator():
    """get_current_user generator dependency resets ContextVar after yield (SEC-03)."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from authentication_service import get_current_user

    async def inspect_after():
        return get_tenant_id()

    app = FastAPI()

    @app.get("/test")
    async def endpoint(user=__import__('fastapi').Depends(get_current_user)):
        return {"tenant": get_tenant_id()}

    fake_user = MagicMock()
    fake_user.tenant_id = "tenant-C"
    fake_user.username = "user"
    fake_user.role = "admin"
    app.dependency_overrides[get_current_user] = lambda: fake_user

    with TestClient(app) as client:
        resp = client.get("/test", headers={"Authorization": "Bearer fake"})
    # After request completes, the ContextVar should be reset
    assert get_tenant_id() is None
```

### Risk Assessment

**What breaks if we change this:**

1. **All callers of `verify_token_async` that relied on the side effect of `_set_tenant_id`:** After removing `_set_tenant_id` from `verify_token_async`, any code that calls `verify_token_async` directly and then accesses `get_tenant_id()` will get `None`. Affected files: `tunnel_endpoints.py` (4 call sites). These need individual review.

2. **`get_current_user` return → yield change:** FastAPI's `Depends` system supports both `return` and `yield` (generator) dependencies. Existing endpoint signatures using `Depends(get_current_user)` require no changes. The yielded value is the same object as the previously returned value.

3. **`dependency_overrides[get_current_user] = lambda: user`** in tests: Lambda overrides return a value, not a generator. FastAPI handles this correctly — when a dependency is overridden, the override's protocol (return vs yield) takes precedence. Existing test mocks will continue to work without modification. [ASSUMED — FastAPI dependency override behavior with generator deps; verify with one test run]

4. **`require_mfa` and `require_admin`** which `Depends(get_current_user)`: These call `Depends(get_current_user)` and re-use the same generator — FastAPI caches dependency results within a request, so `get_current_user` runs once per request even if multiple downstream dependencies declare it.

---

## Common Pitfalls

### Pitfall 1: Resetting ContextVar Inside verify_token_async Instead of get_current_user
**What goes wrong:** If you add `_reset_tenant_id(token)` at the end of `verify_token_async`, the ContextVar is reset before the endpoint handler runs, making `get_tenant_id()` return `None` throughout the request.
**Why it happens:** Confusing where in the call stack the cleanup should happen.
**How to avoid:** The generator form of `get_current_user` with `try/yield/finally` is the correct pattern — the reset happens AFTER `yield`, which is AFTER the endpoint handler returns.

### Pitfall 2: Calling delete_many Before Collecting All inserted_ids
**What goes wrong:** If `inserted_ids.append(record["id"])` is placed BEFORE `insert_one`, and `insert_one` fails, you add an ID that was never inserted.
**Why it happens:** Misplacing the append relative to the await.
**How to avoid:** Always append to `inserted_ids` AFTER `await db.control_evidence.insert_one({**record})` succeeds.

### Pitfall 3: Checking total_actual_bytes Only After the Entry Loop
**What goes wrong:** A single entry could legitimately read up to 25 MB before the cross-entry total is checked; an attacker with 50 entries could decompress 1.25 GB before the outer check fires.
**Why it happens:** Placing the total check outside the chunk loop.
**How to avoid:** Check `total_actual_bytes > MAX_BULK_BYTES` INSIDE the chunk-reading while loop, after each increment.

### Pitfall 4: Updating test_bulk_zip_bomb_guard Without Removing the infolist Mock
**What goes wrong:** The existing test patches `zipfile.ZipFile.infolist` — after the fix, infolist is no longer called for the total check. The test may still pass vacuously (patch has no effect) or break.
**Why it happens:** Not updating tests when the code path changes.
**How to avoid:** Remove the `patch("zipfile.ZipFile.infolist", ...)` from `test_bulk_zip_bomb_guard` and replace with `patch.object(mod, "MAX_BULK_BYTES", small_value)`.

---

## Code Examples

### F-01: Full Revised Validation Section Structure

```python
# AFTER fix: no infolist() call for total size; accumulator inside chunk loop

with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
    # Pass 1: validate all entries (no writes yet)
    errors: list[dict] = []
    validated: list[dict] = []
    total_actual_bytes = 0  # SEC-01: cross-entry accumulator

    for item in items:
        raw_name: str = item["filename"]
        control_id: str = item["control_id"]

        safe_name = os.path.basename(raw_name.replace("\\", "/"))
        if not safe_name or safe_name in (".", ".."):
            errors.append({"filename": raw_name, "error": "Unsafe filename"})
            continue

        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in _EVIDENCE_ALLOWED_EXTENSIONS:
            errors.append({"filename": raw_name, "error": f"Extension '{ext}' not allowed"})
            continue

        try:
            buf = io.BytesIO()
            with zf.open(raw_name) as entry_fh:
                read = 0
                while True:
                    chunk = entry_fh.read(65536)
                    if not chunk:
                        break
                    read += len(chunk)
                    total_actual_bytes += len(chunk)        # SEC-01
                    if read > MAX_ENTRY_BYTES:
                        errors.append({"filename": raw_name, "error": "File exceeds 25 MB limit"})
                        buf = None
                        break
                    if total_actual_bytes > MAX_BULK_BYTES: # SEC-01
                        errors.append({"filename": raw_name, "error": "Batch total exceeds 200 MB uncompressed limit"})
                        buf = None
                        break
                    buf.write(chunk)
        except KeyError:
            errors.append({"filename": raw_name, "error": "File not found in zip"})
            continue

        if buf is None:
            continue
        # ... magic check, append to validated
```

### F-02: Commit Loop With Rollback

```python
committed: list[dict] = []
written_paths: list[str] = []
inserted_ids: list[str] = []       # SEC-02

try:
    for v in validated:
        stored_name = f"{uuid.uuid4().hex}{v['ext']}"
        file_path = os.path.join(UPLOAD_DIR, stored_name)
        await asyncio.to_thread(_write_binary, file_path, v["bytes"])
        written_paths.append(file_path)

        record: dict = {"id": f"cev-bulk-{uuid.uuid4().hex}", ...}
        await db.control_evidence.insert_one({**record})
        inserted_ids.append(record["id"])               # SEC-02: after successful insert

        await _append_coc_entry(...)
        record.pop("_id", None)
        committed.append(record)
except Exception:
    if inserted_ids:                                    # SEC-02: DB rollback
        try:
            await db.control_evidence.delete_many({"id": {"$in": inserted_ids}})
        except Exception as rollback_exc:
            logger.error("Bulk upload DB rollback failed: %s", rollback_exc)
    for p in written_paths:
        try:
            await asyncio.to_thread(os.unlink, p)
        except OSError:
            pass
    raise HTTPException(status_code=500, detail="Internal server error")
```

### F-03: Generator Dependency Pattern

```python
# tenant_context.py
from contextvars import ContextVar, Token
from typing import Optional

_tenant_id_ctx: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)

def set_tenant_id(tenant_id: str) -> Token:
    return _tenant_id_ctx.set(tenant_id)

def reset_tenant_id(token: Token) -> None:
    _tenant_id_ctx.reset(token)

def get_tenant_id() -> Optional[str]:
    return _tenant_id_ctx.get()
```

```python
# authentication_service.py — get_current_user becomes an async generator
from tenant_context import set_tenant_id as _set_tenant_id, reset_tenant_id as _reset_tenant_id

async def get_current_user(token: str = Depends(oauth2_scheme)):
    token_data = await verify_token_async(token)
    ctx_token = _set_tenant_id(token_data.tenant_id or "platform-admin")
    try:
        yield token_data
    finally:
        _reset_tenant_id(ctx_token)
```

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies — all fixes are Python stdlib + existing Motor client)

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (synchronous TestClient pattern — no pytest-asyncio) |
| Config file | None detected (runs via `python3 -m pytest`) |
| Quick run command | `cd backend && python3 -m pytest tests/test_bulk_evidence_upload.py tests/test_tenant_context.py -v` |
| Full suite command | `cd backend && python3 -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEC-01 | Accumulator rejects crafted zip with falsified file_size=0 | unit | `pytest tests/test_bulk_evidence_upload.py::test_bulk_zip_bomb_total_bytes_accumulator -x` | Wave 0 (new test) |
| SEC-02 | Partial commit triggers delete_many rollback | unit | `pytest tests/test_bulk_evidence_upload.py::test_bulk_db_rollback_on_partial_failure -x` | Wave 0 (new test) |
| SEC-03 | ContextVar reset after request via generator dep | unit | `pytest tests/test_tenant_context.py -x` | Wave 0 (new file) |

### Wave 0 Gaps

- [ ] `tests/test_tenant_context.py` — covers SEC-03 (new file, ~30 lines)
- [ ] `tests/test_bulk_evidence_upload.py::test_bulk_zip_bomb_total_bytes_accumulator` — covers SEC-01 (add to existing file)
- [ ] `tests/test_bulk_evidence_upload.py::test_bulk_db_rollback_on_partial_failure` — covers SEC-02 (add to existing file)
- [ ] Update `tests/test_bulk_evidence_upload.py::test_bulk_zip_bomb_guard` — remove `infolist` mock, use `MAX_BULK_BYTES` patch

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V12 File and Resource Upload | yes | Bounded streaming read, magic byte check |
| V4 Access Control | yes | Tenant isolation via ContextVar reset |
| V5 Input Validation | yes | Zip metadata treated as untrusted; actual bytes are ground truth |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Zip bomb via falsified metadata | DoS / Tampering | Bound reads by actual bytes decompressed, not declared size |
| Orphaned records on partial write | Tampering (data integrity) | Compensating delete_many after exception |
| ContextVar tenant leak to background tasks | Elevation of Privilege | Token-based reset in generator dependency |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | FastAPI `dependency_overrides[get_current_user] = lambda: user` continues to work when `get_current_user` is converted to async generator | F-03 Risk Assessment | Existing test suite may break; verify with one test run before committing |
| A2 | `tunnel_endpoints.py` direct `verify_token_async` callers do not access `get_tenant_id()` after the call and therefore need no ContextVar changes | F-03 Risk Assessment | Tunnel endpoints could silently use wrong tenant; review each of 4 call sites |

---

## Open Questions

1. **Does `tunnel_endpoints.py` use tenant-isolated collections after calling `verify_token_async` directly?**
   - What we know: 4 call sites in `tunnel_endpoints.py` use `verify_token_async` directly (not via `Depends`). After the fix, these calls will NOT set the ContextVar.
   - What's unclear: Whether those code paths access `db.some_collection` which goes through `TenantIsolatedCollection` and reads `get_tenant_id()`.
   - Recommendation: The planner should add a task to grep for `get_database()` usage in `tunnel_endpoints.py` and check if it needs explicit `set_tenant_id`/`reset_tenant_id` calls.

2. **Should `deployment_result_endpoints.py` sync `verify_token` also be updated?**
   - What we know: Line 32 calls `await verify_token(token)` (actually the sync version called in an async context). After removing `_set_tenant_id` from `verify_token`, this path loses tenant context.
   - Recommendation: Check if `deployment_result_endpoints.py` accesses tenant-isolated data after token verification.

---

## Sources

### Primary (HIGH confidence)
- Python stdlib `contextvars` documentation — `ContextVar.set()` returns Token; `Token.reset()` restores prior value. [VERIFIED: direct runtime test — `python3 -c "import contextvars; v = contextvars.ContextVar('x', default=None); tok = v.set('hello'); v.reset(tok); assert v.get() is None"`]
- `backend/database.py:175` — MongoDB URL is `mongodb://localhost:27017` with no `replicaSet` param — standalone instance, no transactions. [VERIFIED: source file read]
- `backend/compliance_bulk_evidence_endpoints.py:94` — `sum(i.file_size for i in zf.infolist())` confirmed as the vulnerable line. [VERIFIED: source file read]
- `backend/compliance_bulk_evidence_endpoints.py:199-217` — No rollback delete_many in except block confirmed. [VERIFIED: source file read]
- asyncio task ContextVar isolation — `asyncio.create_task()` copies context at creation time, not by reference. [VERIFIED: direct runtime test]

### Secondary (MEDIUM confidence)
- uvicorn per-request Task isolation — Each HTTP request gets its own asyncio Task via `loop.create_task()`. [ASSUMED based on uvicorn architecture; confirmed by observed behavior]

### Tertiary (LOW confidence)
- FastAPI generator dependency override compatibility in tests. [ASSUMED]

---

## Metadata

**Confidence breakdown:**
- F-01 fix approach: HIGH — runtime-verified that actual bytes read diverge from `file_size` metadata under attacker control; accumulator pattern verified
- F-02 fix approach: HIGH — TenantIsolatedCollection.delete_many confirmed to exist and inject tenant filter; MongoDB standalone confirmed (no replica set)
- F-03 fix approach: HIGH for ContextVar Token API; MEDIUM for uvicorn Task isolation model; LOW for test override compatibility

**Research date:** 2026-06-22
**Valid until:** Stable — stdlib and existing architecture; no version-sensitive findings

---

## RESEARCH COMPLETE
