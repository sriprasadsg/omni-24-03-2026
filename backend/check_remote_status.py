"""One-shot diagnostic: checks agent tenantId vs instruction tenantId."""
import asyncio
import sys
sys.path.insert(0, '.')
from database import get_database

AGENT_ID = "agent-6427ab4b39d540f1a9414dbd48e13df0"

async def main():
    db = get_database()

    # Agent record
    agent = await db.agents.find_one({"id": AGENT_ID})
    agent_tenant = agent.get("tenantId") if agent else "NOT FOUND"
    agent_hostname = agent.get("hostname") if agent else "?"
    agent_status = agent.get("status") if agent else "?"
    agent_last_seen = agent.get("lastSeen") if agent else "?"
    has_remote_cap = "remote_access" in (agent.get("availableCapabilities") or []) if agent else False

    print(f"=== Agent: {agent_hostname} ===")
    print(f"  Status:           {agent_status}")
    print(f"  Last Seen:        {agent_last_seen}")
    print(f"  Agent tenantId:   {agent_tenant}")
    print(f"  remote_access:    {has_remote_cap}")

    # Latest instruction for this agent
    instr = await db.agent_instructions.find_one(
        {"agent_id": AGENT_ID},
        sort=[("created_at", -1)]
    )

    print()
    if instr:
        instr_tenant = instr.get("tenantId")
        instr_type = instr.get("type")
        instr_status = instr.get("status")
        url = (instr.get("payload") or {}).get("url", "")
        host_part = url.split("/")[2] if url and "/" in url else url
        tenant_match = instr_tenant == agent_tenant

        print("=== Latest Instruction ===")
        print(f"  type:             {instr_type}")
        print(f"  status:           {instr_status}")
        print(f"  Instruction tenantId: {instr_tenant}")
        print(f"  Agent tenantId:       {agent_tenant}")
        print(f"  tenantId MATCH:   {tenant_match}")
        print(f"  Tunnel URL:       {url}")
        print(f"  URL host:         {host_part}")
        print()
        if not tenant_match:
            print("[BUG CONFIRMED] Instruction tenantId != agent tenantId")
            print("  Agent polling query requires tenantId match -> instruction is INVISIBLE to agent")
            print("  Fix: restart server to load remote_endpoints.py changes, then create a new session")
        else:
            print("[OK] tenantId matches -> agent should receive this instruction on next poll")
    else:
        print("No instructions found for this agent")

asyncio.run(main())
