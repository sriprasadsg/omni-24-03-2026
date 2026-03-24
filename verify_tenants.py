import requests
import json

BASE_URL = "http://localhost:5000/api"

# Login to get token
def login(email, password):
    url = f"{BASE_URL}/auth/login"
    payload = {"email": email, "password": password}
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
        return resp.json()["access_token"]
    else:
        print(f"Login failed: {resp.text}")
        return None

def verify_fetch_tenants():
    print("=== Verifying GET /api/tenants ===")
    token = login("testadmin@example.com", "password123")
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}
    
    resp = requests.get(f"{BASE_URL}/tenants", headers=headers)
    
    print(f"Status Code: {resp.status_code}")
    if resp.status_code == 200:
        tenants = resp.json()
        print(f"Found {len(tenants)} tenants:")
        for t in tenants:
            print(f" - {t.get('name')} ({t.get('id')})")
    else:
        print(f"Failed to fetch tenants: {resp.text}")

if __name__ == "__main__":
    verify_fetch_tenants()
