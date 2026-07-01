"""
Unit tests for manual evidence upload gaps — EVID-01, EVID-02, EVID-04, EVID-05.

RED phase: tests are written against the INTENDED post-fix behavior.
They will FAIL until compliance_evidence_endpoints.py and
compliance_artifacts_endpoints.py are updated in Tasks 1 and 2.
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

def _make_user(username="user@tenant.com", role="Viewer", tenant_id="tenant-a"):
    from auth_types import TokenData
    return TokenData(username=username, role=role, tenant_id=tenant_id)


def _make_upload_file(filename="evidence.pdf", content=b"%PDF-1.4 test content",
                      content_type="application/pdf"):
    """Return a minimal async-compatible UploadFile mock."""
    uf = MagicMock()
    uf.filename = filename
    uf.content_type = content_type
    uf.read = AsyncMock(return_value=content)
    return uf


def _make_db(asset_doc=None, aggregate_result=None):
    """Build a mock async DB with configurable return values."""
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


def _make_request():
    from fastapi import Request, Response
    req = MagicMock(spec=Request)
    req.headers = {}
    resp = MagicMock(spec=Response)
    return req, resp


# ---------------------------------------------------------------------------
# EVID-01 — size cap
# ---------------------------------------------------------------------------

def test_upload_allowed_types():
    """EVID-01: Valid PDF <= 25 MB returns success and writes an evidence record."""
    from compliance_evidence_endpoints import upload_compliance_evidence

    user = _make_user()
    db = _make_db()
    uf = _make_upload_file("evidence.pdf", b"%PDF-1.4 hello", "application/pdf")
    req, resp = _make_request()

    async def _run():
        with patch("compliance_evidence_endpoints.get_database", return_value=db), \
             patch("compliance_evidence_endpoints.asyncio.to_thread", new=AsyncMock(return_value=None)):
            return await upload_compliance_evidence(
                request=req,
                response=resp,
                asset_id="asset-1",
                file=uf,
                control_id="CTRL-001",
                description="Test upload",
                current_user=user,
            )

    result = asyncio.run(_run())
    assert result.get("success") is True
    assert "evidence" in result


def test_upload_size_limit():
    """EVID-01: File > 25 MB raises HTTPException 413."""
    from compliance_evidence_endpoints import upload_compliance_evidence
    from fastapi.exceptions import HTTPException

    user = _make_user()
    db = _make_db()
    big_content = b"%PDF-" + b"x" * (26 * 1024 * 1024)
    uf = _make_upload_file("large.pdf", big_content, "application/pdf")
    req, resp = _make_request()

    async def _run():
        with patch("compliance_evidence_endpoints.get_database", return_value=db):
            return await upload_compliance_evidence(
                request=req,
                response=resp,
                asset_id="asset-1",
                file=uf,
                control_id="CTRL-001",
                description="",
                current_user=user,
            )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 413


# ---------------------------------------------------------------------------
# EVID-02 — full metadata on evidence record
# ---------------------------------------------------------------------------

def test_upload_record_schema():
    """EVID-02: Record has uploaded_by, description, tenantId, source='manual', systemGenerated=False."""
    from compliance_evidence_endpoints import upload_compliance_evidence

    user = _make_user(username="uploader@tenant.com", tenant_id="tenant-a")
    db = _make_db()
    uf = _make_upload_file("doc.pdf", b"%PDF-1.4 data", "application/pdf")
    req, resp = _make_request()

    async def _run():
        with patch("compliance_evidence_endpoints.get_database", return_value=db), \
             patch("compliance_evidence_endpoints.asyncio.to_thread", new=AsyncMock(return_value=None)):
            return await upload_compliance_evidence(
                request=req,
                response=resp,
                asset_id="asset-1",
                file=uf,
                control_id="CTRL-002",
                description="quarterly audit",
                current_user=user,
            )

    result = asyncio.run(_run())
    ev = result["evidence"]
    assert ev.get("uploaded_by") == "uploader@tenant.com", f"uploaded_by missing; got: {ev}"
    assert ev.get("description") == "quarterly audit", f"description missing; got: {ev}"
    assert ev.get("tenantId") == "tenant-a", f"tenantId missing; got: {ev}"
    assert ev.get("source") == "manual", f"source missing; got: {ev}"
    assert ev.get("systemGenerated") is False, f"systemGenerated missing/wrong; got: {ev}"


# ---------------------------------------------------------------------------
# EVID-05 — magic-byte validation
# ---------------------------------------------------------------------------

def test_magic_bytes_valid_pdf():
    """EVID-05: PDF content with %PDF- magic passes _check_magic."""
    from compliance_artifacts_endpoints import _check_magic
    assert _check_magic(b"%PDF-1.4 rest of content", ".pdf") is True


def test_magic_bytes_mismatch():
    """EVID-05: .pdf whose bytes start with <script raises HTTPException 400 via upload handler."""
    from compliance_evidence_endpoints import upload_compliance_evidence
    from fastapi.exceptions import HTTPException

    user = _make_user()
    db = _make_db()
    evil_content = b"<script>alert(1)</script>"
    uf = _make_upload_file("evil.pdf", evil_content, "application/pdf")
    req, resp = _make_request()

    async def _run():
        with patch("compliance_evidence_endpoints.get_database", return_value=db):
            return await upload_compliance_evidence(
                request=req,
                response=resp,
                asset_id="asset-1",
                file=uf,
                control_id="CTRL-005",
                description="",
                current_user=user,
            )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# EVID-04 — DELETE endpoint
# ---------------------------------------------------------------------------

def _manual_ev_doc(ev_id="ev-manual-abc", uploaded_by="user@tenant.com",
                   tenant_id="tenant-a", system_generated=False):
    """Return simulated aggregate pipeline result for one evidence record."""
    return [{
        "tenantId": tenant_id,
        "evidence": {
            "id": ev_id,
            "name": "doc.pdf",
            "url": f"/static/evidence/{ev_id}.pdf",
            "uploaded_by": uploaded_by,
            "systemGenerated": system_generated,
            "source": "manual",
        }
    }]


def test_delete_own_evidence():
    """EVID-04: Owner can delete their own manual evidence -> success."""
    from compliance_evidence_endpoints import delete_compliance_evidence

    user = _make_user(username="user@tenant.com", role="Viewer", tenant_id="tenant-a")
    agg_result = _manual_ev_doc(uploaded_by="user@tenant.com", tenant_id="tenant-a")
    db = _make_db(aggregate_result=agg_result)

    async def _run():
        with patch("compliance_evidence_endpoints.get_database", return_value=db), \
             patch("pathlib.Path.unlink", return_value=None), \
             patch("pathlib.Path.exists", return_value=False):
            return await delete_compliance_evidence(
                asset_id="asset-1",
                evidence_id="ev-manual-abc",
                current_user=user,
            )

    result = asyncio.run(_run())
    assert result.get("success") is True


def test_delete_other_user_evidence():
    """EVID-04: Non-owner non-admin gets 403 when deleting someone else's evidence."""
    from compliance_evidence_endpoints import delete_compliance_evidence
    from fastapi.exceptions import HTTPException

    user = _make_user(username="other@tenant.com", role="Viewer", tenant_id="tenant-a")
    # Evidence is owned by a different user in the SAME tenant
    agg_result = _manual_ev_doc(uploaded_by="owner@tenant.com", tenant_id="tenant-a")
    db = _make_db(aggregate_result=agg_result)

    async def _run():
        with patch("compliance_evidence_endpoints.get_database", return_value=db):
            return await delete_compliance_evidence(
                asset_id="asset-1",
                evidence_id="ev-manual-abc",
                current_user=user,
            )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 403


def test_admin_delete_any_evidence():
    """EVID-04: Admin (_SUPER_ROLES) can delete any tenant's manual evidence."""
    from compliance_evidence_endpoints import delete_compliance_evidence

    admin = _make_user(username="admin@platform.com", role="admin", tenant_id="platform-admin")
    # Evidence belongs to a completely different tenant
    agg_result = _manual_ev_doc(uploaded_by="somebody@other.com", tenant_id="tenant-b")
    db = _make_db(aggregate_result=agg_result)

    async def _run():
        with patch("compliance_evidence_endpoints.get_database", return_value=db), \
             patch("pathlib.Path.unlink", return_value=None), \
             patch("pathlib.Path.exists", return_value=False):
            return await delete_compliance_evidence(
                asset_id="asset-1",
                evidence_id="ev-manual-abc",
                current_user=admin,
            )

    result = asyncio.run(_run())
    assert result.get("success") is True


def test_delete_automated_evidence_blocked():
    """EVID-04: Deleting a systemGenerated record must raise 403."""
    from compliance_evidence_endpoints import delete_compliance_evidence
    from fastapi.exceptions import HTTPException

    admin = _make_user(username="admin@platform.com", role="admin", tenant_id="platform-admin")
    agg_result = _manual_ev_doc(uploaded_by="system", system_generated=True)
    db = _make_db(aggregate_result=agg_result)

    async def _run():
        with patch("compliance_evidence_endpoints.get_database", return_value=db):
            return await delete_compliance_evidence(
                asset_id="asset-1",
                evidence_id="ev-auto-check-001",
                current_user=admin,
            )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 403
