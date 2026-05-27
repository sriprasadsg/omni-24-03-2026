from fastapi import APIRouter, Depends, HTTPException, Body, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from database import get_database
from authentication_service import get_current_user
import datetime
import re
from cache_service import cached, invalidate_cache
from pagination_utils import paginate_mongo_query, PaginationParams

router = APIRouter(prefix="/api/assets", tags=["Assets"])

@router.get("")
@cached(ttl=60, key_prefix="assets")
async def get_assets(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    os: Optional[str] = None,
    tenant_id: Optional[str] = None,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """Get all assets with pagination and caching"""
    collection = db["assets"]
    
    # RBAC check
    is_admin = current_user.role in ["Super Admin", "super_admin", "admin", "platform-admin"]
    query = {}
    
    if is_admin:
        if tenant_id:
            query["tenantId"] = tenant_id
    else:
        query["tenantId"] = current_user.tenant_id

    if os:
        query["osName"] = {"$regex": re.escape(os), "$options": "i"}
    
    pagination = PaginationParams(page=page, page_size=page_size)
    
    result = await paginate_mongo_query(
        collection,
        query,
        pagination,
        sort={"lastScanned": -1},
        projection={"_id": 0}
    )
    
    return result

@router.get("/search")
@cached(ttl=30, key_prefix="assets_search")
async def search_assets(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """Full-text search across asset name, hostname, IP, and type fields."""
    q = q[:200]
    import re as _re
    regex = {"$regex": _re.escape(q), "$options": "i"}
    query: Dict[str, Any] = {
        "$or": [
            {"name": regex},
            {"hostname": regex},
            {"ipAddress": regex},
            {"type": regex},
            {"os": regex},
        ]
    }
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        caller_tenant = getattr(current_user, "tenant_id", None) or None
        if not caller_tenant:
            raise HTTPException(status_code=403, detail="Tenant context required")
        query["tenantId"] = caller_tenant
    assets = await db.assets.find(query, {"_id": 0}).to_list(length=limit)
    return assets


@router.delete("/bulk")
async def bulk_delete_assets_route(
    ids: List[str] = Body(..., description="List of asset IDs to delete"),
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """Delete multiple assets by ID."""
    ids = ids[:500]
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    query: Dict[str, Any] = {"id": {"$in": ids}}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        caller_tenant = getattr(current_user, "tenant_id", None) or None
        if not caller_tenant:
            raise HTTPException(status_code=403, detail="Tenant context required")
        query["tenantId"] = caller_tenant
    result = await db.assets.delete_many(query)
    invalidate_cache("assets:*")
    return {"success": True, "deleted": result.deleted_count}


@router.get("/{asset_id}")
async def get_asset_details(
    asset_id: str,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """Get details for a specific asset, enriched with agent meta for missing fields."""
    query = {"id": asset_id}

    is_admin = current_user.role in ["Super Admin", "super_admin", "admin", "platform-admin"]
    if not is_admin:
        query["tenantId"] = current_user.tenant_id

    asset = await db.assets.find_one(query, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # ── Enrich from agent meta so detail view shows real hardware fields ──
    hostname = asset.get("hostname")
    agent = None
    if hostname:
        agent = await db.agents.find_one(
            {"hostname": hostname},
            {"_id": 0, "id": 1, "status": 1, "version": 1, "meta": 1}
        )

    if agent:
        meta = agent.get("meta") or {}

        def _missing(field, *bad):
            v = asset.get(field)
            return not v or v in ("Unknown", "Not Available", "00:00:00:00:00:00", *bad)

        if _missing("serialNumber"):
            asset["serialNumber"] = meta.get("serial_number") or asset.get("serialNumber", "")
        if _missing("macAddress"):
            asset["macAddress"] = meta.get("mac_address") or asset.get("macAddress", "")
        if not asset.get("macAddresses") and meta.get("mac_addresses"):
            asset["macAddresses"] = meta["mac_addresses"]
        if _missing("kernel"):
            asset["kernel"] = meta.get("kernel_version") or meta.get("os_version_detail") or asset.get("kernel", "")
        if _missing("osBuild"):
            asset["osBuild"] = meta.get("os_version_detail") or meta.get("kernel_version") or asset.get("osBuild", "")
        if _missing("osDisplayVersion"):
            asset["osDisplayVersion"] = meta.get("os_release") or asset.get("osDisplayVersion", "")
        if _missing("osVersion"):
            asset["osVersion"] = (
                meta.get("os_version") or meta.get("os_version_detail") or asset.get("osVersion", "")
            )
        if _missing("osFullName"):
            asset["osFullName"] = meta.get("os_full_name") or asset.get("osFullName", "")
        if _missing("osEdition"):
            os_full = asset.get("osFullName") or meta.get("os_full_name", "")
            m = re.search(r'\b(Home|Pro|Enterprise|Education|Standard|Datacenter|Server)\b', os_full, re.IGNORECASE)
            if m:
                asset["osEdition"] = m.group(1)
        if _missing("cpuModel"):
            asset["cpuModel"] = meta.get("cpu_model") or asset.get("cpuModel", "")
        if _missing("ram"):
            asset["ram"] = meta.get("memory_gb") or asset.get("ram", "")
        if not asset.get("disks") and meta.get("disks"):
            asset["disks"] = meta["disks"]
        if _missing("osInstalledOn"):
            asset["osInstalledOn"] = meta.get("install_date") or asset.get("osInstalledOn", "")

        # Agent link fields
        asset["agentStatus"] = agent.get("status", "Unknown")
        asset["agentVersion"] = agent.get("version", "")
        asset["agentId"] = agent["id"]

    return asset

@router.get("/{asset_id}/metrics")
async def get_asset_metrics(
    asset_id: str,
    time_range: str = Query("24h", alias="range"),
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """Get metrics history for an asset"""
    asset_query = {"id": asset_id}
    is_admin = current_user.role in ["Super Admin", "super_admin", "admin", "platform-admin"]
    if not is_admin:
        asset_query["tenantId"] = current_user.tenant_id

    asset = await db.assets.find_one(asset_query)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    range_hours = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}.get(time_range, 24)
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=range_hours)).isoformat()

    # Heartbeat handler writes asset_metrics with snake_case "asset_id" key
    raw = await db.asset_metrics.find(
        {"asset_id": asset_id, "timestamp": {"$gte": since}}, {"_id": 0}
    ).sort("timestamp", -1).limit(100).to_list(length=100)

    if raw:
        # Normalise field names — heartbeat stores cpu_percent/memory_percent/disk_percent
        metrics = [
            {
                "timestamp": m.get("timestamp"),
                "cpu":    float(m.get("cpu_percent") or m.get("cpu") or 0),
                "memory": float(m.get("memory_percent") or m.get("memory") or 0),
                "disk":   float(m.get("disk_percent") or m.get("disk") or 0),
                "network": float(
                    (m.get("network_bytes_sent") or 0) + (m.get("network_bytes_recv") or 0)
                ) / (1024 * 1024),
            }
            for m in reversed(raw)  # chronological order for charts
        ]
        return {"assetId": asset_id, "metrics": metrics}

    # Fallback 1 — pull from agent_metrics_history via the agent linked to this asset
    agent = await db.agents.find_one({"assetId": asset_id}, {"_id": 0, "id": 1})
    if not agent:
        # Try matching by hostname (asset_id is "asset-{hostname}")
        hostname = asset_id.replace("asset-", "", 1)
        agent = await db.agents.find_one({"hostname": hostname}, {"_id": 0, "id": 1})

    if agent:
        history = await db.agent_metrics_history.find(
            {"agent_id": agent["id"]}, {"_id": 0}
        ).sort("timestamp", -1).limit(100).to_list(length=100)
        if history:
            metrics = [
                {
                    "timestamp": m.get("timestamp"),
                    "cpu":    float(m.get("cpu") or m.get("cpu_percent") or 0),
                    "memory": float(m.get("memory") or m.get("memory_percent") or 0),
                    "disk":   float(m.get("disk") or m.get("disk_percent") or 0),
                    "network": 0.0,
                }
                for m in reversed(history)
            ]
            return {"assetId": asset_id, "metrics": metrics}

    # Fallback 2 — single snapshot from asset's last-known telemetry
    telemetry = (asset or {}).get("telemetry") or {}
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "assetId": asset_id,
        "metrics": [{
            "timestamp": now.isoformat(),
            "cpu":    float(telemetry.get("cpu_percent", 0)),
            "memory": float(telemetry.get("memory_percent", 0)),
            "disk":   float(telemetry.get("disk_percent", 0)),
            "network": 0.0,
        }],
    }


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: str,
    current_user: Any = Depends(get_current_user)
):
    """
    Delete an asset.
    Requires Admin privileges or Tenant Admin for own tenant.
    """
    db = get_database()
    
    # Check permissions
    user_role = getattr(current_user, "role", None)
    tenant_id = getattr(current_user, "tenant_id", None) or None
    _ASSET_SUPER_ROLES = {"Super Admin", "superadmin", "super_admin", "admin"}
    _asset_read_q: dict = {"id": asset_id}
    if user_role not in _ASSET_SUPER_ROLES:
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        _asset_read_q["tenantId"] = tenant_id

    asset = await db.assets.find_one(_asset_read_q)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Delete asset — include tenantId in delete query for defense-in-depth
    delete_query: dict = {"id": asset_id}
    if user_role not in ["Super Admin", "superadmin", "super_admin", "admin"]:
        delete_query["tenantId"] = tenant_id
    result = await db.assets.delete_one(delete_query)
    
    if result.deleted_count == 0:
         raise HTTPException(status_code=500, detail="Failed to delete asset")
    
    # Cascade Delete: remove any agent linked to this asset, scoped to the asset's tenant
    asset_tenant = asset.get("tenantId")
    cascade_filter: dict = {"assetId": asset_id}
    if asset_tenant:
        cascade_filter["tenantId"] = asset_tenant
    await db.agents.delete_one(cascade_filter)
    
    # Invalidate cache
    invalidate_cache("assets:*")
    invalidate_cache("agents:*")
    
    return {"success": True, "message": f"Asset {asset_id} deleted"}

# Add other asset endpoints here if needed (GET, POST, etc. are currently distributed or missing specific router)
# For now, we focus on the missing DELETE.

@router.put("/{asset_id}/link")
async def link_asset_to_agent(
    asset_id: str,
    agent_data: Dict[str, str] = Body(...),
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """
    Manually link an Asset to a specific Agent.
    Expects body: {"agentId": "agent-123"}
    """
    agent_id = agent_data.get("agentId")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agentId is required")

    # Verify asset exists and user has access
    asset_query = {"id": asset_id}
    if current_user.role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        asset_query["tenantId"] = current_user.tenant_id
        
    asset = await db.assets.find_one(asset_query)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
        
    # Verify agent exists
    agent_query = {"id": agent_id}
    if current_user.role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        agent_query["tenantId"] = current_user.tenant_id
        
    agent = await db.agents.find_one(agent_query)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Update Asset record — include tenantId in filter to prevent cross-tenant writes
    asset_update_filter = {"id": asset_id}
    if current_user.role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        asset_update_filter["tenantId"] = current_user.tenant_id
    await db.assets.update_one(
        asset_update_filter,
        {"$set": {
            "agentStatus": agent.get("status", "Online"),
            "agentVersion": agent.get("version", "1.0.0"),
            "agentCapabilities": agent.get("capabilities", [])
        }}
    )

    # Update Agent record — include tenantId in filter to prevent cross-tenant writes
    agent_update_filter = {"id": agent_id}
    if current_user.role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        agent_update_filter["tenantId"] = current_user.tenant_id
    await db.agents.update_one(
        agent_update_filter,
        {"$set": {"assetId": asset_id}}
    )
    
    # Invalidate cache if needed
    invalidate_cache("assets:*")
    invalidate_cache("agents:*")
    
    return {"success": True, "message": f"Asset {asset_id} successfully linked to Agent {agent_id}"}


class BulkUpdateAssetsRequest(BaseModel):
    assetIds: List[str]
    updates: Dict[str, Any]

@router.post("/bulk-update")
async def bulk_update_assets(
    request: BulkUpdateAssetsRequest,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """
    Update multiple assets at once.
    """
    query = {"id": {"$in": request.assetIds}}
    
    # RBAC logic
    user_role = getattr(current_user, "role", "user")
    tenant_id = getattr(current_user, "tenant_id", None) or None

    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        query["tenantId"] = tenant_id
        
    _BULK_UPDATE_ALLOWLIST = {
        "status", "criticality", "tags", "location", "owner",
        "notes", "maintenanceWindow", "environment", "category",
    }
    safe_updates = {k: v for k, v in request.updates.items() if k in _BULK_UPDATE_ALLOWLIST}
    if not safe_updates:
        raise HTTPException(status_code=400, detail="No valid update fields provided")

    result = await db.assets.update_many(
        query,
        {"$set": {
            **safe_updates,
            "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }}
    )
    
    invalidate_cache("assets:*")

    return {
        "success": True,
        "matched_count": result.matched_count,
        "modified_count": result.modified_count
    }


@router.patch("/{asset_id}/criticality")
async def set_asset_criticality(
    asset_id: str,
    body: Dict[str, Any],
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """
    Set the criticality level of an asset.
    Accepted values: critical | high | medium | low
    This controls whether autonomous actions (e.g. isolate_host) require
    human approval even when confidence is high.
    """
    level = body.get("criticality", "").lower()
    if level not in ("critical", "high", "medium", "low"):
        raise HTTPException(status_code=400, detail="criticality must be critical|high|medium|low")

    asset_query: dict = {"id": asset_id}
    user_role = getattr(current_user, "role", "")
    if user_role not in ("Super Admin", "superadmin", "super_admin", "platform-admin"):
        asset_query["tenantId"] = getattr(current_user, "tenant_id", None)

    result = await db.assets.update_one(
        asset_query,
        {"$set": {
            "criticality": level,
            "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Asset not found")

    invalidate_cache("assets:*")
    return {"asset_id": asset_id, "criticality": level}




