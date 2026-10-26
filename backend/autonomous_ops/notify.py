"""In-app notices for Autonomous Ops (stop pressed, circuit breaker, rate limit).

A notice goes to the platform tenant's feed and, for any other tenant, to that tenant's
admins (the pending_agents.post_to_recipients path). Phase 82 replaces the body of ``notify``
with the on-call channel; callers do not change. ``notify`` never raises: a failing notice
must not block or undo a decision.
"""
import logging
from typing import Any, Dict, Optional

from .scope import raw

logger = logging.getLogger(__name__)


async def notify(db, tenant_id: str, *, title: str, message: str, severity: str = "warning",
                 metadata: Optional[Dict[str, Any]] = None) -> None:
    try:
        import pending_agents
        await pending_agents.post_to_recipients(
            raw(db), {"id": tenant_id}, title, message, severity,
            {"source": "autonomous_ops", **(metadata or {})})
    except Exception as exc:
        logger.warning("autonomous_ops: notice %r for %s not posted: %s", title, tenant_id, exc)
