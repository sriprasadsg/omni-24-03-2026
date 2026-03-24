import requests
import yaml
import json

try:
    with open("agent/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    tenant_id = config["tenant_id"]
    agent_id = "agent-manual-test"
    url = f"http://localhost:5000/api/agents/{agent_id}/heartbeat"

    payload = {
        "version": "1.0.0",
        "hostname": "manual-test-host",
        "tenantId": tenant_id,
        "status": "online",
        "platform": "Windows",
        "ipAddress": "192.168.1.100",
        "tamper_checks_passed": True,
        "checksum": "abc"
    }

    print(f"Sending POST to {url}")
    res = requests.post(url, json=payload)
    print(f"Status: {res.status_code}")
    print(f"Response: {res.text}")

except Exception as e:
    print(f"Error: {e}")
