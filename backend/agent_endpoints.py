from fastapi import APIRouter, Depends, HTTPException, Query, Body, Header, BackgroundTasks
from typing import List, Optional, Dict, Any
from database import get_database
from authentication_service import get_current_user, create_access_token
from datetime import datetime, timezone, timedelta
import uuid
import json
from cache_service import cached, invalidate_cache
from pagination_utils import paginate_mongo_query, PaginationParams

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
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            tenant_id = payload.get("tenant_id")
            if not tenant_id:
                raise HTTPException(status_code=403, detail="Invalid Agent Token: No tenant_id")

            # Revocation check — agent tokens carry a jti since the fix
            jti = payload.get("jti")
            if jti:
                revoked = await db.revoked_tokens.find_one({"jti": jti}, {"_id": 1})
                if revoked:
                    raise HTTPException(status_code=403, detail="Agent token has been revoked")

            tenant = await db.tenants.find_one({"id": tenant_id})
            if not tenant:
                raise HTTPException(status_code=403, detail=f"Tenant {tenant_id} not found")
            return tenant
        except HTTPException:
            raise
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
        "lastSeen": datetime.now(timezone.utc).isoformat(),
        "registeredAt": existing_agent.get("registeredAt") if existing_agent else datetime.now(timezone.utc).isoformat()
    }
    
    # Log to file for debugging
    with open("register_debug.log", "a") as f:
        f.write(f"[{datetime.now(timezone.utc)}] Registering agent {agent_id} for tenant {tenant['id']}\n")
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
        "lastScanned": datetime.now(timezone.utc).isoformat(),
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
    
    try:
        await db.assets.update_one(
            {"id": asset_id},
            {"$set": asset_data},
            upsert=True
        )
        print(f"DEBUG: Asset {asset_id} created/updated.")
    except Exception as e:
        if "E11000 duplicate key error" in str(e):
            print(f"DEBUG: Duplicate key error for asset {asset_id} resolved by straight update.")
            await db.assets.update_one({"id": asset_id}, {"$set": asset_data})
        else:
            raise e
    
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
    
    # Generate agent JWT with a jti so it can be individually revoked
    token_data = {"sub": agent_id, "role": "agent", "tenant_id": tenant["id"], "jti": str(uuid.uuid4())}
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
    current_time = datetime.now(timezone.utc)
    
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
                        # Core telemetry
                        "metrics_collection":  "Systems Telemetry",
                        "log_collection":      "Unified Logging",
                        "process_monitor":     "Process Sentinel",
                        # Security detection
                        "vulnerability_scanning":       "Vulnerability Scanner",
                        "fim":                          "Integrity Guard",
                        "compliance_enforcement":       "Compliance Shield",
                        "runtime_security":             "XDR Behavioral",
                        "edr_realtime":                 "EDR Active",
                        "persistence_detection":        "Persistence Detector",
                        # Network & cloud
                        "network_discovery": "Network Discovery",
                        "cloud_metadata":    "Cloud Metadata Collector",
                        "web_monitor":       "Web Monitor",
                        # Data & privacy
                        "pii_scanner":   "PII Data Scanner",
                        "sbom_analysis": "SBOM Analyzer",
                        # Advanced AI
                        "predictive_health": "Predictive Health AI",
                        "ueba":              "Behavior Analytics (UEBA)",
                        "ebpf_tracing":      "eBPF Kernel Tracer",
                        "shadow_ai":         "Shadow AI Detector",
                        # Remediation
                        "system_patching":              "Autonomous Patching",
                        "software_management":          "Software Manager",
                        "process_injection_simulation": "Injection Simulator",
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
            # Derive baseline from real agent metrics; fall back to conservative defaults
            base_cpu = float(agent.get("cpuUsage") or agent.get("cpu_usage") or 25)
            base_mem = float(agent.get("memoryUsage") or agent.get("memory_usage") or 45)
            current_score = float(agent.get("securityScore") or 78)
            predictions = []
            for i in range(25):
                future_time = current_time + timedelta(hours=i)
                work_boost = 15 if 9 <= future_time.hour <= 17 else 0
                predictions.append({
                    "timestamp": future_time.strftime("%H:%M"),
                    "cpu_prediction": round(min(100, base_cpu + work_boost + (i % 5)), 1),
                    "memory_prediction": round(min(100, base_mem + (i % 8)), 1),
                    "health_score": round(max(70, current_score - (i % 3)), 1),
                })
            warnings = []
            if base_cpu > 70:
                warnings.append("High baseline CPU — monitor for spikes during business hours")
            if base_mem > 80:
                warnings.append("Memory utilisation elevated — consider capacity review")
            if not warnings:
                warnings.append("No anomalies predicted in the next 24 hours")
            agent["meta"]["predictive_health"] = {
                "current_score": round(current_score, 1),
                "predictions": predictions,
                "warnings": warnings,
            }
            
    return result


# ── Search & Bulk (must be declared before /{agent_id} wildcard routes) ────────

@router.get("/search")
async def search_agents_route(
    q: str = Query(..., min_length=1, description="Search query"),
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """Full-text search across agent name, hostname, IP, and OS fields."""
    regex = {"$regex": q, "$options": "i"}
    query: Dict[str, Any] = {
        "$or": [
            {"name": regex},
            {"hostname": regex},
            {"ipAddress": regex},
            {"os": regex},
            {"platform": regex},
        ]
    }
    if status:
        query["status"] = status
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", "default")
    agents = await db.agents.find(query, {"_id": 0}).to_list(length=limit)
    return agents


@router.delete("/bulk")
async def bulk_delete_agents_route(
    ids: List[str] = Body(..., description="List of agent IDs to delete"),
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """Delete multiple agents by ID."""
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    user_role = getattr(current_user, "role", "user")
    query: Dict[str, Any] = {"id": {"$in": ids}}
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", "default")
    result = await db.agents.delete_many(query)
    return {"success": True, "deleted": result.deleted_count}


@router.patch("/bulk")
async def bulk_update_agents_route(
    body: Dict[str, Any] = Body(..., description='{"ids": [...], "patch": {...}}'),
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """Apply the same patch to multiple agents."""
    ids = body.get("ids", [])
    patch = body.get("patch", {})
    if not ids or not patch:
        raise HTTPException(status_code=400, detail="ids and patch are required")
    patch.pop("id", None)
    user_role = getattr(current_user, "role", "user")
    query: Dict[str, Any] = {"id": {"$in": ids}}
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", "default")
    result = await db.agents.update_many(query, {"$set": patch})
    return {"matched": result.matched_count, "modified": result.modified_count}


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
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
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
            {"$set": {"status": "sent", "sent_at": datetime.now(timezone.utc).isoformat()}}
        )
        
    return [{"instruction": i.get("type"), "payload": i.get("payload")} for i in instructions]

@router.post("/{hostname}/instructions/result")
async def report_instruction_result(
    hostname: str, 
    result: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Agent reports the result of an instruction execution.
    """
    logger.info("Agent %s reported instruction result: type=%s status=%s", hostname, result.get("type"), result.get("status"))
    
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
    task_id = f"task-{datetime.now(timezone.utc).timestamp()}"
    
    new_task = {
        "id": task_id,
        "description": task.get("description"),
        "agentId": task.get("agentId"),
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": getattr(current_user, "username", None) or (current_user.get("username") if isinstance(current_user, dict) else None)
    }
    
    await db.agent_tasks.insert_one(new_task)
    return {"success": True, "taskId": task_id}

@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, current_user=Depends(get_current_user)):
    """Frontend polls this for deployment task status."""
    db = get_database()
    
    # Check agent_instructions (primary for software deploy)
    task = await db.agent_instructions.find_one({"id": task_id})
    if task:
        return {
            "task_id": task.get("id", task_id),
            "status": task.get("status", "unknown"),
            "agent_id": task.get("agent_id"),
            "instruction": task.get("instruction"),
            "result": task.get("result"),
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at")
        }
    
    # Fallback: Check agent_tasks collection
    task = await db.agent_tasks.find_one({"id": task_id}, {"_id": 0})
    if task:
        return task
    
    raise HTTPException(status_code=404, detail="Task not found")

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
        {"$set": {"tenantId": target_tenant_id, "updatedAt": datetime.now(timezone.utc).isoformat()}}
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

    def _normalise_caps(raw) -> list:
        """Ensure capabilities are always stored as plain string IDs, not rich objects."""
        if not isinstance(raw, list):
            return []
        return [
            c if isinstance(c, str) else c.get("id", "")
            for c in raw
            if (isinstance(c, str) and c) or (isinstance(c, dict) and c.get("id"))
        ]

    # Fields allowed to update
    allowed_fields = ["capabilities", "agentCapabilities", "status", "alias", "tags", "remediationAttempts"]

    # Prepare update payload
    set_data = {}
    for field in allowed_fields:
        if field in update_data:
            value = update_data[field]
            # Normalise capability lists to plain string IDs before persisting
            if field in ("capabilities", "agentCapabilities"):
                value = _normalise_caps(value)
            set_data[field] = value

            # Keep both field names in sync
            if field == "agentCapabilities":
                set_data["capabilities"] = value
            if field == "capabilities":
                set_data["agentCapabilities"] = value

    if not set_data:
        return agent # No changes

    set_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    
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
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Get the effective configuration for an agent.
    Used by the Agent to pull its config.
    """
    db = get_database()
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        # Fallback: Check if agent_id is actually a hostname
        agent = await db.agents.find_one({"hostname": agent_id})
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        else:
            logger.info(f"Resolved agent configuration request for hostname {agent_id} to ID {agent['id']}")
        
    # Construct config object.
    # Use stored capabilities if the user has ever saved a configuration
    # (key present in document, even if empty = all disabled).
    # Only fall back to defaults for brand-new agents that have never been configured.
    if "capabilities" in agent:
        capabilities = agent["capabilities"]  # respect user's choice, including []
    else:
        capabilities = [
            # Core telemetry (always on by default)
            "metrics_collection",
            "log_collection",
            "process_monitor",
            # Security detection
            "vulnerability_scanning",
            "fim",
            "compliance_enforcement",
            "runtime_security",
            "edr_realtime",
            "persistence_detection",
            # Network & cloud
            "network_discovery",
            "cloud_metadata",
            "web_monitor",
            # Data & privacy
            "pii_scanner",
            "sbom_analysis",
            # Advanced AI
            "predictive_health",
            "ueba",
            "ebpf_tracing",
            "shadow_ai",
            # Remediation
            "system_patching",
            "software_management",
            "process_injection_simulation",
        ]

    # Define default collection intervals (seconds) if not stored
    intervals = agent.get("collectionIntervals", {
        # Core telemetry
        "metrics_collection":  60,
        "log_collection":      300,
        "process_monitor":     30,
        # Security detection
        "vulnerability_scanning":       3600,
        "fim":                          600,
        "compliance_enforcement":       3600,
        "runtime_security":             180,
        "edr_realtime":                 15,
        "persistence_detection":        3600,
        # Network & cloud
        "network_discovery": 7200,
        "cloud_metadata":    900,
        "web_monitor":       300,
        # Data & privacy
        "pii_scanner":   3600,
        "sbom_analysis": 3600,
        # Advanced AI
        "predictive_health": 600,
        "ueba":              300,
        "ebpf_tracing":      60,
        "shadow_ai":         1800,
        # Remediation
        "system_patching":              3600,
        "software_management":          3600,
        "process_injection_simulation": 86400,
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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": getattr(current_user, "email", "unknown")
    }
    
    result = await db.agent_instructions.insert_one(new_instruction)
    
    return {"success": True, "message": "Network scan initiated", "instruction_id": str(result.inserted_id)}

@router.post("/{agent_id}/discovery/results")
async def report_network_scan_results(
    agent_id: str, 
    results: List[Dict[str, Any]] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
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
        
        # Fetch open vulnerabilities for this device from patches collection
        hostname = device.get("hostname") or ""
        vuln_query: dict = {"tenantId": tenant_id,
                            "status": {"$in": ["pending", "Pending", "open", "Open"]}}
        if hostname:
            vuln_query["affectedSoftware"] = {"$regex": hostname, "$options": "i"}
        elif ip:
            vuln_query["affectedSoftware"] = {"$regex": ip, "$options": "i"}
        device_vulns = await db.patches.find(
            vuln_query, {"_id": 0, "cveId": 1, "severity": 1, "description": 1}
        ).to_list(length=20)

        # Fields that change on every heartbeat
        live_fields = {
            "id": device_id,
            "tenantId": tenant_id,
            "discoveredBy": agent_id,
            "ipAddress": ip,
            "macAddress": mac,
            "hostname": hostname or device.get("hostname"),
            "type": device.get("device_type", "Unknown"),
            "status": device.get("status", "Up"),
            "lastSeen": datetime.now(timezone.utc).isoformat(),
            "vulnerabilities": device_vulns,
        }

        # Upsert: only set interfaces/configBackups on first insert
        await db.network_devices.update_one(
            {"id": device_id},
            {
                "$set": live_fields,
                "$setOnInsert": {"interfaces": [], "configBackups": []},
            },
            upsert=True,
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
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
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
        "timestamp": datetime.now(timezone.utc).isoformat()
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
async def decide_approval(
    request_id: str,
    decision: ApprovalDecisionModel,
    current_user: dict = Depends(get_current_user),
):
    """
    Approve or Reject a pending request. Requires authenticated operator.
    """
    if decision.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")
    db = get_database()
    result = await db[APPROVALS_COLLECTION].update_one(
        {"id": request_id, "status": "pending"},
        {"$set": {
            "status": decision.decision,
            "decision_timestamp": datetime.now(timezone.utc).isoformat(),
            "decision_reason": decision.reason,
            "decided_by": getattr(current_user, "username", str(current_user)),
        }}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Request not found or already processed")

    return {"status": "success", "decision": decision.decision}


@router.get("/agentic-decisions/all")
async def list_all_agentic_decisions(
    limit: int = 100,
    status: str = None,
    db=Depends(get_database),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Global view of all agentic decisions across every agent (operator overview)."""
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    cursor = db.agentic_decisions.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    decisions = await cursor.to_list(limit)
    return {
        "decisions": decisions,
        "total": len(decisions),
        "pending": sum(1 for d in decisions if d.get("status") == "pending_approval"),
    }


@router.get("/{agent_id}/goals")
async def get_agent_goals(
    agent_id: str,
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
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
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
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
        "lastSeen": datetime.now(timezone.utc).isoformat(),
        "ipAddress": payload.get("ipAddress"),
        "platform": payload.get("platform"),
        "version": payload.get("version"),
    }
    
    # Update meta if present
    if "meta" in payload:
        for key, value in payload["meta"].items():
            if key in ("capabilities", "available_capabilities"):
                # What the agent *supports* — never overwrite the user-configured
                # enabled list. Store separately as availableCapabilities.
                update_data["availableCapabilities"] = value
            elif key == "capabilities_status":
                update_data["meta.capabilities_status"] = value
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
        {"$set": update_data, "$setOnInsert": {"registeredAt": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )

    # Store a lightweight metrics snapshot for capacity trend analysis
    _meta = payload.get("meta", {})
    if _meta.get("current_cpu") is not None or _meta.get("current_memory") is not None:
        _snapshot = {
            "agent_id": agent_id,
            "hostname": payload.get("hostname", agent_id),
            "cpu": _meta.get("current_cpu", 0),
            "memory": _meta.get("current_memory", 0),
            "disk": _meta.get("disk_usage", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await db.agent_metrics_history.insert_one(_snapshot)
        # Keep only the last 100 snapshots per agent to control collection size
        count = await db.agent_metrics_history.count_documents({"agent_id": agent_id})
        if count > 100:
            oldest = await db.agent_metrics_history.find(
                {"agent_id": agent_id}, {"_id": 1}
            ).sort("timestamp", 1).limit(count - 100).to_list(length=count - 100)
            if oldest:
                await db.agent_metrics_history.delete_many(
                    {"_id": {"$in": [d["_id"] for d in oldest]}}
                )

    # 2. Update corresponding Asset with live metrics
    hostname = payload.get("hostname")
    print(f"DEBUG ASSET UPDATE: Checking hostname: {hostname}")
    if hostname:
        asset_id = f"asset-{hostname}"
        asset_update = {
            "ipAddress": payload.get("ipAddress"),
            "osName": payload.get("platform"),
            "lastScanned": datetime.now(timezone.utc).isoformat(),
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
                "collectedAt": datetime.now(timezone.utc).isoformat()
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
                        "tenantId": payload.get("tenantId", _tenant["id"] if _tenant else "tenant-default"),
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
            timestamp = datetime.now(timezone.utc).isoformat()
            if "meta" in payload:
                meta = payload["meta"]
                metric_doc = {
                    "agent_id": agent_id,
                    "asset_id": asset_id,
                    "tenant_id": payload.get("tenantId", _tenant["id"] if _tenant else "platform-admin"),
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
                    "timestamp": entry.get("timestamp", datetime.now(timezone.utc).isoformat()),
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
                "timestamp": datetime.now(timezone.utc).isoformat()
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
                    "timestamp": conn.get("timestamp", datetime.now(timezone.utc).isoformat())
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
                    "last_scanned": datetime.now(timezone.utc).isoformat()
                }
                # Upsert by agent + package name
                await db.software_inventory.update_one(
                    {"agent_id": agent_id, "name": sw_doc["name"]},
                    {"$set": sw_doc},
                    upsert=True
                )
            print(f"DEBUG: Synced {len(sw_list)} software inventory items for {agent_id}")

    # 9. Bridge FIM violations
    if "fim" in meta:
        fim_data = meta["fim"]
        if isinstance(fim_data, dict) and fim_data.get("violations"):
            import uuid as _uuid
            for v in fim_data["violations"]:
                try:
                    from ueba_service import persist_security_alert
                    background_tasks.add_task(
                        persist_security_alert, db,
                        alert_type="fim_violation",
                        severity="high",
                        title=f"File Integrity Violation: {v.get('path')}",
                        description=f"Critical file modified on agent {agent_id}: {v.get('path')}. "
                                    f"Previous checksum: {v.get('previous_checksum')}, "
                                    f"New checksum: {v.get('current_checksum')}",
                        metadata={**v, "agent_id": agent_id,
                                  "tenantId": payload.get("tenantId", "default")},
                    )
                except ImportError:
                    pass
            await db.fim_violations.insert_many([
                {**v, "agent_id": agent_id,
                 "tenantId": payload.get("tenantId", "default"),
                 "timestamp": datetime.now(timezone.utc).isoformat()}
                for v in fim_data["violations"]
            ])
            print(f"DEBUG: Bridged {len(fim_data['violations'])} FIM violations for {agent_id}")

    # 10. Bridge PII Scanner findings
    if "pii_scanner" in meta:
        pii_data = meta["pii_scanner"]
        if isinstance(pii_data, dict) and pii_data.get("pii_found"):
            try:
                from ueba_service import persist_security_alert
                background_tasks.add_task(
                    persist_security_alert, db,
                    alert_type="pii_detected",
                    severity="high",
                    title=f"PII Detected on Agent {agent_id}",
                    description=f"{pii_data.get('findings_count', 0)} file(s) contain PII patterns "
                                f"({pii_data.get('scanned_count', 0)} files scanned).",
                    metadata={**pii_data, "agent_id": agent_id,
                              "tenantId": payload.get("tenantId", "default")},
                )
            except ImportError:
                pass
            await db.pii_findings.update_one(
                {"agent_id": agent_id},
                {"$set": {**pii_data, "agent_id": agent_id,
                          "tenantId": payload.get("tenantId", "default"),
                          "timestamp": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
            print(f"DEBUG: Bridged PII findings ({pii_data.get('findings_count', 0)}) for {agent_id}")

    # 11. Bridge Runtime Security violations
    if "runtime_security" in meta:
        rs_data = meta["runtime_security"]
        if isinstance(rs_data, dict) and rs_data.get("suspicious_activities"):
            critical_items = [
                a for a in rs_data["suspicious_activities"]
                if a.get("severity") in ("critical", "high")
            ]
            for item in critical_items:
                try:
                    from ueba_service import persist_security_alert
                    background_tasks.add_task(
                        persist_security_alert, db,
                        alert_type="runtime_security",
                        severity=item.get("severity", "high"),
                        title=f"Runtime Threat: {item.get('type')} on {agent_id}",
                        description=item.get("description", "Suspicious runtime activity detected"),
                        metadata={**item, "agent_id": agent_id,
                                  "tenantId": payload.get("tenantId", "default")},
                    )
                except ImportError:
                    pass
            if critical_items:
                print(f"DEBUG: Bridged {len(critical_items)} critical runtime security items for {agent_id}")

# 12. **SOFTWARE DEPLOYMENT EXECUTION** (MSI/Windows support)
    # Check for pending software instructions from /api/software/deploy
    instruction_type = meta.get("pending_instruction_type")
    instruction_payload = meta.get("pending_instruction_payload", {})
    
    if instruction_type and instruction_type.startswith(("install_software", "upgrade_software")):
        pkg_type = instruction_payload.get("pkg_type", "unknown")
        download_url = instruction_payload.get("download_url")
        install_args = instruction_payload.get("install_args", "")
        package_name = instruction_payload.get("package")
        
        execution_result = {"success": False, "message": "Unhandled package type"}
        
        if pkg_type == "msi" and download_url:
            # MSI Silent Install (Windows)
            cmd = f'ms iexec /i "{download_url}" /quiet /norestart {install_args}'.strip()
            try:
                import subprocess
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
                execution_result = {
                    "success": result.returncode == 0,
                    "message": result.stdout or result.stderr or "MSI executed",
                    "exit_code": result.returncode,
                    "stdout": result.stdout[:500],
                    "stderr": result.stderr[:500]
                }
                print(f"MSI Deploy: {package_name} on {agent_id} → {execution_result['success']}")
            except subprocess.TimeoutExpired:
                execution_result = {"success": False, "message": "Installation timeout (5min)"}
            except Exception as exec_err:
                execution_result = {"success": False, "message": f"Execution failed: {exec_err}"}
        
        elif pkg_type == "exe" and download_url:
            # EXE Silent Install via PowerShell download-and-run
            safe_url = download_url.replace("'", "")  # prevent injection in PS string
            safe_args = install_args.replace('"', '').replace("'", "")
            cmd = (
                "powershell -WindowStyle Hidden -Command \""
                f"Invoke-WebRequest -Uri '{safe_url}' -OutFile $env:TEMP\\\\omni_installer.exe; "
                f"& $env:TEMP\\\\omni_installer.exe /S {safe_args}; "
                "Remove-Item $env:TEMP\\\\omni_installer.exe -Force\""
            )
            try:
                import subprocess
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
                execution_result = {
                    "success": result.returncode == 0,
                    "message": result.stdout or result.stderr or "EXE installer executed",
                    "exit_code": result.returncode,
                    "stdout": result.stdout[:500],
                    "stderr": result.stderr[:500],
                }
                print(f"EXE Deploy: {package_name} on {agent_id} → {execution_result['success']}")
            except subprocess.TimeoutExpired:
                execution_result = {"success": False, "message": "Installation timeout (5min)"}
            except Exception as exec_err:
                execution_result = {"success": False, "message": f"Execution failed: {exec_err}"}
        
        # Report result back - Update instruction status
        instruction_id = meta.get("pending_instruction_id")
        if instruction_id:
            await db.agent_instructions.update_one(
                {"id": instruction_id},
                {"$set": {
                    "status": "completed" if execution_result["success"] else "failed",
                    "result": execution_result,
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        
        # Clear pending instruction
        update_data["meta.pending_instruction_type"] = None
        update_data["meta.pending_instruction_payload"] = None
        update_data["meta.pending_instruction_id"] = None

    # 13. Process task execution feedback from agent (existing)
    task_feedback_list = meta.get("task_feedback", [])
    if isinstance(task_feedback_list, list) and task_feedback_list:
        try:
            from response_orchestrator import ResponseOrchestrator
            _orchestrator = ResponseOrchestrator()
            for fb in task_feedback_list:
                task_id = fb.get("task_id")
                if not task_id:
                    continue
                await _orchestrator.record_feedback(
                    task_id=task_id,
                    success=fb.get("success", True),
                    false_positive=fb.get("false_positive", False),
                    message=fb.get("message", ""),
                    reported_by="agent",
                )
            print(f"DEBUG: Processed {len(task_feedback_list)} task feedback entries for {agent_id}")
        except Exception as fb_err:
            print(f"ERROR processing task feedback: {fb_err}")

    return {"success": True}

@router.post("/{agent_id}/software-inventory")
async def report_software_inventory(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Agent reports live software inventory result from 'run_software_scan'.
    """
    db = get_database()
    
    sw_list = payload.get("software_inventory", [])
    os_p    = payload.get("os_patches", {})
    hostname = payload.get("hostname", agent_id)
    tenant_id = payload.get("tenantId", _tenant["id"] if _tenant else "default")

    print(f"DEBUG INVENTORY: Received {len(sw_list)} software items and {os_p.get('pending_count', 0)} OS patches from {hostname}")

    # 1. Update Agent Meta (consistency)
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {
            "meta.software_inventory": sw_list,
            "meta.os_patches": os_p,
            "lastSeen": datetime.now(timezone.utc).isoformat()
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
                "last_scanned": datetime.now(timezone.utc).isoformat()
            }
            await db.software_inventory.update_one(
                {"agent_id": agent_id, "name": sw_doc["name"]},
                {"$set": sw_doc},
                upsert=True
            )
            processed += 1

    return {"success": True, "processed": processed}


# ── IoC Broadcast Polling ──────────────────────────────────────────────────────

@router.get("/{agent_id}/threat-intel")
async def get_threat_intel_broadcasts(
    agent_id: str,
    db=Depends(get_database),
):
    """
    Agents poll this endpoint to receive IoC broadcasts created by the correlation
    engine. Each broadcast is returned only once per agent (seen_agents dedup).
    """
    agent = await db.agents.find_one({"id": agent_id}, {"tenantId": 1})
    if not agent:
        return []
    tenant_id = agent.get("tenantId", "default")

    # Look back 1 hour
    threshold = (datetime.now(timezone.utc) - datetime.timedelta(hours=1)).isoformat()
    broadcasts = await db.threat_intel_broadcast.find(
        {
            "tenant_id": tenant_id,
            "timestamp": {"$gte": threshold},
            "seen_agents": {"$ne": agent_id},
        },
        {"_id": 0},
    ).to_list(length=20)

    if broadcasts:
        await db.threat_intel_broadcast.update_many(
            {"tenant_id": tenant_id, "timestamp": {"$gte": threshold}},
            {"$addToSet": {"seen_agents": agent_id}},
        )

    return broadcasts


@router.post("/{agent_id}/logs/raw")
async def receive_raw_logs(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
):
    """Receive raw OS logs shipped by the LogShipperCapability and ingest into SIEM."""
    logs = payload.get("logs", [])
    if logs:
        now = datetime.now(timezone.utc).isoformat()
        docs = [
            {
                "agent_id": agent_id,
                "source": log.get("source", "unknown"),
                "raw_message": log.get("raw_message", ""),
                "event_id": log.get("event_id"),
                "collected_at": log.get("collected_at", now),
                "ingested_at": now,
            }
            for log in logs
        ]
        await db.raw_logs.insert_many(docs)
    return {"success": True, "ingested": len(logs)}


@router.post("/{agent_id}/threat-hunt-results")
async def receive_threat_hunt_results(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
):
    """Store threat hunt results reported by an agent after run_threat_hunt dispatch."""
    await db.threat_hunt_results.insert_one({
        "agent_id": agent_id,
        "timestamp": payload.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "results": payload.get("results", {}),
    })
    return {"success": True}


# ── Agent Playbook Polling ──────────────────────────────────────────────────

@router.get("/{agent_id}/pending-playbooks")
async def get_pending_playbooks_for_agent(
    agent_id: str,
    db=Depends(get_database),
):
    """
    Agent polls this endpoint to discover playbooks assigned directly to it
    or playbooks triggered by agent-side events (on_agent_start, on_heartbeat,
    on_threat_detected).  Playbooks are returned once per pending cycle — the
    caller is responsible for marking them as received via POST /playbook-ack.
    """
    agent = await db.agents.find_one({"id": agent_id}, {"tenantId": 1})
    if not agent:
        return []

    tenant_id = agent.get("tenantId", "default")

    cursor = db.playbooks.find(
        {
            "tenant_id": {"$in": [tenant_id, "platform"]},
            "enabled": True,
            "$or": [
                {"assigned_agents": agent_id},
                {"trigger_type": {"$in": ["on_agent_start", "on_heartbeat", "on_threat_detected"]}},
            ],
            # Exclude playbooks already acknowledged by this agent
            "acked_agents": {"$ne": agent_id},
        },
        {"_id": 0, "id": 1, "name": 1, "steps": 1, "trigger_type": 1, "trigger_conditions": 1},
    )
    playbooks = await cursor.to_list(length=20)
    return playbooks


@router.post("/{agent_id}/playbook-ack")
async def ack_playbook(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
):
    """Agent acknowledges receipt/execution of a playbook so it isn't re-delivered."""
    playbook_id = payload.get("playbook_id")
    status      = payload.get("status", "received")   # received | executed | failed
    if not playbook_id:
        return {"success": False, "reason": "playbook_id required"}

    await db.playbooks.update_one(
        {"id": playbook_id},
        {
            "$addToSet": {"acked_agents": agent_id},
            "$push": {
                "execution_log": {
                    "agent_id":    agent_id,
                    "status":      status,
                    "acked_at":    datetime.now(timezone.utc).isoformat(),
                }
            },
        },
    )
    return {"success": True}


# ── Dynamic Safety Rules ────────────────────────────────────────────────────

@router.get("/{agent_id}/safety-rules")
async def get_safety_rules(
    agent_id: str,
    db=Depends(get_database),
):
    """
    Return tenant-specific safety guardrail rules for the agent.
    Operators can override the agent's hardcoded defaults via the UI/API.
    Falls back to empty lists (agent uses built-in defaults) when no record exists.
    """
    agent = await db.agents.find_one({"id": agent_id}, {"tenantId": 1})
    tenant_id = agent.get("tenantId") if agent else None
    doc = None
    if tenant_id:
        doc = await db.agent_safety_rules.find_one(
            {"tenant_id": tenant_id}, {"_id": 0}
        )
    return {
        "forbidden_actions": (doc or {}).get("forbidden_actions", []),
        "approval_required": (doc or {}).get("approval_required", []),
        "safe_actions":      (doc or {}).get("safe_actions", []),
    }


@router.put("/{agent_id}/safety-rules")
async def update_safety_rules(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
):
    """Operators update tenant-level safety rules via this endpoint."""
    agent = await db.agents.find_one({"id": agent_id}, {"tenantId": 1})
    if not agent:
        return {"success": False, "reason": "agent not found"}
    tenant_id = agent.get("tenantId")
    await db.agent_safety_rules.update_one(
        {"tenant_id": tenant_id},
        {"$set": {**payload, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "tenant_id": tenant_id}


# ── Agentic Decision Logging ──────────────────────────────────────────────────

@router.post("/{agent_id}/agentic-decision")
async def record_agentic_decision(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    _auth: Dict[str, Any] = Depends(verify_agent_key),
):
    """
    Agent submits an agentic reasoning decision for audit logging and optional
    human approval.  Called when confidence < threshold or action is APPROVAL_REQUIRED.
    """
    doc = {
        "id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "context": payload.get("context", {}),
        "recommended_action": payload.get("recommended_action", "none"),
        "confidence": float(payload.get("confidence", 0.0)),
        "reasoning": payload.get("reasoning", ""),
        "requires_approval": bool(payload.get("requires_approval", False)),
        "status": "pending_approval" if payload.get("requires_approval") else "auto_approved",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.agentic_decisions.insert_one(doc)
    doc.pop("_id", None)
    return {"decision_id": doc["id"], "status": doc["status"]}


@router.get("/{agent_id}/agentic-decisions")
async def list_agentic_decisions(
    agent_id: str,
    limit: int = 50,
    db=Depends(get_database),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Operators view the agent's autonomous decision history."""
    cursor = db.agentic_decisions.find(
        {"agent_id": agent_id}, {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    return {"decisions": await cursor.to_list(limit)}


@router.patch("/{agent_id}/agentic-decisions/{decision_id}")
async def approve_agentic_decision(
    agent_id: str,
    decision_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Operator approves or rejects a pending agentic decision."""
    approved = bool(payload.get("approved", False))
    await db.agentic_decisions.update_one(
        {"id": decision_id, "agent_id": agent_id},
        {"$set": {
            "status": "approved" if approved else "rejected",
            "reviewer_note": payload.get("reviewer_note", ""),
            "reviewed_by": current_user.get("sub"),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"ok": True, "approved": approved}


# ── FIM Event Ingestion (agent-side HTTP fallback) ────────────────────────────

@router.post("/{agent_id}/fim-events")
async def ingest_fim_event(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    _auth=Depends(verify_agent_key),
):
    """Receive FIM events via HTTP when Socket.IO is unavailable."""
    import uuid as _uuid
    doc = {
        "id": str(_uuid.uuid4()),
        "agent_id": agent_id,
        "path": payload.get("path", ""),
        "event_type": payload.get("event_type", "unknown"),
        "severity": payload.get("severity", "high"),
        "message": payload.get("message", ""),
        "source": payload.get("source", "FileWatcher"),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.fim_events.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "event_id": doc["id"]}


@router.get("/{agent_id}/fim-events")
async def list_fim_events(
    agent_id: str,
    limit: int = 100,
    db=Depends(get_database),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Retrieve FIM events for a given agent (operator view)."""
    cursor = db.fim_events.find({"agent_id": agent_id}, {"_id": 0}).sort("received_at", -1).limit(limit)
    return {"events": await cursor.to_list(limit)}


# ── Approval Polling (agent-side) ────────────────────────────────────────────

@router.post("/{agent_id}/shadow-ai-scan")
async def post_shadow_ai_scan(
    agent_id: str,
    body: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent posts Shadow AI detection results (local AI processes, ports, cloud connections)."""
    db = get_database()
    tenant_id = _tenant.get("id", "default")

    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    scanned_at = datetime.now(timezone.utc).isoformat()
    doc = {
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "scanned_at": scanned_at,
        "detected_count": body.get("detected_count", 0),
        "ai_connections": body.get("ai_connections", []),
        "local_ai_processes": body.get("local_ai_processes", []),
        "local_ai_ports": body.get("local_ai_ports", []),
    }
    await db.shadow_ai_scans.insert_one(doc)
    doc.pop("_id", None)

    # Elevate each detected connection to a security alert
    for conn in body.get("ai_connections", []):
        await db.shadow_ai_events.update_one(
            {"agent_id": agent_id, "remote_host": conn.get("remote_host"), "process": conn.get("process")},
            {"$set": {
                "agent_id": agent_id,
                "tenantId": tenant_id,
                "process": conn.get("process"),
                "remote_ip": conn.get("remote_ip"),
                "remote_host": conn.get("remote_host"),
                "timestamp": scanned_at,
            }},
            upsert=True,
        )

    for proc in body.get("local_ai_processes", []):
        await db.security_alerts.insert_one({
            "tenantId": tenant_id,
            "agent_id": agent_id,
            "type": "shadow_ai_process",
            "severity": "medium",
            "title": f"Unauthorized AI process: {proc.get('name', 'unknown')}",
            "description": f"Local AI process '{proc.get('name')}' (PID {proc.get('pid')}) detected on agent {agent_id}",
            "created_at": scanned_at,
            "status": "open",
        })

    return {"success": True, "detected_count": doc["detected_count"]}


@router.get("/{agent_id}/shadow-ai-scans")
async def get_shadow_ai_scans(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Retrieve recent Shadow AI scan history for an agent."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", "default")
    scans = await db.shadow_ai_scans.find(query, {"_id": 0}).sort("scanned_at", -1).to_list(length=limit)
    return scans


@router.post("/{agent_id}/vulnerability-scan")
async def post_vulnerability_scan(
    agent_id: str,
    body: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent posts its latest vulnerability scan results (OSV-backed)."""
    db = get_database()
    tenant_id = _tenant.get("id", "default")

    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    doc = {
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "total_packages": body.get("total_packages", 0),
        "vulnerable_packages": body.get("vulnerable_packages", []),
        "total_cves": body.get("total_cves", 0),
        "scan_source": body.get("scan_source", "osv"),
        "os_patches": body.get("os_patches", {}),
    }

    await db.agent_vulnerability_scans.insert_one(doc)
    doc.pop("_id", None)

    # Mirror critical CVEs into the shared vulnerabilities collection
    for pkg in body.get("vulnerable_packages", []):
        for cve in pkg.get("cves", []):
            severity = cve.get("severity", "Unknown")
            if severity in ("CRITICAL", "HIGH"):
                await db.vulnerabilities.update_one(
                    {"cveId": cve.get("id"), "agentId": agent_id},
                    {"$set": {
                        "cveId": cve.get("id"),
                        "agentId": agent_id,
                        "tenantId": tenant_id,
                        "affectedSoftware": pkg.get("name", ""),
                        "severity": severity,
                        "description": cve.get("summary", ""),
                        "source": "agent_osv_scan",
                        "reported_at": doc["scanned_at"],
                    }},
                    upsert=True,
                )

    return {"success": True, "scan_id": str(doc.get("_id", "")), "total_cves": doc["total_cves"]}


@router.get("/{agent_id}/vulnerability-scans")
async def get_vulnerability_scans(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Retrieve recent vulnerability scan history for an agent."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", "default")
    scans = await db.agent_vulnerability_scans.find(query, {"_id": 0}).sort("scanned_at", -1).to_list(length=limit)
    return scans


@router.post("/{agent_id}/persistence-findings")
async def post_persistence_findings(
    agent_id: str,
    body: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent posts persistence mechanism findings (registry, cron, startup entries)."""
    db = get_database()
    tenant_id = _tenant.get("id", "default")

    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    doc = {
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "total_entries": body.get("total_entries", 0),
        "suspicious_entries": body.get("suspicious_entries", []),
        "critical_count": body.get("critical_count", 0),
        "high_count": body.get("high_count", 0),
        "platform": body.get("platform", "unknown"),
    }

    await db.agent_persistence_findings.insert_one(doc)
    doc.pop("_id", None)

    # Elevate critical persistence findings to security alerts
    for entry in body.get("suspicious_entries", []):
        if entry.get("severity") in ("Critical", "High"):
            await db.security_alerts.insert_one({
                "tenantId": tenant_id,
                "agent_id": agent_id,
                "type": "persistence_mechanism",
                "severity": entry.get("severity", "High").lower(),
                "title": f"Suspicious persistence: {entry.get('name', 'unknown')}",
                "description": entry.get("command", entry.get("path", "")),
                "location": entry.get("location", ""),
                "risk_score": entry.get("risk_score", 0),
                "created_at": doc["scanned_at"],
                "status": "open",
            })

    return {"success": True, "critical_count": doc["critical_count"], "high_count": doc["high_count"]}


@router.get("/{agent_id}/persistence-findings")
async def get_persistence_findings(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Retrieve recent persistence scan history for an agent."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", "default")
    findings = await db.agent_persistence_findings.find(query, {"_id": 0}).sort("scanned_at", -1).to_list(length=limit)
    return findings


@router.get("/{agent_id}/approvals/{request_id}")
async def get_approval_status(
    agent_id: str,
    request_id: str,
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """
    Agent polls this endpoint to check whether a pending approval has been
    decided.  Returns status and, on approval, any additional params.
    """
    db = get_database()
    from bson import ObjectId

    query: Dict[str, Any] = {"agent_id": agent_id}
    try:
        query["_id"] = ObjectId(request_id)
    except Exception:
        query["$or"] = [{"_id": request_id}, {"request_id": request_id}]

    record = await db.playbook_approvals.find_one(query, {"_id": 0})
    if not record:
        # Also look in agent_approval_requests collection
        record = await db.agent_approval_requests.find_one(
            {"agent_id": agent_id, "request_id": request_id}, {"_id": 0}
        )
    if not record:
        raise HTTPException(status_code=404, detail="Approval request not found")

    return {
        "request_id": request_id,
        "status": record.get("status", "pending"),
        "approved_by": record.get("approved_by"),
        "approved_at": record.get("approved_at"),
        "params": record.get("params", {}),
    }


@router.post("/{agent_id}/diagnostics")
async def run_agent_diagnostics(
    agent_id: str,
    current_user=Depends(get_current_user),
):
    """
    Run a lightweight diagnostic check on a registered agent.
    Checks: last-seen recency, heartbeat gap, required capability presence,
    and pending instruction backlog.  Returns structured health status.
    """
    db = get_database()
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    import datetime as _dt

    checks = []

    # 1. Connectivity: last heartbeat within the last 2 minutes
    last_seen_str = agent.get("lastSeen") or agent.get("last_seen", "")
    connectivity_status = "Unknown"
    connectivity_msg = "No heartbeat data available"
    if last_seen_str:
        try:
            last_seen = _dt.datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
            gap_seconds = (_dt.datetime.now(_dt.timezone.utc) - last_seen).total_seconds()
            if gap_seconds <= 120:
                connectivity_status = "Pass"
                connectivity_msg = f"Last heartbeat {int(gap_seconds)}s ago"
            elif gap_seconds <= 600:
                connectivity_status = "Warn"
                connectivity_msg = f"Last heartbeat {int(gap_seconds / 60)}m ago (degraded)"
            else:
                connectivity_status = "Fail"
                connectivity_msg = f"No heartbeat for {int(gap_seconds / 60)}m"
        except ValueError:
            pass
    checks.append({"name": "Connectivity", "status": connectivity_status, "message": connectivity_msg})

    # 2. Service status: agent.status field
    agent_status = agent.get("status", "Unknown")
    svc_ok = agent_status in ("Online", "Active", "online", "active")
    checks.append({
        "name": "Service Status",
        "status": "Pass" if svc_ok else "Warn",
        "message": f"Agent status: {agent_status}",
    })

    # 3. Capability check: agent should report at least one capability
    caps = agent.get("capabilities") or agent.get("agentCapabilities") or []
    checks.append({
        "name": "Capabilities",
        "status": "Pass" if caps else "Warn",
        "message": f"{len(caps)} capabilities registered" if caps else "No capabilities reported",
    })

    # 4. Instruction backlog: pending instructions older than 5 minutes
    cutoff = (_dt.datetime.now(timezone.utc) - _dt.timedelta(minutes=5)).isoformat()
    stale_count = await db.agent_instructions.count_documents({
        "agent_id": agent_id, "status": "pending", "created_at": {"$lt": cutoff}
    })
    checks.append({
        "name": "Instruction Queue",
        "status": "Warn" if stale_count > 0 else "Pass",
        "message": (f"{stale_count} stale pending instruction(s)" if stale_count
                    else "No stale instructions"),
    })

    failures = [c for c in checks if c["status"] == "Fail"]
    warns = [c for c in checks if c["status"] == "Warn"]
    overall = "Unhealthy" if failures else ("Degraded" if warns else "Healthy")

    # Persist the diagnostic result
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {
            "health": {"overallStatus": overall, "checks": checks},
            "lastDiagnosticAt": _dt.datetime.now(timezone.utc).isoformat(),
        }},
    )

    return {
        "agent_id": agent_id,
        "health": {"overallStatus": overall, "checks": checks},
        "status": agent_status,
        "lastSeen": last_seen_str,
    }
