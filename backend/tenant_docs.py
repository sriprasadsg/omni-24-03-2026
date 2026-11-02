"""The one organization document builder (Phase 87).

A direct customer (``tenant_endpoints.create_tenant``, switched over in plan 87-10) and a partner's
customer (``partner_portal_service.create_customer``) are the same kind of document, so both come from
``build_tenant_doc``. ``partnerId`` is written only for a partner's customer: an absent ``partnerId``
means a direct customer (D-12, no backfill).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

import agent_capabilities
import licensing

logger = logging.getLogger(__name__)


def build_tenant_doc(
    name: str,
    *,
    max_agents: int,
    enabled_features: Iterable[str],
    subscription_tier: str = "Free",
    notification_preferences: Optional[Dict[str, Any]] = None,
    partner_id: Optional[str] = None,
) -> Dict[str, Any]:
    """The document ``create_tenant`` has always stored, plus ``partnerId`` when one is given."""
    now = datetime.now(timezone.utc).isoformat()
    doc: Dict[str, Any] = {
        "id": f"tenant_{uuid.uuid4().hex[:12]}",
        "name": name,
        "subscriptionTier": subscription_tier,
        "registrationKey": f"reg_{uuid.uuid4().hex}",
        # Exactly what was selected: no screen is added because its feature is on (spec C6).
        "enabledFeatures": list(dict.fromkeys(enabled_features)),
        "agentCapabilities": agent_capabilities.every_capability(),
        "notificationPreferences": notification_preferences or {},
        "emailConfig": {},
        "maxAgents": max_agents,
        "license": {"maxAgents": max_agents, "seatsUsed": 0,
                    "inactiveReclaimDays": licensing.DEFAULT_RECLAIM_DAYS},
        "createdAt": now,
        "updatedAt": now,
    }
    if partner_id:
        doc["partnerId"] = partner_id
    return doc


async def ensure_tenant_extras(raw, tenant_id: str) -> None:
    """The new tenant gets an explicit Autonomous Ops level now; startup's ensure_all_tenants is the
    backstop, so a failure here never blocks tenant creation."""
    try:
        from autonomous_ops import settings as autonomy_settings
        await autonomy_settings.ensure_tenant(raw, tenant_id)
    except Exception as exc:
        logger.warning("autonomy settings for new tenant %s were not created: %s", tenant_id, exc)
