"""Tests for Phase 30-03: Questionnaire Answer Review Service."""
import pytest
from unittest.mock import ANY, AsyncMock, MagicMock, patch

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

TEST_DRAFT_ID = "draft-123"
TEST_REVIEW_ID = "review-123"
TEST_TENANT_ID = "tenant-123"

def make_mock_db():
    """Use an object with attribute-based collection access for proper mock chaining."""
    class MockDB:
        def __init__(self):
            self.reviews = AsyncMock()
            self.drafts = AsyncMock()
        def __getitem__(self, key):
            if key == "questionnaire_answer_reviews":
                return self.reviews
            elif key == "questionnaire_answer_drafts":
                return self.drafts
            return AsyncMock()
    return MockDB()

def set_pending_draft(db):
    db.drafts.find_one = AsyncMock(return_value={"id": TEST_DRAFT_ID, "tenantId": TEST_TENANT_ID, "status": "pending_review"})

@pytest.mark.asyncio
async def test_create_review_success():
    """Create review for valid pending draft."""
    db = make_mock_db()
    set_pending_draft(db)
    db.reviews.insert_one = AsyncMock()

    review = await create_review(TEST_DRAFT_ID, db, TEST_TENANT_ID)

    assert review is not None
    assert review["id"].startswith("qar-")
    assert review["draftId"] == TEST_DRAFT_ID
    assert review["tenantId"] == TEST_TENANT_ID
    assert review["status"] == "pending"
    db.drafts.find_one.assert_called_once_with(
        {"id": TEST_DRAFT_ID, "tenantId": TEST_TENANT_ID, "status": "pending_review"}
    )
    db.reviews.insert_one.assert_called_once()

@pytest.mark.asyncio
async def test_create_review_draft_not_found():
    """Create review for non-existent draft returns None."""
    db = make_mock_db()
    db.drafts.find_one = AsyncMock(return_value=None)

    review = await create_review("non-existent", db, TEST_TENANT_ID)
    assert review is None

@pytest.mark.asyncio
async def test_create_review_draft_wrong_status():
    """Create review for draft not in pending_review returns None."""
    db = make_mock_db()
    # Mock returns None when filter doesn't match (status != pending_review)
    async def find_one_mock(filter_dict):
        if filter_dict.get("status") == "pending_review":
            return None  # draft exists but wrong status
        return None
    db.drafts.find_one = AsyncMock(side_effect=find_one_mock)

    review = await create_review(TEST_DRAFT_ID, db, TEST_TENANT_ID)
    assert review is None

@pytest.mark.asyncio
async def test_update_review_decision_success():
    """Update review decision propagates to draft."""
    db = make_mock_db()
    db.reviews.find_one_and_update = AsyncMock(
        return_value={"id": TEST_REVIEW_ID, "draftId": TEST_DRAFT_ID, "tenantId": TEST_TENANT_ID, "status": "pending"}
    )
    db.drafts.update_one = AsyncMock()
    db.drafts.find_one = AsyncMock(
        return_value={"id": TEST_DRAFT_ID, "tenantId": TEST_TENANT_ID, "status": "approved"}
    )

    result = await update_review_decision(
        TEST_REVIEW_ID, TEST_DRAFT_ID, "approved", "Looks good", db, TEST_TENANT_ID,
        decided_by="reviewer1", edited_answer_text=None
    )

    assert result is not None
    assert result["id"] == TEST_DRAFT_ID
    db.reviews.find_one_and_update.assert_called_once_with(
        {"id": TEST_REVIEW_ID, "draftId": TEST_DRAFT_ID, "tenantId": TEST_TENANT_ID, "status": "pending"},
        {"$set": {"status": "completed", "comment": "Looks good", "decided_by": "reviewer1", "updated_at": ANY}},
    )
    db.drafts.update_one.assert_called_once_with(
        {"id": TEST_DRAFT_ID, "tenantId": TEST_TENANT_ID},
        {"$set": {"status": "approved", "reviewerId": "reviewer1", "decidedAt": ANY, "reviewComment": "Looks good", "updatedAt": ANY}}
    )

@pytest.mark.asyncio
async def test_update_review_decision_invalid():
    """Invalid decision raises ValueError."""
    db = make_mock_db()
    with pytest.raises(ValueError, match="invalid decision"):
        await update_review_decision(
            TEST_REVIEW_ID, TEST_DRAFT_ID, "invalid_decision", "Some comment", db, TEST_TENANT_ID,
        )

@pytest.mark.asyncio
async def test_update_review_decision_comment_required():
    """Missing comment for reject/needs_revision raises ValueError."""
    db = make_mock_db()
    with pytest.raises(ValueError, match="comment required"):
        await update_review_decision(
            TEST_REVIEW_ID, TEST_DRAFT_ID, "rejected", None, db, TEST_TENANT_ID,
        )

@pytest.mark.asyncio
async def test_mark_submitted_success():
    """Mark approved draft as submitted."""
    db = make_mock_db()
    db.drafts.find_one_and_update = AsyncMock(
        return_value={"id": TEST_DRAFT_ID, "tenantId": TEST_TENANT_ID, "status": "approved"}
    )

    result = await mark_submitted(TEST_DRAFT_ID, db, TEST_TENANT_ID, "reviewer1")

    assert result is not None
    assert result["id"] == TEST_DRAFT_ID
    db.drafts.find_one_and_update.assert_called_once_with(
        {"id": TEST_DRAFT_ID, "tenantId": TEST_TENANT_ID, "status": "approved"},
        {"$set": {"status": "submitted", "submitted_by": "reviewer1", "submitted_at": ANY, "updatedAt": ANY}},
        return_document=True,
        projection={"_id": 0},
    )

@pytest.mark.asyncio
async def test_mark_submitted_not_approved():
    """Non-approved draft returns None from mark_submitted."""
    db = make_mock_db()
    db.drafts.find_one_and_update = AsyncMock(return_value=None)

    result = await mark_submitted(TEST_DRAFT_ID, db, TEST_TENANT_ID, "reviewer1")
    assert result is None

@pytest.mark.asyncio
async def test_list_reviews():
    """List reviews returns sorted list."""
    db = make_mock_db()
    cursor = AsyncMock()
    cursor.to_list = AsyncMock(return_value=[{"id": "rev-1"}])
    sort_mock = MagicMock(return_value=cursor)
    db.reviews.find = MagicMock(return_value=MagicMock(sort=sort_mock))

    result = await list_reviews(TEST_DRAFT_ID, db, TEST_TENANT_ID)

    assert len(result) == 1
    db.reviews.find.assert_called_once_with({"draftId": TEST_DRAFT_ID, "tenantId": TEST_TENANT_ID}, {"_id": 0})

@pytest.mark.asyncio
async def test_list_reviews_empty():
    """List reviews returns empty list when none exist."""
    db = make_mock_db()
    cursor = AsyncMock()
    cursor.to_list = AsyncMock(return_value=[])
    sort_mock = MagicMock(return_value=cursor)
    db.reviews.find = MagicMock(return_value=MagicMock(sort=sort_mock))

    result = await list_reviews(TEST_DRAFT_ID, db, TEST_TENANT_ID)
    assert result == []

@pytest.mark.asyncio
async def test_list_pending_drafts():
    """List pending drafts returns drafts."""
    db = make_mock_db()
    cursor = AsyncMock()
    cursor.to_list = AsyncMock(return_value=[{"id": "draft-1", "status": "pending_review"}])
    db.drafts.find = MagicMock(return_value=cursor)

    result = await list_pending_drafts(db, TEST_TENANT_ID)

    assert len(result) == 1
    assert result[0]["id"] == "draft-1"

@pytest.mark.asyncio
async def test_list_pending_drafts_empty():
    """List pending drafts returns empty list."""
    db = make_mock_db()
    cursor = AsyncMock()
    cursor.to_list = AsyncMock(return_value=[])
    db.drafts.find = MagicMock(return_value=cursor)

    result = await list_pending_drafts(db, TEST_TENANT_ID)
    assert result == []