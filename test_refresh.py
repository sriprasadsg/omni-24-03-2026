import requests
import json

BASE_URL = "http://localhost:5000/api"

print("=" * 60)
print("Testing Refresh Token Implementation")
print("=" * 60)

# Test 1: Login and get tokens
print("\\n1. Testing login...")
login_response = requests.post(
    f"{BASE_URL}/auth/login",
    json={"email": "super@omni.ai", "password": "password123"}
)

if login_response.status_code == 200:
    login_data = login_response.json()
    if login_data.get("success"):
        access_token = login_data.get("access_token")
        refresh_token = login_data.get("refresh_token")
        
        print("SUCCESS: Login successful")
        print(f"  Access token: {access_token[:20] if access_token else 'MISSING'}...")
        print(f"  Refresh token: {refresh_token[:20] if refresh_token else 'MISSING'}...")
        
        if not refresh_token:
            print("ERROR: Refresh token not returned by login endpoint!")
        else:
            # Test 2: Use refresh token to get new access token
            print("\\n2. Testing refresh token endpoint...")
            refresh_response = requests.post(
                f"{BASE_URL}/auth/refresh",
                json={"refresh_token": refresh_token}
            )
            
            if refresh_response.status_code == 200:
                refresh_data = refresh_response.json()
                if refresh_data.get("success") and refresh_data.get("access_token"):
                    new_access_token = refresh_data.get("access_token")
                    print("SUCCESS: Token refresh successful")
                    print(f"  New access token: {new_access_token[:20]}...")
                else:
                    print("ERROR: Refresh endpoint returned invalid data")
                    print(f"  Response: {refresh_data}")
            else:
                print(f"ERROR: Refresh endpoint returned status {refresh_response.status_code}")
                print(f"  Response: {refresh_response.text}")
    else:
        print("ERROR: Login response success=false")
else:
    print(f"ERROR: Login failed with status {login_response.status_code}")
    print(f"Response: {login_response.text}")

print("\\n" + "=" * 60)
print("Test Complete")
print("=" * 60)
