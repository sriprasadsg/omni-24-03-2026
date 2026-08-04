import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rbac_utils import verify_permission
from authentication_service import get_current_user
from database import get_database

# Import the router under test
from native_security_ops_endpoints import router

app = FastAPI()
app.include_router(router)

client = TestClient(app)

@pytest.fixture
def mock_db():
    with patch("native_security_ops_endpoints.get_database") as mock:
        db = MagicMock()
        db.agent_instructions.insert_one = AsyncMock()
        mock.return_value = db
        yield db

@pytest.fixture
def mock_user():
    class User:
        def __init__(self):
            self.id = "user-123"
            self.email = "test@example.com"
            self.tenant_id = "tenant-abc"
            self.role = "admin"
            self.permissions = ["manage:active_response"]

    user = User()
    app.dependency_overrides[get_current_user] = lambda: user
    with patch("native_security_ops_endpoints.verify_permission", new=AsyncMock(return_value=True)):
        yield user
    app.dependency_overrides = {}

@pytest.fixture
def mock_user_no_perms():
    class User:
        def __init__(self):
            self.id = "user-456"
            self.email = "noperms@example.com"
            self.tenant_id = "tenant-abc"
            self.role = "viewer"
            self.permissions = []

    user = User()
    app.dependency_overrides[get_current_user] = lambda: user
    with patch("native_security_ops_endpoints.verify_permission", new=AsyncMock(return_value=False)):
        yield user
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_get_findings_aggregated_and_scoped(mock_db, mock_user):
    mock_db.security_scan_results.find.return_value.to_list = AsyncMock(return_value=[
        {"source": "native", "severity": "high", "target": "/etc/shadow", "verdict": "Malicious", "created_at": "2026-07-31T10:00:00Z", "tenantId": "tenant-abc", "agentId": "agent-1"}
    ])
    mock_db.vulnerabilities.find.return_value.to_list = AsyncMock(return_value=[
        {"severity": "critical", "cveId": "CVE-2023-1234", "assetId": "agent-1", "created_at": "2026-07-31T11:00:00Z", "tenantId": "tenant-abc"}
    ])
    mock_db.fim_events.find.return_value.to_list = AsyncMock(return_value=[
        {"change_type": "modified", "path": "/etc/passwd", "agent_id": "agent-2", "timestamp": "2026-07-31T09:00:00Z", "tenantId": "tenant-abc"}
    ])

    response = client.get("/api/security-ops/findings")
    assert response.status_code == 200
    data = response.json()

    assert "findings" in data
    findings = data["findings"]
    assert len(findings) == 3

    assert findings[0]["source"] == "vulnerability"
    assert findings[0]["severity"] == "critical"

    assert findings[1]["source"] == "scan"
    assert findings[1]["severity"] == "high"

    assert findings[2]["source"] == "fim"
    assert findings[2]["severity"] == "medium"

    mock_db.security_scan_results.find.assert_called_with({"tenantId": "tenant-abc"})
    mock_db.vulnerabilities.find.assert_called_with({"tenantId": "tenant-abc"})
    mock_db.fim_events.find.assert_called_with({"tenantId": "tenant-abc"})

@pytest.mark.asyncio
async def test_get_remediation_queue_scoped(mock_db, mock_user):
    mock_db.remediation_requests.find.return_value.to_list = AsyncMock(return_value=[
        {"id": "rem-1", "status": "pending_approval", "tenantId": "tenant-abc"}
    ])

    response = client.get("/api/security-ops/remediation-queue")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "rem-1"
    mock_db.remediation_requests.find.assert_called_with(
        {"tenantId": "tenant-abc", "status": {"$in": ["pending_approval", "dispatching", "deferred"]}},
        {"_id": 0},
    )

@pytest.mark.asyncio
async def test_trigger_scan_inserts_instruction(mock_db, mock_user):
    mock_db.agents.find_one = AsyncMock(return_value={"id": "agent-1", "tenantId": "tenant-abc"})

    payload = {"agent_id": "agent-1", "type": "file", "target": "/etc"}
    response = client.post("/api/security-ops/trigger-scan", json=payload)

    assert response.status_code == 200
    assert response.json()["queued"] is True

    mock_db.agent_instructions.insert_one.assert_called_once()
    args = mock_db.agent_instructions.insert_one.call_args[0][0]
    assert args["type"] == "scan_file"
    assert args["agent_id"] == "agent-1"
    assert args["payload"]["path"] == "/etc"
    assert args["status"] == "pending"
    assert args["triggered_by"] == "operator"

@pytest.mark.asyncio
async def test_gate_manage_active_response(mock_db, mock_user_no_perms):
    response = client.get("/api/security-ops/findings")
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_fim_status(mock_db, mock_user):
    mock_db.agents.find.return_value.to_list = AsyncMock(return_value=[
        {"id": "agent-1", "hostname": "host1", "meta": {"capabilities": {"fim": {"enabled": True}}}}
    ])
    mock_db.fim_events.count_documents = AsyncMock(return_value=5)

    response = client.get("/api/security-ops/fim-status")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["agent_id"] == "agent-1"
    assert data[0]["events_count"] == 5

@pytest.mark.asyncio
async def test_summary(mock_db, mock_user):
    mock_db.security_scan_results.find.return_value.to_list = AsyncMock(return_value=[
        {"severity": "critical", "tenantId": "tenant-abc"}
    ])
    mock_db.vulnerabilities.find.return_value.to_list = AsyncMock(return_value=[
        {"severity": "critical", "tenantId": "tenant-abc"},
        {"severity": "low", "tenantId": "tenant-abc"},
    ])
    mock_db.remediation_requests.count_documents = AsyncMock(return_value=2)
    mock_db.agents.find.return_value.to_list = AsyncMock(return_value=[
        {"id": "agent-1", "meta": {"capabilities": {"fim": {"enabled": True}}}}
    ])
    mock_db.fim_events.count_documents = AsyncMock(return_value=0)

    response = client.get("/api/security-ops/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["totalFindings"] == 3
    assert data["criticalFindings"] == 2
    assert data["openRemediations"] == 2
    assert data["agentsWithFim"] == 1
    assert data["fimDriftDetected"] is False
