"""Partner suspension, enforced in one place (Phase 87, D-15).

The token verifier calls refuse_if_suspended for partner roles on every request, so a
session issued before a suspension stops working at once, whichever login path issued it.
Sign-in and refresh call it too, to tell the user why. Always closed: a status that
cannot be read refuses the request.
"""
import logging
from typing import Any, Optional

from fastapi import HTTPException

import rbac_defaults

logger = logging.getLogger(__name__)

SUSPENDED_MESSAGE = "This partner account is suspended. Contact your platform administrator to restore access."
SUSPENDED_HEADERS = {"X-Partner-Suspended": "1"}
_UNAVAILABLE_MESSAGE = "Partner status could not be checked. Try again."


def _raw_db() -> Any:
    """The raw database handle (tests replace this)."""
    from database import get_database
    db = get_database()
    return getattr(db, "_db", db)


async def refuse_if_suspended(role: Optional[str], tenant_id: Optional[str]) -> None:
    """Raise 403 for a partner role whose partner is suspended or missing, 503 if unreadable.

    Does nothing for any other role, and makes no lookup for them.
    """
    if not rbac_defaults.is_partner_role(role):
        return
    try:
        doc = await _raw_db().tenants.find_one(
            {"id": tenant_id, "type": "partner"}, {"_id": 0, "partner.status": 1})
    except Exception as exc:
        logger.error("Partner status lookup failed for %s: %s", tenant_id, exc)
        raise HTTPException(status_code=503, detail=_UNAVAILABLE_MESSAGE) from exc
    if not doc or (doc.get("partner") or {}).get("status") != "active":
        raise HTTPException(status_code=403, detail=SUSPENDED_MESSAGE, headers=dict(SUSPENDED_HEADERS))
