import requests
import sys

URL = "http://localhost:3000/health"

try:
    print(f"Checking {URL} (Frontend Proxy)...")
    # Timeout after 3 seconds
    response = requests.get(URL, timeout=3)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200 and "backend-fastapi" in response.text:
        print("PROXY SUCCESS: Backend reachable via Frontend!")
    else:
        print("PROXY FAIL: Backend not reachable or wrong response.")

except Exception as e:
    print(f"Error: {e}")
