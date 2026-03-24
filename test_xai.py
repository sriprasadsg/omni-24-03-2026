import requests
import json

BASE_URL = "http://localhost:5000"

def run_test():
    print("Starting XAI Verification...")
    
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

    # 2. Get Global Importance
    print("\n[2] Fetching Global Feature Importance...")
    try:
        res = requests.get(f"{BASE_URL}/api/xai/global/model-risk-v1", headers=headers)
        if res.status_code == 200:
            data = res.json()
            print(f"Top Feature: {data[0]['feature']} ({data[0]['importance']})")
        else:
            print(f"Failed: {res.text}")
    except Exception as e:
        print(f"Global check failed: {e}")

    # 3. Explain Local Prediction (High Risk Scenario)
    print("\n[3] Explaining 'High Risk' Prediction (5 failed logins)...")
    try:
        payload = {
            "model_id": "model-risk-v1",
            "input": {
                "failed_logins_count": 5,
                "ip_reputation_score": 30, # Low rep
                "access_time_hour": 3 # 3 AM
            }
        }
        res = requests.post(f"{BASE_URL}/api/xai/explain", json=payload, headers=headers)
        if res.status_code == 200:
            exp = res.json()
            print(f"Prediction: {exp['prediction']} ({exp['risk_level']})")
            
            # Verify contributions
            logins = next(f for f in exp['features'] if f['feature'] == 'failed_logins_count')
            print(f"Failed Logins Impact: {logins['shap']}")
            
            if exp['risk_level'] == "HIGH" and logins['shap'] > 0.3:
                print("PASS: High risk correctly attributed to failed logins.")
            else:
                print("FAIL: Explanation logic incorrect.")
        else:
            print(f"Failed: {res.text}")
    except Exception as e:
        print(f"Explanation check failed: {e}")
        
    # 4. Explain Local Prediction (Low Risk Scenario)
    print("\n[4] Explaining 'Low Risk' Prediction...")
    try:
        payload = {
            "model_id": "model-risk-v1",
            "input": {
                "failed_logins_count": 0,
                "ip_reputation_score": 95,
                "access_time_hour": 14
            }
        }
        res = requests.post(f"{BASE_URL}/api/xai/explain", json=payload, headers=headers)
        exp = res.json()
        print(f"Prediction: {exp['prediction']} ({exp['risk_level']})")
        if exp['risk_level'] == "LOW":
             print("PASS: Low risk correctly predicted.")
    except:
        pass

if __name__ == "__main__":
    run_test()
