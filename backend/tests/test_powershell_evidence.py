"""Tests for POST /api/powershell-evidence/submit (Phase 23-01).

Tests:
  1. test_submit_via_registration_key       — X-Registration-Key resolves tenant, 200
  2. test_submit_via_jwt_bearer             — Authorization Bearer JWT resolves tenant, 200
  3. test_submit_calls_process_automated_evidence — process_automated_evidence called correctly
  4. test_submit_unknown_registration_key_returns_401 — bad key → 401
  5. test_submit_cross_tenant_rejected      — JWT tenant_id ≠ key tenant → 403
  6. test_submit_empty_checks_returns_400   — checks: [] → 422 (Pydantic validation)
"""
import sys
import os
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_check(name="Windows Firewall Profiles", status="Pass", details="ok", content="output"):
    return {
        "check": name,
        "status": status,
        "details": details,
        "evidence_content": content,
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
    }


def _minimal_payload(hostname="WIN-HOST-01", checks=None):
    if checks is None:
        checks = [_make_check()]
    return {"hostname": hostname, "checks": checks}


def _make_tenant_doc(tenant_id="tenant-a"):
    return {"id": tenant_id, "registrationKey": "reg-key-abc", "name": "Tenant A"}


def _make_user(tenant_id="tenant-a", role="User"):
    user = MagicMock()
    user.tenant_id = tenant_id
    user.role = role
    return user


def _make_mock_db(tenant_doc=None):
    """Build the mock db object that mimics db._db.tenants.find_one behavior."""
    mock_tenants = MagicMock()
    mock_tenants.find_one = AsyncMock(return_value=tenant_doc)

    mock_db_inner = MagicMock()
    mock_db_inner.tenants = mock_tenants

    mock_db = MagicMock()
    mock_db._db = mock_db_inner
    return mock_db


def _build_client(mock_db, current_user, mock_process):
    """Build test client with get_database and get_optional_user patched at module level."""
    import powershell_evidence_endpoints as mod
    from authentication_service import get_optional_user

    app = FastAPI()
    app.include_router(mod.router)
    # Override JWT dep — no real JWT validation
    app.dependency_overrides[get_optional_user] = lambda: current_user

    with patch("powershell_evidence_endpoints.get_database", return_value=mock_db), \
         patch("powershell_evidence_endpoints.process_automated_evidence", mock_process):
        client = TestClient(app, raise_server_exceptions=True)
        return client, mock_process


# ---------------------------------------------------------------------------
# Test 1: Registration key resolves tenant → 200
# ---------------------------------------------------------------------------

def test_submit_via_registration_key():
    """POST with valid X-Registration-Key returns 200 and accepted count."""
    mock_db = _make_mock_db(tenant_doc=_make_tenant_doc("tenant-a"))
    mock_process = AsyncMock(return_value=None)

    with patch("powershell_evidence_endpoints.get_database", return_value=mock_db), \
         patch("powershell_evidence_endpoints.process_automated_evidence", mock_process):

        import powershell_evidence_endpoints as mod
        from authentication_service import get_optional_user

        app = FastAPI()
        app.include_router(mod.router)
        app.dependency_overrides[get_optional_user] = lambda: None

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/powershell-evidence/submit",
            json=_minimal_payload(),
            headers={"X-Registration-Key": "reg-key-abc"},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "accepted" in data
    assert data["accepted"] == 1


# ---------------------------------------------------------------------------
# Test 2: JWT bearer resolves tenant → 200
# ---------------------------------------------------------------------------

def test_submit_via_jwt_bearer():
    """POST with valid JWT (get_optional_user) returns 200."""
    user = _make_user("tenant-a", "User")
    mock_db = _make_mock_db(tenant_doc=None)
    mock_process = AsyncMock(return_value=None)

    with patch("powershell_evidence_endpoints.get_database", return_value=mock_db), \
         patch("powershell_evidence_endpoints.process_automated_evidence", mock_process):

        import powershell_evidence_endpoints as mod
        from authentication_service import get_optional_user

        app = FastAPI()
        app.include_router(mod.router)
        app.dependency_overrides[get_optional_user] = lambda: user

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/powershell-evidence/submit",
            json=_minimal_payload(),
            headers={"Authorization": "Bearer fake-jwt-token"},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "accepted" in data


# ---------------------------------------------------------------------------
# Test 3: process_automated_evidence called with agent_type="powershell" and hostname
# ---------------------------------------------------------------------------

def test_submit_calls_process_automated_evidence():
    """process_automated_evidence is invoked with agent_type='powershell' and correct hostname."""
    mock_db = _make_mock_db(tenant_doc=_make_tenant_doc("tenant-b"))
    mock_process = AsyncMock(return_value=None)

    hostname = "WIN-SERVER-DC01"
    checks = [_make_check("Windows Firewall Profiles"), _make_check("Windows Defender Antivirus")]

    with patch("powershell_evidence_endpoints.get_database", return_value=mock_db), \
         patch("powershell_evidence_endpoints.process_automated_evidence", mock_process):

        import powershell_evidence_endpoints as mod
        from authentication_service import get_optional_user

        app = FastAPI()
        app.include_router(mod.router)
        app.dependency_overrides[get_optional_user] = lambda: None

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/powershell-evidence/submit",
            json={"hostname": hostname, "checks": checks},
            headers={"X-Registration-Key": "reg-key-abc"},
        )

    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    mock_process.assert_awaited_once()
    call_args = mock_process.call_args
    # First positional arg is hostname
    assert call_args[0][0] == hostname
    # agent_type keyword arg
    assert call_args[1].get("agent_type") == "powershell"


# ---------------------------------------------------------------------------
# Test 4: Unknown registration key → 401
# ---------------------------------------------------------------------------

def test_submit_unknown_registration_key_returns_401():
    """find_one returns None for unknown key → 401 Unauthorized."""
    mock_db = _make_mock_db(tenant_doc=None)  # key not found
    mock_process = AsyncMock(return_value=None)

    with patch("powershell_evidence_endpoints.get_database", return_value=mock_db), \
         patch("powershell_evidence_endpoints.process_automated_evidence", mock_process):

        import powershell_evidence_endpoints as mod
        from authentication_service import get_optional_user

        app = FastAPI()
        app.include_router(mod.router)
        app.dependency_overrides[get_optional_user] = lambda: None

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/powershell-evidence/submit",
            json=_minimal_payload(),
            headers={"X-Registration-Key": "bad-key-xyz"},
        )

    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Test 5: Cross-tenant mismatch → 403
# ---------------------------------------------------------------------------

def test_submit_cross_tenant_rejected():
    """JWT tenant_id 'tenant-a' but key resolves to 'tenant-b' → 403."""
    mock_db = _make_mock_db(tenant_doc=_make_tenant_doc("tenant-b"))  # key belongs to tenant-b
    user = _make_user("tenant-a", "User")  # JWT says tenant-a
    mock_process = AsyncMock(return_value=None)

    with patch("powershell_evidence_endpoints.get_database", return_value=mock_db), \
         patch("powershell_evidence_endpoints.process_automated_evidence", mock_process):

        import powershell_evidence_endpoints as mod
        from authentication_service import get_optional_user

        app = FastAPI()
        app.include_router(mod.router)
        app.dependency_overrides[get_optional_user] = lambda: user

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/powershell-evidence/submit",
            json=_minimal_payload(),
            headers={
                "X-Registration-Key": "reg-key-abc",
                "Authorization": "Bearer fake-jwt",
            },
        )

    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Test 6: Empty checks list → 422 (Pydantic min_length=1 validation)
# ---------------------------------------------------------------------------

def test_submit_empty_checks_returns_400():
    """checks: [] → 422 Unprocessable Entity from Pydantic min_length=1 validation."""
    mock_db = _make_mock_db(tenant_doc=_make_tenant_doc())
    user = _make_user("tenant-a", "User")
    mock_process = AsyncMock(return_value=None)

    with patch("powershell_evidence_endpoints.get_database", return_value=mock_db), \
         patch("powershell_evidence_endpoints.process_automated_evidence", mock_process):

        import powershell_evidence_endpoints as mod
        from authentication_service import get_optional_user

        app = FastAPI()
        app.include_router(mod.router)
        app.dependency_overrides[get_optional_user] = lambda: user

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/powershell-evidence/submit",
            json={"hostname": "WIN-HOST", "checks": []},
            headers={"X-Registration-Key": "reg-key-abc"},
        )

    # Pydantic min_length=1 on the list field returns 422
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
