"""Phase 8 bulk evidence upload tests — BULK-01, BULK-02, BULK-03, security guards.

Uses asyncio.run() (pytest-asyncio not installed — project decision 02-01).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import json
import zipfile
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication_service import get_current_user
import compliance_bulk_evidence_endpoints as bulk_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_zip_bytes(files: dict) -> bytes:
    """Build an in-memory zip from {filename: bytes}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _fake_user(role="admin", tenant_id="tenant-a", username="admin@test.com"):
    user = MagicMock()
    user.role = role
    user.tenant_id = tenant_id
    user.username = username
    return user


def _make_mock_db():
    """Mock db with async insert_one on control_evidence and evidence_audit_log."""
    raw = MagicMock()
    raw.evidence_audit_log = MagicMock()
    raw.evidence_audit_log.insert_one = AsyncMock(
        return_value=MagicMock(inserted_id="coc-id")
    )
    db = MagicMock()
    db._db = raw
    db.control_evidence = MagicMock()
    db.control_evidence.insert_one = AsyncMock(
        return_value=MagicMock(inserted_id="cev-id")
    )
    return db


def _make_bulk_app(user, db_mock):
    """FastAPI app with bulk router + overrides."""
    app = FastAPI()
    app.include_router(bulk_mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


# ---------------------------------------------------------------------------
# BULK-01: valid upload
# ---------------------------------------------------------------------------

def test_bulk_upload_valid():
    """Valid zip with 2 files + manifest → 200, committed=2, success=True (BULK-01)."""
    pdf_bytes = b"%PDF-1.4 test data"
    png_bytes = b"\x89PNG\r\n\x1a\n test data"
    zip_bytes = _make_zip_bytes({"policy.pdf": pdf_bytes, "cert.png": png_bytes})
    manifest = json.dumps([
        {"filename": "policy.pdf", "control_id": "CC6.1"},
        {"filename": "cert.png",   "control_id": "CC9.1"},
    ])
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock), \
         patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("batch.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["committed"] == 2
    assert "batch_id" in body
    assert len(body["evidence"]) == 2


# ---------------------------------------------------------------------------
# BULK-01: manifest validation gates
# ---------------------------------------------------------------------------

def test_bulk_manifest_invalid_json():
    """Non-JSON manifest string → 400 (BULK-01)."""
    zip_bytes = _make_zip_bytes({"f.pdf": b"%PDF-1.4"})
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": "not valid json!!!"},
        )
    assert resp.status_code == 400, resp.text


def test_bulk_manifest_missing_fields():
    """Manifest entry missing control_id key → 400 (BULK-01)."""
    zip_bytes = _make_zip_bytes({"f.pdf": b"%PDF-1.4"})
    manifest = json.dumps([{"filename": "f.pdf"}])  # no control_id
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# BULK-02: zip container guard
# ---------------------------------------------------------------------------

def test_bulk_not_a_zip():
    """Non-zip bytes as zip_file → 400 (BULK-02)."""
    fake_bytes = b"This is definitely not a zip file."
    manifest = json.dumps([{"filename": "x.pdf", "control_id": "CC1.1"}])
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("bad.zip", fake_bytes, "application/zip")},
            data={"manifest": manifest},
        )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# BULK-02: per-file validation — disallowed extension
# ---------------------------------------------------------------------------

def test_bulk_extension_rejected():
    """Zip entry with .exe extension → 422 with per-file error (BULK-02)."""
    zip_bytes = _make_zip_bytes({"malware.exe": b"MZ evil"})
    manifest = json.dumps([{"filename": "malware.exe", "control_id": "CC6.1"}])
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "errors" in detail
    assert any("malware.exe" in e["filename"] for e in detail["errors"])
    db_mock.control_evidence.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# BULK-02: per-file validation — file too large
# ---------------------------------------------------------------------------

def test_bulk_file_too_large():
    """Entry > 25 MB → 422 with per-file error (BULK-02)."""
    big_bytes = b"X" * (26 * 1024 * 1024)  # 26 MB
    zip_bytes = _make_zip_bytes({"big.pdf": big_bytes})
    manifest = json.dumps([{"filename": "big.pdf", "control_id": "CC1.1"}])
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "errors" in detail
    assert any("big.pdf" in e["filename"] for e in detail["errors"])
    db_mock.control_evidence.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# BULK-02: per-file validation — magic bytes mismatch
# ---------------------------------------------------------------------------

def test_bulk_magic_mismatch():
    """.pdf extension + PNG magic bytes → 422; real _check_magic runs (no mock)."""
    png_in_pdf = b"\x89PNG\r\n\x1a\n fake content"
    zip_bytes = _make_zip_bytes({"report.pdf": png_in_pdf})
    manifest = json.dumps([{"filename": "report.pdf", "control_id": "CC2.1"}])
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code == 422, resp.text
    assert "errors" in resp.json()["detail"]
    db_mock.control_evidence.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# BULK-02: per-file validation — entry missing from zip
# ---------------------------------------------------------------------------

def test_bulk_missing_entry():
    """Manifest references file not in zip → 422 per-file error (BULK-02)."""
    zip_bytes = _make_zip_bytes({"present.pdf": b"%PDF-1.4 here"})
    manifest = json.dumps([{"filename": "ghost.pdf", "control_id": "CC3.1"}])
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert any("ghost.pdf" in e["filename"] for e in detail["errors"])
    db_mock.control_evidence.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# BULK-02: validate-all-before-commit — mixed batch
# ---------------------------------------------------------------------------

def test_bulk_mixed_rejects_all():
    """1 valid file + 1 invalid (.exe) → 422, zero insert_one calls (BULK-02)."""
    zip_bytes = _make_zip_bytes({
        "valid.pdf": b"%PDF-1.4 content",
        "evil.exe":  b"MZ bad",
    })
    manifest = json.dumps([
        {"filename": "valid.pdf", "control_id": "CC6.1"},
        {"filename": "evil.exe",  "control_id": "CC6.1"},
    ])
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code == 422, resp.text
    db_mock.control_evidence.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# Security: zip-slip guard
# ---------------------------------------------------------------------------

def test_bulk_zip_slip_guard():
    """Manifest filename '../evil.pdf' → KeyError → 422 (zip-slip attempt fails safely)."""
    zip_bytes = _make_zip_bytes({"evil.pdf": b"%PDF-1.4 content"})
    # Manifest uses traversal path; zf.read('../evil.pdf') raises KeyError
    manifest = json.dumps([{"filename": "../evil.pdf", "control_id": "CC1.1"}])
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "errors" in detail
    db_mock.control_evidence.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# Security: zip-bomb guard
# ---------------------------------------------------------------------------

def test_bulk_zip_bomb_guard():
    """Fake infolist sum > 200 MB → 400 before any zf.read() (security guard)."""
    zip_bytes = _make_zip_bytes({"dummy.pdf": b"%PDF-1.4 x"})
    manifest = json.dumps([{"filename": "dummy.pdf", "control_id": "CC1.1"}])
    # 3 fake entries × 100 MB each = 300 MB > MAX_BULK_BYTES (200 MB)
    fake_info = [MagicMock(file_size=100 * 1024 * 1024) for _ in range(3)]
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock), \
         patch("zipfile.ZipFile.infolist", return_value=fake_info):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code == 400, resp.text
    db_mock.control_evidence.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# BULK-03: committed evidence in control_evidence with correct fields
# ---------------------------------------------------------------------------

def test_bulk_appears_in_control_evidence():
    """After valid upload, insert_one called per file with controlId and source=manual."""
    zip_bytes = _make_zip_bytes({
        "policy.pdf": b"%PDF-1.4 policy",
        "cert.png":   b"\x89PNG\r\n\x1a\n cert",
    })
    manifest = json.dumps([
        {"filename": "policy.pdf", "control_id": "CC6.1"},
        {"filename": "cert.png",   "control_id": "CC9.1"},
    ])
    user = _fake_user(tenant_id="tenant-b")
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock), \
         patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("batch.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code == 200, resp.text
    assert db_mock.control_evidence.insert_one.await_count == 2

    calls = db_mock.control_evidence.insert_one.call_args_list
    control_ids = {c[0][0]["controlId"] for c in calls}
    sources = {c[0][0]["source"] for c in calls}
    tenant_ids = {c[0][0]["tenantId"] for c in calls}

    assert "CC6.1" in control_ids
    assert "CC9.1" in control_ids
    assert sources == {"manual"}
    assert tenant_ids == {"tenant-b"}
