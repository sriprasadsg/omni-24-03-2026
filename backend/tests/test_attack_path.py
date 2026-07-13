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

def test_attack_paths_demo_fallback_when_empty():
    mock_attack_paths_col = _col()
    mock_attack_paths_col.find.return_value.to_list = AsyncMock(return_value=[])
    mock_assets_col = _col()
    mock_assets_col.find.return_value.to_list = AsyncMock(return_value=[])
    mock_vulns_col = _col()
    mock_vulns_col.find.return_value.to_list = AsyncMock(return_value=[])
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
    assert data[0].get("simulated") is True # Demo fallback should be True

def test_edge_field_contract():
    mock_attack_paths_col = _col()
    mock_attack_paths_col.find.return_value.to_list = AsyncMock(return_value=[])
    mock_assets_col = _col()
    mock_assets_col.find.return_value.to_list = AsyncMock(return_value=[])
    mock_vulns_col = _col()
    mock_vulns_col.find.return_value.to_list = AsyncMock(return_value=[])
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

    edge = res.json()[0]["edges"][0]
    assert "source" in edge
    assert "target" in edge
    assert "vulnerability" in edge
    assert "label" not in edge # Should be gone
