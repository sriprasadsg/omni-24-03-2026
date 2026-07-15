from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, Request, Response
from typing import Dict, Any
from database import get_database
from authentication_service import get_current_user, create_access_token
from datetime import datetime, timezone, timedelta
import uuid
from cache_service import invalidate_cache
from rate_limiter import limiter
import logging

router = APIRouter(prefix="/api/agents", tags=["Agents"])
logger = logging.getLogger("agent_registry_endpoints")


@router.post("/register")
@limiter.limit("10/minute")
async def register_agent(request: Request, response: Response, data: Dict[str, Any] = Body(...), background_tasks: BackgroundTasks = None):
    """
    Register a new agent or update an existing one.
    Public endpoint, requires registrationKey.
    """
    db = get_database()
    registration_key = data.get("registrationKey")

    if not registration_key:
        raise HTTPException(status_code=400, detail="Registration key required")

    tenant = await db.tenants.find_one({"registrationKey": registration_key})
    if not tenant:
        raise HTTPException(status_code=404, detail="Invalid registration key")

    from tenant_context import set_tenant_id
    set_tenant_id(tenant["id"])

    hostname = data.get("hostname")
    if not hostname:
        raise HTTPException(status_code=400, detail="Hostname required")

    agent_id = f"agent-{uuid.uuid4().hex}"
    existing_agent = await db.agents.find_one({"hostname": hostname, "tenantId": tenant["id"]})
    if existing_agent:
        agent_id = existing_agent["id"]

    agent_limit = tenant.get("maxAgents", 5)
    if not existing_agent:
        current_agent_count = await db.agents.count_documents({"tenantId": tenant["id"]})
        if current_agent_count >= agent_limit:
            raise HTTPException(
                status_code=403,
                detail=f"Agent limit reached ({agent_limit}). Please upgrade your plan for more capacity."
            )

    agent_data = {
        "id": agent_id,
        "tenantId": tenant["id"],
        "hostname": hostname,
        "platform": data.get("platform", "Unknown"),
        "version": data.get("version", "1.0.0"),
        "ipAddress": data.get("ipAddress", "0.0.0.0"),
        "deviceId": data.get("device_id") or data.get("deviceId"),
        "status": "Online",
        "lastSeen": datetime.now(timezone.utc).isoformat(),
        "registeredAt": existing_agent.get("registeredAt") if existing_agent else datetime.now(timezone.utc).isoformat()
    }

    reg_meta = data.get("meta", {})
    available_caps = reg_meta.get("availableCapabilities") or reg_meta.get("capabilities") or []
    if available_caps:
        agent_data["availableCapabilities"] = available_caps

    await db.agents.update_one({"id": agent_id}, {"$set": agent_data}, upsert=True)

    metrics = data.get("meta", {})
    os_info = metrics.get("os_info", {})
    asset_id = f"asset-{hostname}"
    existing_asset = await db.assets.find_one({"id": asset_id})

    asset_data = {
        "id": asset_id,
        "tenantId": tenant["id"],
        "hostname": hostname,
        "osName": data.get("platform", "Unknown"),
        "osVersion": data.get("osVersion", os_info.get("version", "Unknown")),
        "kernel": data.get("kernel", "Unknown"),
        "serialNumber": data.get("serialNumber", "Not Available"),
        "osEdition": data.get("osEdition") or (existing_asset.get("osEdition") if existing_asset else ""),
        "osDisplayVersion": data.get("osDisplayVersion") or (existing_asset.get("osDisplayVersion") if existing_asset else ""),
        "osInstalledOn": data.get("osInstalledOn") or (existing_asset.get("osInstalledOn") if existing_asset else ""),
        "osBuild": data.get("osBuild") or (existing_asset.get("osBuild") if existing_asset else ""),
        "osExperience": data.get("osExperience") or (existing_asset.get("osExperience") if existing_asset else ""),
        "ipAddress": data.get("ipAddress", "0.0.0.0"),
        "macAddress": data.get("macAddress", "00:00:00:00:00:00"),
        "lastScanned": datetime.now(timezone.utc).isoformat(),
        "cpuModel": data.get("cpuModel", "Unknown"),
        "cpuCores": data.get("cpuCores", 0),
        "ram": data.get("ram", "Unknown"),
        "totalMemoryGB": data.get("totalMemoryGB", 0),
        "disks": data.get("disks", []),
        "installedSoftware": data.get("installedSoftware", []),
        "criticalFiles": existing_asset.get("criticalFiles", []) if existing_asset else [],
        "vulnerabilities": existing_asset.get("vulnerabilities", []) if existing_asset else [],
        "status": "active",
        "type": "server"
    }

    try:
        await db.assets.update_one({"id": asset_id}, {"$set": asset_data}, upsert=True)
    except Exception as e:
        if "E11000 duplicate key error" in str(e):
            await db.assets.update_one({"id": asset_id}, {"$set": asset_data})
        else:
            raise e

    await db.agents.update_one({"id": agent_id}, {"$set": {"assetId": asset_id}})

    try:
        from finops_service import finops_service
        await finops_service.recalculate_tenant_costs(tenant["id"])
    except Exception as e:
        logger.warning("FinOps cost recalculation failed for tenant %s: %s", tenant["id"], e)

    try:
        from admin_evidence_service import run_evidence_collection_for_asset
        if background_tasks is not None:
            background_tasks.add_task(run_evidence_collection_for_asset, hostname, db)
        else:
            import asyncio
            asyncio.create_task(run_evidence_collection_for_asset(hostname, db))
    except Exception as e:
        logger.warning("Evidence collection dispatch failed for host %s: %s", hostname, e)

    token_data = {"sub": agent_id, "role": "agent", "tenant_id": tenant["id"], "jti": str(uuid.uuid4())}
    access_token = create_access_token(data=token_data, expires_delta=timedelta(days=90))
    return {"success": True, "agentId": agent_id, "token": access_token}


@router.put("/{agent_id}/link")
async def link_agent_to_asset(
    agent_id: str,
    asset_data: Dict[str, str] = Body(...),
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """Manually link an Agent to a specific Asset. Expects body: {"assetId": "asset-123"}"""
    asset_id = asset_data.get("assetId")
    if not asset_id:
        raise HTTPException(status_code=400, detail="assetId is required")

    agent_query = {"id": agent_id}
    if current_user.role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        agent_query["tenantId"] = current_user.tenant_id

    agent = await db.agents.find_one(agent_query)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    asset_query = {"id": asset_id}
    if current_user.role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        asset_query["tenantId"] = current_user.tenant_id

    asset = await db.assets.find_one(asset_query)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    await db.agents.update_one(agent_query, {"$set": {"assetId": asset_id}})
    await db.assets.update_one(
        asset_query,
        {"$set": {
            "agentStatus": agent.get("status", "Online"),
            "agentVersion": agent.get("version", "1.0.0"),
            "agentCapabilities": agent.get("capabilities", [])
        }}
    )
    return {"success": True, "message": f"Agent {agent_id} successfully linked to Asset {asset_id}"}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """Delete an agent and its linked asset. Requires Admin or Tenant Admin."""
    user_role = getattr(current_user, "role", None)
    tenant_id = getattr(current_user, "tenant_id", None)
    is_admin = user_role in ["Super Admin", "superadmin", "super_admin", "admin", "platform-admin"]

    query: dict = {"id": agent_id}
    if not is_admin:
        query["tenantId"] = tenant_id

    agent = await db.agents.find_one(query)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.get("assetId"):
        asset_del_filter: dict = {"id": agent["assetId"]}
        if not is_admin:
            asset_del_filter["tenantId"] = tenant_id
        await db.assets.delete_one(asset_del_filter)

    del_result = await db.agents.delete_one(query)
    if del_result.deleted_count == 0:
        raise HTTPException(status_code=500, detail="Failed to delete agent")

    await db.audit_logs.insert_one({
        "action": "DELETE_AGENT",
        "agent_id": agent_id,
        "performed_by": getattr(current_user, "username", str(current_user)),
        "tenant_id": getattr(current_user, "tenant_id", "unknown"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    invalidate_cache("agents:*")
    invalidate_cache("assets:*")
    return {"success": True, "message": f"Agent {agent_id} and its associated Asset successfully deleted"}


@router.put("/{agent_id}/move")
async def move_agent(
    agent_id: str,
    payload: Dict[str, str] = Body(...),
    current_user: Any = Depends(get_current_user)
):
    """Move an agent to a different tenant. Requires Super Admin privileges."""
    db = get_database()

    if getattr(current_user, "role", None) not in ["Super Admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Only Super Admin can move agents between tenants")

    target_tenant_id = payload.get("targetTenantId")
    if not target_tenant_id:
        raise HTTPException(status_code=400, detail="Target tenant ID required")

    target_tenant = await db.tenants.find_one({"id": target_tenant_id})
    if not target_tenant:
        raise HTTPException(status_code=404, detail="Target tenant not found")

    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent["tenantId"] == target_tenant_id:
        return {"success": True, "message": "Agent is already in this tenant"}

    await db.agents.update_one(
        {"id": agent_id, "tenantId": agent["tenantId"]},
        {"$set": {"tenantId": target_tenant_id, "updatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    if agent.get("assetId"):
        await db.assets.update_one(
            {"id": agent["assetId"], "tenantId": agent["tenantId"]},
            {"$set": {"tenantId": target_tenant_id}}
        )

    invalidate_cache("agents:*")
    invalidate_cache("assets:*")
    return {
        "success": True,
        "message": f"Agent {agent['hostname']} moved to tenant {target_tenant['name']}",
        "newTenantId": target_tenant_id
    }


@router.put("/{agent_id}")
async def update_agent(
    agent_id: str,
    update_data: Dict[str, Any] = Body(...),
    current_user: Any = Depends(get_current_user)
):
    """Update agent configuration (e.g. capabilities). Requires Admin privileges."""
    db = get_database()
    user_role = getattr(current_user, "role", None)
    tenant_id = getattr(current_user, "tenant_id", None)
    is_admin = user_role in ["Super Admin", "super_admin", "admin", "platform-admin"]

    query: dict = {"id": agent_id}
    if not is_admin:
        query["tenantId"] = tenant_id

    agent = await db.agents.find_one(query)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    def _normalise_caps(raw) -> list:
        if not isinstance(raw, list):
            return []
        return [
            c if isinstance(c, str) else c.get("id", "")
            for c in raw
            if (isinstance(c, str) and c) or (isinstance(c, dict) and c.get("id"))
        ]

    # Resolve capabilities: 'capabilities' takes precedence over 'agentCapabilities'.
    # Both are mirrors; process once to avoid the second field overwriting the first.
    set_data: Dict[str, Any] = {}
    if "capabilities" in update_data:
        cap_value = _normalise_caps(update_data["capabilities"])
        set_data["capabilities"] = cap_value
        set_data["agentCapabilities"] = cap_value
    elif "agentCapabilities" in update_data:
        cap_value = _normalise_caps(update_data["agentCapabilities"])
        set_data["capabilities"] = cap_value
        set_data["agentCapabilities"] = cap_value

    for field in ["status", "alias", "tags", "remediationAttempts"]:
        if field in update_data:
            set_data[field] = update_data[field]

    if not set_data:
        return agent

    set_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    await db.agents.update_one(query, {"$set": set_data})

    if agent.get("assetId"):
        asset_update_filter: dict = {"id": agent["assetId"]}
        if not is_admin:
            asset_update_filter["tenantId"] = tenant_id
        await db.assets.update_one(
            asset_update_filter,
            {"$set": {"agentCapabilities": set_data.get("capabilities", [])}}
        )

    invalidate_cache("agents:*")
    return await db.agents.find_one({"id": agent_id}, {"_id": 0})


@router.get("/version")
async def get_agent_version():
    """Return the current agent binary version and download URL. Polled by agent auto-update."""
    return {
        "version": "2.0.2-rust",
        "download_url": "/static/omni-agent.exe",
        "release_notes": "58 compliance checks, 175 control IDs, Collect Now runs all sources",
        "min_version": "1.0.0",
    }
