"""Tests for Phase 18 — TIA, LIA, Privacy Notices, Contracts."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_user(tenant_id="tenant-a", role="admin", username="admin1"):
    u = MagicMock(); u.tenant_id = tenant_id; u.role = role; u.username = username
    return u


def _make_db():
    db = MagicMock()
    for col in ("privacy_tia", "privacy_lia", "privacy_notices", "privacy_contracts"):
        c = MagicMock()
        c.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
        c.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))))
        c.find_one = AsyncMock(return_value=None)
        setattr(db._db, col, c)
    return db


def _build_client(mock_db, user):
    import privacy_endpoints as mod
    from auth_utils import get_current_user
    app = FastAPI(); app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    patcher = patch("privacy_endpoints.get_database", return_value=mock_db)
    patcher.start()
    return TestClient(app, raise_server_exceptions=False)


def test_create_tia():
    db = _make_db(); user = _make_user()
    client = _build_client(db, user)
    resp = client.post("/api/privacy/tia", json={"transfer_name": "EU-US Data Transfer", "data_categories": ["HR records"], "source_country": "DE", "destination_country": "US", "legal_basis": "SCC", "risk_level": "high"})
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    assert resp.json()["tia"]["risk_level"] == "high"


def test_tia_risk_level_validation():
    db = _make_db(); user = _make_user()
    client = _build_client(db, user)
    resp = client.post("/api/privacy/tia", json={"transfer_name": "Test", "data_categories": [], "source_country": "DE", "destination_country": "US", "legal_basis": "SCC", "risk_level": "extreme"})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


def test_create_lia():
    db = _make_db(); user = _make_user()
    client = _build_client(db, user)
    resp = client.post("/api/privacy/lia", json={"purpose": "Email marketing", "necessity_test": "Necessary for direct marketing", "balancing_test": "User can opt out any time", "outcome": "approved", "data_subjects": "Customers"})
    assert resp.status_code == 200, f"Got {resp.status_code}"
    assert resp.json()["lia"]["purpose"] == "Email marketing"


def test_create_privacy_notice():
    db = _make_db(); user = _make_user()
    client = _build_client(db, user)
    resp = client.post("/api/privacy/notices", json={"title": "Privacy Policy v2", "content_html": "<p>Updated policy</p>", "effective_date": "2026-07-01", "applies_to": "All users"})
    assert resp.status_code == 200, f"Got {resp.status_code}"
    assert resp.json()["notice"]["title"] == "Privacy Policy v2"


def test_notice_version_history():
    db = _make_db(); user = _make_user()
    # Mock find_one to return a notice with versions
    db._db.privacy_notices.find_one = AsyncMock(return_value={"id": "notice-abc", "tenantId": "tenant-a", "title": "Privacy Policy", "versions": [{"version": 2, "content_html": "<p>v2</p>", "published_at": "2026-06-27T12:00:00Z"}, {"version": 1, "content_html": "<p>v1</p>", "published_at": "2026-01-01T00:00:00Z"}]})
    client = _build_client(db, user)
    resp = client.get("/api/privacy/notices/notice-abc/versions")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


def test_create_contract():
    db = _make_db(); user = _make_user()
    client = _build_client(db, user)
    resp = client.post("/api/privacy/contracts", json={"vendor_name": "Vendor Inc", "type": "DPA", "status": "draft", "expiry_date": "2027-01-01", "parties": ["Our Org", "Vendor Inc"]})
    assert resp.status_code == 200, f"Got {resp.status_code}"
    assert resp.json()["contract"]["type"] == "DPA"


def test_contract_type_validation():
    db = _make_db(); user = _make_user()
    client = _build_client(db, user)
    resp = client.post("/api/privacy/contracts", json={"vendor_name": "Bad", "type": "INVALID", "status": "draft"})
    assert resp.status_code == 422


def test_tenant_isolation():
    db = _make_db(); user = _make_user("tenant-a", "user")
    client = _build_client(db, user)
    resp = client.get("/api/privacy/tia")
    assert resp.status_code == 200
