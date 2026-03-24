import requests
import json

BASE_URL = "http://localhost:5000"

def run_test():
    print("Starting Data Governance Verification...")
    
    # 1. Login
    print("\n[1] Logging in...")
    try:
        auth = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "testadmin@example.com", 
            "password": "password123"
        })
        if auth.status_code != 200:
            print(f"Login failed: {auth.text}")
            return
            
        token = auth.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("Login successful.")
    except Exception as e:
        print(f"Login connection failed: {e}")
        return

    # 2. Get Data Catalog
    print("\n[2] Fetching Data Catalog...")
    try:
        res = requests.get(f"{BASE_URL}/api/governance/catalog", headers=headers)
        if res.status_code == 200:
            print(f"Catalog: {json.dumps(res.json(), indent=2)}")
        else:
            print(f"Failed to get catalog: {res.text}")
    except Exception as e:
        print(f"Catalog check failed: {e}")

    # 3. PII Scan Test (High Sensitivity)
    print("\n[3] Testing PII Scan (Confidential Data)...")
    try:
        sensitive_data = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "ssn": "999-00-1234",
            "notes": "Top secret"
        }
        res = requests.post(f"{BASE_URL}/api/governance/scan", json=sensitive_data, headers=headers)
        print(f"Scan Result: {json.dumps(res.json(), indent=2)}")
        
        result = res.json()
        if "ssn" in result.get("pii_detected", []) and result.get("classification") == "RESTRICTED":
             print("PASS: Correctly identified SSN and classified as RESTRICTED")
        else:
             print("FAIL: Did not correctly identify SSN or classification")
            
    except Exception as e:
        print(f"PII scan failed: {e}")

    # 4. Quality Report
    print("\n[4] Fetching Quality Report...")
    try:
        res = requests.get(f"{BASE_URL}/api/quality/report", headers=headers)
        print(f"Report: {json.dumps(res.json(), indent=2)}")
    except Exception as e:
        print(f"Report check failed: {e}")

if __name__ == "__main__":
    run_test()
