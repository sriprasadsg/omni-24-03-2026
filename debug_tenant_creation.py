import requests
import json

BASE_URL = "http://localhost:5000"

def test_signup():
    print("\n--- Testing /api/auth/signup (Public Registration) ---")
    payload = {
        "companyName": "Test Company Inc",
        "name": "Test User",
        "email": "test@testcompany.com",
        "password": "Password123!" 
    }
    try:
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

def test_create_tenant_admin():
    print("\n--- Testing /api/tenants (Super Admin Creation) ---")
    # First login as super admin to get token (if needed, though app seems to rely on session or just loose auth for now? 
    # Actually, previous analysis showed auth headers might be checked or mocked.
    # Let's verify if POST /api/tenants exists first.
    payload = {
        "name": "Admin Created Tenant",
        "subscriptionTier": "Pro"
    }
    try:
        response = requests.post(f"{BASE_URL}/api/tenants", json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_signup()
    test_create_tenant_admin()
