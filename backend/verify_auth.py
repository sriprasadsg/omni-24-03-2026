
import requests
import json

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
