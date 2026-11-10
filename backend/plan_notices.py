"""Tell a tenant's administrators when its plan, seats or networks change (Phase 88, D-25).

One call writes two records: an entry in the tenant's hash-chained audit ledger (who changed what, from
and to) and an in-app notice in the tenant's feed, read only by the tenant's administrators. Neither
write may undo the change that was just made, so a failure in either is logged and swallowed; the other
record is still written. The platform organization is exempt from plans (D-26) and gets no notice.
"""
import logging
from typing import Any, Dict

import audit_ledger

logger = logging.getLogger(__name__)

PLATFORM_TENANT_ID = "platform-admin"


def _raw(db):
    return getattr(db, "_db", db)


def _actor(actor: Any) -> Dict[str, Any]:
    """The ledger actor: a ready dict, a token with username/role, or a plain e-mail string."""
    if isinstance(actor, dict):
        return actor
    if isinstance(actor, str):
        return {"email": actor}
    return {"email": getattr(actor, "username", None) or "system", "role": getattr(actor, "role", None)}


async def announce(db, tenant_id: str, *, event: str, title: str, message: str, actor: Any,
                   **details: Any) -> None:
    """Record ``event`` for ``tenant_id`` and notify its admins (D-25). ``details`` (who is in ``actor``;
    ``before``/``after`` for a number) go into both the ledger entry and the notice's metadata. Never raises."""
    if not tenant_id or tenant_id == PLATFORM_TENANT_ID:
        return
    try:
        await audit_ledger.event(event, tenant_id, actor=_actor(actor), tenantId=tenant_id, **details)
    except Exception as exc:
        logger.warning("audit for %s on tenant %s was not recorded: %s", event, tenant_id, exc)
    try:
        import pending_agents  # lazy: pending_agents imports this module lazily too
        await pending_agents._post_in_app(
            _raw(db), tenant_id, title, message, "info",
            {"event": event, "tenantId": tenant_id, "audience": pending_agents.TENANT_ADMIN_AUDIENCE, **details})
    except Exception as exc:
        logger.warning("notice for %s on tenant %s was not stored: %s", event, tenant_id, exc)
