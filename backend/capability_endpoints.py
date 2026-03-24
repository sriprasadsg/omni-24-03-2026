from fastapi import APIRouter, HTTPException, Depends, Body
from typing import Dict, Any, List
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service
from datetime import datetime
import logging

router = APIRouter(prefix="/api/agents", tags=["Agent Capabilities"])
logger = logging.getLogger(__name__)

# Capability Registry - defines all available capabilities
CAPABILITY_DEFINITIONS = {
    "metrics_collection": {
        "name": "Metrics Collection",
        "description": "Collects system metrics (CPU, Memory, Disk, Network)",
        "default_interval": 60,
        "category": "Monitoring"
    },
    "log_collection": {
        "name": "Log Collection",
        "description": "Collects system logs (Windows Event Logs, journalctl)",
        "default_interval": 300,
        "category": "Monitoring"
    },
    "fim": {
        "name": "File Integrity Monitoring",
        "description": "Monitors critical files for unauthorized changes",
        "default_interval": 600,
        "category": "Security"
    },
    "vulnerability_scanning": {
        "name": "Vulnerability Scanning",
        "description": "Scans for outdated software and known vulnerabilities",
        "default_interval": 3600,
        "category": "Security"
    },
    "compliance_enforcement": {
        "name": "Compliance Enforcement",
        "description": "Checks compliance with security policies (CIS, SOC2)",
        "default_interval": 3600,
        "category": "Compliance"
    },
    "runtime_security": {
        "name": "Runtime Security",
        "description": "Monitors processes for suspicious behavior",
        "default_interval": 180,
        "category": "Security"
    },
    "predictive_health": {
        "name": "Predictive Health",
        "description": "ML-based predictive failure detection",
        "default_interval": 600,
        "category": "Monitoring"
    },
    "ueba": {
        "name": "UEBA",
        "description": "User and Entity Behavior Analytics",
        "default_interval": 300,
        "category": "Security"
    },
    "sbom_analysis": {
        "name": "SBOM Analysis",
        "description": "Software Bill of Materials generation",
        "default_interval": 3600,
        "category": "Inventory"
    },
    "ebpf_tracing": {
        "name": "eBPF Tracing",
        "description": "Kernel-level tracing (Linux only)",
        "default_interval": 300,
        "category": "Security"
    },
    "system_patching": {
        "name": "System Patching",
        "description": "Monitors and manages OS patches",
        "default_interval": 3600,
        "category": "Patching"
    },
    "software_management": {
        "name": "Software Management",
        "description": "Manages software installation and updates",
        "default_interval": 3600,
        "category": "Inventory"
    },
    "remote_access": {
        "name": "Remote Access",
        "description": "Enables remote shell and desktop access",
        "default_interval": -1,  # On-demand only
        "category": "Management"
    },
    "network_discovery": {
        "name": "Network Discovery",
        "description": "Discovers devices on the network",
        "default_interval": 7200,
        "category": "Inventory"
    },
    "agent_update": {
        "name": "Agent Update",
        "description": "Manages agent self-updates",
        "default_interval": -1,  # On-demand only
        "category": "Management"
    },
    "patch_installer": {
        "name": "Patch Installer",
        "description": "Executes patch deployment and rollback",
        "default_interval": -1,  # On-demand only
        "category": "Patching"
    },
    "process_injection_simulation": {
        "name": "Process Injection Simulation",
        "description": "Simulates process injection attacks for testing",
        "default_interval": -1,  # On-demand only
        "category": "Security Testing"
    },
    "persistence_detection": {
        "name": "Persistence Detection",
        "description": "Detects malware persistence mechanisms",
        "default_interval": 3600,
        "category": "Security"
    }
}

@router.get("/{agent_id}/capabilities")
async def get_agent_capabilities(
    agent_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:agents"))
):
    """Get list of all capabilities and their status for an agent"""
    db = get_database()
    tenant_id = get_tenant_id()
    
    # Verify agent belongs to tenant
    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Get agent configuration
    config = agent.get("capabilityConfig", {})
    enabled_capabilities = config.get("enabledCapabilities", list(CAPABILITY_DEFINITIONS.keys()))
    collection_intervals = config.get("collectionIntervals", {})
    
    # Build response with capability details
    capabilities = []
    for cap_id, cap_def in CAPABILITY_DEFINITIONS.items():
        capabilities.append({
            "id": cap_id,
            "name": cap_def["name"],
            "description": cap_def["description"],
            "category": cap_def["category"],
            "enabled": cap_id in enabled_capabilities,
            "interval": collection_intervals.get(cap_id, cap_def["default_interval"]),
            "defaultInterval": cap_def["default_interval"]
        })
    
    return {
        "agentId": agent_id,
        "capabilities": capabilities,
        "totalCapabilities": len(capabilities),
        "enabledCount": len(enabled_capabilities)
    }

@router.post("/{agent_id}/capabilities/configure")
async def configure_agent_capabilities(
    agent_id: str,
    config: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:agents"))
):
    """Configure which capabilities are enabled for an agent"""
    db = get_database()
    tenant_id = get_tenant_id()
    
    # Verify agent belongs to tenant
    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    enabled_capabilities = config.get("enabledCapabilities", [])
    collection_intervals = config.get("collectionIntervals", {})
    
    # Validate capability IDs
    invalid_caps = [cap for cap in enabled_capabilities if cap not in CAPABILITY_DEFINITIONS]
    if invalid_caps:
        raise HTTPException(status_code=400, detail=f"Invalid capabilities: {invalid_caps}")
    
    # Update agent configuration
    await db.agents.update_one(
        {"id": agent_id, "tenantId": tenant_id},
        {"$set": {
            "capabilityConfig.enabledCapabilities": enabled_capabilities,
            "capabilityConfig.collectionIntervals": collection_intervals,
            "capabilityConfig.lastUpdated": datetime.now().isoformat()
        }}
    )
    
    logger.info(f"Updated capabilities for agent {agent_id}: {len(enabled_capabilities)} enabled")
    
    return {
        "success": True,
        "agentId": agent_id,
        "enabledCapabilities": enabled_capabilities,
        "collectionIntervals": collection_intervals
    }

@router.get("/{agent_id}/capabilities/configuration")
async def get_agent_configuration(agent_id: str):
    """
    Get agent capability configuration (called by agent at startup).
    This endpoint is public (no auth) as agents use API keys.
    """
    db = get_database()
    
    # Find agent by ID (no tenant check as this is agent-initiated)
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        # Return default configuration if agent not found
        return {
            "enabledCapabilities": list(CAPABILITY_DEFINITIONS.keys()),
            "collectionIntervals": {
                cap_id: cap_def["default_interval"] 
                for cap_id, cap_def in CAPABILITY_DEFINITIONS.items()
                if cap_def["default_interval"] > 0
            }
        }
    
    config = agent.get("capabilityConfig", {})
    enabled_capabilities = config.get("enabledCapabilities", list(CAPABILITY_DEFINITIONS.keys()))
    collection_intervals = config.get("collectionIntervals", {})
    
    # Add default intervals for enabled capabilities that don't have custom intervals
    for cap_id in enabled_capabilities:
        if cap_id not in collection_intervals and cap_id in CAPABILITY_DEFINITIONS:
            default_interval = CAPABILITY_DEFINITIONS[cap_id]["default_interval"]
            if default_interval > 0:
                collection_intervals[cap_id] = default_interval
    
    return {
        "enabledCapabilities": enabled_capabilities,
        "collectionIntervals": collection_intervals
    }

@router.post("/{agent_id}/capabilities/{capability_id}/data")
async def ingest_capability_data(
    agent_id: str,
    capability_id: str,
    data: Dict[str, Any] = Body(...)
):
    """
    Ingest data from a specific capability.
    This endpoint is public (no auth) as agents use API keys.
    """
    db = get_database()
    
    # Verify agent exists
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    tenant_id = agent.get("tenantId")
    
    # Store capability data
    capability_record = {
        "agentId": agent_id,
        "tenantId": tenant_id,
        "capabilityId": capability_id,
        "timestamp": datetime.now().isoformat(),
        "status": data.get("status", "success"),
        "data": data.get("data", {}),
        "error": data.get("error")
    }
    
    # Insert into capability_data collection
    await db.capability_data.insert_one(capability_record)
    
    logger.info(f"Ingested {capability_id} data from agent {agent_id}")
    
    return {"success": True, "message": "Data ingested successfully"}

@router.get("/capabilities/definitions")
async def get_capability_definitions(current_user: TokenData = Depends(rbac_service.has_permission("view:agents"))):
    """Get definitions of all available capabilities"""
    return {
        "capabilities": CAPABILITY_DEFINITIONS,
        "totalCount": len(CAPABILITY_DEFINITIONS)
    }
