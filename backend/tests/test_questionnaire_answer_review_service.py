"""Tests for Phase 30-03: Questionnaire Answer Review Service."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from backend.questionnaire_answer_review_service import (
    create_review,
    update_review_decision,
    mark_submitted,
    list_reviews,
    list_pending_drafts,
)

@pytest.fixture
def mock_db():
    """Create mock database with both collections."""
    db = MagicMock()
    db["questionnaire_answer_reviews"] = AsyncMock()
    db["questionnaire_answer_drafts"] = AsyncMock()
    return db

def test_create_review_success(mock_db):
    """Test creating a review for a valid draft."""
    # Mock the draft query
    mock_draft = {"id": "draft-1", "tenantId": "tenant-1", "status": "pending_review"}
    mock_db["questionnaire_answer_drafts"].find_one = AsyncMock(return_value=mock_draft)

    # Mock the review insertion
    mock_db["questionnaire_answer_reviews"].insert_one = AsyncMock()

    review = create_review("draft-1", mock_db, "tenant-1")

    assert review is not None
    assert review["id"].startswith("qar-")
    assert review["draftId"] == "draft-1"
    assert review["tenantId"] == "tenant-1"
    assert review["status"] == "pending"

    mock_db["questionnaire_answer_drafts"].find_one.assert_called_once_with(
        {"id": "draft-1", "tenantId": "tenant-1", "status": "pending_review"}
    )
    mock_db["questionnaire_answer_reviews"].insert_one.assert_called_once()

def test_create_review_draft_not_found(mock_db):
    """Test creating a review for a draft that doesn't exist."""
    mock_db["questionnaire_answer_drafts"].find_one = AsyncMock(return_value=None)

    review = create_review("draft-not-found", mock_db, "tenant-1")

    assert review is None
    mock_db["questionnaire_answer_drafts"].find_one.assert_called_once_with(
        {"id": "draft-not-found", "tenantId": "tenant-1", "status": "pending_review"}
    )

def test_create_review_draft_wrong_status(mock_db):
    """Test creating a review for a draft that is not in pending_review state."""
    # Mock a draft with a different status
    mock_draft = {"id": "draft-1", "tenantId": "tenant-1", "status": "submitted"}
    mock_db["questionnaire_answer_drafts"].find_one = AsyncMock(return_value=mock_draft)

    review = create_review("draft-1", mock_db, "tenant-1")

    assert review is None  # Should return None for wrong status
    mock_db["questionnaire_answer_drafts"].find_one.assert_called_once_with(
        {"id": "draft-1", "tenantId": "tenant-1", "status": "pending_review"}
    )

def test_update_review_decision_success(mock_db):
    """Test updating review decision for a pending review."""
    # Mock the review
    mock_review = {"id": "rev-1", "draftId": "draft-1", "tenantId": "tenant-1", "status": "pending"}
    mock_db["questionnaire_answer_reviews"].find_one_and_update = AsyncMock(return_value=mock_review)
    mock_db["questionnaire_answer_drafts"].update_one = AsyncMock()
    mock_db["questionnaire_answer_drafts"].find_one = AsyncMock(return_value={
        "id": "draft-1", "tenantId": "tenant-1", "status": "approved"
    })

    result = update_review_decision(
        "review-1", "draft-1", "approved", "Looks good", mock_db, "tenant-1",
        decided_by="user1", edited_answer_text=None
    )

    assert result is not None
    assert result["id"] == "draft-1"

    mock_db["questionnaire_answer_reviews"].find_one_and_update.assert_called_once_with(
        {"id": "review-1", "draftId": "draft-1", "tenantId": "tenant-1", "status": "pending"},
        {"$set": {"status": "completed", "comment": "Looks good", "decided_by": "user1", "updated_at": pytest.ANY}}
    )
    mock_db["questionnaire_answer_drafts"].update_one.assert_called_once_with(
        {"id": "draft-1", "tenantId": "tenant-1"},
        {"$set": {
            "status": "approved",
            "reviewerId": "user1",
            "decidedAt": pytest.ANY,
            "reviewComment": "Looks good",
            "updatedAt": pytest.ANY
        }}
    )

def test_update_review_decision_invalid_decision(mock_db):
    """Test updating review with invalid decision."""
    with pytest.raises(ValueError, match="invalid decision"):
        update_review_decision(
            "review-1", "draft-1", "invalid_decision", "comment", mock_db, "tenant-1",
            decided_by="user1"
        )

def test_update_review_decision_comment_required(mock_db):
    """Test that comment is required for certain decisions."""
    with pytest.raises(ValueError, match="comment required"):
        update_review_decision(
            "review-1", "draft-1", "rejected", None, mock_db, "tenant-1",
            decided_by="user1"
        )

def test_mark_submitted_success(mock_db):
    """Test marking a draft as submitted when it's approved."""
    mock_draft = {"id": "draft-1", "tenantId": "tenant-1", "status": "approved"}
    mock_db["questionnaire_answer_drafts"].find_one_and_update = AsyncMock(return_value=mock_draft)

    result = mark_submitted("draft-1", mock_db, "tenant-1", "user1")

    assert result is not None
    assert result["id"] == "draft-1"

    mock_db["questionnaire_answer_drafts"].find_one_and_update.assert_called_once_with(
        {"id": "draft-1", "tenantId": "tenant-1", "status": "approved"},
        {"$set": {"status": "submitted", "submitted_by": "user1", "submitted_at": pytest.ANY, "updatedAt": pytest.ANY}},
        return_document=True
    )

def test_mark_submitted_draft_not_approved(mock_db):
    """Test marking a draft as submitted when it's not in approved state."""
    mock_draft = {"id": "draft-1", "tenantId": "tenant-1", "status": "pending_review"}
    mock_db["questionnaire_answer_drafts"].find_one_and_update = AsyncMock(return_value=None)

    result = mark_submitted("draft-1", mock_db, "tenant-1", "user1")

    assert result is None  # Should return None for wrong status

    mock_db["questionnaire_answer_drafts"].find_one_and_update.assert_called_once_with(
        {"id": "draft-1", "tenantId": "tenant-1", "status": "approved"},
        {"$set": {"status": "submitted", "submitted_by": "user1", "submitted_at": pytest.ANY, "updatedAt": pytest.ANY}},
        return_document=True
    )

def test_list_reviews(mock_db):
    """Test listing reviews for a draft."""
    mock_reviews = [{"id": "rev-1", "draftId": "draft-1", "tenantId": "tenant-1", "status": "pending"}]
    mock_db["questionnaire_answer_reviews"].find.return_value.to_list = AsyncMock(return_value=mock_reviews)

    result = list_reviews("draft-1", mock_db, "tenant-1")

    assert len(result) == 1
    assert result[0]["id"] == "rev-1"
    mock_db["questionnaire_answer_reviews"].find.assert_called_once_with(
        {"draftId": "draft-1", "tenantId": "tenant-1"}
    )

def test_list_pending_drafts(mock_db):
    """Test listing pending drafts for a tenant."""
    mock_drafts = [{"id": "draft-1", "tenantId": "tenant-1", "status": "pending_review"}]
    mock_db["questionnaire_answer_drafts"].find.return_value.to_list = AsyncMock(return_value=mock_drafts)

    result = list_pending_drafts(mock_db, "tenant-1")

    assert len(result) == 1
    assert result[0]["id"] == "draft-1"
    mock_db["questionnaire_answer_drafts"].find.assert_called_once_with(
        {"tenantId": "tenant-1", "status": "pending_review"}
    )