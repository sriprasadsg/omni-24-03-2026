"""
Branch Site / Remote Office Service
Manages site entities and provides per-site aggregated metrics.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)


async def list_sites(tenant_id: str) -> List[Dict]:
    db = get_database()
    cursor = db._db.branch_sites.find({"tenantId": tenant_id}).sort("name", 1)
    docs = await cursor.to_list(length=500)
    for d in docs:
        d.pop("_id", None)
    return docs


async def create_site(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("Site name is required")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": name,
        "description": data.get("description", ""),
        "city": data.get("city", ""),
        "country": data.get("country", ""),
        "timezone": data.get("timezone", "UTC"),
        "ip_ranges": data.get("ip_ranges", []),
        "contact_name": data.get("contact_name", ""),
        "contact_email": data.get("contact_email", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db._db.branch_sites.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_site(site_id: str, tenant_id: str) -> Optional[Dict]:
    db = get_database()
    doc = await db._db.branch_sites.find_one({"id": site_id, "tenantId": tenant_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def update_site(site_id: str, tenant_id: str, data: Dict[str, Any]) -> Optional[Dict]:
    db = get_database()
    allowed = {"name", "description", "city", "country", "timezone", "ip_ranges", "contact_name", "contact_email"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        raise ValueError("No updatable fields provided")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db._db.branch_sites.update_one(
        {"id": site_id, "tenantId": tenant_id},
        {"$set": update},
    )
    return await get_site(site_id, tenant_id)


async def delete_site(site_id: str, tenant_id: str) -> bool:
    db = get_database()
    count = await db._db.agents.count_documents({"tenantId": tenant_id, "site_id": site_id})
    if count > 0:
        raise ValueError(f"Cannot delete: {count} agent(s) are assigned to this site")
    result = await db._db.branch_sites.delete_one({"id": site_id, "tenantId": tenant_id})
    return result.deleted_count > 0


async def assign_agents(site_id: str, agent_ids: List[str], tenant_id: str) -> Dict[str, Any]:
    db = get_database()
    if not await get_site(site_id, tenant_id):
        raise ValueError("Site not found")

    updated = 0
    now = datetime.now(timezone.utc).isoformat()
    for agent_id in agent_ids:
        result = await db._db.agents.update_one(
            {"id": agent_id, "tenantId": tenant_id},
            {"$set": {"site_id": site_id, "updated_at": now}},
        )
        if result.modified_count:
            updated += 1
    return {"updated": updated}


async def get_site_stats(site_id: str, tenant_id: str) -> Dict[str, Any]:
    """Return aggregated health, compliance, and patch stats for a site."""
    db = get_database()
    agents = await db._db.agents.find(
        {"tenantId": tenant_id, "site_id": site_id},
        projection={"id": 1, "status": 1, "health": 1},
    ).to_list(length=5000)

    total_agents = len(agents)
    online = sum(1 for a in agents if a.get("status") == "online")
    agent_ids = [a["id"] for a in agents]

    # Patch compliance: count patches where status == "installed" for these agents
    patch_installed = await db._db.patches.count_documents(
        {"tenantId": tenant_id, "agentId": {"$in": agent_ids}, "status": "installed"}
    ) if agent_ids else 0
    patch_total = await db._db.patches.count_documents(
        {"tenantId": tenant_id, "agentId": {"$in": agent_ids}}
    ) if agent_ids else 0
    patch_pct = round(patch_installed / patch_total * 100, 1) if patch_total else 0

    return {
        "site_id": site_id,
        "total_agents": total_agents,
        "online_agents": online,
        "offline_agents": total_agents - online,
        "patch_compliance_pct": patch_pct,
        "patches_installed": patch_installed,
        "patches_total": patch_total,
    }


async def list_sites_with_stats(tenant_id: str) -> List[Dict]:
    """Return all sites with their aggregated stats."""
    sites = await list_sites(tenant_id)
    result = []
    for site in sites:
        stats = await get_site_stats(site["id"], tenant_id)
        result.append({**site, **stats})
    return result


async def get_summary(tenant_id: str) -> Dict[str, Any]:
    db = get_database()
    total_sites = await db._db.branch_sites.count_documents({"tenantId": tenant_id})
    assigned_agents = await db._db.agents.count_documents({"tenantId": tenant_id, "site_id": {"$exists": True, "$ne": None}})
    return {"total_sites": total_sites, "agents_assigned_to_sites": assigned_agents}
