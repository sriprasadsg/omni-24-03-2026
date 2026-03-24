
import requests
import uuid
import json

BASE_URL = "http://localhost:5000"

def test_capability_persistence():
    # 1. Register a dummy tenant/agent or use existing if known.
    # We will try to update an existing agent if we can find one, or just hit the heartbeat endpoint directly with a new ID.
    
    agent_id = f"test-agent-{uuid.uuid4().hex[:6]}"
    tenant_id = "test-tenant-123"
    
    print(f"Testing with Agent ID: {agent_id}")
    
    # 2. Send Heartbeat with Capabilities
    heartbeat_payload = {
        "hostname": "test-host",
        "tenantId": tenant_id,
        "status": "Online",
        "platform": "Linux",
        "version": "1.0.0",
        "ipAddress": "192.168.1.1",
        "meta": {
            "capabilities": [
                "metrics_collection", 
                "vulnerability_scanning",
                "custom_feature_x"
            ],
            "current_cpu": 45.5,
            "current_memory": 62.1,
            "disk_usage": 33.3,
            "total_memory_gb": 16,
            "disk_total_gb": 500,
            "disk_used_gb": 150
        }
    }
    
    hb_url = f"{BASE_URL}/api/agents/{agent_id}/heartbeat"
    print(f"Sending heartbeat to {hb_url}...")
    
    try:
        with open("token.txt", "r") as f:
            token = f.read().strip()
    except FileNotFoundError:
        print("Error: token.txt not found. Cannot authenticate.")
        return
        
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        resp = requests.post(hb_url, json=heartbeat_payload, headers=headers)
        print(f"Heartbeat Status: {resp.status_code}")
        print(f"Heartbeat Response: {resp.text}")
    except Exception as e:
        print(f"Heartbeat failed: {e}")
        return
        
    user_tenant = "tenant_c1344db58834" # the seeded admin tenant
    print(f"User Tenant: {user_tenant}")
    
    # Re-send heartbeat with CORRECT tenant
    heartbeat_payload["tenantId"] = user_tenant
    requests.post(hb_url, json=heartbeat_payload, headers=headers)
    
    # Now fetch agents
    list_url = f"{BASE_URL}/api/agents"
    list_resp = requests.get(list_url, headers=headers)
    
    if list_resp.status_code == 200:
        agents = list_resp.json().get("items", [])
        target_agent = next((a for a in agents if a["id"] == agent_id), None)
        
        if target_agent:
            print("Found Agent in API.")
            caps = target_agent.get("capabilities")
            print(f"Agent Capabilities: {caps}")
            
            if caps and "custom_feature_x" in caps:
                print("SUCCESS: Capabilities are persisting and served.")
            else:
                print("FAILURE: Capabilities missing or incorrect.")
        else:
            print("Agent not found in list (might be pagination or tenant mismatch).")
    else:
        print(f"Failed to list agents: {list_resp.status_code}")


if __name__ == "__main__":
    test_capability_persistence()
