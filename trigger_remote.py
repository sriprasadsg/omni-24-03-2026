import requests
import time
import pymongo
import datetime

BASE_URL = "http://localhost:5000/api"

def trigger():
    # 1. Login
    print("Logging in...")
    try:
        res = requests.post(f"{BASE_URL}/auth/login", json={"email": "testadmin@example.com", "password": "password123"})
        if res.status_code != 200:
            print(f"Login failed: {res.text}")
            return
        
        data = res.json()
        token = data["access_token"]
        # Use the tenant from the logged in user
        tenant_id = data["user"]["tenantId"] 
        headers = {"Authorization": f"Bearer {token}"}
    except Exception as e:
        print(f"Login/Admin check failed: {e}")
        return

    # 1.5 Ensure Agent Exists in DB (Mocking Registration)
    print("Ensuring agent exists in DB...")
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    db = client["omni_platform"]
    
    agent_id = "agent-test-remote"
    
    db.agents.update_one(
        {"id": agent_id},
        {"$set": {
            "id": agent_id,
            "hostname": "test-remote-host",
            "tenantId": tenant_id, # Must match admin's tenant
            "status": "Online",
            "lastSeen": datetime.datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "platform": "Linux"
        }},
        upsert=True
    )
    print("Agent upserted.")

    # 2. Trigger Command
    print(f"Sending command to {agent_id}...")
    
    payload = {
        "command": "echo 'Hello from Remote Control'",
        "args": ["-la"]
    }
    
    res = requests.post(f"{BASE_URL}/agents/remote/{agent_id}/execute", json=payload, headers=headers)
    
    if res.status_code == 200:
        print("✅ Command Sent Successfully!")
        print(res.json())
    else:
        print(f"❌ Command Failed: {res.status_code}")
        print(res.text)

if __name__ == "__main__":
    trigger()
