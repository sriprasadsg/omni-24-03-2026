
import requests
import json
import time

BASE_URL = "http://localhost:5000/api"

# 1. Login to get token
def login():
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json={
            "email": "super@omni.ai",
            "password": "password123"
        })
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception as e:
        print(f"Login failed: {e}")
        return None

def verify_custom_integration():
    token = login()
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Define Custom Integration
    custom_id = f"custom-test-{int(time.time())}"
    custom_integration = {
        "id": custom_id,
        "name": "My Custom Tool",
        "category": "Custom",
        "description": "A test custom integration",
        "isEnabled": True,
        "config": {"key": "value"}
    }
    
    # 3. Add Custom Integration
    print(f"Adding custom integration: {custom_id}...")
    try:
        resp = requests.post(f"{BASE_URL}/integrations/config", json=custom_integration, headers=headers)
        resp.raise_for_status()
        print("Add success:", resp.json())
    except Exception as e:
        print(f"Failed to add integration: {e}")
        print(resp.text)
        return

    # 4. List Integrations
    print("Fetching integration list...")
    try:
        resp = requests.get(f"{BASE_URL}/integrations/list", headers=headers)
        resp.raise_for_status()
        integrations = resp.json()
        
        # 5. Verify presence
        found = False
        for integration in integrations:
            if integration["id"] == custom_id:
                found = True
                print("Found custom integration in list!")
                print(json.dumps(integration, indent=2))
                break
        
        if found:
            print("VERIFICATION_SUCCESS")
        else:
            print("VERIFICATION_FAILURE: Custom integration not found in list.")
            
    except Exception as e:
        print(f"Failed to list integrations: {e}")

if __name__ == "__main__":
    verify_custom_integration()
