from fastapi import APIRouter, Depends, HTTPException, Body, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from database import get_database
from authentication_service import get_current_user
import datetime
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
        query["osName"] = {"$regex": os, "$options": "i"}
    
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
    regex = {"$regex": q, "$options": "i"}
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
        query["tenantId"] = getattr(current_user, "tenant_id", "default")
    assets = await db.assets.find(query, {"_id": 0}).to_list(length=limit)
    return assets


@router.delete("/bulk")
async def bulk_delete_assets_route(
    ids: List[str] = Body(..., description="List of asset IDs to delete"),
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """Delete multiple assets by ID."""
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    query: Dict[str, Any] = {"id": {"$in": ids}}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", "default")
    result = await db.assets.delete_many(query)
    invalidate_cache("assets:*")
    return {"success": True, "deleted": result.deleted_count}


@router.get("/{asset_id}")
async def get_asset_details(
    asset_id: str,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """Get details for a specific asset"""
    query = {"id": asset_id}
    
    # RBAC check
    is_admin = current_user.role in ["Super Admin", "super_admin", "admin", "platform-admin"]
    if not is_admin:
        query["tenantId"] = current_user.tenant_id
        
    asset = await db.assets.find_one(query, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
        
    return asset

@router.get("/{asset_id}/metrics")
async def get_asset_metrics(
    asset_id: str,
    time_range: str = Query("24h", alias="range"),
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """Get metrics history for an asset"""
    # Verify access to asset first
    asset_query = {"id": asset_id}
    is_admin = current_user.role in ["Super Admin", "super_admin", "admin", "platform-admin"]
    if not is_admin:
        asset_query["tenantId"] = current_user.tenant_id
        
    asset = await db.assets.find_one(asset_query)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # In a real system, we'd fetch from a time-series collection like 'asset_metrics'
    # For this implementation, we simulate/fetch the most recent metrics if they aren't historicized yet
    # or return the telemetry stored on the asset if history is missing.
    
    # Try to find historical metrics
    metrics_cursor = db.asset_metrics.find({"assetId": asset_id}, {"_id": 0}).sort("timestamp", -1).limit(100)
    metrics = await metrics_cursor.to_list(length=100)
    
    if not metrics:
        # No recorded history — seed a single snapshot from the asset's last-known telemetry
        # so charts have at least one real data point rather than random numbers.
        asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
        telemetry = (asset or {}).get("telemetry") or {}
        now = datetime.datetime.now(datetime.timezone.utc)
        metrics.append({
            "timestamp": now.isoformat(),
            "cpu": float(telemetry.get("cpu_percent", 0)),
            "ram": float(telemetry.get("memory_percent", 0)),
            "disk": float(telemetry.get("disk_percent", 0)),
            "network_in": float(telemetry.get("network_bytes_recv", 0)),
            "network_out": float(telemetry.get("network_bytes_sent", 0)),
        })
            
    return {"assetId": asset_id, "metrics": metrics}


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
    tenant_id = getattr(current_user, "tenant_id", None)
    
    asset = await db.assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
        
    if user_role not in ["Super Admin", "superadmin", "super_admin", "admin"] and asset["tenantId"] != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this asset")

    # Delete asset
    result = await db.assets.delete_one({"id": asset_id})
    
    if result.deleted_count == 0:
         raise HTTPException(status_code=500, detail="Failed to delete asset")
    
    # Cascade Delete: If there's an agent linked to this asset, delete it.
    # Note: assets track their links through `agentId` or `agentStatus` depending on how it's linked.
    # We'll search for any agent asserting `assetId == asset_id` and delete it.
    await db.agents.delete_one({"assetId": asset_id})
    
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

    # Update Asset record to reflect the linked agent
    await db.assets.update_one(
        {"id": asset_id},
        {"$set": {
            "agentStatus": agent.get("status", "Online"),
            "agentVersion": agent.get("version", "1.0.0"),
            "agentCapabilities": agent.get("capabilities", [])
        }}
    )
    
    # Update Agent record
    await db.agents.update_one(
        {"id": agent_id},
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
    tenant_id = getattr(current_user, "tenant_id", "default")
    
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = tenant_id
        
    result = await db.assets.update_many(
        query,
        {"$set": {
            **request.updates, 
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

    result = await db.assets.update_one(
        {"id": asset_id},
        {"$set": {
            "criticality": level,
            "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Asset not found")

    invalidate_cache("assets:*")
    return {"asset_id": asset_id, "criticality": level}




