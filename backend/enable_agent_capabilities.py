"""
Script to enable default capabilities for all agents in the database.
Run this once to initialize capability configuration for existing agents.
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "omniagent"

# Default enabled capabilities (all except on-demand ones)
DEFAULT_ENABLED_CAPABILITIES = [
    "metrics_collection",
    "log_collection",
    "fim",
    "vulnerability_scanning",
    "compliance_enforcement",
    "runtime_security",
    "predictive_health",
    "ueba",
    "sbom_analysis",
    "ebpf_tracing",
    "system_patching",
    "software_management",
    "network_discovery",
    "persistence_detection"
]

# Default collection intervals (in seconds)
DEFAULT_INTERVALS = {
    "metrics_collection": 60,
    "log_collection": 300,
    "fim": 600,
    "vulnerability_scanning": 3600,
    "compliance_enforcement": 3600,
    "runtime_security": 180,
    "predictive_health": 600,
    "ueba": 300,
    "sbom_analysis": 3600,
    "ebpf_tracing": 300,
    "system_patching": 3600,
    "software_management": 3600,
    "network_discovery": 7200,
    "persistence_detection": 3600
}

async def enable_capabilities_for_all_agents():
    """Enable default capabilities for all agents"""
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    
    # Update all agents
    result = await db.agents.update_many(
        {},  # Match all agents
        {
            "$set": {
                "capabilityConfig.enabledCapabilities": DEFAULT_ENABLED_CAPABILITIES,
                "capabilityConfig.collectionIntervals": DEFAULT_INTERVALS,
                "capabilityConfig.lastUpdated": "2025-12-19T03:35:00Z"
            }
        }
    )
    
    print(f"✅ Updated {result.modified_count} agents with default capability configuration")
    
    # List all agents and their configuration
    agents = await db.agents.find({}, {"id": 1, "hostname": 1, "capabilityConfig": 1}).to_list(length=100)
    print(f"\n📊 Agent Capability Configuration:")
    for agent in agents:
        config = agent.get("capabilityConfig", {})
        enabled_count = len(config.get("enabledCapabilities", []))
        print(f"  - {agent.get('hostname', agent.get('id'))}: {enabled_count} capabilities enabled")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(enable_capabilities_for_all_agents())
