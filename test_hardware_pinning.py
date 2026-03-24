import requests
import json

def test_pinning():
    base_url = "http://localhost:5000"
    # Replace with a valid agent_id from your DB
    agent_id = "agent-8f7d6a5b" # Placeholder, I should find a real one
    
    # First, find a real agent_id
    try:
        resp = requests.get(f"{base_url}/api/agents", timeout=5)
        if resp.status_code == 200:
            agents = resp.json().get('items', [])
            if agents:
                agent_id = agents[0]['id']
                stored_device_id = agents[0].get('deviceId', 'none')
                print(f"Testing against Agent: {agent_id} (Pinned to: {stored_device_id})")
            else:
                print("No agents found in DB")
                return
    except Exception as e:
        print(f"Error fetching agents: {e}")
        return

    # Simulate rogue heartbeat with WRONG device_id
    payload = {
        "hostname": "rogue-host",
        "ipAddress": "1.2.3.4",
        "platform": "Windows",
        "version": "2.0.1",
        "device_id": "STOLEN-IDENTITY-12345",
        "meta": {}
    }
    
    # We need a valid token to pass verify_agent_key, 
    # but the hardware pinning check happens AFTER that.
    # For this test, if we don't have a token, we can use registration key if we know it.
    
    print("Sending rogue heartbeat...")
    try:
        url = f"{base_url}/api/agents/{agent_id}/heartbeat"
        # We'll try without auth first to see if it even hits the pinning logic
        # (It will likely fail verify_agent_key first)
        resp = requests.post(url, json=payload, timeout=5)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
        
        if resp.status_code == 403 and "Hardware ID mismatch" in resp.text:
            print("✅ SUCCESS: Backend rejected rogue heartbeat due to Hardware ID mismatch!")
        else:
            print("❌ FAILURE: Backend did not enforce hardware pinning.")
            
    except Exception as e:
        print(f"Error sending heartbeat: {e}")

if __name__ == "__main__":
    test_pinning()
