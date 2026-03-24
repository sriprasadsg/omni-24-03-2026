import asyncio
from database import get_database

async def check_logs_and_agents():
    db = get_database()
    
    print("=" * 80)
    print("CHECKING AGENTS")
    print("=" * 80)
    agents = await db.agents.find(
        {"hostname": "simulation-agent-01"}, 
        {"_id": 0}
    ).to_list(length=10)
    
    if agents:
        for agent in agents:
            print(f"\n✓ Agent Found:")
            print(f"  ID: {agent.get('id')}")
            print(f"  Hostname: {agent.get('hostname')}")
            print(f"  Status: {agent.get('status')}")
            print(f"  IP: {agent.get('ipAddress')}")
            print(f"  Last Seen: {agent.get('lastSeen')}")
    else:
        print("\n✗ No agents found with hostname 'simulation-agent-01'")
    
    print("\n" + "=" * 80)
    print("CHECKING LOGS")
    print("=" * 80)
    
    # Check total log count
    total_logs = await db.logs.count_documents({})
    print(f"\nTotal logs in database: {total_logs}")
    
    # Check logs for simulation-agent-01
    sim_logs_by_hostname = await db.logs.count_documents({"hostname": "simulation-agent-01"})
    print(f"Logs with hostname='simulation-agent-01': {sim_logs_by_hostname}")
    
    if agents:
        agent_id = agents[0].get('id')
        sim_logs_by_id = await db.logs.count_documents({"agentId": agent_id})
        print(f"Logs with agentId='{agent_id}': {sim_logs_by_id}")
    
    # Show recent logs
    print("\n" + "-" * 80)
    print("RECENT LOGS (Last 5):")
    print("-" * 80)
    
    recent_logs = await db.logs.find(
        {}, 
        {"_id": 0}
    ).sort("timestamp", -1).limit(5).to_list(length=5)
    
    for i, log in enumerate(recent_logs, 1):
        print(f"\n[{i}] Timestamp: {log.get('timestamp')}")
        print(f"    Severity: {log.get('severity')}")
        print(f"    Service: {log.get('service')}")
        print(f"    Hostname: {log.get('hostname')}")
        print(f"    AgentId: {log.get('agentId')}")
        print(f"    Message: {log.get('message')[:60]}...")
    
    # Check logs specifically for simulation-agent-01
    print("\n" + "-" * 80)
    print("LOGS FOR simulation-agent-01 (Last 3):")
    print("-" * 80)
    
    sim_logs = await db.logs.find(
        {"hostname": "simulation-agent-01"}, 
        {"_id": 0}
    ).sort("timestamp", -1).limit(3).to_list(length=3)
    
    if sim_logs:
        for i, log in enumerate(sim_logs, 1):
            print(f"\n[{i}] Timestamp: {log.get('timestamp')}")
            print(f"    Severity: {log.get('severity')}")
            print(f"    Service: {log.get('service')}")
            print(f"    Hostname: {log.get('hostname')}")
            print(f"    AgentId: {log.get('agentId')}")
            print(f"    Message: {log.get('message')}")
    else:
        print("\n✗ No logs found for simulation-agent-01")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(check_logs_and_agents())
