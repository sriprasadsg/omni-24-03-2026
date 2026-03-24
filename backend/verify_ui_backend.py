import requests
import json
import sys

BASE_URL = "http://localhost:5000/api"
LOGIN_URL = f"{BASE_URL}/auth/login"

USERNAME = "super@omni.ai"
PASSWORD = "password123"

def print_result(feature, status, message=""):
    icon = "OK" if status == "PASS" else "FAIL"
    print(f"[{icon}] {feature}: {message}")

def login():
    try:
        response = requests.post(LOGIN_URL, json={"email": USERNAME, "password": PASSWORD})
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return data.get("access_token")
    except Exception as e:
        print(f"Login failed: {e}")
    return None

def verify_endpoint(token, endpoint, feature_name):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(f"{BASE_URL}/{endpoint}", headers=headers)
        if response.status_code == 200:
            count = 0
            data = response.json()
            if isinstance(data, list):
                count = len(data)
            print_result(feature_name, "PASS", f"Status 200, Items: {count}")
            return True
        else:
            print_result(feature_name, "FAIL", f"Status {response.status_code}")
            return False
    except Exception as e:
        print_result(feature_name, "FAIL", f"Exception: {e}")
        return False

def main():
    print("Starting Backend API Verification for UI Features...")
    
    # 1. Login
    token = login()
    if not token:
        print_result("Authentication", "FAIL", "Could not get token")
        sys.exit(1)
    print_result("Authentication", "PASS", "Logged in as Super Admin")

    # 2. Verify Features
    endpoints = [
        ("agents", "Agents Dashboard"),
        ("assets", "Asset Management"),
        ("compliance", "Compliance Dashboard"),
        ("security-events", "Security Dashboard"),
        ("alerts", "Alerts & Notifications"),
        ("tenants", "Tenant Management"),
        ("users", "User Management"),
        ("logs", "Log Explorer"),
        ("integrations/list", "Settings: Integrations"),
        ("roles", "Settings: Roles"),
        ("sast/statistics", "DevSecOps (SAST)"),
        ("sboms", "SBOM Management")
    ]

    success_count = 0
    for endpoint, name in endpoints:
        if verify_endpoint(token, endpoint, name):
            success_count += 1
            
    print(f"\nVerification Complete: {success_count}/{len(endpoints)} features Verified.")

if __name__ == "__main__":
    main()
