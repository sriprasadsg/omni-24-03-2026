"""
Agent Security Feed Endpoints — Phase 50 (NSCAN-02/03)

GET /api/agents/security/feed-bundle — serves the ed25519-signed SQLite feed
bundle (agent_security_feed_service) to an authenticated agent. The agent sends
its current version via ?have=<version>; when it matches the current bundle the
endpoint returns a no-op (no body re-send). Agent-authenticated via
verify_agent_key (the same dep agent endpoints use) — NOT get_current_user,
since the agent (not a browser) calls this.
"""
import base64
import logging

from fastapi import APIRouter, Depends, Response

import agent_security_feed_service as feed
from agent_auth import verify_agent_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents/security", tags=["Agent Security Feed"])


@router.get("/feed-bundle")
async def get_feed_bundle(have: str | None = None, _agent=Depends(verify_agent_key)):
    """
    Return the signed feed bundle + version + detached signature.

    ?have=<version> equal to the current version → a no-op (updated: false),
    so an up-to-date agent does not re-download the body.
    """
    version = feed.bundle_version()
    if have and have == version:
        return {"updated": False, "version": version}

    data = feed.build_bundle()
    sig = feed.sign_bundle(data)
    return Response(
        content=bytes(data),
        media_type="application/octet-stream",
        headers={
            "X-Feed-Version": version,
            "X-Feed-Signature": base64.b64encode(sig).decode(),
            "X-Feed-Updated": "true",
        },
    )
