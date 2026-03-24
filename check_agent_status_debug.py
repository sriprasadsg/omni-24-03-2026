from pymongo import MongoClient
import sys

def check_agents():
    client = MongoClient('mongodb://localhost:27017')
    db = client['omni_platform']
    
    agents = list(db.agents.find({}, {"id": 1, "hostname": 1, "status": 1, "lastSeen": 1}))
    
    print(f"Total Agents: {len(agents)}")
    online_count = 0
    
    for agent in agents:
        print(f"Agent: {agent.get('hostname')} ({agent.get('id')}) - Status: {agent.get('status')}")
        if agent.get('status') == 'Online':
            online_count += 1
            
    if online_count == 0:
        print("\n❌ NO ONLINE AGENTS FOUND.")
        print("This explains why 'Collect Evidence' fails (it requires online agents).")
        return False
    else:
        print(f"\n✅ Found {online_count} online agents.")
        return True

if __name__ == "__main__":
    check_agents()
