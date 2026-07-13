"""Phase 30 tests — questionnaire answer review endpoints.

Covers the review state machine over HTTP: create review (pending drafts
only), decide (approved / rejected / needs_revision with validation),
T3 submit guard (approved-only), and listing.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication_service import get_current_user
import questionnaire_answer_review_endpoints as ep_mod
from questionnaire_answer_review_service import (
    QUESTIONNAIRE_ANSWER_REVIEWS_COL,
    QUESTIONNAIRE_ANSWER_DRAFTS_COL,
)

TENANT = "tenant-123"
DRAFT_ID = "draft-123"
REVIEW_ID = "review-123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_col():
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock()
    col.find_one_and_update = AsyncMock(return_value=None)
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[])
    col.find = MagicMock(return_value=cursor)
    return col


def _make_db():
    """db is subscripted by collection name in the service — dict-backed mock."""
    cols = {
        QUESTIONNAIRE_ANSWER_REVIEWS_COL: _make_col(),
        QUESTIONNAIRE_ANSWER_DRAFTS_COL: _make_col(),
    }
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=cols.__getitem__)
    return db, cols


def _make_client():
    app = FastAPI()
    app.include_router(ep_mod.router)
    user = MagicMock()
    user.username = "testuser"
    user.tenant_id = TENANT
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _db_patch(db):
    return patch("questionnaire_answer_review_endpoints.get_database", MagicMock(return_value=db))


BASE = "/api/questionnaire-answer-drafts"


# ---------------------------------------------------------------------------
# Create review
# ---------------------------------------------------------------------------

def test_create_review_endpoint_success():
    db, cols = _make_db()
    cols[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find_one = AsyncMock(return_value={
        "id": DRAFT_ID, "tenantId": TENANT, "status": "pending_review",
    })
    client = _make_client()
    with _db_patch(db):
        resp = client.post(f"{BASE}/{DRAFT_ID}/review")

    assert resp.status_code == 200
    data = resp.json()
    assert data["draftId"] == DRAFT_ID
    assert data["status"] == "pending"
    cols[QUESTIONNAIRE_ANSWER_REVIEWS_COL].insert_one.assert_awaited_once()


def test_create_review_endpoint_draft_not_found():
    db, _ = _make_db()  # find_one defaults to None
    client = _make_client()
    with _db_patch(db):
        resp = client.post(f"{BASE}/invalid/review")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Review decision
# ---------------------------------------------------------------------------

def test_update_review_decision_success():
    db, cols = _make_db()
    cols[QUESTIONNAIRE_ANSWER_REVIEWS_COL].find_one_and_update = AsyncMock(return_value={
        "id": REVIEW_ID, "draftId": DRAFT_ID, "status": "pending",
    })
    cols[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find_one = AsyncMock(return_value={
        "id": DRAFT_ID, "tenantId": TENANT, "status": "approved",
    })
    client = _make_client()
    with _db_patch(db):
        resp = client.patch(
            f"{BASE}/{DRAFT_ID}/review/{REVIEW_ID}",
            json={"decision": "approved", "comment": "Looks good"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    cols[QUESTIONNAIRE_ANSWER_DRAFTS_COL].update_one.assert_awaited_once()


def test_update_review_decision_missing_payload():
    db, _ = _make_db()
    client = _make_client()
    with _db_patch(db):
        resp = client.patch(f"{BASE}/{DRAFT_ID}/review/{REVIEW_ID}", json={})
    assert resp.status_code == 400
    assert "decision required" in resp.json()["detail"]


def test_update_review_decision_invalid_decision():
    db, _ = _make_db()
    client = _make_client()
    with _db_patch(db):
        resp = client.patch(
            f"{BASE}/{DRAFT_ID}/review/{REVIEW_ID}",
            json={"decision": "bad-decision"},
        )
    assert resp.status_code == 400
    assert "invalid decision" in resp.json()["detail"]


def test_update_review_decision_requires_comment():
    db, _ = _make_db()
    client = _make_client()
    with _db_patch(db):
        resp = client.patch(
            f"{BASE}/{DRAFT_ID}/review/{REVIEW_ID}",
            json={"decision": "rejected"},
        )
    assert resp.status_code == 400
    assert "comment required" in resp.json()["detail"]


def test_update_review_decision_review_not_found():
    db, _ = _make_db()  # find_one_and_update defaults to None
    client = _make_client()
    with _db_patch(db):
        resp = client.patch(
            f"{BASE}/{DRAFT_ID}/review/{REVIEW_ID}",
            json={"decision": "approved"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Submit (T3 guard)
# ---------------------------------------------------------------------------

def test_submit_draft_success():
    db, cols = _make_db()
    cols[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find_one_and_update = AsyncMock(return_value={
        "id": DRAFT_ID, "tenantId": TENANT, "status": "submitted",
        "submitted_by": "testuser",
    })
    client = _make_client()
    with _db_patch(db):
        resp = client.post(f"{BASE}/{DRAFT_ID}/submit")

    assert resp.status_code == 200
    assert resp.json()["status"] == "submitted"
    # T3 guard: the transition query must filter on approved status
    query = cols[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find_one_and_update.call_args.args[0]
    assert query["status"] == "approved"


def test_submit_draft_not_approved():
    db, _ = _make_db()  # find_one_and_update → None (no approved draft matched)
    client = _make_client()
    with _db_patch(db):
        resp = client.post(f"{BASE}/{DRAFT_ID}/submit")
    assert resp.status_code == 409
    assert "must be in approved state" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_list_reviews_empty():
    db, _ = _make_db()
    client = _make_client()
    with _db_patch(db):
        resp = client.get(f"{BASE}/{DRAFT_ID}/reviews")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_pending_drafts_success():
    db, cols = _make_db()
    cursor = cols[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find.return_value
    cursor.to_list = AsyncMock(return_value=[
        {"id": DRAFT_ID, "tenantId": TENANT, "status": "pending_review"},
    ])
    client = _make_client()
    with _db_patch(db):
        resp = client.get(f"{BASE}/pending-review")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list) and len(body) == 1
    # tenant scoping enforced in the query
    query = cols[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find.call_args.args[0]
    assert query["tenantId"] == TENANT
