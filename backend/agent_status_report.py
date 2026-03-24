import asyncio
from database import connect_to_mongo, get_database
from datetime import datetime, timezone, timedelta

async def check_and_report_agents():
    """Comprehensive agent status check"""
    await connect_to_mongo()
    db = get_database()
    
    agents = await db.agents.find({}).to_list(100)
    
    with open("agent_status_report.txt", "w") as f:
        f.write(f"=== AGENT STATUS REPORT ===\n")
        f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write(f"Total Agents in Database: {len(agents)}\n\n")
        
        if len(agents) == 0:
            f.write("NO AGENTS FOUND IN DATABASE!\n")
            f.write("\nTo register an agent:\n")
            f.write("1. Navigate to Agents page in UI\n")
            f.write("2. Click 'Register Agent'\n")
            f.write("3. Follow installation instructions\n")
            f.write("4. Run: python agent/agent.py\n")
        else:
            now = datetime.now(timezone.utc)
            threshold = now - timedelta(minutes=2)
            
            for agent in agents:
                f.write(f"\n{'='*80}\n")
                f.write(f"Agent ID: {agent.get('id', 'N/A')}\n")
                f.write(f"Hostname: {agent.get('hostname', 'N/A')}\n")
                f.write(f"Status: {agent.get('status', 'N/A')}\n")
                f.write(f"Platform: {agent.get('platform', 'N/A')}\n")
                f.write(f"Asset ID: {agent.get('assetId', 'N/A')}\n")
                f.write(f"Tenant ID: {agent.get('tenantId', 'N/A')}\n")
                f.write(f"Last Seen: {agent.get('lastSeen', 'N/A')}\n")
                f.write(f"IP Address: {agent.get('ipAddress', 'N/A')}\n")
                f.write(f"Version: {agent.get('version', 'N/A')}\n")
                capabilities = agent.get('capabilities', [])
                cap_names = [c.get('name', c.get('id', str(c))) if isinstance(c, dict) else str(c) for c in capabilities]
                f.write(f"Capabilities: {', '.join(cap_names)}\n")
                
                # Check if should be offline
                last_seen_str = agent.get('lastSeen')
                if last_seen_str:
                    try:
                        # Parse the ISO format timestamp
                        if last_seen_str.endswith('Z'):
                            last_seen = datetime.fromisoformat(last_seen_str.replace('Z', '+00:00'))
                        elif '+' in last_seen_str or last_seen_str.count(':') >= 3:
                            last_seen = datetime.fromisoformat(last_seen_str)
                        else:
                            last_seen = datetime.fromisoformat(last_seen_str).replace(tzinfo=timezone.utc)
                        
                        age = now - last_seen
                        f.write(f"Last heartbeat: {age.total_seconds():.1f} seconds ago\n")
                        
                        if age.total_seconds() > 120:
                            f.write(f"⚠️  STATUS: Should be OFFLINE (threshold: 2 minutes)\n")
                        else:
                            f.write(f"✅ STATUS: Should be ONLINE (within 2 minute threshold)\n")
                    except Exception as e:
                        f.write(f"Error parsing lastSeen: {e}\n")
            
            f.write(f"\n{'='*80}\n")
            f.write(f"\nCurrent Time: {now.isoformat()}\n")
            f.write(f"Offline Threshold: Last seen > 2 minutes ago\n")
    
    print("Agent status report written to agent_status_report.txt")

if __name__ == "__main__":
    asyncio.run(check_and_report_agents())
