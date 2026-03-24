import requests
import json

BASE_URL = "http://127.0.0.1:5000/api"

def debug_metrics():
    # 1. Login
    print("Logging in...")
    # Try super@omni.ai which is the seeded super admin
    print("Using super@omni.ai for login...")
    resp = requests.post(
        f"{BASE_URL}/auth/login", 
        json={"email": "super@omni.ai", "password": "password123"},
        headers={"Content-Type": "application/json"}
    )
    
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} - {resp.text}")
        return

    data = resp.json()
    if not data.get("success"):
        print(f"Login failed logic: {data}")
        return
        
    token = data["access_token"]
    print(f"Login successful. Token: {token[:10]}...")
    
    headers = {"Authorization": f"Bearer {token}"}

    # 2. List Assets
    print("Listing assets...")
    resp = requests.get(f"{BASE_URL}/assets", headers=headers)
    if resp.status_code != 200:
        print(f"List assets failed: {resp.text}")
        return
    
    assets = resp.json()
    print(f"Found {len(assets)} assets.")
    if not assets:
        print("No assets found. Cannot test metrics.")
        return

    asset_id = assets[0]["id"]
    print(f"Testing metrics for asset: {asset_id}")

    # 3. Get Metrics
    resp = requests.get(f"{BASE_URL}/assets/{asset_id}/metrics?range=24h", headers=headers)
    print(f"Metrics status: {resp.status_code}")
    print(json.dumps(resp.json(), indent=2))

if __name__ == "__main__":
    debug_metrics()
