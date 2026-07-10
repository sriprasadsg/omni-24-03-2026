"""End-to-end integration test for Phase 30: AI Questionnaire Auto-Answer.
Drives the complete pipeline: create question set -> generate draft -> review -> approve -> submit.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
import uuid

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from backend.authentication_service import get_current_user
from backend.database import get_database
import backend.questionnaire_inbound_endpoints as inbound
import backend.questionnaire_answer_draft_endpoints as draft
import backend.questionnaire_answer_review_endpoints as review
import backend.questionnaire_answer_draft_service as draft_service

def make_mock_user(username="testuser", tenant_id="tenant-123"):
    u = MagicMock()
    u.username = username
    u.tenant_id = tenant_id
    u.roles = ["user", "compliance_reviewer"]
    return u

@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(inbound.router)
    a.include_router(draft.router)
    a.include_router(review.router)
    # Mock auth for all routers
    with patch('authentication_service.get_current_user', lambda: make_mock_user()):
        yield a

@pytest.fixture
def mock_db():
    m = MagicMock()
    m.questionnaire_inbound = AsyncMock()
    m.questionnaire_answer_drafts = AsyncMock()
    m.questionnaire_answer_reviews = AsyncMock()
    return m

@pytest.mark.asyncio
async def test_questionnaire_pipeline_e2e(app, mock_db):
    "Full path: create -> generate -> review -> approve -> submit."

    with patch('backend.database.get_database', return_value=mock_db), \
         patch('backend.questionnaire_inbound_service.get_database', return_value=mock_db), \
         patch('backend.questionnaire_answer_draft_service.get_database', return_value=mock_db), \
         patch('backend.questionnaire_answer_review_service.get_database', return_value=mock_db), \
         patch('backend.rag_service.rag_service.query', new_callable=AsyncMock) as mock_rag, \
         patch('backend.ai_service.ai_service.generate_text', new_callable=AsyncMock) as mock_ai:

        # 1. Setup mocks
        mock_rag.return_value = [{"source": "doc1", "content": "MFA is required."}]
        mock_ai.return_value = '{"answer_text": "Yes, we have MFA.", "confidence": "high", "cited_indices": [0]}'

        # Mock inbound creation
        qni_id = f"qni-{uuid.uuid4().hex}"
        mock_db.questionnaire_inbound.insert_one = AsyncMock()

        # Mock draft creation
        qad_id = f"qad-{uuid.uuid4().hex}"
        mock_db.questionnaire_answer_drafts.insert_one = AsyncMock()
        mock_db.questionnaire_answer_drafts.find_one = AsyncMock(return_value={
            "id": qad_id, "tenantId": "tenant-123", "status": "pending_review",
            "answerText": "Yes, we have MFA."
        })

        # Mock review creation
        qar_id = f"qar-{uuid.uuid4().hex}"
        mock_db.questionnaire_answer_reviews.insert_one = AsyncMock()

        # Mock review update
        mock_db.questionnaire_answer_reviews.find_one_and_update = AsyncMock(return_value={
            "id": qar_id, "status": "pending"
        })

        # Mock draft update to approved
        mock_db.questionnaire_answer_drafts.update_one = AsyncMock()
        mock_db.questionnaire_answer_drafts.find_one.side_effect = [
            # first call for create_review
            {"id": qad_id, "tenantId": "tenant-123", "status": "pending_review"},
            # second call after update_review_decision
            {"id": qad_id, "tenantId": "tenant-123", "status": "approved"},
            # third call for mark_submitted
            {"id": qad_id, "tenantId": "tenant-123", "status": "approved"}
        ]

        # Mock final submission
        mock_db.questionnaire_answer_drafts.find_one_and_update = AsyncMock(return_value={
            "id": qad_id, "status": "submitted"
        })

        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

        # 1. Create Inbound Set
        resp = await client.post("/api/questionnaires/inbound/", json={"title": "Test Set"})
        assert resp.status_code == 200

        # 2. Generate Draft
        resp = await client.post("/api/questionnaire-answer-drafts/generate", params={
            "question_id": "q1", "question_text": "Do you have MFA?"
        })
        assert resp.status_code == 200

        # 3. Create Review
        resp = await client.post(f"/api/questionnaire-answer-drafts/{qad_id}/review")
        assert resp.status_code == 200

        # 4. Approve Review
        resp = await client.patch(f"/api/questionnaire-answer-drafts/{qad_id}/review/{qar_id}", json={
            "decision": "approved", "comment": "Verified."
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        # 5. Submit Draft
        resp = await client.post(f"/api/questionnaire-answer-drafts/{qad_id}/submit")
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"

@pytest.mark.asyncio
async def test_questionnaire_submit_bypass_rejection(app, mock_db):
    "Assertion: Direct pending_review -> submit call is rejected (T3)."

    qad_id = "qad-bypass"
    with patch('backend.database.get_database', return_value=mock_db), \
         patch('backend.questionnaire_answer_review_service.get_database', return_value=mock_db):

        # Implementation uses find_one_and_update with status:"approved" filter.
        # If draft is pending_review, query returns None.
        mock_db.questionnaire_answer_drafts.find_one_and_update = AsyncMock(return_value=None)

        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        resp = await client.post(f"/api/questionnaire-answer-drafts/{qad_id}/submit")

        # Service returns None -> Endpoint returns 409
        assert resp.status_code == 409
        assert "must be in approved state" in resp.json()["detail"]
