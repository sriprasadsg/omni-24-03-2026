"""
Unit tests for PATCH /api/assets/{asset_id}/compliance/status — STATUS-01, STATUS-02.

Covers:
  - Happy path: 200, persists status, captures previous_status
  - Cross-tenant 403: non-admin caller with asset not in their tenant
  - Invalid status 422: Pydantic rejects values outside the Literal enum

Uses asyncio.run() — pytest-asyncio is not installed in this project.
"""
import sys
import os
import asyncio
import pytest
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

    user = _make_user()
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

    # Verify update_one was called with $set and $push
    call_args = db.asset_compliance.update_one.call_args
    update_doc = call_args[0][1]
    assert "status" in update_doc["$set"]
    assert update_doc["$set"]["manual_override"] is True
    assert update_doc["$set"]["overriddenBy"] == "analyst@tenant.com"
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

    user = _make_user(tenant_id="tenant-b")  # asset belongs to tenant-a
    # db.assets.find_one returns None — asset not in tenant-b
    db = _make_db(asset_doc=None)
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

    with pytest.raises(Exception):
        # "invalid" is not in Literal["Compliant", "Non-Compliant", "Pending_Evidence"]
        ComplianceStatusUpdate(control_id="c1", status="invalid")
