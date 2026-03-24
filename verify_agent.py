import requests
import yaml
import time
import os

try:
    # Wait for agent to likely register
    print("Waiting for agent to register...")
    
    config_path = "agent/config.yaml"
    if not os.path.exists(config_path):
        print("Config not found!")
        exit(1)
        
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    base_url = config.get("api_base_url", "http://localhost:5000")
    token = config.get("agent_token")
    
    if not token:
        print("No token in config!")
        exit(1)
    
    print("Checking Agents API...")
    headers = {"Authorization": f"Bearer {token}"}
    
    max_retries = 3
    for i in range(max_retries):
        res = requests.get(f"{base_url}/api/agents", headers=headers)
        
        if res.status_code == 200:
            agents = res.json()
            if len(agents) > 0:
                print(f"Total Agents: {len(agents)}")
                for agent in agents:
                    print(f" - Agent: {agent.get('hostname')} | Status: {agent.get('status')} | ID: {agent.get('id')}")
                    
                    if agent.get('tenantId') != config['tenant_id']:
                        print(f"   ⚠️ Tenant Mismatch: {agent.get('tenantId')} vs {config['tenant_id']}")
                    else:
                         print("   ✅ Tenant OK")
                break
            else:
                print(f"No agents found yet (Attempt {i+1}/{max_retries})")
        else:
            print(f"Failed to fetch agents: {res.status_code} {res.text}")
        
        if i < max_retries - 1:
            time.sleep(2)
            
except Exception as e:
    print(f"Verification Error: {e}")
