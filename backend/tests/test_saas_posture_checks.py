import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import saas_posture_checks_service as svc
import saas_posture_checks_endpoints as ep
from database import get_db
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData

# Test harness based on _chain/_mkdb convention
def _chain(result):
    c = MagicMock()
    c.to_list = AsyncMock(return_value=result)
    return c

def _mkdb():
    db = MagicMock()
    db.saas_check_results = MagicMock()
    db.saas_check_results.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    return db


def _user(role="security_analyst", tenant_id="tenant-a"):
    return TokenData(username="test@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)


def _make_client(db):
    """Depends(get_db) holds the original function object — override it on the
    app; patching database.get_db after import has no effect on the route."""
    app = FastAPI()
    app.include_router(ep.router)
    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)

# --- Service Tests ---
@pytest.mark.asyncio
async def test_run_posture_checks_reshaping():
    """Assert fail->FAIL, pass->PASS, missing->NO-DATA mapping."""
    db = _mkdb()
    connection = {
        "id": "conn-1",
        "tenant_id": "tenant-a",
        "provider": "github"
    }

    # Mock pull_all_evidence to return canned data
    # GITHUB_POSTURE_CHECKS look for _CTRL_SECURE_DEV, _CTRL_SOURCE_CODE, _CTRL_SEC_PATCH
    mock_evidence = [
        {"control_id": "Secure Development & Coding Simulation", "status": "fail", "content": "fail detail"},
        {"control_id": "Access to Source Code Simulation", "status": "pass", "content": "pass detail"}
        # _CTRL_SEC_PATCH missing -> should map to NO-DATA
    ]

    with patch("saas_integration_service.saas_integration_service.pull_all_evidence", new_callable=AsyncMock, return_value=mock_evidence):
        result = await svc.saas_posture_checks_service.run_posture_checks(connection, db)

    assert result["ran"] == 3  # 3 checks defined for GitHub

    # Assert calls to upsert (there should be 3)
    assert db.saas_check_results.update_one.call_count == 3

    # Check one FAIL, one PASS, one NO-DATA
    # Note: update_one is called 3 times, we need to inspect call args
    upserts = [call[0][1]["$set"] for call in db.saas_check_results.update_one.call_args_list]

    # Map by checkId
    results_by_id = {u["checkId"]: u["result"] for u in upserts}
    assert results_by_id["gh-sd-001"] == "FAIL" # SECURE_DEV (fail)
    assert results_by_id["gh-sc-001"] == "PASS" # SOURCE_CODE (pass)
    assert results_by_id["gh-sp-001"] == "NO-DATA" # SEC_PATCH (missing)

# --- Endpoint Tests ---
def test_endpoint_posture_run_success():
    connection = {"id": "conn-1", "tenant_id": "tenant-a", "provider": "github"}
    db = _mkdb()
    db.saas_connections.find_one = AsyncMock(return_value=connection)
    client = _make_client(db)
    with patch("saas_posture_checks_endpoints.svc.saas_posture_checks_service.run_posture_checks", new_callable=AsyncMock, return_value={"ran": 1}):
        response = client.post("/api/saas/posture-checks/conn-1/run")
    assert response.status_code == 200
    assert response.json()["ran"] == 1

def test_endpoint_posture_run_cross_tenant_denied():
    connection = {"id": "conn-1", "tenant_id": "tenant-b", "provider": "github"}
    db = MagicMock()
    db.saas_connections.find_one = AsyncMock(return_value=connection)
    client = _make_client(db)
    response = client.post("/api/saas/posture-checks/conn-1/run")
    assert response.status_code == 403

def test_endpoint_posture_run_not_found():
    db = MagicMock()
    db.saas_connections.find_one = AsyncMock(return_value=None)
    client = _make_client(db)
    response = client.post("/api/saas/posture-checks/conn-x/run")
    assert response.status_code == 404

def test_endpoint_list_results_success():
    tenant_id = "tenant-a"
    connection_id = "conn-1"
    connection = {"id": connection_id, "tenant_id": tenant_id, "provider": "github"}
    mock_results = [{"id": "scr-1", "checkName": "Mock Check", "result": "PASS"}]

    db = MagicMock()
    db.saas_connections.find_one = AsyncMock(return_value=connection)
    db.saas_check_results.find.return_value.to_list = AsyncMock(return_value=mock_results)
    client = _make_client(db)
    response = client.get(f"/api/saas/posture-checks/{connection_id}/results")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["items"][0]["checkName"] == "Mock Check"
    # results query is tenant-scoped
    query = db.saas_check_results.find.call_args.args[0]
    assert query["tenantId"] == tenant_id

def test_endpoint_list_results_cross_tenant_denied():
    connection_id = "conn-1"
    # User's tenant is 'tenant-a' by default in _user()
    connection = {"id": connection_id, "tenant_id": "tenant-b", "provider": "github"}

    db = MagicMock()
    db.saas_connections.find_one = AsyncMock(return_value=connection)
    client = _make_client(db)
    response = client.get(f"/api/saas/posture-checks/{connection_id}/results")

    assert response.status_code == 403
