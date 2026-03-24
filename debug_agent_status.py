
import requests
import json

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbkBleGFmbGV1Y25lLmNvbSIsInJvbGUiOiJUZW5hbnQgQWRtaW4iLCJ0ZW5hbnRfaWQiOiJ0ZW5hbnRfZTFlNTQwZDNhZWVkIiwiZXhwIjoxNzY2MzMxMzE2fQ.CVS_U8eVloAcVZLTVXgu07gKIJew3_KyqPpi33INNNI"
URL = "http://localhost:5000/api/agents"

headers = {"Authorization": f"Bearer {TOKEN}"}

try:
    print(f"Querying {URL}...")
    resp = requests.get(URL, headers=headers)
    print(f"Status Code: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        # Handle paginated response
        items = data.get('items', data) if isinstance(data, dict) else data
        
        print(f"Found {len(items)} agents.")
        for agent in items:
            print(f"Agent: {agent.get('hostname')} | Status: {agent.get('status')} | LastSeen: {agent.get('lastSeen')}")
    else:
        print(f"Error: {resp.text}")
except Exception as e:
    print(f"Exception: {e}")
