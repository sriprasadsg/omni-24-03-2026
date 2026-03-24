import requests
BASE_URL = "http://localhost:5000"
creds = {"email": "super@omni.ai", "password": "password123"}
token = requests.post(f"{BASE_URL}/api/auth/login", json=creds).json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

payload = {
    "type": "chatops",
    "platform": "slack",
    "config": {"webhook_url": "https://example.com"}
}
print(f"Sending: {payload}")
resp = requests.post(f"{BASE_URL}/api/integrations/test", json=payload, headers=headers)
print(f"Status: {resp.status_code}")
print(f"Body: {resp.text}")
