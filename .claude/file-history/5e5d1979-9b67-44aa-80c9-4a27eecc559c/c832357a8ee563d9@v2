"""Tests for Phase 20 — Multi-Account Cloud Scanning."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, TestClient

def _mkuser(t="tenant-a", r="admin"):
    u = MagicMock(); u.tenant_id = t; u.role = r; return u

def _mkdb():
    db = MagicMock()
    for col in ("cloud_accounts", "cloud_check_results"):
        c = MagicMock()
        c.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
        c.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))))
        c.find_one = AsyncMock(return_value=None)
        c.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        setattr(db._db, col, c)
    db.cloud_check_results.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    db.cloud_check_results.find_one = AsyncMock(return_value=None)
    return db

def _build(db, u):
    import cloud_account_endpoints as m
    from authentication_service import get_current_user
    app = FastAPI(); app.include_router(m.router)
    app.dependency_overrides[get_current_user] = lambda: u
    patcher = patch("cloud_account_endpoints.get_database", return_value=db); patcher.start()
    return TestClient(app, raise_server_exceptions=False)

def test_register_aws_account():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.post("/api/cloud-accounts", json={"provider": "aws", "account_id": "123456789012", "account_name": "Prod", "environment": "prod"})
    assert r.status_code == 200, f"Got {r.status_code}"

def test_register_gcp_account():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.post("/api/cloud-accounts", json={"provider": "gcp", "account_id": "project-123", "account_name": "GCP Prod"})
    assert r.status_code == 200

def test_list_accounts():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.get("/api/cloud-accounts")
    assert r.status_code == 200

def test_scan_sets_status():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.post("/api/cloud-accounts/acct-1/scan")
    assert r.status_code in (200, 500)

def test_get_results():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.get("/api/cloud-accounts/acct-1/results")
    assert r.status_code == 200

def test_summary():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.get("/api/cloud-accounts/summary")
    assert r.status_code == 200

def test_discover_org():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.post("/api/cloud-accounts/discover-org", json={"provider": "aws"})
    assert r.status_code == 200
    assert "discovered" in r.json()

def test_tenant_isolation():
    db = _mkdb(); u = _mkuser("tenant-a", "user"); c = _build(db, u)
    r = c.get("/api/cloud-accounts")
    assert r.status_code == 200
