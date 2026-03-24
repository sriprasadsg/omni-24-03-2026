import requests
import time

BASE_URL = "http://localhost:5000"

def verify_mlops():
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

    # 2. Trigger Model Retraining
    print("\n--- Testing MLOps Retraining ---")
    train_url = f"{BASE_URL}/api/mlops/train"
    payload = {"model_name": "Phishing Detector v2", "reason": "Integration Test"}
    
    resp = requests.post(train_url, json=payload, headers=headers)
    if resp.status_code == 200:
        print(f"Training Triggered: {resp.json()}")
        job_id = resp.json().get("job_id")
    else:
        print(f"Failed to trigger training: {resp.status_code} - {resp.text}")
        job_id = None

    # 3. Check History
    time.sleep(1)
    history_url = f"{BASE_URL}/api/mlops/history"
    resp = requests.get(history_url, headers=headers)
    if resp.status_code == 200:
        history = resp.json()
        print(f"History Entries: {len(history)}")
        if len(history) > 0:
            print(f"Latest Job: {history[0]}")
    else:
        print(f"Failed to get history: {resp.status_code}")

    # 4. Check Registry
    registry_url = f"{BASE_URL}/api/mlops/models"
    resp = requests.get(registry_url, headers=headers)
    if resp.status_code == 200:
        print(f"Model Registry: {len(resp.json())} models found.")
    else:
        print(f"Failed to get registry: {resp.status_code}")

    # 5. Test AutoML
    print("\n--- Testing AutoML ---")
    create_study_url = f"{BASE_URL}/api/automl/study"
    resp = requests.post(create_study_url, json={"name": "Optimization Test"}, headers=headers)
    
    if resp.status_code == 200:
        study_id = resp.json().get("study_id")
        print(f"Created Study: {study_id}")
        
        # Run Trials
        run_url = f"{BASE_URL}/api/automl/study/{study_id}/run"
        resp = requests.post(run_url, json={"n_trials": 3}, headers=headers)
        if resp.status_code == 200:
            print(f"Trials Result: {resp.json()}")
        else:
            print(f"Failed to run trials: {resp.status_code} - {resp.text}")
            
    else:
        print(f"Failed to create study: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    verify_mlops()
