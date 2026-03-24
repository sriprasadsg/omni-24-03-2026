import requests
import json
import time

BASE_URL = "http://localhost:5000/api"

def verify_zero_trust():
    print("--- Verifying Zero Trust & Quantum Security ---")
    
    # 1. Device Trust Scores
    try:
        print("1. Checking Device Trust Scores...")
        res = requests.get(f"{BASE_URL}/zero-trust/device-trust-scores")
        if res.status_code == 200:
            devices = res.json()
            print(f"   -> Success: Retrieved {len(devices)} devices.")
            if len(devices) > 0:
                print(f"   -> Sample: {devices[0]['deviceId']} Score: {devices[0]['score']}")
        else:
             print(f"   -> Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"   -> Error: {e}")

    # 2. Session Risks
    try:
        print("\n2. Checking Session Risks (UEBA)...")
        res = requests.get(f"{BASE_URL}/zero-trust/session-risks")
        if res.status_code == 200:
            sessions = res.json()
            print(f"   -> Success: Retrieved {len(sessions)} active sessions.")
            high_risk = [s for s in sessions if s['riskScore'] > 70]
            print(f"   -> High Risk Sessions: {len(high_risk)}")
        else:
             print(f"   -> Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"   -> Error: {e}")

    # 3. Cryptographic Inventory
    try:
        print("\n3. Checking Quantum-Safe Inventory...")
        res = requests.get(f"{BASE_URL}/quantum-security/cryptographic-inventory")
        if res.status_code == 200:
            inventory = res.json()
            vulnerable = [i for i in inventory if i['quantumVulnerable']]
            print(f"   -> Success: Retrieved {len(inventory)} algorithms.")
            print(f"   -> Quantum Vulnerable: {len(vulnerable)} (e.g., {vulnerable[0]['algorithm']})")
        else:
             print(f"   -> Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"   -> Error: {e}")

if __name__ == "__main__":
    verify_zero_trust()
