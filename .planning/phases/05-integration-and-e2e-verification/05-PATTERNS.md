# Phase 5: Integration and E2E Verification — Pattern Map

**Mapped:** 2026-06-18
**Files analyzed:** integration test files (new) + cross-phase seam files (read-only verification)
**Analogs found:** 4 / 4

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/tests/test_cross_phase_contracts.py` | test | request-response | `backend/tests/test_evidence_uploads.py` | exact |
| `backend/tests/test_export_golden_path.py` | test | request-response | `backend/tests/test_audit_export.py` | exact |
| `backend/tests/test_remediation_loop.py` | test | event-driven | `backend/tests/test_rust_heartbeat_parity.py` | role-match |
| `backend/tests/test_tenant_isolation_e2e.py` | test | request-response | `backend/tests/test_audit_export.py` | exact |

---

## Pattern Assignments

### New integration test files (general)

**Analog:** `backend/tests/test_evidence_uploads.py`

**sys.path injection pattern** (lines 14–15 of every existing test file):
```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
```
All test files manually add the backend parent dir to `sys.path` — there is no `conftest.py` that does this automatically for function-level imports. Always add these two lines at module top before any backend imports.

**No TestClient by default — direct async calls via `asyncio.run`**

The dominant pattern is NOT FastAPI `TestClient`. Unit tests call endpoint functions directly with mocked deps:
```python
async def _run():
    with patch("compliance_evidence_endpoints.get_database", return_value=db), \
         patch("compliance_evidence_endpoints.asyncio.to_thread", new=AsyncMock(return_value=None)):
        return await upload_compliance_evidence(
            request=req, response=resp, asset_id="asset-1",
            file=uf, control_id="CTRL-001", description="Test upload",
            current_user=user,
        )
result = asyncio.run(_run())
```
`TestClient` is used **only** for HTTP-level routing tests (e.g., cross-tenant 403 checks), and only when the test genuinely needs the HTTP layer:
```python
from fastapi.testclient import TestClient
from fastapi import FastAPI
app = FastAPI()
app.include_router(compliance_reports_endpoints.router)
app.dependency_overrides[get_current_user] = lambda: caller
client = TestClient(app, raise_server_exceptions=False)
response = client.get("/api/compliance/reports/download/compliance_report_x_1.pdf")
assert response.status_code == 403
```

**DB mock factory pattern** (`backend/tests/test_evidence_uploads.py` lines 36–54):
```python
def _make_db(asset_doc=None, aggregate_result=None):
    db = MagicMock()

    assets_col = MagicMock()
    assets_col.find_one = AsyncMock(
        return_value=asset_doc if asset_doc is not None
        else {"id": "asset-1", "tenantId": "tenant-a"}
    )
    db.assets = assets_col

    ac_col = MagicMock()
    ac_col.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    agg_mock = MagicMock()
    agg_mock.to_list = AsyncMock(return_value=aggregate_result or [])
    ac_col.aggregate = MagicMock(return_value=agg_mock)
    db.asset_compliance = ac_col

    return db
```
Key: `aggregate` returns a `MagicMock` whose `.to_list` is an `AsyncMock`. Never use `AsyncMock` for the aggregate call itself — only `.to_list` is async.

**conftest.py shared DB fixture** (`backend/tests/conftest.py` lines 41–72):
```python
def _make_col(**overrides):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock()
    col.find = MagicMock(return_value=AsyncMock())
    col.find.return_value.to_list = AsyncMock(return_value=[])
    col.distinct = AsyncMock(return_value=[])
    col.aggregate = MagicMock(return_value=AsyncMock())
    col.aggregate.return_value.to_list = AsyncMock(return_value=[])
    for k, v in overrides.items():
        setattr(col, k, v)
    return col

@pytest.fixture
def mock_db():
    col = _make_col()
    db = MagicMock()
    db.__getattr__ = MagicMock(return_value=col)
    for name in ("assets", "asset_compliance", "agents", ...):
        setattr(db, name, _make_col())
    return db
```
Prefer the conftest `mock_db` fixture for new tests. Use local `_make_db()` helpers only when you need configurable return values (e.g., `aggregate_result`).

**User/token helper pattern** (`backend/tests/conftest.py` lines 15–34):
```python
def make_token_data(username="test@example.com", role="User", tenant_id="tenant-test"):
    from auth_types import TokenData
    td = TokenData(username=username, role=role, tenant_id=tenant_id)
    return td

def make_super_admin_token():
    return make_token_data(role="Super Admin", tenant_id="platform-admin")

def make_tenant_token(tenant_id="tenant-a"):
    return make_token_data(tenant_id=tenant_id)
```

**App-factory helper for TestClient tests** (`backend/tests/conftest.py` lines 116–134):
```python
def make_test_app(*routers, current_user_override=None, db_override=None):
    from fastapi import FastAPI
    from authentication_service import get_current_user
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    if current_user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: current_user_override
    return app, db_override
```

---

### `backend/tests/test_cross_phase_contracts.py` (data contract verification)

**Analog:** `backend/tests/test_rust_heartbeat_parity.py` (direct function call + mock DB)

**Processor mock runner pattern** (lines 59–84 of `test_rust_heartbeat_parity.py`):
```python
def _mock_db():
    from unittest.mock import AsyncMock, MagicMock
    col = MagicMock()
    col.update_one = AsyncMock()
    col.find_one = AsyncMock(return_value=None)
    db = MagicMock()
    db.asset_compliance = col
    db.assets = MagicMock()
    db.assets.find_one = AsyncMock(return_value=None)
    return db

def _run_processor(db):
    import asyncio
    from unittest.mock import patch, MagicMock
    ctx = MagicMock()
    ctx.get_tenant_id = MagicMock(return_value=None)
    ctx.set_tenant_id = MagicMock()
    with patch.dict("sys.modules", {"tenant_context": ctx}):
        from compliance_evidence_processor import process_automated_evidence
        asyncio.run(process_automated_evidence(hostname, compliance_data, db, agent_type="rust"))
```
The `tenant_context` module is not importable in test environments — always mock it via `patch.dict("sys.modules", {"tenant_context": ctx})` before importing `compliance_evidence_processor`.

**Inspecting `update_one` call args** (lines 104–116 of `test_rust_heartbeat_parity.py`):
```python
for c in db.asset_compliance.update_one.call_args_list:
    args, _ = c
    if not args:
        continue
    if len(args) >= 2 and "$set" in args[1]:
        assert args[1]["$set"].get("agent_type") == "rust"
    if isinstance(args[0], dict) and "controlId" in args[0]:
        filters_seen.add(args[0]["controlId"])
```

---

### `backend/tests/test_tenant_isolation_e2e.py` (two-tenant scenario)

**Analog:** `backend/tests/test_audit_export.py` lines 82–105

**Two-tenant TestClient pattern** (lines 82–105 of `test_audit_export.py`):
```python
def test_legacy_download_blocks_cross_tenant():
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from authentication_service import get_current_user
    import compliance_reports_endpoints

    # Caller belongs to tenant-a
    caller = _make_user(role="Viewer", tenant_id="tenant-a")
    # DB says the resource belongs to tenant-b
    mock_db = _make_reports_db("tenant-b")

    app = FastAPI()
    app.include_router(compliance_reports_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: caller

    with patch.object(compliance_reports_endpoints, "get_database",
                      return_value=mock_db, create=True), \
         patch("os.path.exists", return_value=True):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/compliance/reports/download/compliance_report_x_1.pdf")

    assert response.status_code == 403
```
Pattern: caller's `tenant_id` != resource's `tenantId` in DB → expect 403. Use `patch.object(module, "get_database", ...)` not `patch("database.get_database")` — the module-level reference must be patched, not the origin.

---

## Cross-Phase Data Contract Field Map

### Phase 1 writer: `process_automated_evidence` → `asset_compliance`

**Source:** `backend/compliance_evidence_processor.py` lines 234–266

Fields written to `asset_compliance` document (`$set`):
| Field | Value |
|---|---|
| `tenantId` | tenant_id (looked up from asset/agent) |
| `status` | `"Compliant"` / `"Warning"` / `"Non-Compliant"` |
| `checkName` | check_name string |
| `lastUpdated` | ISO timestamp |
| `lastAutomatedCheck` | ISO timestamp |
| `agent_type` | agent_type param (`"rust"`, `"python"`, etc.) |

Fields written to `asset_compliance.evidence[]` (`$push`):
| Field | Value |
|---|---|
| `id` | `"auto-ev-{hostname}-{controlId}-{check_slug}-{timestamp}"` |
| `name` | `"System Check: {check_name}"` |
| `url` | `"#"` |
| `type` | `"application/json"` |
| `uploadedAt` | ISO timestamp |
| `assetId` | `"asset-{hostname}"` |
| `controlId` | stripped control ID |
| `tenantId` | tenant_id |
| `systemGenerated` | `True` |
| `content` | markdown string |
| `agent_type` | agent_type param |

**NOTE — `source` field is ABSENT from automated evidence records.** The processor never sets `source`. This is intentional: `_flatten_evidence` classifies a record as automated when `systemGenerated is True OR source is None`. Both conditions hold for automated records.

---

### Phase 2 writer: `upload_compliance_evidence` → `asset_compliance`

**Source:** `backend/compliance_evidence_endpoints.py` lines 85–98

Fields written to `asset_compliance` document (`$set`):
| Field | Value |
|---|---|
| `status` | `"Pending_Review"` |
| `lastUpdated` | ISO timestamp |
| `tenantId` | caller's tenant_id from JWT |

Fields written to `asset_compliance.evidence[]` (`$push`):
| Field | Value |
|---|---|
| `id` | `"ev-manual-{uuid4().hex}"` |
| `name` | `os.path.basename(file.filename)` |
| `url` | `"/static/evidence/{safe_filename}"` |
| `type` | `file.content_type` |
| `uploadedAt` | ISO timestamp |
| `assetId` | path param `asset_id` |
| `controlId` | form param `control_id` |
| `tenantId` | caller's tenant_id from JWT |
| `uploaded_by` | caller's username from JWT |
| `description` | form param `description` |
| `source` | `"manual"` |
| `systemGenerated` | `False` |

---

### Phase 3 reader: `_flatten_evidence` from `asset_compliance.evidence[]`

**Source:** `backend/compliance_reporting_data.py` lines 46–93

Fields read from each evidence dict:
| Field read | Fallbacks | Used for |
|---|---|---|
| `id` | `url`, `name` | deduplication key |
| `systemGenerated` | (boolean) | auto/manual classification |
| `source` | (absent = auto) | auto/manual classification — `None` → auto |
| `name` | `filename` | display name with `[Auto]`/`[Manual]` prefix |
| `url` | — | url list |
| `description` | — | description list |
| `uploadedAt` | `uploaded_at`, `date`, `lastUpdated` | date list, truncated to `[:10]` |
| `status` | — | status list |

**Classification rule** (line 65):
```python
is_auto = e.get("systemGenerated") is True or e.get("source") is None
```

---

### Field consistency analysis (writer → reader)

| Field | Phase 1 writes | Phase 2 writes | Phase 3 reads | Consistent? |
|---|---|---|---|---|
| `name` | `"System Check: {check_name}"` | `os.path.basename(filename)` | `e.get("name")` | YES |
| `source` | NOT SET (absent) | `"manual"` | `e.get("source")` — `None` → auto | YES (by design) |
| `systemGenerated` | `True` | `False` | `e.get("systemGenerated") is True` | YES |
| `url` | `"#"` | `"/static/evidence/..."` | `e.get("url")` | YES |
| `uploadedAt` | ISO timestamp | ISO timestamp | `e.get("uploadedAt")` | YES |
| `tenantId` | set on doc + evidence sub-doc | set on doc + evidence sub-doc | not read by `_flatten_evidence` | N/A |
| `agent_type` | set | NOT SET | NOT READ | N/A |

**No field name mismatches found** between writers (Phases 1 and 2) and reader (Phase 3 `_flatten_evidence`). The `source`-absent convention for automated evidence is the only subtlety — it is intentional, not a bug.

---

### Phase 3 export golden path (FrameworkDetail.tsx → API)

**Source:** `components/FrameworkDetail.tsx` lines 270–289, `services/apiService.ts` lines 3306–3336

Export is triggered by `handleGenerateReport()` which selects one of three `apiService` calls based on `reportFormat` state:

| Format | apiService method | Endpoint | Body |
|---|---|---|---|
| `csv` | `generateComplianceReport(framework.id)` | `POST /api/compliance/reports/generate` | `FormData { framework_id }` |
| `excel` | `generateExcelComplianceReport(framework.id)` | `POST /api/compliance/reports/generate/excel` | `FormData { framework_id }` |
| `pdf` | `generatePDFComplianceReport(framework.id)` | `POST /api/compliance/reports/generate/pdf` | `FormData { framework_id }` |

**`tenant_id` is NOT in the request body.** It is derived server-side from the JWT (`current_user.tenant_id`) inside the report generation endpoints. The frontend sends only `framework_id`. Integration tests must verify tenant scoping is enforced via the JWT, not a body param.

---

### Phase 4 remediation loop: `report_instruction_result` → WebSocket

**Source:** `backend/agent_tasks_endpoints.py` lines 82–110

After `process_automated_evidence` is called on a heartbeat result containing `compliance_checks`:
1. The function calls `broadcast_remediation_update(tenant_id, payload)` for each matching open remediation task.
2. `tenant_id` is extracted from the agent's verified key dict: `_tenant.get("tenant_id") or _tenant.get("tenantId") or _tenant.get("id", "")`.
3. Socket.IO event emitted: **`remediation_update`** (not `compliance_update`, not `compliance_alert`).
4. Payload shape: `{"task_id": t.get("id", ""), "control_id": ctrl_id, "status": "evidence_updated"}` plus `"timestamp"` added by `broadcast_remediation_update`.

**Source:** `backend/websocket_manager.py` lines 297–321

```python
async def broadcast_remediation_update(tenant_id: str, payload: dict) -> None:
    payload['timestamp'] = payload.get('timestamp', datetime.now(timezone.utc).isoformat())
    for sid in list(connected_clients[tenant_id]):
        await sio.emit('remediation_update', payload, room=sid)
```

The compliance status change itself (new `asset_compliance` status from `process_automated_evidence`) does NOT emit a separate Socket.IO event — only `remediation_update` is broadcast, and only when there is an open remediation task matching the control. Frontend must poll or listen on `remediation_update` for live evidence-loop feedback.

---

## Shared Patterns

### Auth dependency override (all TestClient tests)
**Source:** `backend/tests/test_audit_export.py` lines 89–90, 98
```python
app.dependency_overrides[get_current_user] = lambda: caller
with patch.object(compliance_reports_endpoints, "get_database", return_value=mock_db, create=True):
    client = TestClient(app, raise_server_exceptions=False)
```
Always use `raise_server_exceptions=False` when testing expected 4xx responses so Starlette does not re-raise the HTTPException before the status code is checked.

### Module-level `get_database` patch
**Source:** `backend/tests/test_evidence_uploads.py` lines 79–80
```python
with patch("compliance_evidence_endpoints.get_database", return_value=db):
```
Patch the module-local reference (`module_name.get_database`), not `database.get_database`. Each endpoint module imports `get_database` at import time; patching the origin has no effect after import.

### tenant_context mock (processor tests)
**Source:** `backend/tests/test_rust_heartbeat_parity.py` lines 76–84
```python
ctx = MagicMock()
ctx.get_tenant_id = MagicMock(return_value=None)
ctx.set_tenant_id = MagicMock()
with patch.dict("sys.modules", {"tenant_context": ctx}):
    from compliance_evidence_processor import process_automated_evidence
```
Always mock `tenant_context` as a sys.modules entry before importing `compliance_evidence_processor` in tests. The module does a top-level `from tenant_context import set_tenant_id, get_tenant_id` inside the function body — the `patch.dict` must be active before that import runs.

---

## No Analog Found

None. All new integration test files have direct analogs in the existing test suite.

---

## Metadata

**Analog search scope:** `backend/tests/`, `backend/compliance_evidence_processor.py`, `backend/compliance_evidence_endpoints.py`, `backend/compliance_reporting_data.py`, `backend/agent_tasks_endpoints.py`, `backend/websocket_manager.py`, `components/FrameworkDetail.tsx`, `services/apiService.ts`
**Files scanned:** 12
**Pattern extraction date:** 2026-06-18
