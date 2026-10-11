import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData
from attack_path_endpoints import router

# Helper from test_automation_and_baa.py
def _col(**overrides):
    col = MagicMock()
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[])

    col.find = MagicMock(return_value=cursor)
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock()

    for k, v in overrides.items():
        setattr(col, k, v)
    return col

def _db(**collections):
    db = MagicMock()
    db.__getitem__ = lambda self, name: getattr(self, name, _col())
    for name, col in collections.items():
        setattr(db, name, col)
    return db

def _user(role="security_analyst", tenant_id="t1"):
    return TokenData(username="test@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)

def _app(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app

def test_attack_paths_prefers_real_correlation():
    # Need 2+ assets so entry != target pair isn't skipped
    assets = [
        {"id": "a1", "name": "Web-Gateway", "isInternetFacing": True, "type": "Web Server"},
        {"id": "a2", "name": "Prod-DB", "type": "Database", "sensitivityLevel": "Critical"},
    ]
    vulns = [{"assetId": "a1", "severity": "Critical", "cveId": "CVE-REAL"}]

    mock_assets_col = _col()
    mock_assets_col.find.return_value.to_list = AsyncMock(return_value=assets)
    mock_vulns_col = _col()
    mock_vulns_col.find.return_value.to_list = AsyncMock(return_value=vulns)
    mock_attack_paths_col = _col()
    mock_attack_paths_col.find.return_value.to_list = AsyncMock(return_value=[])
    mock_cspm_col = _col()
    mock_cspm_col.find.return_value.to_list = AsyncMock(return_value=[])

    db = _db(
        attack_paths=mock_attack_paths_col,
        assets=mock_assets_col,
        vulnerabilities=mock_vulns_col,
        cspm_findings=mock_cspm_col
    )
    app = _app(router, _user())

    with patch("attack_path_endpoints.get_database", return_value=db):
        res = TestClient(app).get("/api/security/attack-paths")

    assert res.status_code == 200
    data = res.json()
    assert len(data) > 0
    assert data[0].get("simulated") is False  # real correlation branch

def _paths_db(assets=(), vulns=(), stored=()):
    mock_attack_paths_col = _col()
    mock_attack_paths_col.find.return_value.to_list = AsyncMock(return_value=list(stored))
    mock_attack_paths_col.delete_many = AsyncMock()
    mock_assets_col = _col()
    mock_assets_col.find.return_value.to_list = AsyncMock(return_value=list(assets))
    mock_vulns_col = _col()
    mock_vulns_col.find.return_value.to_list = AsyncMock(return_value=list(vulns))
    mock_cspm_col = _col()
    mock_cspm_col.find.return_value.to_list = AsyncMock(return_value=[])
    return _db(
        attack_paths=mock_attack_paths_col,
        assets=mock_assets_col,
        vulnerabilities=mock_vulns_col,
        cspm_findings=mock_cspm_col
    )


def _get_paths(db):
    app = _app(router, _user())
    with patch("attack_path_endpoints.get_database", return_value=db):
        return TestClient(app).get("/api/security/attack-paths")


def test_attack_paths_empty_when_no_data():
    # No assets or vulnerabilities: no paths, and never invented demo scenarios
    db = _paths_db()
    res = _get_paths(db)
    assert res.status_code == 200
    assert res.json() == []
    db.attack_paths.update_one.assert_not_called()


def test_no_path_without_entry_vulnerability():
    # Assets alone are not an exploit chain; the entry needs an open vulnerability
    assets = [
        {"id": "a1", "name": "Web-Gateway", "isInternetFacing": True, "type": "Web Server"},
        {"id": "a2", "name": "Prod-DB", "type": "Database"},
    ]
    res = _get_paths(_paths_db(assets=assets))
    assert res.status_code == 200
    assert res.json() == []


def test_stored_demo_paths_are_purged():
    stored = [{"id": "demo", "name": "Exposed API Gateway → Production Database", "simulated": True,
               "nodes": [], "edges": []}]
    db = _paths_db(stored=stored)
    res = _get_paths(db)
    assert res.json() == []
    db.attack_paths.delete_many.assert_awaited_once()


def test_edge_field_contract():
    assets = [
        {"id": "a1", "name": "Web-Gateway", "isInternetFacing": True, "type": "Web Server"},
        {"id": "a2", "name": "Prod-DB", "type": "Database"},
    ]
    vulns = [{"assetId": "a1", "severity": "High", "cveId": "CVE-REAL"}]
    res = _get_paths(_paths_db(assets=assets, vulns=vulns))

    edge = res.json()[0]["edges"][0]
    assert "source" in edge
    assert "target" in edge
    assert "vulnerability" in edge
    assert edge["vulnerability"] == "CVE-REAL"
    assert "label" not in edge # Should be gone
