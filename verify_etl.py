import requests
import time

BASE_URL = "http://localhost:5000"

def verify_etl():
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
        print(f"Login failed to connect: {e}")
        return

    if not data.get("success"):
        print(f"Login failed: {data}")
        return

    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Login Success.")

    # 2. Trigger ETL Job
    print("Triggering ETL Job...")
    etl_url = f"{BASE_URL}/api/etl/run"
    resp = requests.post(etl_url, headers=headers)
    
    if resp.status_code != 200:
        print(f"Failed to trigger ETL: {resp.status_code} - {resp.text}")
        return
        
    print(f"ETL Job Triggered: {resp.json()}")
    
    # 3. Wait and Check History
    print("Waiting for job to complete (5s context switch)...")
    time.sleep(5)
    
    history_url = f"{BASE_URL}/api/etl/history"
    resp = requests.get(history_url, headers=headers)
    
    if resp.status_code != 200:
        print(f"Failed to get history: {resp.status_code} - {resp.text}")
        return
        
    jobs = resp.json()
    print(f"Found {len(jobs)} ETL jobs.")
    if len(jobs) > 0:
        latest = jobs[0]
        print(f"Latest Job Status: {latest.get('status')}")
        print(f"Details: {latest.get('details')}")
        
    # 4. Check Warehouse Stats
    print("Checking Warehouse Stats...")
    stats_url = f"{BASE_URL}/api/warehouse/stats"
    resp = requests.get(stats_url, headers=headers)
    
    if resp.status_code == 200:
        print(f"Warehouse Stats: {resp.json()}")
    else:
        print(f"Failed to get stats: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    verify_etl()
