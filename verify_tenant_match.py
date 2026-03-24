import requests
import json

TARGET_TENANT = "tenant_test_123"

try:
    resp = requests.get("http://localhost:5000/api/agents")
    if resp.status_code == 200:
        agents = resp.json()
        print(f"Total Agents: {len(agents)}")
        for a in agents:
            tid = a.get('tenantId')
            print(f"Agent Host: {a.get('hostname')}")
            print(f"Agent Tenant: {repr(tid)}")
            print(f"Target Tenant: {repr(TARGET_TENANT)}")
            print(f"Match: {tid == TARGET_TENANT}")
            print("-" * 20)
    else:
        print(f"Error: {resp.status_code} {resp.text}")
except Exception as e:
    print(e)
