import requests
import json
import time

BASE_URL = "http://localhost:5000"

def run_test():
    print("Starting MLOps Verification...")
    
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
        print(f"Login connection failed: {e}")
        return

    # 2. List initial models
    print("\n[2] Listing Models...")
    try:
        res = requests.get(f"{BASE_URL}/api/mlops/models", headers=headers)
        if res.status_code == 200:
            models = res.json()
            print(f"Found {len(models)} models.")
            for m in models:
                print(f"- {m['name']} ({m['version']}) [{m['stage']}]")
        else:
            print(f"Failed to list models: {res.text}")
    except Exception as e:
        print(f"Model list failed: {e}")

    # 3. Trigger Retraining
    print("\n[3] Triggering Retraining for 'Phishing Detector'...")
    job_id = None
    try:
        res = requests.post(f"{BASE_URL}/api/mlops/train", json={"model_name": "Phishing Detector", "reason": "Test Script"}, headers=headers)
        if res.status_code == 200:
            data = res.json()
            job_id = data["job_id"]
            print(f"Job triggered: {job_id}")
        else:
            print(f"Failed to trigger: {res.text}")
    except Exception as e:
        print(f"Trigger failed: {e}")

    # 4. Monitor Job
    if job_id:
        print("\n[4] Monitoring Job Progress...")
        for i in range(10): # Max wait 10s (simulated job takes ~5-6s)
            time.sleep(1)
            try:
                hist = requests.get(f"{BASE_URL}/api/mlops/history", headers=headers).json()
                job = next((j for j in hist if j["job_id"] == job_id), None)
                if job:
                    print(f"Status: {job['status']} ({job['progress']}%)")
                    if job["status"] in ["Completed", "Failed"]:
                        if job["status"] == "Completed":
                            print(f"Metrics: {job.get('metrics')}")
                            print(f"New Version ID: {job.get('new_version_id')}")
                        break
            except Exception as e:
                print(f"Monitor error: {e}")

    # 5. Verify New Version in Registry
    print("\n[5] Verifying New Version...")
    try:
        res = requests.get(f"{BASE_URL}/api/mlops/models", headers=headers)
        models = res.json()
        phishing_models = [m for m in models if m["name"] == "Phishing Detector"]
        print(f"Found {len(phishing_models)} versions of Phishing Detector.")
        
        # Determine latest
        latest = phishing_models[0] # assuming sorted or just check name
        print(f"Latest: {latest['version']} - {latest['stage']}")
        
        if latest["stage"] == "Staging":
            print("PASS: New version is in Staging")
        else:
            print("FAIL: New version not found in Staging")

    except Exception as e:
        print(f"Verification failed: {e}")

if __name__ == "__main__":
    run_test()
