"""Simple tests for Phase 30-02: Inbound Questionnaire Intake (questionnaire_inbound_endpoints)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from backend.questionnaire_inbound_endpoints import router

def make_mock_user():
    """Create a mock user for testing."""
    user = MagicMock()
    user.username = "testuser"
    user.tenant_id = "test_tenant"
    user.roles = ["user"]
    return user

@pytest.fixture
def app():
    """Create a FastAPI app with the router."""
    application = FastAPI()
    application.include_router(router)
    return application

# Mock the auth dependency at the module level where it's used
import backend.questionnaire_inbound_endpoints
with patch.object(backend.questionnaire_inbound_endpoints, 'get_current_user', lambda: make_mock_user()):
    @pytest.fixture
    def mock_auth_app(app):
        return app

# Mock database
@pytest.fixture
def mock_db():
    m = MagicMock()
    m.questionnaire_inbound = AsyncMock()
    m.questionnaire_inbound.find.return_value.to_list = AsyncMock(return_value=[])
    return m

TEST_SET = {
    "id": "qni-1",
    "tenantId": "test_tenant",
    "title": "Test Set",
    "questions": [{"id": "q1", "text": "Q1", "rowIndex": 0}],
    "status": "Draft",
    "createdBy": "testuser",
    "created_at": "2000-01-01T00:00:00Z",
    "updated_at": "2000-01-01T00:00:00Z"
}

def test_app_fixture(app):
    """Verify the app fixture works."""
    assert app is not None

@pytest.mark.asyncio
async def test_questionnaire_inbound_modules_exist():
    """Verify that the Phase 30-02 modules have been created."""
    from backend.questionnaire_inbound_service import questionnaire_inbound_service
    from backend.questionnaire_inbound_endpoints import router

    assert questionnaire_inbound_service is not None
    assert router is not None
    print("✓ Phase 30-02 modules created successfully")

@pytest.mark.asyncio
async def test_service_import_and_interface(mock_db):
    """Test that the service can be imported and has expected methods."""
    with patch('backend.questionnaire_inbound_service.get_database') as gdb:
        gdb.return_value = mock_db
        from backend.questionnaire_inbound_service import questionnaire_inbound_service

        # Check service has the expected methods
        assert hasattr(questionnaire_inbound_service, 'create_question_set')
        assert hasattr(questionnaire_inbound_service, 'list_question_sets')
        assert hasattr(questionnaire_inbound_service, 'get_question_set')
        assert hasattr(questionnaire_inbound_service, 'parse_upload')

        print("✓ Service interface is correct")

if __name__ == "__main__":
    # Run tests directly if executed as script
    pytest.main([__file__, "-v"])