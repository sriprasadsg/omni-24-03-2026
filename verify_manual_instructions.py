
import requests
import json
import sys

BASE_URL = "http://localhost:5000"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbkBleGFmbHVlbmNlLmNvbSIsInJvbGUiOiJUZW5hbnQgQWRtaW4iLCJ0ZW5hbnRfaWQiOiJ0ZW5hbnRfODJkZGEwZjMzYmM0IiwiZXhwIjoxODAxNjkwNjQ1fQ.SJv2EXw-5-BXJQTVpx2C-8h7p_xCpOMxNf0LJraufvU"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def verify_manual_instructions():
    print("Fetching compliance frameworks...")
    try:
        resp = requests.get(f"{BASE_URL}/api/compliance", headers=HEADERS)
        resp.raise_for_status()
        frameworks = resp.json()
        
        found_fedramp = False
        found_ccpa = False
        
        print(f"Found {len(frameworks)} frameworks.")
        
        for fw in frameworks:
            fw_id = fw.get('id')
            print(f"Checking framework: {fw_id}")
            for control in fw.get('controls', []):
                c_id = control.get('id')
                
                if c_id == "fedramp-AC-2":
                    instructions = control.get('manual_evidence_instructions')
                    if instructions:
                        print(f"  [SUCCESS] Found instructions for {c_id}: {instructions[:50]}...")
                        found_fedramp = True
                    else:
                        print(f"  [FAIL] Instructions MISSING for {c_id}")
                        
                if c_id == "ccpa-Privacy-1":
                    instructions = control.get('manual_evidence_instructions')
                    if instructions:
                        print(f"  [SUCCESS] Found instructions for {c_id}: {instructions[:50]}...")
                        found_ccpa = True
                    else:
                        print(f"  [FAIL] Instructions MISSING for {c_id}")

        if found_fedramp and found_ccpa:
            print("\n✅ VERIFICATION SUCCESSFUL: Manual instructions found for both controls.")
            return True
        else:
            print("\n❌ VERIFICATION FAILED: Missing instructions.")
            return False

    except Exception as e:
        print(f"Error checking frameworks: {e}")
        return False

if __name__ == "__main__":
    if verify_manual_instructions():
        sys.exit(0)
    else:
        sys.exit(1)
