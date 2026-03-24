import requests
import json

BASE_URL = "http://localhost:5000"

def verify_integrations():
    print("--- Verifying Integrations ---")
    
    # 1. Login
    login_url = f"{BASE_URL}/api/auth/login"
    creds = {"email": "super@omni.ai", "password": "password123"}
    try:
        resp = requests.post(login_url, json=creds)
        token = resp.json().get("access_token")
    except Exception:
        token = None
    
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    # 2. List Configs (should be empty initially or mock)
    print("\n[1] Listing Integrations...")
    resp = requests.get(f"{BASE_URL}/api/integrations/configs", headers=headers)
    print(f"Configs: {resp.status_code}")
    if resp.status_code == 200:
        print(resp.json())
        
    # 3. Save Config - Try multiple endpoints
    print("\n[2] Saving Config...")
    slack_config = {
        "type": "chatops", "platform": "slack", "enabled": True, "webhook_url": "https://hooks.slack.com/services/test"
    }
    
    # Try singular (v1)
    url_v1 = f"{BASE_URL}/api/integrations/config"
    print(f"POST {url_v1}")
    resp = requests.post(url_v1, json=slack_config, headers=headers)
    print(f"Result V1: {resp.status_code}")
    
    if resp.status_code != 200:
        # Try plural (v2)
        url_v2 = f"{BASE_URL}/api/integrations/configs"
        print(f"POST {url_v2}")
        payload_v2 = {"id": "slack-mock", "type": "chatops", "config": slack_config}
        resp = requests.post(url_v2, json=payload_v2, headers=headers)
        print(f"Result V2: {resp.status_code}")

    # 4. Test Notification
    print("\n[3] Testing Notification...")
    test_payload = {"type": "chatops", "platform": "slack", "config": slack_config}
    resp = requests.post(f"{BASE_URL}/api/integrations/test", json=test_payload, headers=headers)
    print(f"Test POST Result: {resp.status_code}")
    try:
        print(f"Response: {resp.json()}")
    except:
        print(f"Raw: {resp.text}")

if __name__ == "__main__":
    verify_integrations()
