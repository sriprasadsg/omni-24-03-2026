import urllib.request, json, sys, traceback
from urllib.error import HTTPError

url = "http://127.0.0.1:5000/api/auth/login"
data = {"email": "super@omni.ai", "password": "password123"}
req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})

try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode()[:200])
except HTTPError as e:
    print(f"HTTPError: {e.code}")
    print(e.read().decode())
except Exception as e:
    traceback.print_exc()
