import requests
import json
import sys

# Configuration
BASE_URL = "http://localhost:5000"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
CHAT_URL = f"{BASE_URL}/api/ai/chat"

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

def verify_chat():
    headers = get_auth_headers()
    
    payload = {
        "message": "Hello, are you online?",
        "context": {"currentView": "Dashboard"}
    }
    
    print("\n[Test] Sending Chat Message to AI...")
    try:
        resp = requests.post(CHAT_URL, json=payload, headers=headers)
        
        if resp.status_code == 404:
            print("❌ Endpoints NOT found (404). The router is likely not responding.")
            sys.exit(1)
            
        if resp.status_code != 200:
            print(f"FAILED to chat. Status: {resp.status_code}, Response: {resp.text}")
            sys.exit(1)
        
        data = resp.json()
        response_text = data.get("response")
        
        print("\n✅ AI Response Received:")
        print(f"--------------------------------------------------")
        print(f"{response_text}")
        print(f"--------------------------------------------------")
        
        if "AI Service not configured" in response_text:
             print("⚠️  Warning: AI Service reachable but not configured (API Key missing?).")
        else:
             print("✅ AI Service is fully functional.")

    except Exception as e:
        print(f"An error occurred during verification: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_chat()
