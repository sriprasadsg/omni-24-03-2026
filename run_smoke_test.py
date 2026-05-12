import requests
import jwt
import sys
import os

BASE_URL = "http://localhost:5000"

def test_1():
    print("1. Health check")
    r = requests.get(f"{BASE_URL}/api/health")
    r.raise_for_status()
    print(r.json())

def test_2():
    print("\n2. Login")
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email":"super@omni.ai", "password":"password123"})
    r.raise_for_status()
    token = r.json()["access_token"]
    print("Logged in. Token acquired.")
    return token

def test_3(token):
    print("\n3. List attack patterns")
    r = requests.get(f"{BASE_URL}/api/correlations/patterns/list", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    print("Patterns count:", len(r.json()))

def test_4(token):
    print("\n4. List playbooks")
    r = requests.get(f"{BASE_URL}/api/playbooks", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    print("Playbooks count:", len(r.json()))

def test_5(token):
    print("\n5. Check threat feed collection")
    r = requests.get(f"{BASE_URL}/api/threat-intel/feed", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    print("Threat feed entries:", len(r.json()))

def test_6(token):
    print("\n6. Create a security event")
    data = {"event_type":"ransomware_detected","source_ip":"10.0.0.1","severity":"critical","description":"Test"}
    r = requests.post(f"{BASE_URL}/api/security-events", json=data, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    print("Event created:", r.json().get('id', 'No ID'))

def test_7(token):
    print("\n7. Run manual correlation")
    data = {"tenant_id":"platform-admin","time_window_minutes":60}
    r = requests.post(f"{BASE_URL}/api/correlations/run", json=data, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    print("Correlation run finish:", r.json())

def test_8():
    print("\n8. YARA string scan")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))
    from capabilities.yara_scanner import get_yara_scanner
    s = get_yara_scanner()
    print("mimikatz.exe scan:", s.scan_string('mimikatz.exe'))
    print("chrome.exe scan:", s.scan_string('chrome.exe'))

def test_9(token):
    print("\n9. Verify token has jti")
    data = jwt.decode(token, options={'verify_signature':False})
    print('jti present:', 'jti' in data)
    print('role:', data.get('role'))
    assert 'jti' in data

def test_10(token):
    print("\n10. List roles")
    r = requests.get(f"{BASE_URL}/api/roles", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    print("Roles count:", len(r.json()))

if __name__ == "__main__":
    try:
        test_1()
        token = test_2()
        test_3(token)
        test_4(token)
        test_5(token)
        test_6(token)
        test_7(token)
        test_8()
        test_9(token)
        test_10(token)
        print("\nSUCCESS: All Quick Smoke tests passed successfully!")
    except Exception as e:
        print(f"\nFAILURE: Test failed with error {e}")
        sys.exit(1)
