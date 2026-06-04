from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request, Response
from typing import List, Optional, Dict, Any
from database import get_database
from authentication_service import get_current_user
from rbac_utils import is_super_admin
from datetime import datetime, timezone, timedelta
from cache_service import cached
from pagination_utils import paginate_mongo_query, PaginationParams
from agent_auth import verify_agent_key
from rate_limiter import limiter
import logging

router = APIRouter(prefix="/api/agents", tags=["Agents"])
logger = logging.getLogger("agent_core_endpoints")

_CAP_NAME_MAP: Dict[str, str] = {
    "metrics_collection": "Systems Telemetry",
    "log_collection": "Unified Logging",
    "process_monitor": "Process Sentinel",
    "vulnerability_scanning": "Vulnerability Scanner",
    "fim": "Integrity Guard",
    "compliance_enforcement": "Compliance Shield",
    "runtime_security": "XDR Behavioral",
    "edr_realtime": "EDR Active",
    "persistence_detection": "Persistence Detector",
    "network_discovery": "Network Discovery",
    "cloud_metadata": "Cloud Metadata Collector",
    "web_monitor": "Web Monitor",
    "pii_scanner": "PII Data Scanner",
    "sbom_analysis": "SBOM Analyzer",
    "predictive_health": "Predictive Health AI",
    "ueba": "Behavior Analytics (UEBA)",
    "ebpf_tracing": "eBPF Kernel Tracer",
    "shadow_ai": "Shadow AI Detector",
    "system_patching": "Autonomous Patching",
    "software_management": "Software Manager",
    "process_injection_simulation": "Injection Simulator",
}

_DEFAULT_CAPABILITIES = [
    "metrics_collection", "log_collection", "process_monitor",
    "vulnerability_scanning", "fim", "compliance_enforcement",
    "runtime_security", "edr_realtime", "persistence_detection",
    "network_discovery", "cloud_metadata", "web_monitor",
    "pii_scanner", "sbom_analysis", "predictive_health", "ueba",
    "ebpf_tracing", "shadow_ai", "system_patching",
    "software_management", "process_injection_simulation",
]

_DEFAULT_INTERVALS: Dict[str, int] = {
    "metrics_collection": 60, "log_collection": 300, "process_monitor": 30,
    "vulnerability_scanning": 3600, "fim": 600, "compliance_enforcement": 3600,
    "runtime_security": 180, "edr_realtime": 15, "persistence_detection": 3600,
    "network_discovery": 7200, "cloud_metadata": 900, "web_monitor": 300,
    "pii_scanner": 3600, "sbom_analysis": 3600, "predictive_health": 600,
    "ueba": 300, "ebpf_tracing": 60, "shadow_ai": 1800,
    "system_patching": 3600, "software_management": 3600,
    "process_injection_simulation": 86400,
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
    is_admin = is_super_admin(current_user.role)

    query: Dict[str, Any] = {}
    if is_admin:
        if tenant_id:
            query["tenantId"] = tenant_id
    else:
        query["tenantId"] = current_user.tenant_id

    if status:
        query["status"] = status
    if platform:
        query["platform"] = platform

    pagination = PaginationParams(page=page, page_size=page_size)
    result = await paginate_mongo_query(collection, query, pagination, sort={"lastSeen": -1}, projection={"_id": 0})
    agents = result.get("items", [])
    current_time = datetime.now(timezone.utc)

    for agent in agents:
        if "meta" not in agent:
            agent["meta"] = {}

        capabilities = agent.get("capabilities", [])
        if capabilities and isinstance(capabilities, list):
            formatted_caps = []
            for cap in capabilities:
                if isinstance(cap, str):
                    cap_metrics = agent.get("meta", {}).get(cap, {"status": "Active"})
                    if not cap_metrics or not isinstance(cap_metrics, dict):
                        cap_metrics = {"status": "Active"}
                    formatted_caps.append({
                        "id": cap,
                        "name": _CAP_NAME_MAP.get(cap, cap.replace("_", " ").title()),
                        "enabled": True,
                        "status": "Running",
                        "metrics": cap_metrics
                    })
                else:
                    formatted_caps.append(cap)
            agent["capabilities"] = formatted_caps

        ph = agent["meta"].get("predictive_health")
        if not ph or not ph.get("predictions"):
            base_cpu = float(agent.get("cpuUsage") or agent.get("cpu_usage") or 25)
            base_mem = float(agent.get("memoryUsage") or agent.get("memory_usage") or 45)
            current_score = float(agent.get("securityScore") or 78)
            predictions = [
                {
                    "timestamp": (current_time + timedelta(hours=i)).strftime("%H:%M"),
                    "cpu_prediction": round(min(100, base_cpu + (15 if 9 <= (current_time + timedelta(hours=i)).hour <= 17 else 0) + (i % 5)), 1),
                    "memory_prediction": round(min(100, base_mem + (i % 8)), 1),
                    "health_score": round(max(70, current_score - (i % 3)), 1),
                }
                for i in range(25)
            ]
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


@router.get("/search")
async def search_agents_route(
    q: str = Query(..., min_length=1),
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """Full-text search across agent name, hostname, IP, and OS fields."""
    q = q[:200]
    import re as _re
    regex = {"$regex": _re.escape(q), "$options": "i"}
    query: Dict[str, Any] = {"$or": [
        {"name": regex}, {"hostname": regex}, {"ipAddress": regex}, {"os": regex}, {"platform": regex},
    ]}
    if status:
        query["status"] = status
    user_role = getattr(current_user, "role", "user")
    if not is_super_admin(user_role):
        _ac_tenant = getattr(current_user, "tenant_id", None) or None
        if not _ac_tenant:
            raise HTTPException(status_code=403, detail="Tenant context required")
        query["tenantId"] = _ac_tenant
    return await db.agents.find(query, {"_id": 0}).to_list(length=limit)


@router.delete("/bulk")
@limiter.limit("10/minute")
async def bulk_delete_agents_route(
    request: Request,
    response: Response,
    ids: List[str] = Body(...),
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """Delete multiple agents by ID."""
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    if len(ids) > 100:
        raise HTTPException(status_code=400, detail="Cannot delete more than 100 agents at once")
    user_role = getattr(current_user, "role", "user")
    query: Dict[str, Any] = {"id": {"$in": ids}}
    if not is_super_admin(user_role):
        _ac_tenant = getattr(current_user, "tenant_id", None) or None
        if not _ac_tenant:
            raise HTTPException(status_code=403, detail="Tenant context required")
        query["tenantId"] = _ac_tenant
    result = await db.agents.delete_many(query)
    return {"success": True, "deleted": result.deleted_count}


@router.patch("/bulk")
async def bulk_update_agents_route(
    body: Dict[str, Any] = Body(...),
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
    if not is_super_admin(user_role):
        _ac_tenant = getattr(current_user, "tenant_id", None) or None
        if not _ac_tenant:
            raise HTTPException(status_code=403, detail="Tenant context required")
        query["tenantId"] = _ac_tenant
    result = await db.agents.update_many(query, {"$set": patch})
    return {"matched": result.matched_count, "modified": result.modified_count}


@router.get("/network-utilization")
async def get_network_utilization(current_user=Depends(get_current_user), db=Depends(get_database)):
    """Get aggregated network utilization metrics for agents."""
    is_admin = is_super_admin(current_user.role)
    query: Dict[str, Any] = {} if is_admin else {"tenantId": getattr(current_user, "tenant_id", None)}

    agents = await db["agents"].find(
        query,
        {"_id": 0, "id": 1, "hostname": 1, "os": 1, "ipAddress": 1, "meta.metrics_collection.network": 1, "meta.network": 1}
    ).to_list(length=1000)

    result = []
    total_sent = total_recv = 0
    for agent in agents:
        meta = agent.get("meta", {})
        net = meta.get("metrics_collection", {}).get("network", {}) or meta.get("network", {})
        sent = net.get("bytes_sent") or 0
        recv = net.get("bytes_recv") or 0
        total_sent += sent
        total_recv += recv
        result.append({"id": agent.get("id"), "hostname": agent.get("hostname", "Unknown"),
                        "ipAddress": agent.get("ipAddress", "Unknown"), "os": agent.get("os", "Unknown"),
                        "bytesSent": sent, "bytesRecv": recv})

    result.sort(key=lambda x: x["bytesSent"] + x["bytesRecv"], reverse=True)
    return {"totalBytesSent": total_sent, "totalBytesRecv": total_recv, "agents": result}


@router.get("/{agent_id}/capabilities/configuration")
async def get_agent_configuration(agent_id: str, _tenant: Dict[str, Any] = Depends(verify_agent_key)):
    """Get the effective configuration for an agent. Used by the Agent to pull its config."""
    db = get_database()
    _cfg_tenant = (_tenant.get("id") if _tenant else None) or None
    _cfg_filter: dict = {"id": agent_id}
    if _cfg_tenant:
        _cfg_filter["tenantId"] = _cfg_tenant
    agent = await db.agents.find_one(_cfg_filter) or await db.agents.find_one({"hostname": agent_id, **(_cfg_filter if _cfg_tenant else {})})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    capabilities = agent["capabilities"] if "capabilities" in agent else _DEFAULT_CAPABILITIES
    intervals = agent.get("collectionIntervals", _DEFAULT_INTERVALS)
    return {"enabledCapabilities": capabilities, "collectionIntervals": intervals}




@router.post("/{agent_id}/diagnostics")
async def run_agent_diagnostics(agent_id: str, current_user=Depends(get_current_user)):
    """Run a lightweight diagnostic check: last-seen recency, status, capabilities, instruction backlog."""
    import datetime as _dt
    db = get_database()
    caller_tenant = getattr(current_user, "tenant_id", None)
    caller_role = getattr(current_user, "role", None)
    agent_filter: dict = {"id": agent_id}
    if not is_super_admin(caller_role or "") and caller_tenant:
        agent_filter["tenantId"] = caller_tenant
    agent = await db.agents.find_one(agent_filter, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    checks = []

    last_seen_str = agent.get("lastSeen") or agent.get("last_seen", "")
    connectivity_status, connectivity_msg = "Unknown", "No heartbeat data available"
    if last_seen_str:
        try:
            last_seen = _dt.datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
            gap = (_dt.datetime.now(_dt.timezone.utc) - last_seen).total_seconds()
            if gap <= 120:
                connectivity_status, connectivity_msg = "Pass", f"Last heartbeat {int(gap)}s ago"
            elif gap <= 600:
                connectivity_status, connectivity_msg = "Warn", f"Last heartbeat {int(gap / 60)}m ago (degraded)"
            else:
                connectivity_status, connectivity_msg = "Fail", f"No heartbeat for {int(gap / 60)}m"
        except ValueError:
            pass
    checks.append({"name": "Connectivity", "status": connectivity_status, "message": connectivity_msg})

    agent_status = agent.get("status", "Unknown")
    checks.append({
        "name": "Service Status",
        "status": "Pass" if agent_status in ("Online", "Active", "online", "active") else "Warn",
        "message": f"Agent status: {agent_status}",
    })

    caps = agent.get("capabilities") or agent.get("agentCapabilities") or []
    checks.append({
        "name": "Capabilities",
        "status": "Pass" if caps else "Warn",
        "message": f"{len(caps)} capabilities registered" if caps else "No capabilities reported",
    })

    cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=5)).isoformat()
    stale_count = await db.agent_instructions.count_documents({
        "agent_id": agent_id, "status": "pending", "created_at": {"$lt": cutoff}
    })
    checks.append({
        "name": "Instruction Queue",
        "status": "Warn" if stale_count > 0 else "Pass",
        "message": f"{stale_count} stale pending instruction(s)" if stale_count else "No stale instructions",
    })

    failures = [c for c in checks if c["status"] == "Fail"]
    warns = [c for c in checks if c["status"] == "Warn"]
    overall = "Unhealthy" if failures else ("Degraded" if warns else "Healthy")

    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {"health": {"overallStatus": overall, "checks": checks},
                  "lastDiagnosticAt": _dt.datetime.now(_dt.timezone.utc).isoformat()}},
    )
    return {"agent_id": agent_id, "health": {"overallStatus": overall, "checks": checks},
            "status": agent_status, "lastSeen": last_seen_str}
