
import requests
import json
import sys

BASE_URL = "http://localhost:5000"

def get_auth_token():
    # 0. Root Check
    try:
        root = requests.get(f"{BASE_URL}/")
        print(f"Root Check: {root.status_code} - {root.text}")
    except Exception as e:
        print(f"Root Check Failed: {e}")

    # 1. Health Check
    try:
        health = requests.get(f"{BASE_URL}/health")
        print(f"Health Check: {health.status_code} - {health.text[:100]}")
    except Exception as e:
        print(f"Health Check Failed: {e}")
        return None

    # 2. Try Login Paths
    paths = ["/api/auth/login"]
    
    # Use testadmin user found in DB
    data = {"email": "testadmin@example.com", "password": "any"}
    
    for path in paths:
        url = f"{BASE_URL}{path}"
        print(f"Trying: {url}")
        try:
            response = requests.post(url, json=data)
            if response.status_code == 200:
                print(f"Login OK")
                return response.json().get("access_token")
            else:
                print(f"Fail: {response.status_code}")
                # print(f"Msg: {response.text}") # Don't print full html if 404
                print(f"Msg: {response.text[:200]}")
        except Exception as e:
            print(f"Err: {e}")
            
    print("Login All Failed")
    return None

def test_llm_settings_persistence():
    token = get_auth_token()
    if not token:
        print("Skipping test due to login failure.")
        return False

    headers = {
        "Authorization": f"Bearer {token}"
    }

    url = f"{BASE_URL}/api/settings/llm"
    
    # Payload with custom models
    payload = {
        "provider": "Gemini",
        "apiKey": "test-api-key-123",
        "model": "gemini-1.5-pro-custom",
        "customModels": ["gemini-1.5-pro-custom", "my-finetuned-model"]
    }
    
    print(f"Sending payload: {json.dumps(payload, indent=2)}")
    
    # 1. Save Settings
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        print(f"Failed to save settings: {response.status_code}")
        print(response.text)
        return False
        
    print("Settings saved successfully.")
    
    # 2. Retrieve Settings
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to get settings: {response.status_code}")
        return False
        
    saved_settings = response.json()
    print(f"Retrieved settings: {json.dumps(saved_settings, indent=2)}")
    
    # 3. Verify Custom Models
    if saved_settings.get("customModels") == payload["customModels"]:
        print("SUCCESS: Custom models persisted correctly.")
        return True
    else:
        print("FAILURE: Custom models did not match.")
        print(f"Expected: {payload['customModels']}")
        print(f"Got: {saved_settings.get('customModels')}")
        return False

if __name__ == "__main__":
    if test_llm_settings_persistence():
        print("Backend verification PASSED")
        sys.exit(0)
    else:
        print("Backend verification FAILED")
        sys.exit(1)
