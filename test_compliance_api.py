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
        frameworks_url = "http://localhost:5000/api/compliance"
        f_resp = requests.get(frameworks_url, headers=headers)
        if f_resp.status_code != 200:
            print(f"Get Frameworks FAILED: {f_resp.status_code} {f_resp.text}")
            return
            
        frameworks = f_resp.json()
        print(f"Frameworks found: {len(frameworks)}")
        for f in frameworks:
            print(f"- {f.get('name')} (ID: {f.get('id')})")
            
        # 3. Get AI Governance Models
        models_url = "http://localhost:5000/api/ai-governance/models"
        m_resp = requests.get(models_url, headers=headers)
        if m_resp.status_code == 200:
            models = m_resp.json()
            print(f"\nAI Models found: {len(models)}")
            for m in models:
                print(f"- {m.get('name')} (ID: {m.get('id')})")
        else:
             print(f"\nGet AI Models FAILED: {m_resp.status_code}")

    except Exception as e:
        print(f"Error during API test: {e}")

if __name__ == "__main__":
    test_compliance()
