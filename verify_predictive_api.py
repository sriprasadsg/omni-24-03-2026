import requests
import json
import time

BASE_URL = "http://localhost:5000"

def run_verification():
    print("=== Starting API Verification for Predictive Health ===")
    
    # 1. Login
    try:
        print("1. Authenticating...")
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "testadmin@example.com",
            "password": "password123"
        })
        if resp.status_code != 200:
            print(f"❌ Login failed: {resp.text}")
            return
        
        data = resp.json()
        token = data['access_token']
        headers = {"Authorization": f"Bearer {token}"}
        print("✅ Authentication successful")
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return

    # 2. Fetch Agents
    try:
        print("\n2. Fetching Agents...")
        resp = requests.get(f"{BASE_URL}/api/agents", headers=headers)
        if resp.status_code != 200:
            print(f"❌ Failed to get agents: {resp.text}")
            return
        


        agents = resp.json()
        print(f"✅ Retrieved object from backend")
        print(f"DEBUG: Type of agents: {type(agents)}")
        if isinstance(agents, dict):
             print(f"DEBUG: Content of agents dict: {json.dumps(agents, indent=2)}")
             # Handle paginated response if applicable
             if "items" in agents:
                 agents = agents["items"]
                 print(f"DEBUG: Extracted {len(agents)} agents from 'items' key")
             else:
                 print("ERROR: Expected list or dict with 'items' key.")
                 return

        if len(agents) > 0:
            print(f"DEBUG: Type of first agent: {type(agents[0])}")

        # 3. Analyze Predictive Data
        print("\n3. Verifying Predictive Health Data Structure...")
        
        online_count = 0
        valid_predictive_count = 0
        
        for i, agent in enumerate(agents):
            if not isinstance(agent, dict):
                print(f"❌ Error: Agent at index {i} is not a dict, it is {type(agent)}")
                continue

            aid = agent.get('id')
            status = agent.get('status')
            
            if status == 'Online':
                online_count += 1
            
            # Check Meta
            meta = agent.get('meta', {})
            ph = meta.get('predictive_health')
            
            if ph:
                score = ph.get('current_score')
                predictions = ph.get('predictions', [])
                warnings = ph.get('warnings', [])
                
                print(f"\n[Agent {aid}] Status: {status}")
                print(f"  - Health Score: {score}")
                print(f"  - Forecast Points: {len(predictions)}")
                print(f"  - Warnings: {len(warnings)}")
                
                if predictions:
                    # Verify forecast structure
                    p1 = predictions[0]
                    if all(k in p1 for k in ['cpu_prediction', 'memory_prediction', 'timestamp', 'health_score']):
                         valid_predictive_count += 1
                         print(f"  - ✅ Forecast structure valid")
                    else:
                         print(f"  - ❌ Invalid forecast structure: {p1.keys()}")
            else:
                if status == 'Online':
                    print(f"\n[Agent {aid}] Status: {status} - ⚠️ No predictive data yet")

        print(f"\n=== Verification Summary ===")
        print(f"Online Agents: {online_count}")
        print(f"Agents with Valid Predictive Data: {valid_predictive_count}")
        
        if valid_predictive_count > 0:
            print("\n✅ PASSED: Backend is serving correctly formatted predictive analytics data.")
            print("The Frontend should display this correctly.")
        else:
            print("\n⚠️ WARNING: backend is reachable but no predictive data was found. Simulator might need more time or 'meta' field is missing.")

    except Exception as e:
        print(f"❌ Error during verification: {e}")

if __name__ == "__main__":
    run_verification()
