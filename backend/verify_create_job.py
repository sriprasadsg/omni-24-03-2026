
import requests
import json

BASE_URL = "http://localhost:5000"

def login():
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "super@omni.ai",
            "password": "password123"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            print("Login failed")
            return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def verify_create_job():
    token = login()
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}

    job_data = {
        "type": "maintenance",
        "details": {"target": "server-01", "action": "clean_logs"}
    }

    print("Creating Job...")
    try:
        resp = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=headers)
        
        if resp.status_code == 200:
            print(f"SUCCESS: Job created. ID: {resp.json().get('id')}")
            print(json.dumps(resp.json(), indent=2))
        else:
            print(f"FAILURE: {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    verify_create_job()
