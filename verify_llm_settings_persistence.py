import requests
import json
import sys

# Configuration
BASE_URL = "http://localhost:5000"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
SETTINGS_URL = f"{BASE_URL}/api/settings/llm"

# Credentials (default super admin)
# Credentials (default super admin)
EMAIL = "super@omni.ai"
PASSWORD = "password123"

def get_auth_headers():
    """Authenticate and return headers with JWT token."""
    print(f"Authenticating as {EMAIL}...")
    try:
        response = requests.post(LOGIN_URL, json={"email": EMAIL, "password": PASSWORD})
        response.raise_for_status()
        data = response.json()
        if not data.get("success"):
            print(f"Login failed: {data.get('error')}")
            sys.exit(1)
            
        token = data.get("access_token")
        print("Authentication successful.")
        return {"Authorization": f"Bearer {token}"}
    except requests.exceptions.RequestException as e:
        print(f"Login error: {e}")
        if e.response:
            print(f"Response: {e.response.text}")
        sys.exit(1)

def verify_persistence():
    headers = get_auth_headers()
    
    # 1. Defined Custom Models to Add
    test_models = ["gpt-4-turbo-custom", "claude-3-opus-custom", "local-llama-3"]
    
    payload = {
        "provider": "Gemini",
        "apiKey": "AIzaSyDVN6ccV7gcKa7NXPmumok-XPOKi6TjdeM",  # The Key we want to ensure
        "customModels": test_models,
        "enabled": True
    }
    
    print("\n[Test] Saving LLM Settings with Custom Models...")
    try:
        # Save Settings
        resp = requests.post(SETTINGS_URL, json=payload, headers=headers)
        if resp.status_code != 200:
            print(f"FAILED to save settings. Status: {resp.status_code}, Response: {resp.text}")
            sys.exit(1)
        
        print("Save successful. Verifying persistence...")
        
        # Retrieve Settings
        resp_get = requests.get(SETTINGS_URL, headers=headers)
        if resp_get.status_code != 200:
            print(f"FAILED to get settings. Status: {resp_get.status_code}")
            sys.exit(1)
            
        saved_data = resp_get.json()
        
        # Verify API Key
        if saved_data.get("apiKey") != payload["apiKey"]:
            print(f"❌ API Key Mismatch! Expected: {payload['apiKey']}, Got: {saved_data.get('apiKey')}")
        else:
            print("✅ API Key persisted correctly.")

        # Verify Custom Models
        saved_models = saved_data.get("customModels", [])
        if set(saved_models) == set(test_models):
            print("✅ Custom Models persisted correctly.")
        else:
            print(f"❌ Custom Models Mismatch! Expected: {test_models}, Got: {saved_models}")
            
    except Exception as e:
        print(f"An error occurred during verification: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_persistence()
