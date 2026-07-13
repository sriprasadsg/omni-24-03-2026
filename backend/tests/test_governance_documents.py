"""Tests for Governance Document Management."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from auth_types import TokenData

# ─── helpers ─────────────────────────────────────────────────────────────────

def _col():
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id='x'))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.find = MagicMock()
    mock_cursor = AsyncMock()
    mock_cursor.sort.return_value.to_list = AsyncMock(return_value=[])
    col.find.return_value = mock_cursor
    return col

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.governance_documents = _col()
    db.roles = MagicMock()
    db.roles.find_one = AsyncMock(return_value=None)
    return db

@pytest.fixture
def client(mock_db):
    with patch('rbac_utils.get_database', return_value=mock_db):
        with patch('governance_document_endpoints.get_database', return_value=mock_db):
            # This is the critical patch for database.mongodb.db
            with patch('database.mongodb.db', new_callable=MagicMock, return_value=mock_db.governance_documents.database):
                from authentication_service import get_current_user
                from governance_document_endpoints import router
                from rbac_utils import require_permission

                app = FastAPI()
                app.include_router(router)
                # Mock auth
                mock_user = MagicMock(spec=TokenData)
                mock_user.tenant_id = 'tenant-a'
                mock_user.role = 'admin'
                mock_user.username = 'user@tenant.com'
                app.dependency_overrides[get_current_user] = lambda: mock_user
                app.dependency_overrides[require_permission] = lambda perm: lambda: mock_user
                yield TestClient(app, raise_server_exceptions=True)

# ─── tests ─────────────────────────────────────────────────────────────────

class TestGovernanceDocuments:

    def test_create_document(self, client):
        res = client.post('/api/governance/documents', json={
            'title': 'Policy A',
            'content': 'Body',
            'doc_type': 'policy'
        })
        assert res.status_code == 200
        data = res.json()
        assert data['status'] == 'draft'
        assert data['current_version'] == 1