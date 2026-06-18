"""
E2E Integration tests — Wave 0 RED scaffold.

Tests the three integration gaps discovered during Phase 5 research:
  GAP-1: _tenant_filter in compliance_remediation_endpoints calls .get() on TokenData → HTTP 500
  GAP-2: list_compliance_reports uses os.listdir with no tenant filter → info leak
  GAP-3: process_automated_evidence has no fallback_tenant_id → orphaned first-heartbeat evidence

Each gap test is written to FAIL before the corresponding fix is applied (RED).
The golden-path placeholder is marked skip — it is implemented in Wave 1 (05-01).
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
    import importlib, pathlib

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
# Golden-path placeholder — Wave 1 (05-01)
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="implemented in 05-01: full golden-path integration test")
def test_golden_path_placeholder():
    """
    Placeholder for the Wave 1 golden-path integration test.

    Will verify the complete flow:
      Rust agent heartbeat → evidence processing → export → remediation loop
    Skipped in Wave 0 — this test is scaffolded to record intent.
    """
    assert False, "This test must be implemented in Wave 1 (05-01)"
