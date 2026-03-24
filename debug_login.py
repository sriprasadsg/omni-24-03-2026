import requests
import json

URL = "http://localhost:5000/api/auth/login"
PAYLOAD = {
    "email": "super@omni.ai",
    "password": "password123"
}

print(f"Testing Login API: {URL}")
print(f"Payload: {PAYLOAD}")

try:
    response = requests.post(URL, json=PAYLOAD)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response Headers: {response.headers}")
    print(f"Response Body: {response.text}")
    
    if response.status_code == 200 and response.json().get("success"):
        print("\n[OK] LOGIN SUCCESSFUL (Backend verified)")
    else:
        print("\n[FAIL] LOGIN FAILED")
except Exception as e:
    print(f"\n[FAIL] EXCEPTION: {e}")
