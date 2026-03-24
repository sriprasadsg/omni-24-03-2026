import requests
import json
import time

BASE_URL = "http://localhost:5000"

def run_test():
    print("Starting AutoML Verification...")
    
    # 1. Login
    try:
        auth = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "testadmin@example.com", 
            "password": "password123"
        })
        token = auth.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("[1] Login successful.")
    except Exception as e:
        print(f"Login failed: {e}")
        return

    # 2. Create Study
    try:
        study_name = "Test Study - Optimize MLP"
        res = requests.post(f"{BASE_URL}/api/automl/study", json={"name": study_name}, headers=headers)
        study_id = res.json()["study_id"]
        print(f"[2] Created Study: {study_id}")
    except Exception as e:
        print(f"Create Study failed: {e}")
        return

    # 3. Run Trials
    print("[3] Running 5 Trials (this may take 2-3 seconds)...")
    try:
        res = requests.post(f"{BASE_URL}/api/automl/study/{study_id}/run", json={"n_trials": 5}, headers=headers)
        print(f"Run complete: {res.json()}")
    except Exception as e:
        print(f"Run Trials failed: {e}")

    # 4. Check Results
    print("[4] Fetching Results...")
    try:
        res = requests.get(f"{BASE_URL}/api/automl/study/{study_id}", headers=headers)
        data = res.json()
        
        trials = data["trials"]
        print(f"Total Trials: {len(trials)}")
        
        best = data["best_trial"]
        if best:
            print(f"Best Trial Score: {best['value']}")
            print(f"Best Params: {best['params']}")
            print("PASS: Successfully identified best trial.")
        else:
            print("FAIL: No best trial found.")
            
    except Exception as e:
        print(f"Fetch Results failed: {e}")

if __name__ == "__main__":
    run_test()
