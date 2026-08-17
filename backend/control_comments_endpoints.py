"""Control comment threads API endpoints (Phase 42, CMT-01).

Router prefix: /api/control-comments

Role gating:
  - POST (create comment): admin / super_admin / compliance_reviewer only (D-01)
  - GET  (list comments):  any authenticated tenant user (A2)

No PATCH/DELETE route exists for this resource — D-03 immutability is
enforced purely by the absence of a mutation route.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from notification_service import get_notification_service
from rate_limiter import limiter
from control_comments_service import add_comment, list_comments, resolve_mentions

logger = logging.getLogger(__name__)
router = APIRouter()

# D-01: kept in sync by hand with the equivalent literal in
# components/ControlCommentsPanel.tsx. The backend always re-enforces
# authorization server-side regardless of the frontend list, so drift here
# is a UI-confusion risk (composer visibility), not an authz bypass.
_COMMENT_AUTHOR_ROLES = {"admin", "super_admin", "compliance_reviewer"}


# ── Request models ───────────────────────────────────────────────────────────


class CreateCommentRequest(BaseModel):
    control_id: str
    text: str = Field(..., min_length=1, max_length=2000)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/api/control-comments")
@limiter.limit("30/minute")
async def post_control_comment(
    request: Request,
    response: Response,
    body: CreateCommentRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a comment on a compliance control. Role-gated (D-01)."""
    if current_user.role not in _COMMENT_AUTHOR_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only admins and compliance reviewers can comment",
        )

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    db = get_database()
    comment = await add_comment(
        db, body.control_id, author=current_user.username, text=body.text
    )
    # D-03: no PATCH/DELETE route exists for this resource anywhere — absence
    # IS the enforcement.

    for mention_email in await resolve_mentions(db, body.text):
        try:
            svc = get_notification_service(db)
            await svc.send_alert(
                title="You were mentioned in a control comment",
                message=f'{current_user.username} mentioned you: "{body.text[:120]}"',
                severity="info",
                recipients=[mention_email],
                tenant_id=tenant_id,
                channels=[],  # D-02: in-app only — no email/sms/slack dispatch
                metadata={"control_id": body.control_id, "event": "mention"},
            )
        except Exception:
            # Non-fatal: mirrors tickets_endpoints.py's mention-notification
            # error handling — a notification failure never fails the
            # comment write (T-42-07).
            pass

    return comment


@router.get("/api/control-comments")
async def get_control_comments(
    control_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """List comments on a control. Open to any authenticated tenant user (A2)
    — tenant isolation is still enforced by the db handle."""
    db = get_database()
    return await list_comments(db, control_id)
