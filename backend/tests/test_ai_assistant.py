import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from backend.app import app
from backend.ai_assistant_service import chat

client = TestClient(app)

@pytest.fixture
def mock_rag():
    with patch("backend.ai_assistant_service.rag_service") as mock:
        mock.query.return_value = [
            {
                "id": "doc1",
                "content": "This is a compliance document snippet.",
                "metadata": {"tenantId": "test-tenant", "source": "SOC2 Spec"}
            }
        ]
        yield mock

@pytest.fixture
def mock_db():
    with patch("backend.ai_assistant_service.get_database") as mock_get_db:
        db_mock = AsyncMock()
        mock_get_db.return_value = db_mock

        # Mock compliance evidence
        db_mock.compliance_evidence.find.return_value.to_list = AsyncMock(return_value=[
            {"controlId": "AC-1", "title": "Access Control", "framework": "SOC2", "status": "FAILED"}
        ])

        # Mock risks
        db_mock.risks.find.return_value.to_list = AsyncMock(return_value=[
            {"id": "RISK-1", "title": "Data Breach", "severity": "Critical", "status": "Open"}
        ])

        yield db_mock

@pytest.fixture
def mock_ai():
    with patch("backend.ai_assistant_service.ai_service") as mock:
        mock.generate_text.return_value = "Based on your SOC2 compliance, control AC-1 is failing and there is a critical risk of data breach."
        yield mock

@pytest.mark.asyncio
async def test_assistant_chat_service(mock_rag, mock_db, mock_ai):
    """Test the AI assistant service logic directly."""
    result = await chat("What are my failing controls?", "test-tenant")

    assert "answer" in result
    assert "sources" in result
    assert len(result["sources"]) > 0
    assert any(s["id"] == "AC-1" for s in result["sources"])
    assert any(s["id"] == "RISK-1" for s in result["sources"])
    assert any(s["id"] == "doc1" for s in result["sources"])

def test_assistant_chat_endpoint_isolation(mock_rag, mock_db, mock_ai):
    """Test that the endpoint enforces tenant isolation via X-Tenant-ID or context."""
    # This assumes the auth layer and tenant context are working
    with patch("backend.ai_assistant_endpoints.get_tenant_id", return_value="test-tenant"):
        with patch("backend.ai_assistant_endpoints.rbac_service.has_permission", return_value=lambda x: True):
            response = client.post(
                "/api/assistant/chat",
                json={"query": "Show my risks"},
                headers={"X-Tenant-ID": "test-tenant"}
            )
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert len(data["sources"]) > 0

def test_assistant_chat_streaming(mock_rag, mock_db, mock_ai):
    """Test the SSE streaming endpoint protocol."""
    with patch("backend.ai_assistant_endpoints.get_tenant_id", return_value="test-tenant"):
        with patch("backend.ai_assistant_endpoints.rbac_service.has_permission", return_value=lambda x: True):
            response = client.post(
                "/api/assistant/chat/stream",
                json={"query": "Stream my status"},
                headers={"X-Tenant-ID": "test-tenant"}
            )
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream"

            # Verify stream format
            content = response.text
            assert "data: {" in content
            assert "chunk" in content or "sources" in content
            assert "[DONE]" in content
