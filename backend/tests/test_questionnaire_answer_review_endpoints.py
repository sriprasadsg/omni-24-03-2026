"""Questionnaire answer review endpoints — thin wrappers around review service functions."""
"""Simple functional glue — if any function raising ValueError or returning None breaks flow,
these tests verify alignment."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from backend.questionnaire_answer_review_service import (
    create_review,
    update_review_decision,
    mark_submitted,
    list_reviews,
    list_pending_drafts,
    QUESTIONNAIRE_ANSWER_REVIEWS_COL,
    QUESTIONNAIRE_ANSWER_DRAFTS_COL,
)
from backend.questionnaire_answer_review_endpoints import router
from database import get_database

def make_mock_user():
    u = MagicMock()
    u.username = "testuser"
    u.tenant_id = "tenant-123"
    u.roles = ["user"]
    return u

@pytest.fixture
def app():
    "FastAPI instance with router."
    a = FastAPI()
    a.include_router(router)
    # patch exact dependency path
    with patch('authentication_service.get_current_user', lambda: make_mock_user()):
        yield a

@pytest.fixture
def mock_db():
    m = MagicMock()
    m[QUESTIONNAIRE_ANSWER_REVIEWS_COL] = AsyncMock()
    m[QUESTIONNAIRE_ANSWER_DRAFTS_COL] = AsyncMock()
    # Mock find_one_and_update returning draft updated doc
    m[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find_one = AsyncMock(return_value={
        "id": "draft-123", "tenantId": "tenant-123", "status": "pending_review"
    })
    return m

TEST_DRAFT_ID = "draft-123"
TEST_REVIEW_ID = "review-123"

def test_create_review_endpoint_success(app, mock_db):
    "POST /drafts/{draft_id}/review returns review if draft found pending."
    with patch.object(sys.modules[__name__], 'get_database', return_value=mock_db):
        client = TestClient(app)
        resp = client.post(f"/questionnaire-answer-drafts/drafts/{TEST_DRAFT_ID}/review")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "status" in data

def test_create_review_endpoint_draft_not_found(app, mock_db):
    patch('backend.database.get_database', return_value=mock_db)
    mock_db[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find_one = AsyncMock(return_value=None)
    client = TestClient(app)
    resp = client.post(f"/questionnaire-answer-drafts/drafts/invalid/review")
    assert resp.status_code == 404

def test_update_review_decision_success(app, mock_db):
    "PATCH /drafts/{draft_id}/review/{review_id} can update with approved."
    with patch('backend.database.get_database', return_value=mock_db):
        client = TestClient(app)
        payload = {"decision": "approved", "comment": "Looks good"}
        resp = client.patch(
            f"/questionnaire-answer-drafts/drafts/{TEST_DRAFT_ID}/review/{TEST_REVIEW_ID}",
            json=payload
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

def test_update_review_decision_missing_payload(app, mock_db):
    patch('backend.database.get_database', return_value=mock_db)
    client = TestClient(app)
    resp = client.patch(
        f"/questionnaire-answer-drafts/drafts/{TEST_DRAFT_ID}/review/{TEST_REVIEW_ID}",
        json={}
    )
    assert resp.status_code == 400

def test_update_review_decision_invalid_decision(app, mock_db):
    patch('backend.database.get_database', return_value=mock_db)
    client = TestClient(app)
    resp = client.patch(
        f"/questionnaire-answer-drafts/drafts/{TEST_DRAFT_ID}/review/{TEST_REVIEW_ID}",
        json={"decision": "bad-decision"}
    )
    assert resp.status_code == 400

def test_update_review_decision_requires_comment(app, mock_db):
    patch('backend.database.get_database', return_value=mock_db)
    client = TestClient(app)
    resp = client.patch(
        f"/questionnaire-answer-drafts/drafts/{TEST_DRAFT_ID}/review/{TEST_REVIEW_ID}",
        json={"decision": "rejected"}
    )
    assert resp.status_code == 400

def test_submit_draft_success(app, mock_db):
    patch('backend.database.get_database', return_value=mock_db)
    with patch('backend.questionnaire_answer_review_service.mark_submitted') as mock_mark:
        mock_mark.return_value = {
            "id": TEST_DRAFT_ID, "tenantId": "tenant-123", "status": "submitted",
            "submitted_by": "testuser", "submitted_at": pytest.ANY, "updatedAt": pytest.ANY
        }
        client = TestClient(app)
        resp = client.post(
            f"/questionnaire-answer-drafts/drafts/{TEST_DRAFT_ID}/submit"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"
        mock_mark.assert_called_once()

def test_submit_draft_not_approved(app, mock_db, monkeypatch):
    patch('backend.database.get_database', return_value=mock_db)
    # Mock mark_submitted to return None (not approved)
    monkeypatch.setattr('backend.questionnaire_answer_review_service.mark_submitted',
                        lambda draft_id, get_db, tenant_id, user: None)
    client = TestClient(app)
    resp = client.post(f"/questionnaire-answer-drafts/drafts/{TEST_DRAFT_ID}/submit")
    assert resp.status_code == 409
    assert "must be in approved state" in resp.json()["detail"]

def test_list_reviews_not_found_draft(app, mock_db):
    patch('backend.database.get_database', return_value=mock_db)
    client = TestClient(app)
    resp = client.get(f"/questionnaire-answer-drafts/drafts/{TEST_DRAFT_ID}/reviews")
    assert resp.status_code == 200
    assert resp.json() == []

def test_list_reviews_empty(app, mock_db):
    patch('backend.database.get_database', return_value=mock_db)
    client = TestClient(app)
    resp = client.get(f"/questionnaire-answer-drafts/drafts/{TEST_DRAFT_ID}/reviews")
    assert resp.status_code == 200
    assert resp.json() == []

def test_list_pending_drafts_success(app, mock_db):
    patch('backend.database.get_database', return_value=mock_db)
    resp = client.get("/questionnaire-answer-drafts/pending-review")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)