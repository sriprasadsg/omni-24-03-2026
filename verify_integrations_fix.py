import requests
import json
import time

BASE_URL = "http://localhost:5000"

def login():
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "super@omni.ai",
            "password": "password123"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            print(f"Login failed: {response.text}")
            return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def check_integrations(token):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(f"{BASE_URL}/api/integrations/list", headers=headers)
        if response.status_code == 200:
            integrations = response.json()
            print(f"Found {len(integrations)} integrations.")
            for i in integrations:
                print(f"- {i['name']} (Enabled: {i.get('isEnabled', False)})")
            return len(integrations) > 0
        else:
            print(f"Fetch integrations failed: {response.text}")
            return False
    except Exception as e:
        print(f"Fetch integrations error: {e}")
        return False

if __name__ == "__main__":
    print("Waiting for backend to be fully ready...")
    time.sleep(2)
    token = login()
    if token:
        success = check_integrations(token)
        if success:
            print("VERIFICATION SUCCESS: Integrations list is populated.")
        else:
            print("VERIFICATION FAILED: Integrations list is empty or error.")
    else:
        print("VERIFICATION FAILED: Could not login.")
