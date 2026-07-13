import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from main import app # Assuming main.py initializes the FastMCP app

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="module")
async def client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

# Mock database and tenant context for testing
@pytest.fixture(autouse=True)
def mock_dependencies():
    with (
        patch("database.get_database") as mock_get_database,
        patch("tenant_context.get_tenant_id") as mock_get_tenant_id,
        patch("cloud_checks_service.cloud_checks_service") as mock_cloud_checks_service,
    ):
        mock_db_instance = AsyncMock()
        mock_db_instance._db.compliance_frameworks.find.return_value.to_list.return_value = [
            {"id": "soc2", "name": "SOC 2"},
            {"id": "iso27001", "name": "ISO 27001"},
        ]
        mock_db_instance.asset_compliance.find.return_value.to_list.return_value = [
            {"status": "Compliant"}, {"status": "Non-Compliant"}
        ]
        mock_db_instance.cloud_findings.find.return_value.sort.return_value.to_list.return_value = [
            {"id": "finding1", "severity": "high"}
        ]
        mock_get_database.return_value = mock_db_instance
        mock_get_tenant_id.return_value = "test-tenant-id"
        yield

async def test_mcp_list_tools_via_http(client: AsyncClient):
    response = await client.get("/api/mcp/tools")
    assert response.status_code == 200
    assert "tools" in response.json()
    tool_names = {t["name"] for t in response.json()["tools"]}
    expected_tools = {
        "list_frameworks",
        "get_control_status",
        "run_cloud_check",
        "list_findings",
        "get_compliance_score",
        "list_compliance_controls",
        "get_compliance_control",
        "list_evidence",
        "get_risk_register",
        "get_attack_paths",
    }
    assert tool_names == expected_tools

async def test_mcp_execute_list_frameworks(client: AsyncClient):
    response = await client.post(
        "/api/mcp/execute/list_frameworks",
        json={}
    )
    assert response.status_code == 200
    assert "result" in response.json()
    assert len(response.json()["result"]) == 2
    assert response.json()["result"][0]["id"] == "soc2"

async def test_mcp_execute_get_control_status(client: AsyncClient):
    response = await client.post(
        "/api/mcp/execute/get_control_status",
        json={"control_id": "test_control"}
    )
    assert response.status_code == 200
    assert response.json()["result"]["control_id"] == "test_control"
    assert response.json()["result"]["assets"] == 2

async def test_mcp_execute_run_cloud_check(client: AsyncClient):
    mock_cloud_checks_service = AsyncMock()
    mock_cloud_checks_service.run_checks.return_value = {"status": "completed"}
    with patch("cloud_checks_service.cloud_checks_service", mock_cloud_checks_service):
        response = await client.post(
            "/api/mcp/execute/run_cloud_check",
            json={
                "provider": "aws",
                "account_id": "12345"
            }
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

async def test_mcp_execute_list_findings(client: AsyncClient):
    response = await client.post(
        "/api/mcp/execute/list_findings",
        json={"severity": "high", "limit": 10}
    )
    assert response.status_code == 200
    assert len(response.json()["result"]) == 1
    assert response.json()["result"][0]["severity"] == "high"

async def test_mcp_execute_get_compliance_score(client: AsyncClient):
    response = await client.post(
        "/api/mcp/execute/get_compliance_score",
        json={"framework": "soc2"}
    )
    assert response.status_code == 200
    assert response.json()["result"]["score"] == 50
    assert response.json()["result"]["framework"] == "soc2"

# Test error handling for run_cloud_check
async def test_mcp_execute_run_cloud_check_invalid_provider(client: AsyncClient):
    response = await client.post(
        "/api/mcp/execute/run_cloud_check",
        json={
            "provider": "invalid",
            "account_id": "12345"
        }
    )
    assert response.status_code == 400
    assert "provider must be" in response.json()["detail"]

async def test_mcp_execute_run_cloud_check_not_found(client: AsyncClient):
    mock_cloud_checks_service = AsyncMock()
    mock_cloud_checks_service.run_checks.return_value = {"error": "Cloud account not found"}
    with patch("cloud_checks_service.cloud_checks_service", mock_cloud_checks_service):
        response = await client.post(
            "/api/mcp/execute/run_cloud_check",
            json={
                "provider": "aws",
                "account_id": "nonexistent"
            }
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Cloud account not found"

# Test error handling for list_findings invalid limit
async def test_mcp_execute_list_findings_invalid_limit(client: AsyncClient):
    response = await client.post(
        "/api/mcp/execute/list_findings",
        json={"limit": "abc"}
    )
    assert response.status_code == 400
    assert "limit must be a positive integer" in response.json()["detail"]

# Test error handling for get_compliance_score unknown framework
async def test_mcp_execute_get_compliance_score_unknown_framework(client: AsyncClient):
    response = await client.post(
        "/api/mcp/execute/get_compliance_score",
        json={"framework": "unknown_fw"}
    )
    assert response.status_code == 404
    assert "Unknown framework" in response.json()["detail"]
