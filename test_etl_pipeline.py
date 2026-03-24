import requests
import time
import json

BASE_URL = "http://localhost:5000"

def run_manual_test():
    print("Starting ETL Pipeline Verification...")
    
    # 1. Login
    print("\n[1] Logging in...")
    try:
        auth = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "testadmin@example.com", 
            "password": "password123"
        })
        if auth.status_code != 200:
            print(f"Login failed: {auth.text}")
            return
            
        token = auth.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("Login successful.")
    except Exception as e:
        print(f"Login failed to connect: {e}")
        return

    # 2. Trigger ETL
    print("\n[2] Triggering ETL Job...")
    try:
        res = requests.post(f"{BASE_URL}/api/etl/run", headers=headers)
        if res.status_code == 200:
            print(f"Success: {res.json()}")
        else:
            print(f"Failed: {res.text}")
    except Exception as e:
        print(f"ETL Trigger failed: {e}")

    # 3. Wait for background processing
    print("\n[3] Waiting 3 seconds for job to process...")
    time.sleep(3)
    
    # 4. Check ETL History
    print("\n[4] Checking ETL History...")
    try:
        hist = requests.get(f"{BASE_URL}/api/etl/history", headers=headers)
        if hist.status_code == 200:
            jobs = hist.json()
            print(f"Found {len(jobs)} jobs.")
            if len(jobs) > 0:
                print(f"Latest Job Status: {jobs[0].get('status')}")
                print(f"Job Details: {jobs[0].get('details')}")
        else:
            print(f"Failed to get history: {hist.text}")
    except Exception as e:
        print(f"History check failed: {e}")
    
    # 5. Check Warehouse Stats
    print("\n[5] Checking Data Warehouse Stats...")
    try:
        stats = requests.get(f"{BASE_URL}/api/warehouse/stats", headers=headers)
        if stats.status_code == 200:
            print(f"Stats: {json.dumps(stats.json(), indent=2)}")
        else:
            print(f"Failed to get stats: {stats.text}")
    except Exception as e:
        print(f"Stats check failed: {e}")

if __name__ == "__main__":
    run_manual_test()
