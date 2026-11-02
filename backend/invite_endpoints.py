"""Public invite-link status for the accept-invite page (Phase 87, D-09).

The route is public because the invitee has no session yet: the link in the email is the only
credential they hold. The page posts the link's secret here to learn whether it is valid, expired,
used or invalid before it shows the set-password form (which itself posts to the existing
``/api/auth/reset-password/confirm``). The secret travels in the request body, never in the query
string, so access logs never hold it, and the answer never echoes it. The route is rate limited,
since a caller who can guess secrets could otherwise probe for live invites.
"""
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

import partner_invites
from database import mongodb
from rate_limiter import limiter

router = APIRouter(prefix="/api/auth/invite", tags=["Authentication"])


class InviteStatusBody(BaseModel):
    token: str = Field(..., min_length=1, max_length=512)


@router.post("/status")
@limiter.limit("10/minute")
async def invite_status(request: Request, response: Response, body: InviteStatusBody):
    """State of an invite link: valid (with organization, email, role kind), expired, used or invalid."""
    return await partner_invites.invite_state(mongodb.db, body.token)
