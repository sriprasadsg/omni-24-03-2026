import requests
import json

BASE_URL = "http://localhost:5000/api"

def test_login():
    print("Testing login for super@omni.ai...")
    payload = {
        "email": "super@omni.ai",
        "password": "password123"
    }
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200 and response.json().get("success"):
            print("LOGIN SUCCESS!")
            return response.json().get("access_token") # Wait, does it return access_token?
            # app.py login returns: {"success": True, "user": ..., "tenant": ...}
            # It doesn't seem to return access_token in the login response in app.py?
            # Let's check app.py login response again.
        else:
            print("LOGIN FAILED")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    test_login()
