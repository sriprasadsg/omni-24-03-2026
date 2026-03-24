import requests
import json
import time

BASE_URL = "http://localhost:5000/api/digital_twin"

def verify_simulation():
    print("--- Verifying Digital Twin Simulation ---")
    
    # 1. Check Twin State
    try:
        print("1. Checking Digital Twin State...")
        res = requests.get(f"{BASE_URL}/state")
        if res.status_code == 200:
            print(f"   -> Success: {res.json()}")
        else:
            print(f"   -> Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"   -> Error: {e}")
        return

    # 2. Run Simulation (Patch)
    try:
        print("\n2. Running 'Patch' Simulation...")
        payload = {
            "action_type": "patch",
            "target_id": "global",
            "details": "Deploy KB2026-Security-Fix to all Windows Servers"
        }
        res = requests.post(f"{BASE_URL}/simulate", json=payload)
        if res.status_code == 200:
            data = res.json()
            print("   -> Success:")
            print(f"      - Probability: {data['success_probability']}%")
            print(f"      - Impact Score: {data['impact_score']}/100")
            print(f"      - Conflicts: {data['conflicts']}")
        else:
             print(f"   -> Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"   -> Error: {e}")

    # 3. Run Simulation (Risky Firewall Logic)
    try:
        print("\n3. Running 'Risky Firewall' Simulation...")
        payload = {
            "action_type": "firewall_rule",
            "target_id": "firewall-01",
            "details": "Allow all traffic on port 22"
        }
        res = requests.post(f"{BASE_URL}/simulate", json=payload)
        if res.status_code == 200:
            data = res.json()
            print("   -> Success:")
            print(f"      - Compliance: {data['compliance_check']}")
            print(f"      - Conflicts: {data['conflicts']}")
        else:
             print(f"   -> Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"   -> Error: {e}")

if __name__ == "__main__":
    verify_simulation()
