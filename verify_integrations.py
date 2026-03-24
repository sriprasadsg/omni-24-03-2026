import requests
import json

BASE_URL = "http://127.0.0.1:5000/api"

def verify_integrations():
    print("1. Listing Integrations Configs...")
    try:
        res = requests.get(f"{BASE_URL}/integrations/configs")
        res.raise_for_status()
        print(f"   [+] Success. Current configs: {len(res.json())}")
    except Exception as e:
        print(f"   [-] Failed to list configs: {e}")
        return

    print("2. Saving Mock Slack Config...")
    config = {
        "type": "chatops",
        "platform": "slack",
        "enabled": True,
        "webhook_url": "https://hooks.slack.com/services/EXAMPLE/WEBHOOK/URL12345"
    }
    
    try:
        res = requests.post(f"{BASE_URL}/integrations/config", json=config)
        res.raise_for_status()
        print("   [+] Saved Mock Slack Config")
    except Exception as e:
        print(f"   [-] Failed to save config: {e}")
        return

    print("3. Testing Mock Slack Connection...")
    # Expecting failure from Slack API because URL is fake, but success from backend logic handling
    test_req = {
        "type": "chatops",
        "platform": "slack",
        "config": config
    }
    
    try:
        res = requests.post(f"{BASE_URL}/integrations/test", json=test_req)
        # We expect 200 OK from our API, but the JSON result might say success=False
        res.raise_for_status()
        data = res.json()
        print(f"   [+] API Call Successful. Result: {data}")
        
        if not data['success'] and "Missing Webhook URL" not in str(data):
            print("   [+] Correctly attempted to reach Slack (and failed as expected with fake URL)")
        
    except Exception as e:
        print(f"   [-] Failed to test integration: {e}")

if __name__ == "__main__":
    verify_integrations()
