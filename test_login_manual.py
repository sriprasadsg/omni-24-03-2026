import requests
import time

URL = "http://localhost:5001/api/auth/login"
EMAIL = "super@omni.ai"
PASSWORD = "password123"

def test_login():
    payload = {"username": EMAIL, "password": PASSWORD} # FastAPI OAuth2PasswordRequestForm usually expects username/password
    # But wait, looking at the code (I haven't seen the auth endpoint code yet), it might be JSON body with email/password.
    # Let's try both or check the code.
    # checking apiService.ts: body: JSON.stringify({ email, password })
    
    payload_json = {"email": EMAIL, "password": PASSWORD}
    
    try:
        print(f"Attempting login to {URL} with {EMAIL}...")
        response = requests.post(URL, json=payload_json)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("LOGIN SUCCESS!")
        else:
            print("LOGIN FAILED")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_login()
