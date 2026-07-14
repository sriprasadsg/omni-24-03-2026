"""Questionnaire answer review workflow — submit/approve/reject/needs_revision/mark-submitted.

Reviews stored in `questionnaire_answer_reviews`. Drafts stored in
`questionnaire_answer_drafts` (created by plan 30-04). Published-state machines:

  draft (status=pending_review)
    → approved | rejected | needs_revision        (decision)
    → submitted                                  (terminal; only from approved)

T3 guard: `mark_submitted` filters on {status:"approved"} — the only DB query
that can transition to "submitted". A draft in any other state returns None.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

QUESTIONNAIRE_ANSWER_REVIEWS_COL = "questionnaire_answer_reviews"
QUESTIONNAIRE_ANSWER_DRAFTS_COL = "questionnaire_answer_drafts"

_VALID_DECISIONS = {"approved", "rejected", "needs_revision"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_review_id() -> str:
    return f"qar-{uuid.uuid4().hex}"


async def create_review(draft_id: str, db, tenant_id: str) -> Dict[str, Any]:
    """Insert a pending review record for the draft; refuse if no matching pending draft."""
    draft = await db[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find_one(
        {"id": draft_id, "tenantId": tenant_id, "status": "pending_review"}
    )
    if draft is None:
        return None
    review_doc = {
        "id": _generate_review_id(),
        "draftId": draft_id,
        "tenantId": tenant_id,
        "status": "pending",
        "comment": None,
        "decided_by": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db[QUESTIONNAIRE_ANSWER_REVIEWS_COL].insert_one(review_doc)
    review_doc.pop("_id", None)
    return review_doc


async def update_review_decision(
    review_id: str,
    draft_id: str,
    decision: str,
    comment: Optional[str],
    db,
    tenant_id: str,
    decided_by: Optional[str] = None,
    edited_answer_text: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Validate/apply a decision; propagate review status to the draft doc."""
    if decision not in _VALID_DECISIONS:
        raise ValueError(f"invalid decision: {decision}")
    if decision in ("rejected", "needs_revision") and not comment:
        raise ValueError("comment required for decision")
    review = await db[QUESTIONNAIRE_ANSWER_REVIEWS_COL].find_one_and_update(
        {"id": review_id, "draftId": draft_id, "tenantId": tenant_id, "status": "pending"},
        {"$set": {"status": "completed", "comment": comment, "decided_by": decided_by, "updated_at": _now_iso()}},
    )
    if review is None:
        return None
    now = _now_iso()
    draft_update = {
        "status": decision,
        "reviewerId": decided_by,
        "decidedAt": now,
        "reviewComment": comment,
        "updatedAt": now,
    }
    if edited_answer_text is not None:
        draft_update["answerText"] = edited_answer_text
    await db[QUESTIONNAIRE_ANSWER_DRAFTS_COL].update_one(
        {"id": draft_id, "tenantId": tenant_id},
        {"$set": draft_update},
    )
    return await db[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find_one({"id": draft_id, "tenantId": tenant_id}, {"_id": 0})


async def mark_submitted(draft_id: str, db, tenant_id: str, submitted_by: str) -> Optional[Dict[str, Any]]:
    """T3 guard: only `approved` drafts transition to `submitted`."""
    now = _now_iso()
    return await db[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find_one_and_update(
        {"id": draft_id, "tenantId": tenant_id, "status": "approved"},
        {"$set": {"status": "submitted", "submitted_by": submitted_by, "submitted_at": now, "updatedAt": now}},
        return_document=True,
        projection={"_id": 0},
    )


async def list_reviews(draft_id: str, db, tenant_id: str):
    cursor = db[QUESTIONNAIRE_ANSWER_REVIEWS_COL].find({"draftId": draft_id, "tenantId": tenant_id}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(length=None)


async def list_pending_drafts(db, tenant_id: str):
    cursor = db[QUESTIONNAIRE_ANSWER_DRAFTS_COL].find({"tenantId": tenant_id, "status": "pending_review"}, {"_id": 0})
    return await cursor.to_list(length=None)