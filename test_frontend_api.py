"""
Test frontend API call to match exactly what the browser does
"""
import requests
import json

API_BASE = "http://localhost:5000/api"

# Test 1: Exact backend call
print("=" * 60)
print("TEST 1: Direct API Call (simulating Invoke-WebRequest)")
print("=" * 60)

response = requests.post(
    f"{API_BASE}/auth/login",
    headers={"Content-Type": "application/json"},
    json={"email": "super@omni.ai", "password": "password123"}
)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")
print()

# Test 2: With lowercase email (frontend does .strip().lower())
print("=" * 60)
print("TEST 2: With Lowercase Email (as frontend does)")
print("=" * 60)

response2 = requests.post(
    f"{API_BASE}/auth/login",
    headers={"Content-Type": "application/json"},
    json={"email": "super@omni.ai".strip().lower(), "password": "password123"}
)

print(f"Status Code: {response2.status_code}")
print(f"Response: {response2.json()}")
print()

# Test 3: Check database for actual email format
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017')
db = client['omni_platform']

print("=" * 60)
print("TEST 3:  Checking Actual Emails in Database")
print("=" * 60)

users = list(db.users.find({}, {"email": 1, "name": 1, "role": 1}))
for user in users:
    print(f"Email (exact): '{user.get('email')}'")
    print(f"Name: {user.get('name')}")
    print(f"Role: {user.get('role')}")
    print()

print("=" * 60)
print("DIAGNOSIS:")
print("=" * 60)

if response.status_code == 200 and response.json().get('success'):
    print("✅ Backend authentication is WORKING!")
    print("Issue must be in frontend fetch call or response handling")
else:
    print("❌ Backend authentication FAILED")
    print(f"Error: {response.json().get('error')}")
