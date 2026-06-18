"""
E2E Integration tests — Wave 0 RED scaffold + Wave 1 full suite.

Wave 0 (05-00): GAP-1 (_tenant_filter on TokenData), GAP-2 (list_reports tenant filter),
  GAP-3 (fallback_tenant_id on process_automated_evidence).
Wave 1 (05-01): golden-path, cross-tenant isolation, regression tests.
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
    from auth_types import TokenData
    return TokenData(username="user@example.com", role=role, tenant_id=tenant_id)


def _make_reports_db(tenant_id: str, filenames: list | None = None):
    docs = [{"filename": fn, "tenantId": tenant_id, "created": "2026-06-01T00:00:00"}
            for fn in (filenames or [f"report_{tenant_id}_001.pdf"])]
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    col = MagicMock()
    col.find = MagicMock(return_value=cursor)
    db = MagicMock()
    db.compliance_reports = col
    return db


def _make_processor_db(tenant_id="tenant-a"):
    db = MagicMock()
    db.assets = MagicMock()
    db.assets.find_one = AsyncMock(return_value={"id": "asset-rust-host-1", "tenantId": tenant_id})
    db.agents = MagicMock()
    db.agents.find_one = AsyncMock(return_value={"hostname": "rust-host-1", "tenantId": tenant_id})
    db.asset_compliance = MagicMock()
    db.asset_compliance.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return db


def _make_remediation_db():
    db = MagicMock()
    tasks_col = MagicMock()
    tasks_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))
    tasks_col.find_one = AsyncMock(return_value=None)
    tasks_col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    tasks_col.find = MagicMock(return_value=cursor)
    db.compliance_remediation_tasks = tasks_col
    db.assets = MagicMock()
    db.assets.find_one = AsyncMock(return_value=None)
    return db


def _ctx_mock():
    ctx = MagicMock()
    ctx.get_tenant_id = MagicMock(return_value=None)
    ctx.set_tenant_id = MagicMock()
    return ctx


# ---------------------------------------------------------------------------
# GAP-1: _tenant_filter must accept TokenData
# ---------------------------------------------------------------------------

def test_remediation_tenant_filter_accepts_token_data():
    """GAP-1: _tenant_filter with TokenData returns {tenantId} or {} (not AttributeError)."""
    import compliance_remediation_endpoints as cre
    user = _make_user(role="User", tenant_id="tenant-a")
    assert cre._tenant_filter(user) == {"tenantId": "tenant-a"}
    admin = _make_user(role="Super Admin", tenant_id="platform-admin")
    assert cre._tenant_filter(admin) == {}


def test_remediation_created_by_uses_username():
    """GAP-1: compliance_remediation_endpoints uses getattr, not .get(), on current_user."""
    import compliance_remediation_endpoints as cre
    import pathlib
    source = pathlib.Path(cre.__file__).read_text()
    assert 'current_user.get("email")' not in source
    assert "getattr(current_user" in source


# ---------------------------------------------------------------------------
# GAP-2: list_compliance_reports queries db.compliance_reports
# ---------------------------------------------------------------------------

def test_list_reports_filters_by_tenant():
    """GAP-2: list_compliance_reports uses db query (not os.listdir) with tenantId filter."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from authentication_service import get_current_user
    import compliance_reports_endpoints

    caller = _make_user(role="User", tenant_id="tenant-a")
    db = _make_reports_db("tenant-a", filenames=["report_tenant-a_001.pdf"])
    app = FastAPI()
    app.include_router(compliance_reports_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: caller

    with patch.object(compliance_reports_endpoints, "get_database", return_value=db, create=True):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/compliance/reports")

    assert response.status_code == 200
    db.compliance_reports.find.assert_called_once()
    filenames = [r["filename"] for r in response.json()]
    assert all("tenant-a" in fn for fn in filenames)


# ---------------------------------------------------------------------------
# GAP-3: process_automated_evidence has fallback_tenant_id param
# ---------------------------------------------------------------------------

def test_process_evidence_has_fallback_tenant_param():
    """GAP-3: process_automated_evidence has fallback_tenant_id=None parameter."""
    from compliance_evidence_processor import process_automated_evidence
    params = inspect.signature(process_automated_evidence).parameters
    assert "fallback_tenant_id" in params
    assert params["fallback_tenant_id"].default is None


# ---------------------------------------------------------------------------
# Task 1: Golden-path integration test (Wave 1 — 05-01)
# ---------------------------------------------------------------------------

def test_golden_path_evidence_to_remediation():
    """
    INT-01, INT-03, INT-05: Full golden-path within tenant-a.
    Leg 1: process_automated_evidence writes agent_type='rust' + systemGenerated=True evidence.
    Leg 2: _flatten_evidence returns auto_count=1, manual_count=1, [Auto]/[Manual] prefixes.
    Leg 3: _tenant_filter(TokenData) returns {"tenantId": "tenant-a"}.
    Leg 4: create_task called with tenant_filter={"tenantId":"tenant-a"}, created_by from username.
    """
    # Leg 1 — processor writes evidence
    db = _make_processor_db()
    compliance_data = {"compliance_checks": [{
        "check": "Windows Defender Antivirus",
        "status": "Pass",
        "details": "running",
        "evidence_content": '{"state": "enabled"}',
    }]}
    with patch.dict("sys.modules", {"tenant_context": _ctx_mock()}):
        from compliance_evidence_processor import process_automated_evidence
        asyncio.run(process_automated_evidence(
            "rust-host-1", compliance_data, db, agent_type="rust", fallback_tenant_id="tenant-a"
        ))

    assert db.asset_compliance.update_one.call_count >= 1, "update_one not called"
    agent_type_found = evidence_pushed = False
    for call in db.asset_compliance.update_one.call_args_list:
        args, _ = call
        if len(args) >= 2 and isinstance(args[1], dict):
            if "$set" in args[1] and args[1]["$set"].get("agent_type") == "rust":
                agent_type_found = True
            if "$push" in args[1] and args[1]["$push"].get("evidence", {}).get("systemGenerated"):
                evidence_pushed = True
    assert agent_type_found, "agent_type='rust' not in $set"
    assert evidence_pushed, "no systemGenerated=True evidence pushed"

    # Leg 2 — flatten auto + manual
    from compliance_reporting_data import _flatten_evidence
    result = _flatten_evidence([
        {"id": "a1", "name": "System Check: Windows Defender Antivirus", "systemGenerated": True, "url": "#"},
        {"id": "m1", "name": "audit_evidence.pdf", "source": "manual", "systemGenerated": False, "url": "/static/ev/x.pdf"},
    ])
    assert result["auto_count"] == 1
    assert result["manual_count"] == 1
    assert result["count"] == 2
    assert "[Auto] System Check: Windows Defender Antivirus" in result["names"]
    assert "[Manual] audit_evidence.pdf" in result["names"]

    # Leg 3 — _tenant_filter on TokenData
    import compliance_remediation_endpoints as cre
    user = _make_user(role="User", tenant_id="tenant-a")
    assert cre._tenant_filter(user) == {"tenantId": "tenant-a"}

    # Leg 4 — create_task receives correct tenant_filter + created_by
    import compliance_remediation_service as svc
    captured = {}

    async def _fake_create(db, data, tenant_filter, created_by):
        captured.update({"tenant_filter": tenant_filter, "created_by": created_by})
        return {"id": "t1", "status": "open", "tenantId": tenant_filter.get("tenantId")}

    rem_db = _make_remediation_db()
    from compliance_remediation_endpoints import TaskCreate
    body = TaskCreate(title="Fix Defender", control_id="CC6.8", asset_id="asset-1",
                      framework_id="soc2", priority="high", description="enable defender")
    with patch.object(svc, "create_task", side_effect=_fake_create):
        with patch.object(cre, "get_database", return_value=rem_db, create=True):
            asyncio.run(cre.create_task(body=body, current_user=user))

    assert captured.get("tenant_filter") == {"tenantId": "tenant-a"}
    assert captured.get("created_by") == "user@example.com"


# ---------------------------------------------------------------------------
# Task 2: Cross-tenant isolation tests (Wave 1 — 05-01)
# ---------------------------------------------------------------------------

def test_cross_tenant_report_download_blocked():
    """INT-07, INT-15: tenant-a caller downloading a tenant-b report → 403."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from authentication_service import get_current_user
    import compliance_reports_endpoints

    caller = _make_user(role="Viewer", tenant_id="tenant-a")
    db = MagicMock()
    db.compliance_reports = MagicMock()
    db.compliance_reports.find_one = AsyncMock(
        return_value={"filename": "rpt_tb.pdf", "tenantId": "tenant-b"})

    app = FastAPI()
    app.include_router(compliance_reports_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: caller

    with patch.object(compliance_reports_endpoints, "get_database", return_value=db, create=True), \
         patch("os.path.exists", return_value=True):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/compliance/reports/download/rpt_tb.pdf")

    assert response.status_code == 403


def test_cross_tenant_report_download_owner_allowed():
    """INT-15: tenant-a caller downloading their own report must NOT be 403."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from authentication_service import get_current_user
    import compliance_reports_endpoints

    caller = _make_user(role="Viewer", tenant_id="tenant-a")
    db = MagicMock()
    db.compliance_reports = MagicMock()
    db.compliance_reports.find_one = AsyncMock(
        return_value={"filename": "rpt_ta.pdf", "tenantId": "tenant-a"})

    app = FastAPI()
    app.include_router(compliance_reports_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: caller

    with patch.object(compliance_reports_endpoints, "get_database", return_value=db, create=True), \
         patch("os.path.exists", return_value=False):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/compliance/reports/download/rpt_ta.pdf")

    assert response.status_code != 403


def test_cross_tenant_report_list_shows_own_only():
    """INT-15, GAP-2: GET /api/compliance/reports scoped to tenant-a (relies on GAP-2 fix)."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from authentication_service import get_current_user
    import compliance_reports_endpoints

    caller = _make_user(role="User", tenant_id="tenant-a")
    db = _make_reports_db("tenant-a", filenames=["report_tenant-a_001.pdf", "report_tenant-a_002.pdf"])
    app = FastAPI()
    app.include_router(compliance_reports_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: caller

    with patch.object(compliance_reports_endpoints, "get_database", return_value=db, create=True):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/compliance/reports")

    assert response.status_code == 200
    filenames = [r["filename"] for r in response.json()]
    assert all("tenant-a" in fn for fn in filenames)
    call_args = db.compliance_reports.find.call_args
    query = (call_args[0][0] if call_args[0] else None) or call_args[1].get("filter", {})
    assert query.get("tenantId") == "tenant-a"


def test_cross_tenant_task_list_blocked():
    """INT-14: list_tasks passes {tenantId: tenant-a} for regular user; {} for super-admin."""
    import compliance_remediation_service as svc
    import compliance_remediation_endpoints as cre

    filters_seen = []

    async def _fake_list(db, tenant_filter, status=None, control_id=None):
        filters_seen.append(tenant_filter)
        return []

    rem_db = _make_remediation_db()
    user = _make_user(role="User", tenant_id="tenant-a")
    with patch.object(svc, "list_tasks", side_effect=_fake_list):
        with patch.object(cre, "get_database", return_value=rem_db, create=True):
            asyncio.run(cre.list_tasks(current_user=user))
    assert filters_seen == [{"tenantId": "tenant-a"}]

    filters_seen.clear()
    admin = _make_user(role="Super Admin", tenant_id="platform-admin")
    with patch.object(svc, "list_tasks", side_effect=_fake_list):
        with patch.object(cre, "get_database", return_value=rem_db, create=True):
            asyncio.run(cre.list_tasks(current_user=admin))
    assert filters_seen == [{}]


def test_cross_tenant_evidence_upload_blocked():
    """INT-13: upload to tenant-b asset by tenant-a caller → 403 (asset not found in tenant)."""
    from fastapi import Request, Response
    from fastapi.exceptions import HTTPException
    from compliance_evidence_endpoints import upload_compliance_evidence

    caller = _make_user(role="Viewer", tenant_id="tenant-a")
    db = MagicMock()
    db.assets = MagicMock()
    db.assets.find_one = AsyncMock(return_value=None)  # not found in tenant-a
    db.asset_compliance = MagicMock()
    db.asset_compliance.update_one = AsyncMock(return_value=MagicMock(matched_count=1))

    uf = MagicMock()
    uf.filename = "evidence.pdf"
    uf.content_type = "application/pdf"
    uf.read = AsyncMock(return_value=b"%PDF-1.4 content")

    req = MagicMock(spec=Request)
    req.headers = {}

    async def _run():
        with patch("compliance_evidence_endpoints.get_database", return_value=db):
            return await upload_compliance_evidence(
                request=req, response=MagicMock(spec=Response),
                asset_id="asset-tenant-b-001", file=uf,
                control_id="CC6.1", description="", current_user=caller,
            )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Task 3: Regression tests (Wave 1 — 05-01)
# ---------------------------------------------------------------------------

def test_process_automated_evidence_3arg_backward_compat():
    """INT-08 regression: 3-arg call (no agent_type, no fallback_tenant_id) still writes evidence."""
    db = MagicMock()
    db.assets = MagicMock()
    db.assets.find_one = AsyncMock(return_value=None)
    db.agents = MagicMock()
    db.agents.find_one = AsyncMock(return_value=None)
    db.asset_compliance = MagicMock()
    db.asset_compliance.update_one = AsyncMock(return_value=MagicMock(matched_count=1))

    compliance_data = {"compliance_checks": [{
        "check": "Windows Defender Antivirus", "status": "Pass", "details": "ok"
    }]}
    with patch.dict("sys.modules", {"tenant_context": _ctx_mock()}):
        from compliance_evidence_processor import process_automated_evidence
        asyncio.run(process_automated_evidence("legacy-host", compliance_data, db))

    assert db.asset_compliance.update_one.call_count >= 1, "3-arg call did not write evidence"


def test_report_instruction_result_still_calls_process_evidence():
    """
    INT-08 regression: agent_tasks_endpoints.report_instruction_result calls
    process_automated_evidence when compliance_checks present. Also asserts
    signature back-compat: agent_type and fallback_tenant_id default to None.
    """
    from compliance_evidence_processor import process_automated_evidence
    params = inspect.signature(process_automated_evidence).parameters
    assert params.get("agent_type") is not None and params["agent_type"].default is None
    assert params.get("fallback_tenant_id") is not None and params["fallback_tenant_id"].default is None

    from agent_tasks_endpoints import report_instruction_result

    db = MagicMock()
    db.agent_instructions = MagicMock()
    db.agent_instructions.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    db.compliance_remediation_tasks = MagicMock()
    db.compliance_remediation_tasks.find = MagicMock(
        return_value=MagicMock(to_list=AsyncMock(return_value=[]))
    )

    call_count = []

    async def _fake_process(hostname, data, db, *args, **kwargs):
        call_count.append(1)

    with patch("compliance_endpoints.process_automated_evidence", side_effect=_fake_process), \
         patch("agent_tasks_endpoints.get_database", return_value=db, create=True):
        asyncio.run(report_instruction_result(
            hostname="agent-host",
            result={"task_id": "t1", "status": "success", "compliance_checks": [
                {"check": "Windows Defender Antivirus", "status": "Pass"}
            ]},
            _tenant={"tenant_id": "tenant-a"},
        ))

    assert len(call_count) == 1, f"Expected process_automated_evidence called once, got {len(call_count)}"
