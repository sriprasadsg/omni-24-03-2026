import requests
import time

BASE_URL = "http://localhost:5000"

def verify_ab():
    # 1. Login
    login_url = f"{BASE_URL}/api/auth/login"
    creds = {
        "email": "super@omni.ai",
        "password": "password123"
    }
    
    print(f"Logging in as {creds['email']}...")
    try:
        resp = requests.post(login_url, json=creds)
        data = resp.json()
    except Exception as e:
        print(f"Login failed: {e}")
        return

    if not data.get("success"):
        print(f"Login failed: {data}")
        return

    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Create Experiment
    print("\n--- Creating Experiment ---")
    payload = {
        "name": "Checkout Flow V2",
        "description": "Testing simplified checkout",
        "variants": ["Control", "OnePage", "Modal"]
    }
    resp = requests.post(f"{BASE_URL}/api/experiments/", json=payload, headers=headers)
    
    if resp.status_code == 200:
        exp_id = resp.json().get("experiment_id")
        print(f"Created Experiment: {exp_id}")
    else:
        print(f"Failed to create experiment: {resp.status_code} - {resp.text}")
        return

    # 3. Assign Variants (Simulate Traffic)
    print("\n--- Simulating Traffic ---")
    users = [f"user_{i}" for i in range(10)]
    for user_id in users:
        resp = requests.get(f"{BASE_URL}/api/experiments/{exp_id}/variant?user_id={user_id}")
        if resp.status_code == 200:
            print(f"User {user_id} -> {resp.json().get('variant')}")
        
    # 4. Track Conversions
    print("\n--- Tracking Conversions ---")
    # Convert first 3 users
    for user_id in users[:3]:
        resp = requests.post(
            f"{BASE_URL}/api/experiments/{exp_id}/track", 
            json={"user_id": user_id}
        )
        if resp.status_code == 200:
             print(f"Converted User {user_id}")

    # 5. Get Results
    print("\n--- Fetching Results ---")
    resp = requests.get(f"{BASE_URL}/api/experiments/{exp_id}/results", headers=headers)
    if resp.status_code == 200:
        print(f"Results: {resp.json()}")
    else:
        print(f"Failed to get results: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    verify_ab()
