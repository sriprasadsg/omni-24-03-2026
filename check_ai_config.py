
import requests
import json

def check_config():
    try:
        # First login to get token
        login_url = "http://localhost:5000/api/auth/login"
        login_data = {"email": "admin@exafluence.com", "password": "password123"}
        resp = requests.post(login_url, json=login_data)
        token = resp.json().get("access_token")
        
        headers = {"Authorization": f"Bearer {token}"}
        config_url = "http://localhost:5000/api/ai/config"
        resp = requests.get(config_url, headers=headers)
        print(json.dumps(resp.json(), indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_config()
