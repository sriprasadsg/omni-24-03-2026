import requests
import json

try:
    response = requests.get("http://127.0.0.1:8000/api/agents")
    data = response.json()
    print(f"Status: {response.status_code}")
    if len(data) > 0:
        agent = data[0]
        meta = agent.get("meta", {})
        ph = meta.get("predictive_health", {})
        print(f"Agent 0 Predictive Health Present: {bool(ph)}")
        if ph:
            print(f"Current Score: {ph.get('current_score')}")
            print(f"Predictions Count: {len(ph.get('predictions', []))}")
    else:
        print("No agents found")
except Exception as e:
    print(e)
