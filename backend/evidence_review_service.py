"""Evidence review workflow — submit, approve, reject, request changes.

Stores review records in `evidence_reviews` collection and tracks the current
review state on each evidence object via `asset_compliance.evidence[].status`.

Review lifecycle:
  Uploaded → submit-for-review → pending_review
    → approved              → approved
    → rejected              → rejected
    → changes_requested     → needs_revision → submit-for-review → pending_review
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_EVIDENCE_REVIEWS_COL = "evidence_reviews"

# ── Helpers ────────────────────────────────────────────────────────────────────


def _generate_id() -> str:
    return f"rev-{uuid.uuid4().hex}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_decisions() -> set[str]:
    return {"approved", "rejected", "changes_requested"}


def requires_comment(decision: str) -> bool:
    """Returns True when a comment is mandatory for this decision."""
    return decision in ("rejected", "changes_requested")


# ── Review lifecycle ───────────────────────────────────────────────────────────


async def submit_for_review(
    evidence_id: str,
    db,
    tenant_id: str,
) -> bool:
    """Set evidence status to pending_review (no review record created yet).

    Uses positional $ operator — evidence.id must be unique within the array.
    Returns True if a document was actually modified.
    """
    result = await db.asset_compliance.update_one(
        {"evidence.id": evidence_id, "tenantId": tenant_id},
        {
            "$set": {
                "evidence.$.status": "pending_review",
                "evidence.$.review_updated_at": _now_iso(),
            }
        },
    )
    return result.modified_count > 0


async def create_review(
    evidence_id: str,
    reviewer: str,
    comment: str,
    db,
    tenant_id: str,
) -> dict:
    """Create a new review record with status 'pending'."""
    now = _now_iso()
    review = {
        "id": _generate_id(),
        "tenantId": tenant_id,
        "evidenceId": evidence_id,
        "reviewer": reviewer,
        "status": "pending",
        "comment": comment,
        "created_at": now,
        "updated_at": now,
    }
    await db._db[_EVIDENCE_REVIEWS_COL].insert_one(review)
    return review


async def update_review_decision(
    review_id: str,
    decision: str,
    comment: str,
    db,
    tenant_id: str,
) -> dict | None:
    """Update a review decision and propagate status to the evidence record.

    decision must be one of: approved, rejected, changes_requested.
    rejected / changes_requested require a non-empty comment.

    Evidence status mapping:
      approved          → approved
      rejected          → rejected
      changes_requested → needs_revision

    Scoped to tenant_id to prevent cross-tenant access to review records.

    Returns the updated review dict, or None if not found.
    """
    now = _now_iso()
    decision = decision.lower()
    if decision not in _valid_decisions():
        raise ValueError(f"Invalid decision '{decision}'. Must be one of {_valid_decisions()}")

    evidence_status = {
        "approved": "approved",
        "rejected": "rejected",
        "changes_requested": "needs_revision",
    }[decision]

    # 1. Update the review record
    review = await db._db[_EVIDENCE_REVIEWS_COL].find_one_and_update(
        {"id": review_id, "tenantId": tenant_id},
        {
            "$set": {
                "status": decision,
                "comment": comment,
                "updated_at": now,
            }
        },
        return_document=True,
    )
    if not review:
        return None

    # 2. Propagate status to evidence record in asset_compliance
    evidence_id = review.get("evidenceId", "")
    if evidence_id:
        await db.asset_compliance.update_one(
            {"evidence.id": evidence_id, "tenantId": tenant_id},
            {
                "$set": {
                    "evidence.$.status": evidence_status,
                    "evidence.$.review_updated_at": now,
                }
            },
        )

    return review


async def get_reviews(
    evidence_id: str,
    db,
    tenant_id: str,
) -> list[dict]:
    """Return all review records for a given evidence item, newest first."""
    cursor = (
        db._db[_EVIDENCE_REVIEWS_COL]
        .find({"evidenceId": evidence_id, "tenantId": tenant_id})
        .sort("created_at", -1)
    )
    return await cursor.to_list(length=None)


async def get_pending_evidence(
    db,
    tenant_id: str,
) -> list[dict]:
    """Return all asset compliance documents with pending_review evidence.

    Uses $unwind + $match aggregation to flatten the evidence array and
    filter to only items with status === 'pending_review'.
    """
    pipeline = [
        {"$match": {"tenantId": tenant_id}},
        {"$unwind": "$evidence"},
        {"$match": {"evidence.status": "pending_review"}},
        {
            "$project": {
                "assetId": 1,
                "controlId": 1,
                "status": 1,
                "lastUpdated": 1,
                "checkName": 1,
                "evidence_id": "$evidence.id",
                "evidence_name": "$evidence.name",
                "evidence_date": "$evidence.uploadedAt",
                "evidence_agent_type": "$evidence.agent_type",
            }
        },
        {"$sort": {"evidence.review_updated_at": -1}},
    ]
    cursor = db.asset_compliance.aggregate(pipeline)
    return await cursor.to_list(length=None)
