#!/usr/bin/env python3
"""
Claude-Flow <-> Backend Agent Sync Bridge

Syncs registered agents from backend database to claude-flow swarm state.
Runs as a background worker or on-demand.
"""

import json
import asyncio
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

# Add backend to path
sys.path.insert(0, '/home/user/enterprise-omni-agent-ai-platform/backend')

from database import get_database
from authentication_service import create_access_token

CLAUDE_FLOW_DIR = Path('/home/user/enterprise-omni-agent-ai-platform/.claude-flow')
SWARM_STATE_FILE = CLAUDE_FLOW_DIR / 'swarm' / 'swarm-state.json'
METRICS_DIR = CLAUDE_FLOW_DIR / 'metrics'


def load_swarm_state() -> Dict:
    with open(SWARM_STATE_FILE) as f:
        return json.load(f)


def save_swarm_state(state: Dict) -> None:
    with open(SWARM_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


async def fetch_backend_agents() -> List[Dict]:
    """Fetch all agents from backend database."""
    db = get_database()
    agents = await db.agents.find({}).to_list(length=1000)
    return agents


def transform_agent_to_claude_flow(agent: Dict) -> Dict:
    """Transform backend agent to claude-flow agent format."""
    return {
        "id": agent.get("id"),
        "name": agent.get("hostname", "unknown"),
        "type": "windows-rust",
        "status": agent.get("status", "Online").lower(),
        "platform": agent.get("platform", "Windows"),
        "version": agent.get("version", "2.1.0"),
        "tenantId": agent.get("tenantId"),
        "capabilities": agent.get("capabilities", []) or agent.get("availableCapabilities", []),
        "ipAddress": agent.get("ipAddress", "0.0.0.0"),
        "lastSeen": agent.get("lastSeen"),
        "registeredAt": agent.get("registeredAt"),
    }


def update_swarm_agents(swarm_state: Dict, agents: List[Dict]) -> None:
    """Update the active swarm's agent list."""
    # Find active swarm
    active_swarm = None
    for swarm_id, swarm in swarm_state.get("swarms", {}).items():
        if swarm.get("status") == "running":
            active_swarm = swarm
            break

    if not active_swarm:
        print("No active swarm found")
        return

    active_swarm["agents"] = agents
    active_swarm["updatedAt"] = datetime.now(timezone.utc).isoformat()
    print(f"Updated swarm {active_swarm['swarmId']} with {len(agents)} agents")


def update_metrics(agents: List[Dict]) -> None:
    """Update claude-flow metrics files."""
    swarm_activity = METRICS_DIR / 'swarm-activity.json'
    v3_progress = METRICS_DIR / 'v3-progress.json'

    # swarm-activity.json
    activity = {
        "initialized": "2026-06-04T08:11:22.049Z",
        "routing": {"accuracy": 0, "decisions": 0},
        "patterns": {"shortTerm": 0, "longTerm": 0, "quality": 0},
        "sessions": {
            "total": len(agents),
            "current": agents[0]["id"] if agents else None
        },
        "agent_count": len(agents),
        "active": len(agents) > 0,
        "coordination_active": len(agents) > 0,
    }
    with open(swarm_activity, 'w') as f:
        json.dump(activity, f, indent=2)

    # v3-progress.json
    progress = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "processes": {
            "agentic_flow": len(agents),
            "mcp_server": 1,
            "estimated_agents": len(agents)
        },
        "swarm": {
            "active": True,
            "agent_count": len(agents),
            "coordination_active": len(agents) > 0
        },
        "integration": {
            "agentic_flow_active": True,
            "mcp_active": True
        },
        "_initialized": True
    }
    with open(v3_progress, 'w') as f:
        json.dump(progress, f, indent=2)

    print(f"Updated metrics: {len(agents)} agents")


async def main():
    print("Starting claude-flow <-> backend agent sync...")

    # Load current state
    swarm_state = load_swarm_state()

    # Fetch agents from backend
    agents = await fetch_backend_agents()
    print(f"Fetched {len(agents)} agents from backend")

    # Transform to claude-flow format
    cf_agents = [transform_agent_to_claude_flow(a) for a in agents]

    # Update swarm state
    update_swarm_agents(swarm_state, cf_agents)
    save_swarm_state(swarm_state)

    # Update metrics
    update_metrics(cf_agents)

    print("Sync complete!")
    return cf_agents


if __name__ == "__main__":
    asyncio.run(main())