import requests
import json

try:
    resp = requests.get("http://localhost:5000/api/agents")
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        agents = resp.json()
        print(f"Count: {len(agents)}")
        for a in agents:
            print(f"ID: {a.get('id')}, Host: {a.get('hostname')}, Tenant: {a.get('tenantId')}, IP: {a.get('ipAddress')}")
    else:
        print(resp.text)
except Exception as e:
    print(e)
