
import requests
import json

BASE_URL = "http://localhost:5000/api"

def login():
    response = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "super@omni.ai",
        "password": "password123"
    })
    if response.status_code != 200:
        print("Login failed:", response.text)
        return None
    return response.json()["access_token"]

def verify_historical_data(token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/analytics/historical", headers=headers)
    
    if response.status_code != 200:
        print("Failed to fetch historical data:", response.text)
        return

    data = response.json()
    print(f"DEBUG: Data type is {type(data)}")
    
    if isinstance(data, dict):
        print("KEYS_FOUND:", list(data.keys()))
        if "alerts" in data and "compliance" in data and "vulnerabilities" in data:
            print("VERIFICATION_SUCCESS")
            print(f"Alerts count: {len(data['alerts'])}")
        else:
            print("VERIFICATION_FAILURE: Missing keys")
    else:
        print("FAILURE: Response is not a dictionary.")

if __name__ == "__main__":
    token = login()
    if token:
        verify_historical_data(token)
