"""
Unit tests for audit-ready export gaps — AUDIT-03, AUDIT-04.

RED phase: tests for evidence source labelling and cross-tenant download block
will FAIL until compliance_reporting_data.py and compliance_reports_endpoints.py
are patched in Tasks 1 and 2.
"""
import sys
import os
import asyncio
import inspect
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(role="Viewer", tenant_id="tenant-a"):
    from auth_types import TokenData
    return TokenData(username="user@example.com", role=role, tenant_id=tenant_id)


def _make_reports_db(report_tenant_id: str):
    """Build a mock DB whose compliance_reports.find_one returns a doc with the given tenantId."""
    db = MagicMock()
    col = MagicMock()
    col.find_one = AsyncMock(return_value={"filename": "compliance_report_x_1.pdf",
                                           "tenantId": report_tenant_id})
    db.compliance_reports = col
    return db


# ---------------------------------------------------------------------------
# AUDIT-03: Evidence source labelling
# ---------------------------------------------------------------------------

def test_evidence_source_labelling():
    """AUDIT-03: _flatten_evidence prefixes names and returns auto_count/manual_count."""
    from compliance_reporting_data import _flatten_evidence

    evidence_list = [
        {"id": "a1", "name": "Admin Check: X", "systemGenerated": True},
        {"id": "m1", "name": "soc2.pdf", "source": "manual", "systemGenerated": False},
    ]

    result = _flatten_evidence(evidence_list)

    assert result["auto_count"] == 1, f"Expected auto_count=1, got {result.get('auto_count')}"
    assert result["manual_count"] == 1, f"Expected manual_count=1, got {result.get('manual_count')}"
    assert result["count"] == 2, f"Expected count=2, got {result.get('count')}"
    assert "[Auto] Admin Check: X" in result["names"], (
        f"Expected '[Auto] Admin Check: X' in names, got: {result['names']}"
    )
    assert "[Manual] soc2.pdf" in result["names"], (
        f"Expected '[Manual] soc2.pdf' in names, got: {result['names']}"
    )


# ---------------------------------------------------------------------------
# AUDIT-04 (data layer): _build_report_data must accept tenant_id param
# ---------------------------------------------------------------------------

def test_build_report_data_accepts_tenant_id():
    """AUDIT-04/data-layer: _build_report_data signature must include 'tenant_id' parameter."""
    from compliance_reporting_data import _build_report_data

    params = inspect.signature(_build_report_data).parameters
    assert "tenant_id" in params, (
        f"_build_report_data missing 'tenant_id' parameter; found: {list(params.keys())}"
    )


# ---------------------------------------------------------------------------
# AUDIT-04: Legacy download route — cross-tenant access must be blocked
# ---------------------------------------------------------------------------

def test_legacy_download_blocks_cross_tenant():
    """AUDIT-04: Tenant-A user downloading a tenant-B report via legacy route returns HTTP 403."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from authentication_service import get_current_user
    import compliance_reports_endpoints

    # Override auth dependency
    caller = _make_user(role="Viewer", tenant_id="tenant-a")
    # DB reports the file belongs to tenant-b
    mock_db = _make_reports_db("tenant-b")

    app = FastAPI()
    app.include_router(compliance_reports_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: caller

    with patch.object(compliance_reports_endpoints, "get_database", return_value=mock_db, create=True), \
         patch("os.path.exists", return_value=True):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/compliance/reports/download/compliance_report_x_1.pdf")

    assert response.status_code == 403, (
        f"Expected 403 for cross-tenant download, got {response.status_code}"
    )


def test_legacy_download_allows_owner():
    """AUDIT-04: Tenant-A user downloading their own report must NOT return 403."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from authentication_service import get_current_user
    import compliance_reports_endpoints

    caller = _make_user(role="Viewer", tenant_id="tenant-a")
    # DB reports the file belongs to tenant-a (same as caller)
    mock_db = _make_reports_db("tenant-a")

    app = FastAPI()
    app.include_router(compliance_reports_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: caller

    # Serve a real file from a real reports dir (instead of mocking
    # os.path.exists=False, which made the route 404 before ever reaching
    # the tenant-ownership check at line 103 — see IN-02). This exercises
    # the actual DB ownership lookup and lets the request complete with a
    # genuine 200.
    with tempfile.TemporaryDirectory() as tmp_dir:
        real_file = os.path.join(tmp_dir, "compliance_report_x_1.pdf")
        with open(real_file, "wb") as f:
            f.write(b"%PDF-1.4 fake pdf content for test")

        with patch.object(compliance_reports_endpoints, "get_database", return_value=mock_db, create=True), \
             patch.object(compliance_reports_endpoints, "_REPORTS_DIR", tmp_dir):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/compliance/reports/download/compliance_report_x_1.pdf")

    assert response.status_code == 200, f"Owner should receive 200, got {response.status_code}"


# ---------------------------------------------------------------------------
# AUDIT-01: PDF header completeness (Wave 2 — RED until _generate_pdf updated)
# ---------------------------------------------------------------------------

def test_pdf_header_fields():
    """AUDIT-01/03: _generate_pdf must accept tenant_id and resolve tenant name from db.tenants."""
    import inspect
    from compliance_reporting_pdf import _generate_pdf

    sig = inspect.signature(_generate_pdf)
    params = sig.parameters

    assert "tenant_id" in params, (
        f"_generate_pdf missing 'tenant_id' parameter; found: {list(params.keys())}"
    )
    assert params["tenant_id"].default is None, (
        f"'tenant_id' should default to None, got: {params['tenant_id'].default}"
    )


# ---------------------------------------------------------------------------
# AUDIT-02: XLSX header completeness (Wave 2 — RED until _generate_excel updated)
# ---------------------------------------------------------------------------

def test_xlsx_header_fields():
    """AUDIT-02/03: _generate_excel must accept tenant_id and resolve tenant name from db.tenants."""
    import inspect
    from compliance_reporting_excel import _generate_excel, _generate_all_excel

    sig_single = inspect.signature(_generate_excel)
    params_single = sig_single.parameters

    assert "tenant_id" in params_single, (
        f"_generate_excel missing 'tenant_id' parameter; found: {list(params_single.keys())}"
    )
    assert params_single["tenant_id"].default is None, (
        "'tenant_id' in _generate_excel should default to None"
    )

    sig_all = inspect.signature(_generate_all_excel)
    params_all = sig_all.parameters

    assert "tenant_id" in params_all, (
        f"_generate_all_excel missing 'tenant_id' parameter; found: {list(params_all.keys())}"
    )
