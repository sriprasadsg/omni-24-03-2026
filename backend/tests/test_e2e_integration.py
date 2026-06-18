"""
E2E Integration tests — Wave 0 RED scaffold + Wave 1 full suite.

Wave 0 (05-00) tests the three integration gaps:
  GAP-1: _tenant_filter in compliance_remediation_endpoints calls .get() on TokenData → HTTP 500
  GAP-2: list_compliance_reports uses os.listdir with no tenant filter → info leak
  GAP-3: process_automated_evidence has no fallback_tenant_id → orphaned first-heartbeat evidence

Wave 1 (05-01) adds:
  Golden path: heartbeat → evidence written → auto+manual flatten → tenant-scoped remediation task
  Cross-tenant isolation: report download/list, task CRUD, evidence upload all blocked across tenants
  Regression: legacy 3-arg process_automated_evidence still writes evidence after Phase 4 changes
"""
import sys
import os
import inspect
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(role="User", tenant_id="tenant-a"):
    """Build a TokenData matching what get_current_user actually returns."""
    from auth_types import TokenData
    return TokenData(username="user@example.com", role=role, tenant_id=tenant_id)


def _make_reports_db(tenant_id: str, filenames: list | None = None):
    """
    Build a mock DB whose compliance_reports.find().to_list() returns docs
    seeded for *tenant_id* — used in GAP-2 tests.

    The find → to_list chain must mirror conftest._make_col pattern:
      db.compliance_reports.find(filter).to_list(length=None)
    """
    docs = []
    for fn in (filenames or [f"report_{tenant_id}_001.pdf"]):
        docs.append({"filename": fn, "tenantId": tenant_id, "created": "2026-06-01T00:00:00"})

    find_cursor = MagicMock()
    find_cursor.to_list = AsyncMock(return_value=docs)

    col = MagicMock()
    col.find = MagicMock(return_value=find_cursor)

    db = MagicMock()
    db.compliance_reports = col
    return db


def _make_processor_db(tenant_id="tenant-a", agents_tenant_id=None):
    """Build a mock DB suitable for process_automated_evidence calls."""
    db = MagicMock()

    assets_col = MagicMock()
    assets_col.find_one = AsyncMock(
        return_value={"id": f"asset-rust-host-1", "tenantId": tenant_id}
    )
    db.assets = assets_col

    agents_col = MagicMock()
    agents_col.find_one = AsyncMock(
        return_value={"hostname": "rust-host-1", "tenantId": agents_tenant_id or tenant_id}
    )
    db.agents = agents_col

    ac_col = MagicMock()
    ac_col.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    db.asset_compliance = ac_col

    return db


def _make_remediation_db():
    """Build a mock DB for compliance_remediation_service calls."""
    db = MagicMock()

    tasks_col = MagicMock()
    tasks_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))
    tasks_col.find_one = AsyncMock(return_value=None)
    tasks_col.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    tasks_col.find = MagicMock(return_value=cursor)
    db.compliance_remediation_tasks = tasks_col

    assets_col = MagicMock()
    assets_col.find_one = AsyncMock(return_value=None)
    db.assets = assets_col

    return db


# ---------------------------------------------------------------------------
# GAP-1 test: _tenant_filter must accept TokenData (not only dicts)
# ---------------------------------------------------------------------------

def test_remediation_tenant_filter_accepts_token_data():
    """
    GAP-1 (RED): _tenant_filter called with a TokenData user must return
    {"tenantId": "tenant-a"} for a regular user and {} for a Super Admin.

    FAILS before fix because _tenant_filter calls user.get("role") which
    raises AttributeError on a TokenData dataclass.
    """
    import compliance_remediation_endpoints as cre

    # Regular user → should return tenant filter dict
    user = _make_user(role="User", tenant_id="tenant-a")
    result = cre._tenant_filter(user)
    assert result == {"tenantId": "tenant-a"}, (
        f"Expected {{'tenantId': 'tenant-a'}}, got {result}"
    )

    # Super Admin → should return empty dict (no tenant filter)
    admin = _make_user(role="Super Admin", tenant_id="platform-admin")
    admin_result = cre._tenant_filter(admin)
    assert admin_result == {}, (
        f"Expected {{}} for Super Admin, got {admin_result}"
    )


# ---------------------------------------------------------------------------
# GAP-1 test: created_by must use getattr, not .get()
# ---------------------------------------------------------------------------

def test_remediation_created_by_uses_username():
    """
    GAP-1 (RED): compliance_remediation_endpoints must use getattr on current_user
    to extract the username (TokenData has no .get() method and no 'email' field).

    Verifies by inspecting module source — passes only after the .get() calls
    are replaced with getattr() calls.
    """
    import compliance_remediation_endpoints as cre
    import pathlib

    source = pathlib.Path(cre.__file__).read_text()

    # Must NOT contain old dict-style .get("email") or .get("username") on current_user
    assert 'current_user.get("email")' not in source, (
        'compliance_remediation_endpoints still contains current_user.get("email") — '
        "replace with getattr(current_user, 'username', None)"
    )
    # Must contain new getattr pattern
    assert "getattr(current_user" in source, (
        "compliance_remediation_endpoints does not yet use getattr(current_user, ...) — "
        "getattr pattern required for TokenData compatibility"
    )


# ---------------------------------------------------------------------------
# GAP-2 test: list_compliance_reports must query db.compliance_reports
# ---------------------------------------------------------------------------

def test_list_reports_filters_by_tenant():
    """
    GAP-2 (RED): list_compliance_reports must query db.compliance_reports with a
    tenantId filter instead of using os.listdir.

    Verifies that:
      1. db.compliance_reports.find was called (DB path taken, not filesystem).
      2. The caller receives only their own tenant's filenames.

    FAILS before fix because the current implementation uses os.listdir with
    no tenant filter.
    """
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from authentication_service import get_current_user
    import compliance_reports_endpoints

    caller = _make_user(role="User", tenant_id="tenant-a")
    db = _make_reports_db(
        tenant_id="tenant-a",
        filenames=["report_tenant-a_001.pdf"],
    )

    app = FastAPI()
    app.include_router(compliance_reports_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: caller

    with patch.object(
        compliance_reports_endpoints, "get_database", return_value=db, create=True
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/compliance/reports")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )

    data = response.json()
    # Verify DB path was used (find was called on compliance_reports collection)
    db.compliance_reports.find.assert_called_once(), (
        "db.compliance_reports.find was not called — endpoint may still be using os.listdir"
    )

    # Verify only tenant-a filenames are returned
    filenames = [r["filename"] for r in data]
    assert all("tenant-a" in fn for fn in filenames), (
        f"Expected only tenant-a reports, got: {filenames}"
    )


# ---------------------------------------------------------------------------
# GAP-3 test: process_automated_evidence must have fallback_tenant_id param
# ---------------------------------------------------------------------------

def test_process_evidence_has_fallback_tenant_param():
    """
    GAP-3 (RED): process_automated_evidence signature must include a
    'fallback_tenant_id' parameter with a default of None.

    FAILS before fix because the current signature does not include
    fallback_tenant_id.
    """
    from compliance_evidence_processor import process_automated_evidence

    sig = inspect.signature(process_automated_evidence)
    params = sig.parameters

    assert "fallback_tenant_id" in params, (
        f"process_automated_evidence missing 'fallback_tenant_id' parameter. "
        f"Current params: {list(params.keys())}"
    )
    assert params["fallback_tenant_id"].default is None, (
        f"'fallback_tenant_id' should default to None, "
        f"got: {params['fallback_tenant_id'].default}"
    )


# ---------------------------------------------------------------------------
# Task 1: Golden-path integration test (Wave 1 — 05-01)
# Replaces the SKIPPED test_golden_path_placeholder from Wave 0.
# ---------------------------------------------------------------------------

def test_golden_path_evidence_to_remediation():
    """
    INT-01, INT-03, INT-05: Full golden-path integration test.

    Verifies data-contract seams across all four phases within tenant-a:
      1. process_automated_evidence writes an asset_compliance record with
         agent_type="rust" and systemGenerated=True evidence
      2. An auto + manual evidence pair is accepted by _flatten_evidence
         returning auto_count=1, manual_count=1 with [Auto]/[Manual] name prefixes
      3. _tenant_filter with TokenData(role="user", tenant_id="tenant-a") returns
         {"tenantId": "tenant-a"}
      4. compliance_remediation_service.create_task called with the correct
         tenant_filter and created_by from TokenData.username
    """
    # ------------------------------------------------------------------
    # Leg 1: process_automated_evidence writes evidence with agent_type
    # ------------------------------------------------------------------
    db = _make_processor_db(tenant_id="tenant-a")

    compliance_data = {
        "compliance_checks": [
            {
                "check": "Windows Defender Antivirus",
                "status": "Pass",
                "details": "Defender running",
                "evidence_content": '{"state": "enabled"}',
            }
        ]
    }

    ctx = MagicMock()
    ctx.get_tenant_id = MagicMock(return_value=None)
    ctx.set_tenant_id = MagicMock()

    with patch.dict("sys.modules", {"tenant_context": ctx}):
        from compliance_evidence_processor import process_automated_evidence
        asyncio.run(
            process_automated_evidence(
                "rust-host-1",
                compliance_data,
                db,
                agent_type="rust",
                fallback_tenant_id="tenant-a",
            )
        )

    # Verify update_one was called and agent_type="rust" is in the $set
    assert db.asset_compliance.update_one.call_count >= 1, (
        "asset_compliance.update_one was not called — evidence was not written"
    )
    agent_type_found = False
    evidence_pushed = False
    for call in db.asset_compliance.update_one.call_args_list:
        args, kwargs = call
        if len(args) >= 2 and isinstance(args[1], dict):
            update_doc = args[1]
            if "$set" in update_doc and update_doc["$set"].get("agent_type") == "rust":
                agent_type_found = True
            if "$push" in update_doc:
                pushed_ev = update_doc["$push"].get("evidence", {})
                if pushed_ev.get("systemGenerated") is True:
                    evidence_pushed = True

    assert agent_type_found, "agent_type='rust' not found in any $set call"
    assert evidence_pushed, "No systemGenerated=True evidence record was pushed"

    # ------------------------------------------------------------------
    # Leg 2: _flatten_evidence correctly classifies auto + manual evidence
    # ------------------------------------------------------------------
    from compliance_reporting_data import _flatten_evidence

    auto_ev = {
        "id": "auto-ev-rust-host-1-CC6.8-windows-defender-antivirus-ts",
        "name": "System Check: Windows Defender Antivirus",
        "systemGenerated": True,
        "url": "#",
    }
    manual_ev = {
        "id": "ev-manual-abc123",
        "name": "audit_evidence.pdf",
        "source": "manual",
        "systemGenerated": False,
        "url": "/static/evidence/audit_evidence.pdf",
    }

    result = _flatten_evidence([auto_ev, manual_ev])

    assert result["auto_count"] == 1, f"Expected auto_count=1, got {result.get('auto_count')}"
    assert result["manual_count"] == 1, f"Expected manual_count=1, got {result.get('manual_count')}"
    assert result["count"] == 2, f"Expected count=2, got {result.get('count')}"
    assert "[Auto] System Check: Windows Defender Antivirus" in result["names"], (
        f"Expected '[Auto]' prefixed name in names; got: {result['names']}"
    )
    assert "[Manual] audit_evidence.pdf" in result["names"], (
        f"Expected '[Manual]' prefixed name in names; got: {result['names']}"
    )

    # ------------------------------------------------------------------
    # Leg 3: _tenant_filter returns correct dict for TokenData
    # ------------------------------------------------------------------
    import compliance_remediation_endpoints as cre

    user = _make_user(role="User", tenant_id="tenant-a")
    tf = cre._tenant_filter(user)
    assert tf == {"tenantId": "tenant-a"}, (
        f"_tenant_filter returned {tf!r} instead of {{'tenantId': 'tenant-a'}}"
    )

    # ------------------------------------------------------------------
    # Leg 4: create_task receives correct tenant_filter and created_by
    # ------------------------------------------------------------------
    import compliance_remediation_service as svc

    rem_db = _make_remediation_db()
    captured = {}

    async def _fake_create_task(db, data, tenant_filter, created_by):
        captured["tenant_filter"] = tenant_filter
        captured["created_by"] = created_by
        return {"id": "task-123", "status": "open", "tenantId": tenant_filter.get("tenantId")}

    with patch.object(svc, "create_task", side_effect=_fake_create_task):
        with patch.object(cre, "get_database", return_value=rem_db, create=True):
            task_data = {
                "title": "Fix Windows Defender",
                "control_id": "CC6.8",
                "asset_id": "asset-rust-host-1",
                "framework_id": "soc2",
                "priority": "high",
                "due_date": None,
                "description": "Enable and update Windows Defender",
                "assignee": "",
            }
            from compliance_remediation_endpoints import TaskCreate
            body = TaskCreate(**task_data)

            async def _run_create():
                return await cre.create_task(body=body, current_user=user)

            asyncio.run(_run_create())

    assert captured.get("tenant_filter") == {"tenantId": "tenant-a"}, (
        f"create_task called with wrong tenant_filter: {captured.get('tenant_filter')!r}"
    )
    assert captured.get("created_by") == "user@example.com", (
        f"create_task called with wrong created_by: {captured.get('created_by')!r}"
    )


# ---------------------------------------------------------------------------
# Task 2: Cross-tenant isolation tests (Wave 1 — 05-01)
# ---------------------------------------------------------------------------

def test_cross_tenant_report_download_blocked():
    """
    INT-07, INT-15: Tenant-A user downloading a tenant-B report returns HTTP 403.
    Mirrors test_audit_export.py::test_legacy_download_blocks_cross_tenant.
    """
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from authentication_service import get_current_user
    import compliance_reports_endpoints

    caller = _make_user(role="Viewer", tenant_id="tenant-a")

    # DB says the report belongs to tenant-b
    db = MagicMock()
    col = MagicMock()
    col.find_one = AsyncMock(
        return_value={"filename": "compliance_report_tb_001.pdf", "tenantId": "tenant-b"}
    )
    db.compliance_reports = col

    app = FastAPI()
    app.include_router(compliance_reports_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: caller

    with patch.object(
        compliance_reports_endpoints, "get_database", return_value=db, create=True
    ), patch("os.path.exists", return_value=True):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/compliance/reports/download/compliance_report_tb_001.pdf")

    assert response.status_code == 403, (
        f"Expected 403 for cross-tenant download, got {response.status_code}"
    )


def test_cross_tenant_report_download_owner_allowed():
    """
    INT-15: Tenant-A user downloading their own report must NOT return 403.
    """
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from authentication_service import get_current_user
    import compliance_reports_endpoints

    caller = _make_user(role="Viewer", tenant_id="tenant-a")

    # DB says the report belongs to tenant-a (same as caller)
    db = MagicMock()
    col = MagicMock()
    col.find_one = AsyncMock(
        return_value={"filename": "compliance_report_ta_001.pdf", "tenantId": "tenant-a"}
    )
    db.compliance_reports = col

    app = FastAPI()
    app.include_router(compliance_reports_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: caller

    with patch.object(
        compliance_reports_endpoints, "get_database", return_value=db, create=True
    ), patch("os.path.exists", return_value=False):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/compliance/reports/download/compliance_report_ta_001.pdf")

    assert response.status_code != 403, (
        f"Owner should not receive 403, got {response.status_code}"
    )


def test_cross_tenant_report_list_shows_own_only():
    """
    INT-15, GAP-2: GET /api/compliance/reports with tenant-a caller returns
    only tenant-a reports (relies on Wave 0 GAP-2 fix).

    The endpoint calls db.compliance_reports.find({tenantId: "tenant-a"}).to_list(),
    so we mock that to return mixed docs but the call asserts the query is scoped.
    """
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from authentication_service import get_current_user
    import compliance_reports_endpoints

    caller = _make_user(role="User", tenant_id="tenant-a")

    # Only tenant-a docs returned (endpoint passes {tenantId: tenant-a} to find)
    db = _make_reports_db(
        tenant_id="tenant-a",
        filenames=["report_tenant-a_001.pdf", "report_tenant-a_002.pdf"],
    )

    app = FastAPI()
    app.include_router(compliance_reports_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: caller

    with patch.object(
        compliance_reports_endpoints, "get_database", return_value=db, create=True
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/compliance/reports")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    data = response.json()
    filenames = [r["filename"] for r in data]
    assert all("tenant-a" in fn for fn in filenames), (
        f"Expected only tenant-a reports; got: {filenames}"
    )
    # Confirm find() was called with a tenant filter (not empty)
    db.compliance_reports.find.assert_called()
    call_args = db.compliance_reports.find.call_args
    query = call_args[0][0] if call_args[0] else call_args[1].get("filter", {})
    assert query.get("tenantId") == "tenant-a", (
        f"Expected find called with tenantId='tenant-a', got: {query}"
    )


def test_cross_tenant_task_list_blocked():
    """
    INT-14: list_tasks for a tenant-a user passes tenant_filter={"tenantId":"tenant-a"}
    into svc.list_tasks so tenant-b tasks are never queried.
    Super-admin TokenData → tenant_filter={} (sees all).
    """
    import compliance_remediation_service as svc
    import compliance_remediation_endpoints as cre

    captured_filters = []

    async def _fake_list_tasks(db, tenant_filter, status=None, control_id=None):
        captured_filters.append(tenant_filter)
        return []

    rem_db = _make_remediation_db()

    # --- Tenant user: filter must include tenantId ---
    user = _make_user(role="User", tenant_id="tenant-a")

    with patch.object(svc, "list_tasks", side_effect=_fake_list_tasks):
        with patch.object(cre, "get_database", return_value=rem_db, create=True):
            async def _run_list_user():
                return await cre.list_tasks(current_user=user)
            asyncio.run(_run_list_user())

    assert len(captured_filters) == 1, "list_tasks not called"
    assert captured_filters[0] == {"tenantId": "tenant-a"}, (
        f"Tenant user: expected filter {{'tenantId':'tenant-a'}}, got {captured_filters[0]!r}"
    )

    # --- Super admin: filter must be empty ---
    captured_filters.clear()
    admin = _make_user(role="Super Admin", tenant_id="platform-admin")

    with patch.object(svc, "list_tasks", side_effect=_fake_list_tasks):
        with patch.object(cre, "get_database", return_value=rem_db, create=True):
            async def _run_list_admin():
                return await cre.list_tasks(current_user=admin)
            asyncio.run(_run_list_admin())

    assert len(captured_filters) == 1, "list_tasks not called for admin"
    assert captured_filters[0] == {}, (
        f"Super admin: expected empty filter, got {captured_filters[0]!r}"
    )


def test_cross_tenant_evidence_upload_blocked():
    """
    INT-13: upload_compliance_evidence called for an asset belonging to tenant-b
    with a tenant-a caller raises HTTPException 403 (asset ownership check).
    Uses the direct-async-call pattern from test_evidence_uploads.py.
    """
    from fastapi import Request, Response
    from fastapi.exceptions import HTTPException
    from compliance_evidence_endpoints import upload_compliance_evidence

    # Caller is tenant-a
    caller = _make_user(role="Viewer", tenant_id="tenant-a")

    # DB says asset belongs to tenant-b (find_one returns None for tenant-a query)
    db = MagicMock()
    assets_col = MagicMock()
    assets_col.find_one = AsyncMock(return_value=None)  # no asset found for tenant-a
    db.assets = assets_col
    ac_col = MagicMock()
    ac_col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    db.asset_compliance = ac_col

    uf = MagicMock()
    uf.filename = "evidence.pdf"
    uf.content_type = "application/pdf"
    uf.read = AsyncMock(return_value=b"%PDF-1.4 content")

    req = MagicMock(spec=Request)
    req.headers = {}
    resp = MagicMock(spec=Response)

    async def _run():
        with patch("compliance_evidence_endpoints.get_database", return_value=db):
            return await upload_compliance_evidence(
                request=req,
                response=resp,
                asset_id="asset-tenant-b-001",
                file=uf,
                control_id="CC6.1",
                description="",
                current_user=caller,
            )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 403, (
        f"Expected 403 for cross-tenant upload, got {exc_info.value.status_code}"
    )


# ---------------------------------------------------------------------------
# Task 3: Regression tests (Wave 1 — 05-01)
# ---------------------------------------------------------------------------

def test_process_automated_evidence_3arg_backward_compat():
    """
    INT-08 regression: process_automated_evidence(hostname, compliance_data, db)
    called with only 3 positional args (no agent_type, no fallback_tenant_id)
    still writes asset_compliance evidence records.

    Guards against regression from Phase 4's agent_tasks_endpoints.py modification.
    """
    # DB returns None for asset/agent lookup (first-heartbeat scenario)
    db = MagicMock()
    db.assets.find_one = AsyncMock(return_value=None)
    db.agents = MagicMock()
    db.agents.find_one = AsyncMock(return_value=None)
    db.asset_compliance.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1, modified_count=1)
    )

    compliance_data = {
        "compliance_checks": [
            {
                "check": "Windows Defender Antivirus",
                "status": "Pass",
                "details": "Defender running",
            }
        ]
    }

    ctx = MagicMock()
    ctx.get_tenant_id = MagicMock(return_value=None)
    ctx.set_tenant_id = MagicMock()

    with patch.dict("sys.modules", {"tenant_context": ctx}):
        from compliance_evidence_processor import process_automated_evidence
        # Call with only 3 positional args — legacy Python agent path
        asyncio.run(process_automated_evidence("legacy-host", compliance_data, db))

    # update_one must have been called (evidence records written)
    # When tenant_id is None (no asset/agent found and no fallback), the processor
    # still iterates through checks and fires update_one calls.
    assert db.asset_compliance.update_one.call_count >= 1, (
        "asset_compliance.update_one was not called — legacy 3-arg path is broken"
    )


def test_report_instruction_result_still_calls_process_evidence():
    """
    INT-08 regression: agent_tasks_endpoints.report_instruction_result still
    imports and calls process_automated_evidence when result contains
    compliance_checks.

    Also asserts signature back-compat: agent_type and fallback_tenant_id both
    default to None so the existing 3-positional-arg call site remains valid.
    """
    # Assert signature back-compat via inspect
    from compliance_evidence_processor import process_automated_evidence
    sig = inspect.signature(process_automated_evidence)
    params = sig.parameters

    assert "agent_type" in params, (
        "process_automated_evidence is missing 'agent_type' parameter"
    )
    assert params["agent_type"].default is None, (
        f"'agent_type' should default to None, got: {params['agent_type'].default}"
    )
    assert "fallback_tenant_id" in params, (
        "process_automated_evidence is missing 'fallback_tenant_id' parameter"
    )
    assert params["fallback_tenant_id"].default is None, (
        f"'fallback_tenant_id' should default to None, got: {params['fallback_tenant_id'].default}"
    )

    # Verify agent_tasks_endpoints calls process_automated_evidence when
    # compliance_checks is present in the instruction result
    from agent_tasks_endpoints import report_instruction_result
    from agent_auth import verify_agent_key

    db = MagicMock()
    db.agent_instructions.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1)
    )
    db.compliance_remediation_tasks.find = MagicMock(
        return_value=MagicMock(to_list=AsyncMock(return_value=[]))
    )

    _tenant = {"tenant_id": "tenant-a", "tenantId": "tenant-a"}

    result_payload = {
        "task_id": "task-001",
        "status": "success",
        "compliance_checks": [
            {"check": "Windows Defender Antivirus", "status": "Pass", "details": "ok"}
        ],
    }

    evidence_call_count = []

    async def _fake_process_evidence(hostname, data, db, *args, **kwargs):
        evidence_call_count.append(1)

    with patch(
        "compliance_endpoints.process_automated_evidence",
        side_effect=_fake_process_evidence,
    ), patch("agent_tasks_endpoints.get_database", return_value=db, create=True):
        asyncio.run(
            report_instruction_result(
                hostname="agent-host",
                result=result_payload,
                _tenant=_tenant,
            )
        )

    # process_automated_evidence should have been called once
    assert len(evidence_call_count) == 1, (
        f"Expected process_automated_evidence called once, got {len(evidence_call_count)} calls. "
        "Phase 4 may have broken the evidence call path."
    )
