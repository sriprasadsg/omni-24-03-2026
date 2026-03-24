import requests
import json
import sys

BASE_URL = "http://localhost:5000/api"

def test_endpoint(name, method, path, data=None, headers=None):
    url = f"{BASE_URL}{path}"
    print(f"Testing {name} ({method} {path})...", end=" ")
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=5)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers, timeout=5)
        
        if response.status_code in [200, 201, 302, 307]:
            print(f"PASSED ({response.status_code})")
            return response.json() if response.status_code in [200, 201] else True
        else:
            print(f"FAILED ({response.status_code})")
            print(f"  Response: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def main():
    # 1. Login to get token
    login_data = {"email": "super@omni.ai", "password": "password123"}
    login_resp = test_endpoint("Login", "POST", "/auth/login", data=login_data)
    if not login_resp:
        print("Could not login. Skipping other tests.")
        return

    token = login_resp.get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Test Phase 1 (AI Chat) - Only checking config as we don't have keys
    test_endpoint("AI Config", "GET", "/ai/config", headers=headers)
    
    # 3. Test Phase 3 (Billing/Invoices)
    test_endpoint("List Invoices", "GET", "/billing/invoices", headers=headers)
    
    # 4. Test Phase 4 (SSO Status)
    test_endpoint("SSO Providers", "GET", "/sso/providers")
    
    # 5. Test Phase 8 (Voice Status)
    test_endpoint("Voice Status", "GET", "/voice/status", headers=headers)
    
    # 6. Test Phase 9 (Agent Metrics - Static Check)
    # We use a dummy ID just to see if the router responds
    test_endpoint("Agent Metrics Current", "GET", "/agents/dummy-agent-id/metrics/current", headers=headers)

if __name__ == "__main__":
    main()
