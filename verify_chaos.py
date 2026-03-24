import requests
import json
import time

BASE_URL = "http://localhost:5000/api/chaos"

def verify_chaos():
    print("--- Verifying Chaos Engineering ---")
    
    # 1. List Experiments
    try:
        print("1. Listing Chaos Experiments...")
        res = requests.get(f"{BASE_URL}/experiments")
        if res.status_code == 200:
            experiments = res.json()
            print(f"   -> Success: Retrieved {len(experiments)} experiments.")
            if len(experiments) > 0:
                print(f"   -> Sample: {experiments[1]['name']} - Status: {experiments[1]['status']}")
        else:
             print(f"   -> Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"   -> Error: {e}")

    # 2. Trigger Experiment
    try:
        print("\n2. Triggering 'Random Pod Killer' (exp-001)...")
        res = requests.post(f"{BASE_URL}/trigger?experiment_id=exp-001")
        if res.status_code == 200:
            print(f"   -> Success: {res.json()['message']}")
        else:
             print(f"   -> Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"   -> Error: {e}")


if __name__ == "__main__":
    verify_chaos()
