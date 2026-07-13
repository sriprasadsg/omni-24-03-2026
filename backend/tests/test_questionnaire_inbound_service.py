"""Tests for Phase 30-02: Inbound Questionnaire Intake."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from backend.questionnaire_inbound_endpoints import router
from backend.questionnaire_inbound_service import questionnaire_inbound_service

def make_mock_user():
    u = MagicMock()
    u.username = "testuser"
    u.tenant_id = "test_tenant"
    u.roles = ["user"]
    return u

@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    # Patch the exact import used by questionnaire_inbound_endpoints
    a.dependency_overrides[router.routes[0].dependencies[0].dependency] = lambda: make_mock_user()
    # The above won't work directly; we patch at module level instead
    return a

@pytest.fixture(autouse=True)
def mock_auth():
    # Patch the exact module where get_current_user is imported in questionnaire_inbound_endpoints
    with patch('authentication_service.get_current_user', lambda: make_mock_user()):
        yield

@pytest.fixture
def mock_db():
    m = MagicMock()
    m.questionnaire_inbound = AsyncMock()
    m.questionnaire_inbound.find.return_value.to_list = AsyncMock(return_value=[])
    return m

TEST_SET = {"id":"qni-1","tenantId":"test_tenant","title":"T","questions":[{"id":"q1","text":"Q?","rowIndex":0}],"status":"Draft","createdBy":"testuser","created_at":"2000-01-01","updated_at":"2000-01-01"}

def test_app_fixture(app):
    assert app is not None

@pytest.mark.asyncio
async def test_create_success(app, mock_db):
    with patch('backend.questionnaire_inbound_service.get_database') as gdb:
        mock_db.questionnaire_inbound.insert_one = AsyncMock()
        gdb.return_value = mock_db
        c = TestClient(app)
        r = c.post("/api/questionnaires/inbound/", json={"title":"T","questions":[{"text":"Q?"}]})
        assert r.status_code == 200
        assert r.json()["id"].startswith("qni-")
        assert r.json()["status"] == "Draft"

@pytest.mark.asyncio
async def test_list_empty(app, mock_db):
    with patch('backend.questionnaire_inbound_service.get_database') as gdb:
        gdb.return_value = mock_db
        c = TestClient(app)
        r = c.get("/api/questionnaires/inbound/")
        assert r.status_code == 200
        assert r.json() == []

@pytest.mark.asyncio
async def test_list_with_data(app, mock_db):
    with patch('backend.questionnaire_inbound_service.get_database') as gdb:
        mock_db.questionnaire_inbound.find.return_value.to_list = AsyncMock(return_value=[TEST_SET])
        gdb.return_value = mock_db
        c = TestClient(app)
        r = c.get("/api/questionnaires/inbound/")
        assert r.status_code == 200
        assert len(r.json()) == 1

@pytest.mark.asyncio
async def test_get_found(app, mock_db):
    with patch('backend.questionnaire_inbound_service.get_database') as gdb:
        mock_db.questionnaire_inbound.find_one = AsyncMock(return_value=TEST_SET)
        gdb.return_value = mock_db
        c = TestClient(app)
        r = c.get("/api/questionnaires/inbound/qni-1")
        assert r.status_code == 200
        assert r.json()["id"] == TEST_SET["id"]

@pytest.mark.asyncio
async def test_get_not_found(app, mock_db):
    with patch('backend.questionnaire_inbound_service.get_database') as gdb:
        mock_db.questionnaire_inbound.find_one = AsyncMock(return_value=None)
        gdb.return_value = mock_db
        c = TestClient(app)
        r = c.get("/api/questionnaires/inbound/qni-x")
        assert r.status_code == 404

@pytest.mark.asyncio
async def test_upload_csv_happy(app, mock_db):
    with patch('backend.questionnaire_inbound_service.get_database') as gdb:
        mock_db.questionnaire_inbound.find_one = AsyncMock(return_value={"id":"qni-1","tenantId":"test_tenant","questions":[]})
        mock_db.questionnaire_inbound.update_one = AsyncMock()
        gdb.return_value = mock_db
        c = TestClient(app)
        r = c.post("/api/questionnaires/inbound/qni-1/upload", files={"file":("t.csv",b"Question Text\nQ1?\nQ2?","text/csv")})
        assert r.status_code == 200
        assert len(r.json()["questions"]) == 2
        assert r.json()["questions"][0]["text"] == "Q1?"

@pytest.mark.asyncio
async def test_upload_bad_header(app, mock_db):
    with patch('backend.questionnaire_inbound_service.get_database') as gdb:
        mock_db.questionnaire_inbound.find_one = AsyncMock(return_value={"id":"qni-1","tenantId":"test_tenant","questions":[]})
        gdb.return_value = mock_db
        c = TestClient(app)
        r = c.post("/api/questionnaires/inbound/qni-1/upload", files={"file":("t.csv",b"BadHeader\nv1\nv2","text/csv")})
        assert r.status_code == 400
        assert "No recognized question column header" in r.json()["detail"]

@pytest.mark.asyncio
async def test_upload_not_found(app, mock_db):
    with patch('backend.questionnaire_inbound_service.get_database') as gdb:
        mock_db.questionnaire_inbound.find_one = AsyncMock(return_value=None)
        gdb.return_value = mock_db
        c = TestClient(app)
        r = c.post("/api/questionnaires/inbound/qni-x/upload", files={"file":("t.csv",b"Question Text\nQ?.","text/csv")})
        assert r.status_code == 404