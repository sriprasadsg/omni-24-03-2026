"""Migration 037: tell tenants that the IDS/IPS compliance control was corrected (88.1, stage 1).

Until now ``ids_ips_enabled`` passed whenever a tenant had any ``security_alerts`` row from the last 7 days, which
proved no IDS at all. It now passes only for a reporting network sensor, so the control fails for every tenant
until one is connected. Every tenant the old rule passed at the moment this runs gets one in-app notice for its
admins. A tenant that already has the notice is skipped, so a second run posts nothing.
"""
import logging
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "One in-app notice per tenant whose IDS/IPS control flips from a false pass (88.1 stage 1)."
KIND = "ids_check_corrected"
TITLE = "IDS/IPS compliance control corrected"
MESSAGE = (
    "The IDS/IPS control in your compliance frameworks used to pass whenever any security alert existed. "
    "That did not prove an intrusion detection system is running, so the result was wrong. "
    "The control now passes only when a network sensor is reporting to this platform, and it shows as failed "
    "until one is connected. A firewall IPS is not verified by this platform."
)

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    import pending_agents

    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    passed = [tenant for tenant in await db.security_alerts.distinct("tenantId", {"created_at": {"$gte": cutoff}})
              if isinstance(tenant, str)]
    tenants = sorted(row["id"] for row in await db.tenants.find({"id": {"$in": passed}}, {"_id": 0, "id": 1})
                     .to_list(length=None))
    posted = []
    for tenant_id in tenants:
        if await db.notifications.find_one({"tenantId": tenant_id, "metadata.kind": KIND}, {"_id": 1}):
            continue
        await pending_agents._post_in_app(db, tenant_id, TITLE, MESSAGE, "warning",
                                          {"kind": KIND, "audience": pending_agents.TENANT_ADMIN_AUDIENCE})
        posted.append(tenant_id)
    logger.info("migration 037: IDS/IPS correction notice posted to %d tenants: %s",
                len(posted), ", ".join(posted) or "none")
