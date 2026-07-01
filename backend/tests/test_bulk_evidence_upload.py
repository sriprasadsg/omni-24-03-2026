"""Phase 8 bulk evidence upload tests — BULK-01, BULK-02, BULK-03, security guards.

All tests are synchronous (TestClient). asyncio.to_thread is patched where needed.
(pytest-asyncio not installed — project decision 02-01)
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
# Security: zip-bomb guard (updated — uses MAX_BULK_BYTES patch, not infolist mock)
# ---------------------------------------------------------------------------

def test_bulk_zip_bomb_guard():
    """Actual decompressed bytes exceed patched MAX_BULK_BYTES → 413/422 (SEC-01 guard).

    Uses a DEFLATE-compressed zip so the compressed container is smaller than the
    patched threshold, proving the accumulator (not the container-size guard) fires.
    """
    large_content = b"X" * 1000
    deflated_buf = io.BytesIO()
    with zipfile.ZipFile(deflated_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("dummy.pdf", b"%PDF-1.4 " + large_content)
        zf.writestr("extra.pdf", b"%PDF-1.4 " + large_content)
    zip_bytes = deflated_buf.getvalue()
    manifest = json.dumps([
        {"filename": "dummy.pdf", "control_id": "CC1.1"},
        {"filename": "extra.pdf", "control_id": "CC1.2"},
    ])
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "get_database", return_value=db_mock), \
         patch.object(bulk_mod, "MAX_BULK_BYTES", 500):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code in (413, 422), resp.text
    db_mock.control_evidence.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# Security: SEC-01 — accumulator-based total-size guard
# ---------------------------------------------------------------------------

def test_bulk_zip_bomb_total_bytes_accumulator():
    """Deflated zip: compressed size passes the container guard, but actual decompressed
    bytes exceed the patched MAX_BULK_BYTES → 413/422 (SEC-01 accumulator guard).

    The zip is created with ZIP_DEFLATED so compressed << uncompressed.  We patch
    MAX_BULK_BYTES to a value between the compressed size (~232 bytes) and the
    total uncompressed content (~2018 bytes).  This proves the accumulator counts
    real bytes, not the compressed envelope size or the spoofable infolist metadata.
    """
    # ~1000 bytes of repetitive content per entry compresses well with DEFLATE.
    # Uncompressed per entry ≈ 1009 bytes; total ≈ 2018 bytes.
    large_content = b"X" * 1000
    pdf_bytes_a = b"%PDF-1.4 " + large_content
    pdf_bytes_b = b"%PDF-1.4 " + large_content

    deflated_buf = io.BytesIO()
    with zipfile.ZipFile(deflated_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.pdf", pdf_bytes_a)
        zf.writestr("b.pdf", pdf_bytes_b)
    zip_bytes = deflated_buf.getvalue()
    # Compressed zip is ~232 bytes; uncompressed total ~2018 bytes.
    # Patch MAX_BULK_BYTES = 500: compressed passes guard (232 < 500), accumulator fires.

    manifest = json.dumps([
        {"filename": "a.pdf", "control_id": "CC1.1"},
        {"filename": "b.pdf", "control_id": "CC1.2"},
    ])
    user = _fake_user()
    db_mock = _make_mock_db()
    app = _make_bulk_app(user, db_mock)

    with patch.object(bulk_mod, "MAX_BULK_BYTES", 500), \
         patch.object(bulk_mod, "get_database", return_value=db_mock):
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("b.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code in (413, 422), resp.text
    db_mock.control_evidence.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# Security: SEC-02 — DB rollback on partial commit failure
# ---------------------------------------------------------------------------

def test_bulk_db_rollback_on_partial_failure():
    """Mid-batch insert_one failure triggers delete_many for already-inserted IDs (SEC-02).

    First insert succeeds; second raises.  Expects:
    - HTTP 500
    - delete_many called exactly once with the first record's id in the $in list
    """
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

    # First insert succeeds, second raises — AsyncMock side_effect list
    db_mock.control_evidence.insert_one = AsyncMock(
        side_effect=[MagicMock(inserted_id="cev-id-1"), Exception("DB error")]
    )
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
    # Rollback: delete_many must be called exactly once
    db_mock.control_evidence.delete_many.assert_awaited_once()
    call_args = db_mock.control_evidence.delete_many.call_args[0][0]
    assert "id" in call_args, f"Expected 'id' key in filter, got: {call_args}"
    assert "$in" in call_args["id"], f"Expected '$in' in id filter, got: {call_args['id']}"
    assert len(call_args["id"]["$in"]) == 1, \
        f"Expected 1 ID in rollback (only first insert succeeded), got: {call_args['id']['$in']}"


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

    # Assert CoC entries were written (one per committed file)
    assert db_mock._db.evidence_audit_log.insert_one.await_count == 2
    coc_calls = db_mock._db.evidence_audit_log.insert_one.call_args_list
    assert all(c[0][0]["action_type"] == "create" for c in coc_calls)
    assert all(c[0][0]["tenantId"] == "tenant-b" for c in coc_calls)
