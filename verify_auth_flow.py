import requests
import time

BASE_URL = "http://localhost:5000/api"

def test_auth():
    print("Testing Authentication Flow...")
    
    # 1. Test Login (Success) - using default created user 'demo' or 'super@omni.ai'
    # Need to check create_test_user.py to see what users exist.
    # Usually 'admin' / 'admin123' or similar. 
    # Let's try to register or use known creds.
    
    # app.py seeds: user@enterprise.com / user123 (hashed?)
    # or admin@enterprise.com / admin123
    
    username = "testadmin@example.com" 
    password = "TestPass123!" 
    
    print(f"Attempting login as {username}...")
    try:
        data = {
            "username": username,
            "password": password
        }
        res = requests.post(f"{BASE_URL}/auth/login", json=data) # requests.post(json=...) sets Content-Type: application/json
        
        if res.status_code == 200:
            token_data = res.json()
            print(f"✅ Login Successful! Data: {token_data}")
            access_token = token_data['access_token']
        else:
            print(f"❌ Login Failed: {res.status_code}")
            print(f"Response Body: {res.text}")
            return
            
        # 2. Test Protected Endpoint (/me)
        print("Testing /auth/me with token...")
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get(f"{BASE_URL}/auth/me", headers=headers)
        if resp.status_code == 200:
            print(f"✅ /me Verified: {resp.json()}")
        else:
            print(f"❌ /me Failed: {resp.status_code} - {resp.text}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_auth()
