import requests
import json

def test_compliance():
    try:
        # 1. Login
        login_url = "http://localhost:5000/api/auth/login"
        login_data = {"email": "admin@exafluence.com", "password": "password123"}
        resp = requests.post(login_url, json=login_data)
        if resp.status_code != 200:
            print(f"Login FAILED: {resp.status_code} {resp.text}")
            return
            
        token = resp.json().get("access_token")
        print(f"Login SUCCESS. Token received.")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Get Frameworks
        print("\n--- Compliance Frameworks ---")
        f_resp = requests.get("http://localhost:5000/api/compliance", headers=headers)
        if f_resp.status_code == 200:
            print(f"Frameworks found: {len(f_resp.json())}")
        
        # 3. Get AI Policies
        print("\n--- AI Policies ---")
        p_resp = requests.get("http://localhost:5000/api/ai-governance/policies", headers=headers)
        if p_resp.status_code == 200:
            policies = p_resp.json()
            print(f"AI Policies found: {len(policies)}")
        
        # 4. Get AI Models
        print("\n--- AI Models ---")
        m_resp = requests.get("http://localhost:5000/api/ai-governance/models", headers=headers)
        if m_resp.status_code == 200:
            models = m_resp.json()
            print(f"AI Models found: {len(models)}")

    except Exception as e:
        print(f"Error during API test: {e}")

if __name__ == "__main__":
    test_compliance()
