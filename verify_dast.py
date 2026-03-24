import requests
import json
import sys

BASE_URL = "http://localhost:5000/api/dast"

def verify_dast():
    print(f"Testing DAST Endpoints at {BASE_URL}...")
    
    # 1. Get Scans
    try:
        response = requests.get(f"{BASE_URL}/scans")
        if response.status_code == 200:
            scans = response.json()
            print("\n[SUCCESS] GET /scans")
            print(f"Count: {len(scans)}")
            if len(scans) > 0:
                print(json.dumps(scans[0], indent=2))
        else:
            print(f"\n[FAILURE] GET /scans - Status: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"\n[ERROR] GET /scans: {e}")

    # 2. Start Scan
    target = {"url": "https://test.app.internal"}
    try:
        response = requests.post(f"{BASE_URL}/scans", json=target)
        if response.status_code == 200:
            new_scan = response.json()
            print("\n[SUCCESS] POST /scans")
            print(json.dumps(new_scan, indent=2))
            
            # 3. Get Scan Details
            scan_id = new_scan['id']
            detail_res = requests.get(f"{BASE_URL}/scans/{scan_id}")
            if detail_res.status_code == 200:
                print(f"\n[SUCCESS] GET /scans/{scan_id}")
            else:
                 print(f"\n[FAILURE] GET /scans/{scan_id} - Status: {detail_res.status_code}")

        else:
            print(f"\n[FAILURE] POST /scans - Status: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"\n[ERROR] POST /scans: {e}")

    # 4. Get Findings
    try:
        response = requests.get(f"{BASE_URL}/findings")
        if response.status_code == 200:
             findings = response.json()
             print("\n[SUCCESS] GET /findings")
             print(f"Count: {len(findings)}")
        else:
            print(f"\n[FAILURE] GET /findings - Status: {response.status_code}")
    except Exception as e:
         print(f"\n[ERROR] GET /findings: {e}")

if __name__ == "__main__":
    verify_dast()
