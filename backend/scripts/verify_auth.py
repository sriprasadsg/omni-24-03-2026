
import os
import requests

BASE_URL = "http://localhost:5000"
_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "super@omni.ai")
_PASSWORD = os.environ.get("SUPER_ADMIN_PASSWORD", "")
if not _PASSWORD:
    raise SystemExit("SUPER_ADMIN_PASSWORD environment variable is required to run this script")

def login():
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": _EMAIL,
            "password": _PASSWORD,
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            print(f"Login failed: {response.text}")
            return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def verify_auth():
    token = login()
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}
    
    print("Testing /api/test-auth...")
    try:
        resp = requests.get(f"{BASE_URL}/api/test-auth", headers=headers)
        print(f"Response: {resp.status_code}")
        print(resp.text)
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    verify_auth()
