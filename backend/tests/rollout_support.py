"""Shared fixtures for the staged patch rollout tests (Phase 84).

Real-database helpers (use with ``tests._mongo_test_db.mongo_db``). They build on
``tests.autonomy_support`` (``seed_tenant``). Later plans add helpers inside their own test files,
not here.
"""
from datetime import datetime, timezone

from tests.autonomy_support import seed_tenant


def iso(value):
    return value.isoformat()


async def seed_rollout_tenant(db, tenant_id, *, shadow=False):
    """A ticked tenant with every agent capability on (the patch installer one is the one that matters)."""
    await seed_tenant(db, tenant_id, shadow=shadow)
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"agentCapabilities": ["all"]}})


async def seed_rollout_agent(db, tenant, agent_id, *, hostname, platform, tokens, pending, boot_time,
                             last_seen=None, scan_at=None):
    """An enrolled agent as a 2.1.16-shaped heartbeat leaves it: response tokens, a boot time, and a
    patch scan (``pending`` is a list of package names or KB ids, ``scan_at`` the scan timestamp)."""
    seen = last_seen or datetime.now(timezone.utc)
    scanned = scan_at or seen
    await db.agents.replace_one(
        {"id": agent_id},
        {"id": agent_id, "tenantId": tenant, "hostname": hostname, "ipAddress": "10.9.9.9", "status": "Online",
         "platform": platform, "lastSeen": iso(seen),
         "meta": {"response_actions": {"tokens": list(tokens)},
                  "response_state": {"boot_time": boot_time},
                  "system_patching": {"timestamp": iso(scanned), "pending_update_count": len(pending),
                                      "pending_updates": [{"id": p, "title": p} for p in pending]}}},
        upsert=True)


async def seed_window(db, tenant, *, zone="UTC", start, end, days=None, recurrence="daily", name="Window"):
    """A maintenance window in the new stored shape, and the tenant's time zone."""
    await db.maintenance_settings.update_one({"tenantId": tenant}, {"$set": {"tenantId": tenant, "timeZone": zone}},
                                             upsert=True)
    await db.maintenance_windows.insert_one({
        "id": f"w-{name}-{start}-{end}", "tenantId": tenant, "name": name, "recurrence": recurrence,
        "startTime": start, "endTime": end, "daysOfWeek": days, "isActive": True})


async def seed_rings(db, tenant, rings):
    """The tenant's saved rings: a list of dicts with key, name, groupIds and optional checks."""
    await db.patch_rollout_settings.replace_one({"tenantId": tenant}, {"tenantId": tenant, "rings": rings}, upsert=True)


async def seed_group(db, tenant, group_id, agent_ids):
    """An agent group and its members."""
    await db.agent_groups.replace_one({"id": group_id}, {"id": group_id, "tenantId": tenant, "name": group_id},
                                      upsert=True)
    for agent_id in agent_ids:
        await db.agent_group_members.replace_one({"group_id": group_id, "agent_id": agent_id},
                                                 {"group_id": group_id, "agent_id": agent_id, "tenantId": tenant},
                                                 upsert=True)


async def post_result(db, job_id, agent_id, body):
    """The agent's install result, posted through the same function the deployment result route calls."""
    from deployment_result_endpoints import record_agent_patch_result
    return await record_agent_patch_result(db, job_id, agent_id, body)


def success_result(patch_ids, *, reboot=False):
    """A 2.1.16-shaped completed install result for ``patch_ids``."""
    return {"status": "completed", "successful": len(patch_ids), "failed": 0, "total": len(patch_ids),
            "results": [{"patch_id": p, "status": "success", "reboot_required": reboot} for p in patch_ids]}


def failure_result(patch_ids, message="install failed"):
    return {"status": "failed", "successful": 0, "failed": len(patch_ids), "total": len(patch_ids),
            "results": [{"patch_id": p, "status": "failed", "message": message} for p in patch_ids]}
