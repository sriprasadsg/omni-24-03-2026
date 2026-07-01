"""Evidence review workflow API endpoints.

Router prefix: /api/evidence (review-related sub-routes)

Role gating:
  - submit-for-review:  any authenticated user
  - create review:      any authenticated user
  - review decision:    admin / super_admin / compliance_reviewer only
  - GET reviews:        any authenticated user (own tenant)
  - GET pending:        any authenticated user (own tenant)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from rate_limiter import limiter
from evidence_review_service import (
    submit_for_review,
    create_review,
    update_review_decision,
    get_reviews,
    get_pending_evidence,
    requires_comment,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_REVIEWER_ROLES = {"admin", "super_admin", "compliance_reviewer"}


# ── Request / Response models ──────────────────────────────────────────────────


class CreateReviewRequest(BaseModel):
    comment: str = Field(..., min_length=1, max_length=2000)


class UpdateDecisionRequest(BaseModel):
    decision: str = Field(..., pattern=r"^(approved|rejected|changes_requested)$")
    comment: str = Field("", max_length=2000)


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/api/evidence/{evidence_id}/submit-for-review")
@limiter.limit("30/minute")
async def submit_evidence_for_review(
    request: Request,
    response: Response,
    evidence_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Set evidence status to pending_review."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    db = get_database()
    ok = await submit_for_review(evidence_id, db, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Evidence not found or already in review")
    return {"success": True, "status": "pending_review"}


@router.post("/api/evidence/{evidence_id}/review")
@limiter.limit("30/minute")
async def create_evidence_review(
    request: Request,
    response: Response,
    evidence_id: str,
    body: CreateReviewRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a review record for an evidence item."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    db = get_database()
    try:
        review = await create_review(
            evidence_id=evidence_id,
            reviewer=current_user.username or "unknown",
            comment=body.comment,
            db=db,
            tenant_id=tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"success": True, "review": review}


@router.patch("/api/evidence/{evidence_id}/review/{review_id}")
@limiter.limit("30/minute")
async def update_evidence_review(
    request: Request,
    response: Response,
    evidence_id: str,
    review_id: str,
    body: UpdateDecisionRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Update a review decision (approve/reject/request changes).

    Role-gated to admin / super_admin / compliance_reviewer.
    """
    if current_user.role not in _REVIEWER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only admins and compliance reviewers can make review decisions",
        )

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    if requires_comment(body.decision) and not body.comment.strip():
        raise HTTPException(
            status_code=422,
            detail=f"Comment is required for decision '{body.decision}'",
        )

    db = get_database()
    try:
        review = await update_review_decision(review_id, body.decision, body.comment, db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.get("evidenceId") != evidence_id:
        raise HTTPException(
            status_code=404,
            detail="Review does not belong to the specified evidence item",
        )

    # Non-repudiable audit trail for review decisions — the review record itself
    # is mutable in place, so this is the only append-only record of who decided
    # what and when (T-10).
    await db.audit_logs.insert_one({
        "action": "evidence_review_decision",
        "tenantId": tenant_id,
        "evidence_id": evidence_id,
        "review_id": review_id,
        "decision": body.decision,
        "performed_by": current_user.username or "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {"success": True, "review": review}


@router.get("/api/evidence/{evidence_id}/reviews")
async def list_evidence_reviews(
    evidence_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Return all review records for an evidence item, newest first."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    db = get_database()
    reviews = await get_reviews(evidence_id, db, tenant_id)
    return {"reviews": reviews, "count": len(reviews)}


@router.get("/api/evidence/pending-review")
async def list_pending_review_evidence(
    current_user: TokenData = Depends(get_current_user),
):
    """Return all evidence with pending_review status for this tenant."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    db = get_database()
    items = await get_pending_evidence(db, tenant_id)
    return {"items": items, "count": len(items)}
