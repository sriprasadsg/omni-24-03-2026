import requests
import json
import sys

BASE_URL = "http://localhost:5000/api/chaos"

def verify_chaos_engineering():
    print(f"Testing Chaos Engineering Endpoints at {BASE_URL}...")
    
    # 1. Get Experiments
    try:
        response = requests.get(f"{BASE_URL}/experiments")
        if response.status_code == 200:
            experiments = response.json()
            print("\n[SUCCESS] GET /experiments")
            print(f"Count: {len(experiments)}")
            print(json.dumps(experiments[:2], indent=2)) # Print first 2
        else:
            print(f"\n[FAILURE] GET /experiments - Status: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"\n[ERROR] GET /experiments: {e}")

    # 2. Create Experiment
    new_experiment = {
        "id": "exp-ver-001",
        "tenantId": "tenant-verification",
        "name": "Verification Chaos Experiment",
        "type": "Network Latency",
        "target": "verification-service",
        "status": "Scheduled",
        "lastRun": "N/A"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/experiments", json=new_experiment)
        if response.status_code == 200:
            created_exp = response.json()
            print("\n[SUCCESS] POST /experiments")
            print(json.dumps(created_exp, indent=2))
        else:
            print(f"\n[FAILURE] POST /experiments - Status: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"\n[ERROR] POST /experiments: {e}")

    # 3. Run Experiment
    try:
        response = requests.post(f"{BASE_URL}/experiments/exp-ver-001/run")
        if response.status_code == 200:
            result = response.json()
            print("\n[SUCCESS] POST /experiments/exp-ver-001/run")
            print(json.dumps(result, indent=2))
        else:
            print(f"\n[FAILURE] POST /experiments/run - Status: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"\n[ERROR] POST /experiments/run: {e}")

if __name__ == "__main__":
    verify_chaos_engineering()
