import requests
import time

url = "http://localhost:5001/"
print(f"Checking {url}...")

try:
    resp = requests.get(url)
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text}")
except Exception as e:
    print(f"Exception: {e}")
