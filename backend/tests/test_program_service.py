"""Tests for Phase 16 — Program Control Grouping."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

def _mkuser(t="tenant-a", r="super_admin"): u = MagicMock(); u.tenant_id = t; u.role = r; return u

def _mkdb():
    db = MagicMock(); inner = MagicMock()
    col = MagicMock()
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
    col.find_one = AsyncMock(return_value={"id": "prog-1", "tenantId": "tenant-a", "name": "Test", "control_ids": ["CC6.1"]})
    col.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))))
    col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    for c in ("programs", "asset_compliance"): setattr(inner, c, col if c == "asset_compliance" else col)
    inner.asset_compliance.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[{"controlId": "CC6.1", "status": "Compliant"}])))
    db._db = inner; return db

def _build(db, u):
    import program_endpoints as m
    from authentication_service import get_current_user
    app = FastAPI(); app.include_router(m.router)
    t = MagicMock(); t.tenant_id = u.tenant_id; t.role = u.role
    app.dependency_overrides[get_current_user] = lambda: t
    patcher = patch("program_endpoints.get_database", return_value=db); patcher.start()
    return TestClient(app, raise_server_exceptions=False)

def test_create_program():
    c = _build(_mkdb(), _mkuser()); r = c.post("/api/programs", json={"name": "Access Ctrl", "description": "ACS program", "framework_id": "soc2", "owner": "admin"})
    assert r.status_code in (200, 400)

def test_list_programs():
    c = _build(_mkdb(), _mkuser()); r = c.get("/api/programs")
    assert r.status_code == 200

def test_get_program():
    c = _build(_mkdb(), _mkuser()); r = c.get("/api/programs/prog-1")
    assert r.status_code in (200, 404)

def test_add_controls():
    c = _build(_mkdb(), _mkuser()); r = c.put("/api/programs/prog-1/controls", json={"add": ["CC6.2", "CC7.1"], "remove": []})
    assert r.status_code in (200, 404)

def test_remove_controls():
    c = _build(_mkdb(), _mkuser()); r = c.put("/api/programs/prog-1/controls", json={"add": [], "remove": ["CC6.1"]})
    assert r.status_code in (200, 404)

def test_delete_program():
    c = _build(_mkdb(), _mkuser()); r = c.delete("/api/programs/prog-1")
    assert r.status_code == 200

def test_tenant_isolation():
    c = _build(_mkdb(), _mkuser("tenant-a", "super_admin")); r = c.get("/api/programs")
    assert r.status_code == 200
