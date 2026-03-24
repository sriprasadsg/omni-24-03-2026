import requests
import json

def test_signup():
    url = "http://127.0.0.1:5000/api/auth/signup"
    payload = {
        "companyName": "Final Fix Corp",
        "name": "Fixed Hunter",
        "email": "fixed-bug-final@omni.ai",
        "password": "Password123!"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"Response Body: {json.dumps(data, indent=2)}")
        
        if response.status_code == 200:
            if "access_token" in data and "refresh_token" in data:
                print("SUCCESS: Tokens found in response!")
            else:
                print("FAILURE: Tokens MISSING in response!")
        elif response.status_code == 400:
            print(f"INFO: User likely already exists: {data.get('detail')}")
    except Exception as e:
        print(f"Error during request: {e}")

if __name__ == "__main__":
    test_signup()
