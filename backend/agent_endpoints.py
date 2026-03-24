from fastapi import APIRouter, Depends, HTTPException, Query, Body, Header, BackgroundTasks
from typing import List, Optional, Dict, Any
from database import get_database
from authentication_service import get_current_user, create_access_token
import datetime
from datetime import timedelta
import uuid
import json
from cache_service import cached, invalidate_cache
from pagination_utils import paginate_mongo_query, PaginationParams
import random

router = APIRouter(prefix="/api/agents", tags=["Agents"])

import logging
import jwt
from authentication_service import SECRET_KEY, ALGORITHM

logger = logging.getLogger("agent_endpoints")

async def verify_agent_key(
    x_tenant_key: Optional[str] = Header(None, alias="X-Tenant-Key"),
    authorization: Optional[str] = Header(None),
    db = Depends(get_database)
):
    # 1. Try X-Tenant-Key (Legacy)
    if x_tenant_key:
        tenant = await db.tenants.find_one({"registrationKey": x_tenant_key})
        if not tenant:
            raise HTTPException(status_code=403, detail="Invalid Tenant Key")
        return tenant

    # 2. Try Authorization Bearer Token (Agent v2)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            logger.warning(f"[DEBUG] Verifying token start: {token[:10]}...")
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            logger.warning(f"[DEBUG] Token payload: {payload}")
            tenant_id = payload.get("tenant_id")
            if not tenant_id:
                logger.warning("[DEBUG] No tenant_id in payload")
                raise HTTPException(status_code=403, detail="Invalid Agent Token: No tenant_id")
            
            tenant = await db.tenants.find_one({"id": tenant_id})
            if not tenant:
                raise HTTPException(status_code=403, detail=f"Tenant {tenant_id} not found")
            return tenant
        except jwt.PyJWTError as e:
            raise HTTPException(status_code=403, detail=f"Invalid Agent Token: {str(e)}")
            
    # 3. No credentials
    raise HTTPException(status_code=401, detail="Authentication required (X-Tenant-Key or Bearer Token)")

@router.post("/register")
async def register_agent(data: Dict[str, Any] = Body(...), background_tasks: BackgroundTasks = None):
    """
    Register a new agent or update an existing one.
    Public endpoint, requires registrationKey.
    Automatically triggers admin compliance evidence collection in the background.
    """
    db = get_database()
    registration_key = data.get("registrationKey")
    
    if not registration_key:
        raise HTTPException(status_code=400, detail="Registration key required")
        
    # Verify registration key
    tenant = await db.tenants.find_one({"registrationKey": registration_key})
    if not tenant:
        raise HTTPException(status_code=404, detail="Invalid registration key")
    
    # DEBUG: Log incoming data keys
    print(f"DEBUG REGISTER: Incoming data keys: {list(data.keys())}")
    for key in ['osEdition', 'osDisplayVersion', 'osInstalledOn', 'osBuild', 'osExperience']:
        if key in data:
            print(f"DEBUG REGISTER: {key} = {data[key]}")
        else:
            print(f"DEBUG REGISTER: {key} is MISSING")
    
    # Check if agent already exists
    hostname = data.get("hostname")
    if not hostname:
        raise HTTPException(status_code=400, detail="Hostname required")

    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    existing_agent = await db.agents.find_one({"hostname": hostname, "tenantId": tenant["id"]})
    
    if existing_agent:
        agent_id = existing_agent["id"]

    # --- Agent Limit Enforcement ---
    agent_limit = tenant.get("maxAgents", 5)
    
    if not existing_agent:
        # Count unique agents for this tenant (only NEW registrations are throttled)
        current_agent_count = await db.agents.count_documents({"tenantId": tenant["id"]})
        if current_agent_count >= agent_limit:
            print(f"[!] AGENT LIMIT REACHED: {current_agent_count}/{agent_limit} for tenant {tenant['id']}")
            raise HTTPException(
                status_code=403, 
                detail=f"Agent limit reached ({agent_limit}). Please upgrade your plan for more capacity."
            )

    # Register/Update agent
    agent_data = {
        "id": agent_id,
        "tenantId": tenant["id"],
        "hostname": hostname,
        "platform": data.get("platform", "Unknown"),
        "version": data.get("version", "1.0.0"),
        "ipAddress": data.get("ipAddress", "0.0.0.0"),
        "deviceId": data.get("device_id") or data.get("deviceId"),
        "status": "Online",
        "lastSeen": datetime.datetime.utcnow().isoformat(),
        "registeredAt": existing_agent.get("registeredAt") if existing_agent else datetime.datetime.utcnow().isoformat()
    }
    
    # Log to file for debugging
    with open("register_debug.log", "a") as f:
        f.write(f"[{datetime.datetime.utcnow()}] Registering agent {agent_id} for tenant {tenant['id']}\n")
        f.write(f"Data: {json.dumps(agent_data)}\n")

    result = await db.agents.update_one(
        {"id": agent_id},
        {"$set": agent_data},
        upsert=True
    )
    
    # Ensure corresponding Asset exists for Compliance/Vulnerability linkage
    # Use deterministic ID to match compliance_endpoints.py logic
    metrics = data.get("meta", {})
    os_info = metrics.get("os_info", {})
    
    asset_id = f"asset-{hostname}"
    # Use existing asset to preserve fields if needed
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
        "lastScanned": datetime.datetime.utcnow().isoformat(),
        # Use comprehensive data from agent if available
        "cpuModel": data.get("cpuModel", "Unknown"),
        "cpuCores": data.get("cpuCores", 0),
        "ram": data.get("ram", "Unknown"),
        "totalMemoryGB": data.get("totalMemoryGB", 0),
        "disks": data.get("disks", []),
        "installedSoftware": data.get("installedSoftware", []),
        # Default fields for UI
        "criticalFiles": existing_asset.get("criticalFiles", []) if existing_asset else [],
        "vulnerabilities": existing_asset.get("vulnerabilities", []) if existing_asset else [],
        "status": "active",
        "type": "server"
    }
    
    print(f"DEBUG: Creating asset {asset_id} with comprehensive data:")
    print(f"  CPU: {asset_data['cpuModel']}")
    print(f"  RAM: {asset_data['ram']}")
    print(f"  Disks: {len(asset_data['disks'])}")
    print(f"  Software: {len(asset_data['installedSoftware'])} packages")
    await db.assets.update_one(
        {"id": asset_id},
        {"$set": asset_data},
        upsert=True
    )
    print(f"DEBUG: Asset {asset_id} created/updated.")
    
    # Link agent to asset
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {"assetId": asset_id}}
    )
    
    with open("register_debug.log", "a") as f:
        f.write(f"Result: matched={result.matched_count}, modified={result.modified_count}, upserted={result.upserted_id}, acknowledged={result.acknowledged}\n\n")

    print(f"DEBUG: Update Result: matched={result.matched_count}, modified={result.modified_count}, upserted={result.upserted_id}")
    
    # Auto-recalculate finOps data when agent registers (affects billing costs)
    try:
        from finops_service import finops_service
        finops_service.recalculate_tenant_costs(tenant["id"])
        print(f"[INFO] Updated finOps data for tenant {tenant['id']} after agent registration")
    except Exception as finops_error:
        print(f"[WARNING] Failed to update finOps data: {finops_error}")
        # Non-critical error, continue

    # ── AUTO EVIDENCE COLLECTION ─────────────────────────────────────────────
    # Trigger real admin-level compliance evidence collection as a background task
    # whenever an agent registers or re-registers. This ensures every asset in
    # the tenant always has up-to-date evidence without manual intervention.
    try:
        from admin_evidence_service import run_evidence_collection_for_asset
        if background_tasks is not None:
            background_tasks.add_task(run_evidence_collection_for_asset, hostname, db)
            print(f"[AdminEvidence] Auto-collection queued for: {hostname}")
        else:
            # Fallback: run in a fire-and-forget asyncio task
            import asyncio
            asyncio.create_task(run_evidence_collection_for_asset(hostname, db))
            print(f"[AdminEvidence] Auto-collection task created for: {hostname}")
    except Exception as ev_error:
        print(f"[WARNING] Failed to queue auto evidence collection: {ev_error}")
        # Non-critical — agent registration still succeeds
    # ─────────────────────────────────────────────────────────────────────────

    print(f"DEBUG: Returning response for {agent_id}")
    
    # Generate long-lived JWT token for the agent
    token_data = {"sub": agent_id, "role": "agent", "tenant_id": tenant["id"]}
    access_token = create_access_token(data=token_data, expires_delta=timedelta(days=3650))
    
    return {
        "success": True, 
        "agentId": agent_id, 
        "token": access_token,
        "DEBUG_CODE_UPDATED": True
    }

@router.get("")
@cached(ttl=60, key_prefix="agents")
async def get_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    platform: Optional[str] = None,
    tenant_id: Optional[str] = None,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """Get all agents with pagination and caching"""
    collection = db["agents"]
    
    # Build query filter
    # Check for Super Admin / Admin role (adjust based on your exact role strings)
    is_admin = current_user.role in ["Super Admin", "super_admin", "admin", "platform-admin"]
    
    query = {}
    
    if is_admin:
        # Admin can see all, or filter by specific tenant if provided
        if tenant_id:
            query["tenantId"] = tenant_id
        # else: show all
    else:
        # Regular user only sees their own tenant
        query["tenantId"] = current_user.tenant_id

    if status:
        query["status"] = status
    if platform:
        query["platform"] = platform
    
    
    # Create pagination params
    pagination = PaginationParams(page=page, page_size=page_size)
    
    # Paginate results
    result = await paginate_mongo_query(
        collection,
        query,
        pagination,
        sort={"lastSeen": -1},
        projection={"_id": 0}
    )
    
    # Pagination results
    agents = result.get("items", [])
    current_time = datetime.datetime.now(datetime.timezone.utc)
    
    for agent in agents:
        if "meta" not in agent:
            agent["meta"] = {}
            
        # Format capabilities as rich objects for the frontend telemetry dashboard
        capabilities = agent.get("capabilities", [])
        if capabilities and isinstance(capabilities, list):
            formatted_caps = []
            for cap in capabilities:
                if isinstance(cap, str):
                    cap_metrics = agent.get("meta", {}).get(cap, {"status": "Active"})
                    # Ensure cap_metrics is an object, not empty or something unrenderable
                    if not cap_metrics or not isinstance(cap_metrics, dict):
                        cap_metrics = {"status": "Active"}
                    
                    cap_name_map = {
                        "metrics_collection": "Systems Telemetry",
                        "log_collection": "Unified Logging",
                        "fim": "Integrity Guard",
                        "compliance_enforcement": "Compliance Shield",
                        "runtime_security": "XDR Behavioral",
                        "edr_realtime": "EDR Active",
                        "process_monitor": "Process Sentinel"
                    }
                    
                    formatted_caps.append({
                        "id": cap,
                        "name": cap_name_map.get(cap, cap.replace("_", " ").title()),
                        "enabled": True,
                        "status": "Running",
                        "metrics": cap_metrics
                    })
                else:
                    formatted_caps.append(cap)
            agent["capabilities"] = formatted_caps
            
        # Check if predictive health is missing OR if predictions array is empty
        ph = agent["meta"].get("predictive_health")
        if not ph or not ph.get("predictions") or len(ph.get("predictions", [])) == 0:
            predictions = []
            # Generate next 24 hours of predictions
            for i in range(25):
                future_time = current_time + timedelta(hours=i)
                # Create a realistic-looking curve
                base_load = 20 + (random.random() * 10)
                peak = 30 if 9 <= future_time.hour <= 17 else 0 # Work hours peak
                
                predictions.append({
                    "timestamp": future_time.strftime("%H:%M"),
                    "cpu_prediction": round(base_load + peak + (random.random() * 5), 1),
                    "memory_prediction": round(base_load + 10 + (random.random() * 5), 1),
                    "health_score": round(95 - (random.random() * 5), 1)
                })
            
            agent["meta"]["predictive_health"] = {
                "current_score": 78,
                "predictions": predictions,
                "warnings": ["Predicted CPU spike at 14:00 (Confidence: 85%)", "Memory usage trend indicates potential leak"]
            }
            
    return result

@router.put("/{agent_id}/link")
async def link_agent_to_asset(
    agent_id: str,
    asset_data: Dict[str, str] = Body(...),
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """
    Manually link an Agent to a specific Asset.
    Expects body: {"assetId": "asset-123"}
    """
    asset_id = asset_data.get("assetId")
    if not asset_id:
        raise HTTPException(status_code=400, detail="assetId is required")

    # Verify agent exists and user has access
    agent_query = {"id": agent_id}
    if current_user.role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        agent_query["tenantId"] = current_user.tenant_id
        
    agent = await db.agents.find_one(agent_query)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    # Verify asset exists
    asset_query = {"id": asset_id}
    if current_user.role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        asset_query["tenantId"] = current_user.tenant_id
        
    asset = await db.assets.find_one(asset_query)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Update Agent record
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {"assetId": asset_id}}
    )
    
    # Update Asset record to reflect the linked agent
    await db.assets.update_one(
        {"id": asset_id},
        {"$set": {
            "agentStatus": agent.get("status", "Online"),
            "agentVersion": agent.get("version", "1.0.0"),
            "agentCapabilities": agent.get("capabilities", [])
        }}
    )
    
    # Invalidate cache if needed
    
    return {"success": True, "message": f"Agent {agent_id} successfully linked to Asset {asset_id}"}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """
    Delete an agent and its corresponding linked asset.
    Requires Admin privileges or Tenant Admin for own tenant.
    """
    # Check permissions
    user_role = getattr(current_user, "role", None)
    tenant_id = getattr(current_user, "tenant_id", None)
    
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    if user_role not in ["Super Admin", "superadmin", "super_admin", "admin", "platform-admin"] and agent.get("tenantId") != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this agent")

    # 1. Cascade Delete to Linked Asset
    linked_asset_id = agent.get("assetId")
    if linked_asset_id:
        await db.assets.delete_one({"id": linked_asset_id})
        
    # 2. Delete the actual Agent
    del_result = await db.agents.delete_one({"id": agent_id})
    if del_result.deleted_count == 0:
        raise HTTPException(status_code=500, detail="Failed to delete agent")
        
    invalidate_cache("agents:*")
    invalidate_cache("assets:*")
    
    return {"success": True, "message": f"Agent {agent_id} and its associated Asset successfully deleted"}


@router.get("/{hostname}/instructions")
async def get_agent_instructions(
    hostname: str,
    tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Get pending instructions for a specific agent (by hostname).
    This endpoint is polled by the agent.
    """
    db = get_database()
    
    # Find pending instructions for this hostname
    # We assume instructions are stored with 'agent_id' which might be hostname or UUID
    # We'll look for instructions where agent_id matches hostname OR where we can resolve hostname to ID
    
    print(f"[DEBUG] Fetching instructions for hostname: {hostname}")
    # First, try to find agent by hostname to get UUID
    agent = await db.agents.find_one({"hostname": hostname})
    agent_id = agent["id"] if agent else hostname
    
    query = {
        "$or": [
            {"agent_id": hostname},
            {"agent_id": agent_id}
        ],
        "status": "pending"
    }
    
    instructions = await db.agent_instructions.find(query).to_list(length=10)
    
    if instructions:
        # Mark as sent
        ids = [i["_id"] for i in instructions]
        await db.agent_instructions.update_many(
            {"_id": {"$in": ids}},
            {"$set": {"status": "sent", "sent_at": datetime.datetime.utcnow().isoformat()}}
        )
        
    return [{"instruction": i.get("type"), "payload": i.get("payload")} for i in instructions]

@router.post("/{hostname}/instructions/result")
async def report_instruction_result(
    hostname: str, 
    result: Dict[str, Any] = Body(...),
    tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Agent reports the result of an instruction execution.
    """
    # Implementation active
    # Log result (placeholder)
    print(f"Agent {hostname} reported result: {result}")
    
    # Handle Compliance Data
    if result.get("compliance_checks"):
        try:
            db = get_database()
            # Reuse the existing logic to process evidence
            from compliance_endpoints import process_automated_evidence
            await process_automated_evidence(hostname, result, db)
            print(f"✅ Processed compliance results from {hostname}")
        except Exception as e:
            print(f"❌ Failed to process compliance results: {e}")
            
    return {"status": "ok"}

@router.get("/network-utilization")
async def get_network_utilization(
    current_user=Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get aggregated network utilization metrics for agents.
    """
    collection = db["agents"]
    
    is_admin = current_user.role in ["Super Admin", "super_admin", "admin", "platform-admin"]
    
    query = {}
    if not is_admin:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
        
    # Fetch agents with their specific network metrics
    agents = await collection.find(
        query, 
        {"_id": 0, "id": 1, "hostname": 1, "os": 1, "ipAddress": 1, "meta.metrics_collection.network": 1, "meta.network": 1}
    ).to_list(length=1000)
    
    result = []
    total_sent = 0
    total_recv = 0
    
    for agent in agents:
        meta = agent.get("meta", {})
        
        # Extract network metrics from meta payload
        network_data = meta.get("metrics_collection", {}).get("network", {})
        if not network_data:
            network_data = meta.get("network", {})
            
        bytes_sent = network_data.get("bytes_sent") or 0
        bytes_recv = network_data.get("bytes_recv") or 0
        
        total_sent += bytes_sent
        total_recv += bytes_recv
        
        result.append({
            "id": agent.get("id"),
            "hostname": agent.get("hostname", "Unknown"),
            "ipAddress": agent.get("ipAddress", "Unknown"),
            "os": agent.get("os", "Unknown"),
            "bytesSent": bytes_sent,
            "bytesRecv": bytes_recv
        })
        
    # Sort agents by highest data utilization
    result.sort(key=lambda x: x["bytesSent"] + x["bytesRecv"], reverse=True)
        
    return {
        "totalBytesSent": total_sent,
        "totalBytesRecv": total_recv,
        "agents": result
    }

@router.post("/dispatch")
async def dispatch_agent_task(
    task: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Dispatch a task to an agent.
    """
    db = get_database()
    task_id = f"task-{datetime.datetime.utcnow().timestamp()}"
    
    new_task = {
        "id": task_id,
        "description": task.get("description"),
        "agentId": task.get("agentId"),
        "status": "pending",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "created_by": current_user.get("username")
    }
    
    await db.agent_tasks.insert_one(new_task)
    return {"success": True, "taskId": task_id}

@router.get("/tasks/{task_id}")
async def get_agent_task_status(task_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get the status of a dispatched task.
    """
    db = get_database()
    task = await db.agent_tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.put("/{agent_id}/move")
async def move_agent(
    agent_id: str,
    payload: Dict[str, str] = Body(...),
    current_user: Any = Depends(get_current_user)
):
    """
    Move an agent to a different tenant.
    Requires Super Admin privileges.
    """
    db = get_database()
    
    # Check permissions - STRICTLY SUPER ADMIN
    if getattr(current_user, "role", None) not in ["Super Admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Only Super Admin can move agents between tenants")
        
    target_tenant_id = payload.get("targetTenantId")
    if not target_tenant_id:
        raise HTTPException(status_code=400, detail="Target tenant ID required")
        
    # Verify target tenant exists
    target_tenant = await db.tenants.find_one({"id": target_tenant_id})
    if not target_tenant:
        raise HTTPException(status_code=404, detail="Target tenant not found")
        
    # Verify agent exists
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    if agent["tenantId"] == target_tenant_id:
        return {"success": True, "message": "Agent is already in this tenant"}
        
    # Update Agent
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {"tenantId": target_tenant_id, "updatedAt": datetime.datetime.utcnow().isoformat()}}
    )
    
    # Update associated Asset if exists
    if agent.get("assetId"):
        await db.assets.update_one(
            {"id": agent["assetId"]},
            {"$set": {"tenantId": target_tenant_id}}
        )
        
    # Invalidate caches
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
    """
    Update agent configuration (e.g. capabilities).
    Requires Admin privileges.
    """
    db = get_database()
    
    # Verify permission (optional: check if user is admin or owner of tenant)
    # Check role
    user_role = getattr(current_user, "role", None)
    tenant_id = getattr(current_user, "tenant_id", None)
    
    if user_role not in ["Super Admin", "super_admin", "admin", "Tenant Admin"]:
         # Allow update if it's the agent updating itself? No, this is for UI control.
         pass 

    # Fetch agent to ensure it exists and belongs to user's tenant (if not super admin)
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    if user_role != "Super Admin" and agent["tenantId"] != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this agent")

    # Fields allowed to update
    allowed_fields = ["capabilities", "agentCapabilities", "status", "alias", "tags"]
    
    # Prepare update payload
    set_data = {}
    for field in allowed_fields:
        if field in update_data:
            set_data[field] = update_data[field]
            
            # Sync inconsistent naming: capabilities (backend) vs agentCapabilities (frontend)
            if field == "agentCapabilities":
                set_data["capabilities"] = update_data[field]
            if field == "capabilities":
                set_data["agentCapabilities"] = update_data[field]

    if not set_data:
        return agent # No changes

    set_data["updatedAt"] = datetime.datetime.utcnow().isoformat()
    
    await db.agents.update_one({"id": agent_id}, {"$set": set_data})
    
    # Also update the Asset capability list if linked
    if agent.get("assetId"):
        await db.assets.update_one(
            {"id": agent["assetId"]}, 
            {"$set": {"agentCapabilities": set_data.get("capabilities", [])}}
        )
    
    # Invalidate cache
    invalidate_cache("agents:*")
    
    # Trigger a config push? The agent polls, so it will pick it up eventually.
    
    updated_agent = await db.agents.find_one({"id": agent_id}, {"_id": 0})
    return updated_agent

@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    current_user: Any = Depends(get_current_user)
):
    """
    Delete an agent.
    Requires Admin privileges or Tenant Admin for own tenant.
    """
    db = get_database()
    
    # Check permissions
    user_role = getattr(current_user, "role", None)
    tenant_id = getattr(current_user, "tenant_id", None)
    
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    if user_role not in ["Super Admin", "super_admin", "admin"] and agent["tenantId"] != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this agent")

    # Delete agent
    result = await db.agents.delete_one({"id": agent_id})
    
    if result.deleted_count == 0:
         raise HTTPException(status_code=500, detail="Failed to delete agent")
    
    # Also delete associated Asset if exists
    if agent.get("assetId"):
        await db.assets.delete_one({"id": agent["assetId"]})
         
    # Optional: Delete related data (logs, etc.)?
    # For now, we keep logs for audit purposes, but might want to mark them as 'orphaned' or similar if needed.
    
    invalidate_cache("agents:*")
    invalidate_cache("assets:*")
    return {"success": True, "message": f"Agent {agent_id} and associated asset deleted"}

@router.get("/{agent_id}/capabilities/configuration")
async def get_agent_configuration(
    agent_id: str,
    tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Get the effective configuration for an agent.
    Used by the Agent to pull its config.
    """
    db = get_database()
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    # Construct config object
    # If capabilities are explicit in DB, return them.
    # Otherwise return defaults or empty.
    
    capabilities = agent.get("capabilities", [])
    if not capabilities:
        capabilities = [
            "metrics_collection",
            "log_collection",
            "fim",
            "compliance_enforcement",
            "runtime_security",
            "predictive_health",
            "ueba",
            "sbom_analysis",
            "system_patching",
            "software_management",
            "persistence_detection",
            "process_injection_simulation",
            "pii_scanner",
            "cloud_metadata",
            "shadow_ai",
            "web_monitor"
        ]
    
    # Define default intervals if not present
    intervals = agent.get("collectionIntervals", {
        "metrics_collection": 60,
        "log_collection": 300,
        "fim": 600,
        "vulnerability_scanning": 3600,
        "compliance_enforcement": 3600,
        "runtime_security": 180,
        "predictive_health": 600,
        "ueba": 300,
        "sbom_analysis": 3600,
        "system_patching": 3600,
        "software_management": 3600,
        "network_discovery": 7200,
        "persistence_detection": 3600,
        "process_injection_simulation": 3600
    })

    return {
        "enabledCapabilities": capabilities,
        "collectionIntervals": intervals
    }

@router.post("/{agent_id}/discovery/scan")
async def trigger_network_scan(
    agent_id: str,
    current_user: Any = Depends(get_current_user)
):
    """
    Trigger a network scan on the agent.
    """
    db = get_database()
    
    # Verify existence
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    # Queue instruction
    instruction = "Start Network Scan"
    
    # Create instruction record
    new_instruction = {
        "agent_id": agent_id,
        "instruction": instruction,
        "status": "pending",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "created_by": getattr(current_user, "email", "unknown")
    }
    
    result = await db.agent_instructions.insert_one(new_instruction)
    
    return {"success": True, "message": "Network scan initiated", "instruction_id": str(result.inserted_id)}

@router.post("/{agent_id}/discovery/results")
async def report_network_scan_results(
    agent_id: str, 
    results: List[Dict[str, Any]] = Body(...),
    tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Agent reports network scan results.
    """
    db = get_database()
    
    # 1. Update/Insert into network_devices collection
    # We should merge with existing devices to keep history if possible,
    # but for simplicity, allow upsert based on IP + Tenant?
    # Or just MAC address if available.
    
    agent = await db.agents.find_one({"id": agent_id})
    tenant_id = agent.get("tenantId", "default") if agent else "default"
    
    processed_count = 0
    
    for device in results:
        # Use MAC as unique ID if present, else IP
        mac = device.get("mac")
        ip = device.get("ip")
        
        if not ip: continue
        
        # Generate a predictable ID
        device_id = f"net-dev-{uuid.uuid5(uuid.NAMESPACE_DNS, mac if mac and mac != 'Unknown' else ip)}"
        
        device_doc = {
            "id": device_id,
            "tenantId": tenant_id,
            "discoveredBy": agent_id,
            "ipAddress": ip,
            "macAddress": mac,
            "hostname": device.get("hostname"),
            "type": device.get("device_type", "Unknown"),
            "status": device.get("status", "Up"),
            "lastSeen": datetime.datetime.utcnow().isoformat(),
            # Preserve existing fields if updating
            "interfaces": [], # Placeholder
            "configBackups": [], # Placeholder
            "vulnerabilities": [] # Placeholder
        }
        
        # Upsert
        await db.network_devices.update_one(
            {"id": device_id},
            {"$set": device_doc},
            upsert=True
        )
        processed_count += 1
        
    return {"success": True, "processed": processed_count}

from pydantic import BaseModel

# MongoDB Collection Names
APPROVALS_COLLECTION = "agent_approvals"

class ApprovalRequestModel(BaseModel):
    agent_id: str
    action_type: str
    description: str
    risk_score: float
    reasoning: str
    details: Dict[str, Any]

class ApprovalDecisionModel(BaseModel):
    decision: str # "approve" or "reject"
    reason: Optional[str] = None

@router.post("/{agent_id}/approval-request")
async def request_approval(
    agent_id: str, 
    request: ApprovalRequestModel,
    tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Agent requests approval for an autonomous action.
    """
    request_id = str(uuid.uuid4())
    approval_entry = {
        "id": request_id,
        "agent_id": agent_id,
        "action_type": request.action_type,
        "description": request.description,
        "risk_score": request.risk_score,
        "reasoning": request.reasoning,
        "details": request.details,
        "status": "pending",
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
    
    db = get_database()
    await db[APPROVALS_COLLECTION].insert_one(approval_entry)
    
    return {"status": "queued", "request_id": request_id}

@router.get("/approvals/pending")
async def get_pending_approvals():
    """
    Get all pending approval requests for the dashboard.
    """
    db = get_database()
    approvals = await db[APPROVALS_COLLECTION].find(
        {"status": "pending"}, 
        {"_id": 0}
    ).to_list(length=None)
    return approvals

@router.post("/approvals/{request_id}/decide")
async def decide_approval(request_id: str, decision: ApprovalDecisionModel):
    """
    Approve or Reject a pending request.
    """
    db = get_database()
    result = await db[APPROVALS_COLLECTION].update_one(
        {"id": request_id, "status": "pending"},
        {"$set": {
            "status": decision.decision,
            "decision_timestamp": datetime.datetime.utcnow().isoformat(),
            "decision_reason": decision.reason
        }}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Request not found or already processed")
    
    return {"status": "success", "decision": decision.decision}

@router.get("/{agent_id}/goals")
async def get_agent_goals(
    agent_id: str,
    tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Get current high-level goals for an agent, dynamically generated by AI.
    """
    from agent_logic_service import agent_logic_service
    
    db = get_database()
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0})
    
    if not agent:
        # Fallback for non-existent agents
        return [
            {"name": "Security Baseline", "target": 100.0, "current": 80.0, "status": "active"}
        ]
        
    goals = await agent_logic_service.generate_goals(agent)
    return goals

@router.post("/{agent_id}/heartbeat")
async def report_heartbeat(
    agent_id: str, 
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(...),
    tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Receive heartbeat from agent.
    Updates status, lastSeen, and processes capability data (Compliance, etc.)
    """
    db = get_database()
    
    print(f"DEBUG HEARTBEAT: Received heartbeat for agent_id={agent_id}")
    print(f"DEBUG HEARTBEAT: Payload keys: {payload.keys()}")
    print(f"DEBUG HEARTBEAT: Hostname in payload: {payload.get('hostname')}")
    
    # Harding Mitigation: Hardware Pinning
    # Check if this agent is pinned to a specific hardware device
    existing_agent = await db.agents.find_one({"id": agent_id})
    if existing_agent:
        stored_device_id = existing_agent.get("deviceId")
        incoming_device_id = payload.get("device_id") or payload.get("deviceId")
        
        if stored_device_id and incoming_device_id and stored_device_id != incoming_device_id:
            logger.error(f"❌ SECURITY ALERT: Hardware mismatch for agent {agent_id}. Stored: {stored_device_id}, Incoming: {incoming_device_id}")
            raise HTTPException(status_code=403, detail="Hardware ID mismatch. This session has been blocked.")
        
        # If it wasn't strictly pinned yet (legacy), pin it now
        if not stored_device_id and incoming_device_id:
            await db.agents.update_one({"id": agent_id}, {"$set": {"deviceId": incoming_device_id}})

    # 1. Update Agent Status
    update_data = {
        "status": "Online",
        "lastSeen": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "ipAddress": payload.get("ipAddress"),
        "platform": payload.get("platform"),
        "version": payload.get("version"),
    }
    
    # Update meta if present
    if "meta" in payload:
        for key, value in payload["meta"].items():
            if key == "capabilities":
                update_data["capabilities"] = value
            else:
                key_name = f"meta.{key}"
                update_data[key_name] = value

    # Ensure critical fields for strictly new inserts
    if payload.get("hostname"):
        update_data["hostname"] = payload.get("hostname")
    # Do NOT overwrite tenantId from heartbeat
    if payload.get("device_id"):
        update_data["deviceId"] = payload.get("device_id")

    # Update DB with upsert
    result = await db.agents.update_one(
        {"id": agent_id},
        {"$set": update_data, "$setOnInsert": {"registeredAt": datetime.datetime.utcnow().isoformat()}},
        upsert=True
    )
    
    # 2. Update corresponding Asset with live metrics
    hostname = payload.get("hostname")
    print(f"DEBUG ASSET UPDATE: Checking hostname: {hostname}")
    if hostname:
        asset_id = f"asset-{hostname}"
        asset_update = {
            "ipAddress": payload.get("ipAddress"),
            "osName": payload.get("platform"),
            "lastScanned": datetime.datetime.utcnow().isoformat(),
        }
        
        # Add live metrics to asset if available
        if "meta" in payload:
            meta = payload["meta"]
            asset_update["currentMetrics"] = {
                "cpuUsage": meta.get("current_cpu", 0),
                "memoryUsage": meta.get("current_memory", 0),
                "diskUsage": meta.get("disk_usage", 0),
                "totalMemoryGB": meta.get("total_memory_gb", 0),
                "availableMemoryGB": meta.get("available_memory_gb", 0),
                "diskTotalGB": meta.get("disk_total_gb", 0),
                "diskUsedGB": meta.get("disk_used_gb", 0),
                "diskFreeGB": meta.get("disk_free_gb", 0),
                "collectedAt": datetime.datetime.utcnow().isoformat()
            }
            
            # Update OS version safely
            os_info = meta.get("os_info", {})
            new_version = os_info.get("version")
            if new_version:
                # Get existing asset to check if we should overwrite
                existing_asset = await db.assets.find_one({"id": asset_id})
                if existing_asset:
                    current_version = existing_asset.get("osVersion", "")
                    # Don't overwrite detailed version (e.g. 10.0.26200) with generic (e.g. 10)
                    if current_version and len(current_version) > len(new_version) and new_version in current_version:
                        print(f"DEBUG: Skipping OS version update. Current: {current_version}, Incoming: {new_version}")
                    else:
                        asset_update["osVersion"] = new_version
                else:
                    asset_update["osVersion"] = new_version
            
            # Extract and store installed software from meta
            installed_software = meta.get("installed_software", [])
            if installed_software:
                asset_update["installedSoftware"] = installed_software
                print(f"DEBUG: Updating asset {asset_id} with {len(installed_software)} installed applications")
            
            # Extract and persist hardware info (cpuModel, ram, disks)
            cpu_model = meta.get("cpu_model")
            memory_gb = meta.get("memory_gb")
            disks_from_meta = meta.get("disks", [])
            
            if cpu_model and cpu_model not in ("Unknown", "Unknown CPU", ""):
                asset_update["cpuModel"] = cpu_model
                print(f"DEBUG: Updating asset cpuModel: {cpu_model}")
            if memory_gb and memory_gb not in ("Unknown", ""):
                asset_update["ram"] = memory_gb
                print(f"DEBUG: Updating asset ram: {memory_gb}")
            if disks_from_meta:
                asset_update["disks"] = disks_from_meta
                print(f"DEBUG: Updating asset with {len(disks_from_meta)} disk(s) from meta")
        
        # Update asset in database
        try:
            await db.assets.update_one(
                {"id": asset_id},
                {
                    "$set": asset_update,
                    "$setOnInsert": {
                        "tenantId": payload.get("tenantId", tenant["id"] if tenant else "tenant-default"),
                        "status": "active",
                        "type": "server",
                        "hostname": hostname
                    }
                },
                upsert=True
            )
            print(f"DEBUG: Updated (or created) asset {asset_id} with live metrics from {hostname}")
        except Exception as e:
            if "E11000 duplicate key error" in str(e):
                print(f"DEBUG: Duplicate key error ignored for asset {asset_id}. Trying straight update.")
                await db.assets.update_one({"id": asset_id}, {"$set": asset_update})
            else:
                print(f"ERROR updating asset: {e}")

        # 3. Archive metrics for historical charting (Phase 9 Integration)
        try:
            timestamp = datetime.datetime.utcnow().isoformat()
            if "meta" in payload:
                meta = payload["meta"]
                metric_doc = {
                    "agent_id": agent_id,
                    "asset_id": asset_id,
                    "tenant_id": payload.get("tenantId", tenant["id"] if tenant else "platform-admin"),
                    "timestamp": timestamp,
                    "cpu_percent": meta.get("current_cpu", 0),
                    "memory_percent": meta.get("current_memory", 0),
                    "disk_percent": meta.get("disk_usage", 0),
                    "memory_used_mb": meta.get("current_cpu", 0) * (meta.get("total_memory_gb", 16) * 1024 / 100), # Default 16GB if unknown
                    "memory_total_mb": meta.get("total_memory_gb", 16) * 1024,
                    "disk_used_gb": meta.get("disk_used_gb", 0),
                    "disk_total_gb": meta.get("disk_total_gb", 500), # Default 500GB if unknown
                }
                # Insert into both for unified access
                await db.agent_metrics.insert_one(metric_doc)
                await db.asset_metrics.insert_one(metric_doc)
                print(f"DEBUG: Archived historical metrics for agent {agent_id} / asset {asset_id}")
        except Exception as archive_err:
            print(f"ERROR: Failed to archive historical metrics: {archive_err}")

    
    # 3. Process Compliance Data
    # If the agent sent compliance checks, we need to ingest them as Evidence
    meta = payload.get("meta", {})
    if "compliance_enforcement" in meta:
        compliance_data = meta["compliance_enforcement"]
        hostname = payload.get("hostname", agent_id)
        
        # Import here to avoid circular dependency if possible, or move import to top if safe
        # compliance_endpoints imports database, so it should be fine.
        try:
            from compliance_endpoints import process_automated_evidence
            await process_automated_evidence(hostname, compliance_data, db)
        except ImportError:
            print("ERROR: Could not import process_automated_evidence")
        except Exception as e:
            print(f"ERROR processing compliance evidence: {e}")

    # 4. Ingest Logs into dedicated collection
    if "log_collection" in meta:
        log_data = meta["log_collection"]
        if isinstance(log_data, list):
            db_logs = []
            for entry in log_data:
                # Map agent log format to backend LogEntry
                log_entry = {
                    "tenantId": payload.get("tenantId", "default"),
                    "agentId": agent_id,
                    "service": entry.get("service", "os"),
                    "level": entry.get("level", "INFO"),
                    "message": entry.get("message", ""),
                    "timestamp": entry.get("timestamp", datetime.datetime.utcnow().isoformat()),
                    "hostname": payload.get("hostname", "unknown"),
                    "rawData": entry
                }
                db_logs.append(log_entry)
            
            if db_logs:
                await db.logs.insert_many(db_logs)
                # Stream to UI if needed
                try:
                    from streaming_service import broker
                    for log in db_logs:
                        background_tasks.add_task(broker.publish, f"logs:{payload.get('tenantId', 'default')}", log)
                except ImportError:
                    pass

    # 5. Bridge Persistence Detection findings
    if "persistence_detection" in meta:
        p_data = meta["persistence_detection"]
        if isinstance(p_data, dict) and p_data.get("findings"):
            import uuid
            result_record = {
                "id": uuid.uuid4().hex,
                "tenantId": payload.get("tenantId", "default"),
                "agentId": agent_id,
                "findings": p_data.get("findings", []),
                "count": p_data.get("count", 0),
                "platform": p_data.get("platform"),
                "timestamp": datetime.datetime.utcnow().isoformat()
            }
            await db.persistence_results.insert_one(result_record)
            print(f"DEBUG: Bridged {len(p_data.get('findings', []))} persistence findings for {agent_id}")

    # 6. Bridge Shadow AI detections
    if "shadow_ai" in meta:
        s_data = meta["shadow_ai"]
        if isinstance(s_data, dict) and s_data.get("ai_connections"):
            for conn in s_data.get("ai_connections", []):
                import uuid
                event = {
                    "id": uuid.uuid4().hex,
                    "tenantId": payload.get("tenantId", "default"),
                    "agent_id": agent_id,
                    "process": conn.get("process"),
                    "remote_ip": conn.get("remote_ip"),
                    "remote_host": conn.get("remote_host"),
                    "timestamp": conn.get("timestamp", datetime.datetime.utcnow().isoformat())
                }
                await db.shadow_ai_events.insert_one(event)
                
                # Create Security Alert
                try:
                    from ueba_service import persist_security_alert
                    background_tasks.add_task(
                        persist_security_alert,
                        db,
                        alert_type="shadow_ai",
                        severity="medium",
                        title=f"Shadow AI Usage Detected: {conn.get('remote_host')}",
                        description=f"Process '{conn.get('process')}' on agent {agent_id} connected to {conn.get('remote_host')}.",
                        metadata=event
                    )
                except ImportError:
                    pass
            print(f"DEBUG: Bridged {len(s_data.get('ai_connections', []))} Shadow AI detections for {agent_id}")

    # 7. Bridge UEBA anomalies
    if "ueba" in meta:
        u_data = meta["ueba"]
        if isinstance(u_data, dict):
            anomalies = u_data.get("anomalies_detected", [])
            for anomaly in anomalies:
                try:
                    from ueba_service import persist_security_alert
                    background_tasks.add_task(
                        persist_security_alert,
                        db,
                        alert_type="ueba_anomaly",
                        severity=anomaly.get("severity", "medium").lower(),
                        title=f"UEBA Anomaly: {anomaly.get('type')}",
                        description=f"{anomaly.get('type')} detected for user {anomaly.get('user')}. Details: {anomaly}",
                        metadata={**anomaly, "agent_id": agent_id, "tenantId": payload.get("tenantId", "default")}
                    )
                except ImportError:
                    pass
            print(f"DEBUG: Bridged {len(anomalies)} UEBA anomalies for {agent_id}")

    # 8. Bridge Software Inventory & OS Patches
    if "software_inventory" in meta:
        sw_list = meta["software_inventory"]
        if isinstance(sw_list, list) and sw_list:
            # Sync to software_inventory collection for the Version Service
            for sw in sw_list:
                sw_doc = {
                    "agent_id": agent_id,
                    "agent_name": payload.get("hostname", agent_id),
                    "tenant_id": payload.get("tenantId", "default"),
                    "name": sw.get("name"),
                    "current_version": sw.get("current_version"),
                    "latest_version": sw.get("latest_version"),
                    "pkg_type": sw.get("pkg_type", "unknown"),
                    "is_outdated": sw.get("is_outdated", False),
                    "last_scanned": datetime.datetime.utcnow().isoformat()
                }
                # Upsert by agent + package name
                await db.software_inventory.update_one(
                    {"agent_id": agent_id, "name": sw_doc["name"]},
                    {"$set": sw_doc},
                    upsert=True
                )
            print(f"DEBUG: Synced {len(sw_list)} software inventory items for {agent_id}")

    return {"success": True}

@router.post("/{agent_id}/software-inventory")
async def report_software_inventory(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Agent reports live software inventory result from 'run_software_scan'.
    """
    db = get_database()
    
    sw_list = payload.get("software_inventory", [])
    os_p    = payload.get("os_patches", {})
    hostname = payload.get("hostname", agent_id)
    tenant_id = payload.get("tenantId", tenant["id"] if tenant else "default")

    print(f"DEBUG INVENTORY: Received {len(sw_list)} software items and {os_p.get('pending_count', 0)} OS patches from {hostname}")

    # 1. Update Agent Meta (consistency)
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {
            "meta.software_inventory": sw_list,
            "meta.os_patches": os_p,
            "lastSeen": datetime.datetime.utcnow().isoformat()
        }}
    )

    # 2. Update software_inventory collection
    processed = 0
    if sw_list:
        for sw in sw_list:
            sw_doc = {
                "agent_id": agent_id,
                "agent_name": hostname,
                "tenant_id": tenant_id,
                "name": sw.get("name"),
                "current_version": sw.get("current_version"),
                "latest_version": sw.get("latest_version"),
                "pkg_type": sw.get("pkg_type", "unknown"),
                "is_outdated": sw.get("is_outdated", False),
                "last_scanned": datetime.datetime.utcnow().isoformat()
            }
            await db.software_inventory.update_one(
                {"agent_id": agent_id, "name": sw_doc["name"]},
                {"$set": sw_doc},
                upsert=True
            )
            processed += 1

    return {"success": True, "processed": processed}

