import requests
import time

urls = [
    "http://localhost:5001/test-debug",
    "http://localhost:5001/api/install-script"
]

time.sleep(2)

for url in urls:
    print(f"Checking {url}...")
    try:
        resp = requests.get(url)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            print("Response: " + resp.text[:100])
        else:
            print("Error: " + resp.text[:100])
    except Exception as e:
        print(f"Exception: {e}")
