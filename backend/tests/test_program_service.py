"""Tests for Phase 16 — Program Control Grouping."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

def _mkuser(t="tenant-a", r="super_admin"): u = MagicMock(); u.tenant_id = t; u.role = r; return u

def _mkdb(program_doc=None, asset_compliance_docs=None):
    """Mock db matching program_service's raw db._db access pattern (both
    programs and asset_compliance are read via db._db, bypassing the
    tenant-isolated wrapper, so the explicit tenant_id argument threaded
    through _compute_status_rollup is what actually scopes the query —
    see WR-01). programs and asset_compliance must be distinct mock
    objects — aliasing them causes configuring one to silently clobber
    the other.
    """
    db = MagicMock()
    inner = MagicMock()

    programs_col = MagicMock()
    programs_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
    programs_col.find_one = AsyncMock(return_value=program_doc)
    programs_col.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[program_doc] if program_doc else [])
        ))
    ))
    programs_col.update_one = AsyncMock(return_value=MagicMock())
    programs_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    inner.programs = programs_col

    asset_compliance_col = MagicMock()
    asset_compliance_col.find = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=asset_compliance_docs or [])
    ))
    inner.asset_compliance = asset_compliance_col

    db._db = inner
    return db

def _build(db, u):
    import program_endpoints as m
    from authentication_service import get_current_user
    from tenant_context import set_tenant_id
    app = FastAPI(); app.include_router(m.router)
    t = MagicMock(); t.tenant_id = u.tenant_id; t.role = u.role
    app.dependency_overrides[get_current_user] = lambda: t
    # program_endpoints reads tenant_id from the tenant_context contextvar
    # (not from the injected user), so it must be primed the same way the
    # real get_current_user would prime it in production.
    set_tenant_id(u.tenant_id)
    patcher = patch("program_endpoints.get_database", return_value=db); patcher.start()
    return TestClient(app, raise_server_exceptions=False)

def test_create_program():
    db = _mkdb()
    c = _build(db, _mkuser())
    r = c.post("/api/programs", json={
        "name": "Access Ctrl", "description": "ACS program",
        "framework_id": "soc2", "owner": "admin", "control_ids": ["CC6.1"],
    })
    assert r.status_code == 200
    body = r.json()["program"]
    assert body["name"] == "Access Ctrl"
    assert body["framework_id"] == "soc2"
    assert body["owner"] == "admin"
    assert body["control_ids"] == ["CC6.1"]
    assert "id" in body

def test_add_controls_to_program():
    program_doc = {"id": "prog-1", "tenantId": "tenant-a", "name": "Test", "control_ids": ["CC6.1"]}
    db = _mkdb(program_doc=program_doc)
    c = _build(db, _mkuser())
    r = c.put("/api/programs/prog-1/controls", json={"add": ["CC6.2", "CC7.1"], "remove": []})
    assert r.status_code == 200
    body = r.json()["program"]
    assert set(body["control_ids"]) == {"CC6.1", "CC6.2", "CC7.1"}

def test_remove_controls_from_program():
    program_doc = {"id": "prog-1", "tenantId": "tenant-a", "name": "Test", "control_ids": ["CC6.1", "CC6.2"]}
    db = _mkdb(program_doc=program_doc)
    c = _build(db, _mkuser())
    r = c.put("/api/programs/prog-1/controls", json={"add": [], "remove": ["CC6.1"]})
    assert r.status_code == 200
    body = r.json()["program"]
    assert body["control_ids"] == ["CC6.2"]

def test_status_rollup_compliant():
    # 5 controls, 4 Compliant + 0 failing -> passing >= total*0.8 and
    # failing == 0 -> "compliant" (per plan's threshold spec).
    control_ids = ["C1", "C2", "C3", "C4", "C5"]
    program_doc = {"id": "prog-1", "tenantId": "tenant-a", "name": "Test", "control_ids": control_ids}
    ac_docs = [
        {"controlId": "C1", "status": "Compliant"},
        {"controlId": "C2", "status": "Compliant"},
        {"controlId": "C3", "status": "Compliant"},
        {"controlId": "C4", "status": "Compliant"},
    ]
    db = _mkdb(program_doc=program_doc, asset_compliance_docs=ac_docs)
    c = _build(db, _mkuser())
    r = c.get("/api/programs/prog-1")
    assert r.status_code == 200
    rollup = r.json()["program"]["status_rollup"]
    assert rollup == {"total": 5, "passing": 4, "failing": 0, "not_assessed": 1, "status": "compliant"}

def test_status_rollup_at_risk():
    # Any failing > 0 -> "at_risk", regardless of how many are passing.
    control_ids = ["C1", "C2"]
    program_doc = {"id": "prog-1", "tenantId": "tenant-a", "name": "Test", "control_ids": control_ids}
    ac_docs = [
        {"controlId": "C1", "status": "Compliant"},
        {"controlId": "C2", "status": "Non-Compliant"},
    ]
    db = _mkdb(program_doc=program_doc, asset_compliance_docs=ac_docs)
    c = _build(db, _mkuser())
    r = c.get("/api/programs/prog-1")
    assert r.status_code == 200
    rollup = r.json()["program"]["status_rollup"]
    assert rollup["status"] == "at_risk"
    assert rollup["passing"] == 1
    assert rollup["failing"] == 1

def test_list_programs_includes_rollup():
    program_doc = {"id": "prog-1", "tenantId": "tenant-a", "name": "Test", "control_ids": ["C1"]}
    ac_docs = [{"controlId": "C1", "status": "Compliant"}]
    db = _mkdb(program_doc=program_doc, asset_compliance_docs=ac_docs)
    c = _build(db, _mkuser())
    r = c.get("/api/programs")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    item = body["items"][0]
    assert item["id"] == "prog-1"
    assert "status_rollup" in item
    assert item["status_rollup"]["status"] == "compliant"

def test_tenant_isolation():
    # A unit-level substitute for "two tenants never see each other's data":
    # assert the Mongo query issued for each request is scoped to that
    # request's OWN tenant_id, and that a second, differently-tenanted
    # request scopes independently rather than reusing the prior tenant.
    db_a = _mkdb(program_doc={"id": "prog-1", "tenantId": "tenant-a", "name": "A", "control_ids": []})
    c_a = _build(db_a, _mkuser("tenant-a", "super_admin"))
    r_a = c_a.get("/api/programs")
    assert r_a.status_code == 200
    filter_a = db_a._db.programs.find.call_args.args[0]
    assert filter_a == {"tenantId": "tenant-a"}

    db_b = _mkdb(program_doc={"id": "prog-2", "tenantId": "tenant-b", "name": "B", "control_ids": []})
    c_b = _build(db_b, _mkuser("tenant-b", "super_admin"))
    r_b = c_b.get("/api/programs")
    assert r_b.status_code == 200
    filter_b = db_b._db.programs.find.call_args.args[0]
    assert filter_b == {"tenantId": "tenant-b"}
