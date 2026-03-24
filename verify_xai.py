import requests
import json

BASE_URL = "http://localhost:5000"

def verify_xai():
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
    
    # 2. Test Global Importance
    print("\n--- Testing Global Importance ---")
    model_id = "phishing-detector-v1"
    resp = requests.get(f"{BASE_URL}/api/xai/global/{model_id}", headers=headers)
    
    if resp.status_code == 200:
        print(f"Global Importance: {resp.json()}")
    else:
        print(f"Failed to get global importance: {resp.status_code} - {resp.text}")

    # 3. Test Local Explanation
    print("\n--- Testing Local Explanation (SHAP) ---")
    payload = {
        "model_id": model_id,
        "input": {
            "feature1": 0.5,
            "feature2": 1.2,
            "feature3": -0.8
        }
    }
    resp = requests.post(f"{BASE_URL}/api/xai/explain", json=payload, headers=headers)
    
    if resp.status_code == 200:
        print(f"Explanation: {json.dumps(resp.json(), indent=2)}")
    else:
        print(f"Failed to explain: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    verify_xai()
