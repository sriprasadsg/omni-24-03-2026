import requests
import json

url = "http://localhost:8000/api/auth/signup"
payload = {
    "companyName": "Acme Corp",
    "name": "Admin User",
    "email": "admin@acme.com",
    "password": "Password123"
}
headers = {
    "Content-Type": "application/json"
}

try:
    response = requests.post(url, json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
