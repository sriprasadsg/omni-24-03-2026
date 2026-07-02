"""
Unit tests for PATCH /api/assets/{asset_id}/compliance/status — STATUS-01, STATUS-02.

Covers:
  - Happy path: 200, persists status, captures previous_status
  - Cross-tenant 403: non-admin caller with asset not in their tenant
  - Invalid status 422: Pydantic rejects values outside the Literal enum
  - Insufficient permissions 403: read-only role cannot override status (CR-04)

Uses asyncio.run() — pytest-asyncio is not installed in this project.
"""
import sys
import os
import asyncio
import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username="analyst@tenant.com", role="Viewer", tenant_id="tenant-a"):
    from auth_types import TokenData
    return TokenData(username=username, role=role, tenant_id=tenant_id)


def _make_db(asset_doc="default", compliance_doc=None):
    """Build a mock async DB for compliance_status_endpoints tests."""
    db = MagicMock()

    # assets collection
    assets_col = MagicMock()
    assets_col.find_one = AsyncMock(
        return_value={"id": "a1", "tenantId": "tenant-a"} if asset_doc == "default" else asset_doc
    )
    db.assets = assets_col

    # asset_compliance collection
    ac_col = MagicMock()
    ac_col.find_one = AsyncMock(return_value=compliance_doc)
    # find_one_and_update returns the pre-update doc (return_document=BEFORE
    # default), mirroring the atomic previous_status capture (WR-03).
    ac_col.find_one_and_update = AsyncMock(return_value=compliance_doc)
    ac_col.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    db.asset_compliance = ac_col

    return db


# ---------------------------------------------------------------------------
# Test 1 — Happy path (STATUS-01 + STATUS-02)
# ---------------------------------------------------------------------------

def test_patch_compliance_status_success():
    """STATUS-01/02: 200 response, previous_status captured from existing doc."""
    from compliance_status_endpoints import patch_asset_compliance_status, ComplianceStatusUpdate
    from fastapi.exceptions import HTTPException

    # role must be in _WRITE_ROLES (CR-04) — "Viewer" is a read-only role
    user = _make_user(role="admin")
    # Existing compliance doc has status "Non-Compliant" — should be captured as previous_status
    db = _make_db(
        asset_doc={"id": "a1", "tenantId": "tenant-a"},
        compliance_doc={"status": "Non-Compliant"},
    )
    body = ComplianceStatusUpdate(control_id="c1", status="Compliant", notes="Remediation verified")

    async def _run():
        with patch("compliance_status_endpoints.get_database", return_value=db):
            return await patch_asset_compliance_status("a1", body, current_user=user)

    result = asyncio.run(_run())

    assert result["ok"] is True
    assert result["status"] == "Compliant"
    assert result["previous_status"] == "Non-Compliant"

    # Verify find_one_and_update (atomic status write) was called with $set
    faou_call_args = db.asset_compliance.find_one_and_update.call_args
    set_doc = faou_call_args[0][1]
    assert "status" in set_doc["$set"]
    assert set_doc["$set"]["manual_override"] is True
    assert set_doc["$set"]["overriddenBy"] == "analyst@tenant.com"

    # Verify update_one (history append) was called with $push
    call_args = db.asset_compliance.update_one.call_args
    update_doc = call_args[0][1]
    assert "status_history" in update_doc["$push"]
    history_entry = update_doc["$push"]["status_history"]
    assert history_entry["previous_status"] == "Non-Compliant"
    assert history_entry["changedBy"] == "analyst@tenant.com"


# ---------------------------------------------------------------------------
# Test 2 — Cross-tenant 403
# ---------------------------------------------------------------------------

def test_patch_compliance_status_cross_tenant_403():
    """Non-admin caller whose tenant does not own the asset receives 403."""
    from compliance_status_endpoints import patch_asset_compliance_status, ComplianceStatusUpdate
    from fastapi.exceptions import HTTPException

    # role="Admin" satisfies the CR-04 write-role gate but is not in the
    # tenant-bypass _SUPER_ROLES set (case-sensitive, lowercase "admin" only),
    # so this exercises the tenant-isolation check specifically.
    user = _make_user(role="Admin", tenant_id="tenant-b")  # caller is in tenant-b
    # Asset exists in the DB but belongs to tenant-a — resolved_tenant_id != caller's tenant_id
    db = _make_db(asset_doc={"id": "a1", "tenantId": "tenant-a"})
    body = ComplianceStatusUpdate(control_id="c1", status="Compliant")

    async def _run():
        with patch("compliance_status_endpoints.get_database", return_value=db):
            return await patch_asset_compliance_status("a1", body, current_user=user)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Test 3 — Invalid status 422
# ---------------------------------------------------------------------------

def test_patch_compliance_status_invalid_status_422():
    """Pydantic rejects a status value outside the Literal enum."""
    from compliance_status_endpoints import ComplianceStatusUpdate

    with pytest.raises(ValidationError):
        # "invalid" is not in Literal["Compliant", "Non-Compliant", "Pending_Evidence"]
        ComplianceStatusUpdate(control_id="c1", status="invalid")


# ---------------------------------------------------------------------------
# Test 4 — Insufficient permissions 403 (CR-04)
# ---------------------------------------------------------------------------

def test_patch_compliance_status_read_only_role_403():
    """A read-only role (e.g. Viewer) cannot override compliance status, even
    within its own tenant — write requires membership in _WRITE_ROLES."""
    from compliance_status_endpoints import patch_asset_compliance_status, ComplianceStatusUpdate
    from fastapi.exceptions import HTTPException

    user = _make_user(role="Viewer", tenant_id="tenant-a")
    db = _make_db(asset_doc={"id": "a1", "tenantId": "tenant-a"})
    body = ComplianceStatusUpdate(control_id="c1", status="Compliant")

    async def _run():
        with patch("compliance_status_endpoints.get_database", return_value=db):
            return await patch_asset_compliance_status("a1", body, current_user=user)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())

    assert exc_info.value.status_code == 403
    assert "permission" in exc_info.value.detail.lower()
