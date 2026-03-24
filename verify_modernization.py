import requests
import json
import sys

BASE_URL = "http://localhost:5000/api"

def test_login_hardening():
    print("Testing Login Hardening (Plaintext bypass removal)...")
    payload = {"email": "super@omni.ai", "password": "password123"}
    # This should still work because password123 is the correct hashed password
    resp = requests.post(f"{BASE_URL}/auth/login", json=payload)
    if resp.status_code == 200 and resp.json().get("success"):
        print("✅ Standard login successful.")
    else:
        print(f"❌ Standard login failed: {resp.text}")

    # This should fail even if we try a "bypass" style (if we had one, but we removed the plaintext check)
    # We'll test with a wrong password that definitely isn't the hash
    payload_wrong = {"email": "super@omni.ai", "password": "wrong_password"}
    resp_wrong = requests.post(f"{BASE_URL}/auth/login", json=payload_wrong)
    data = resp_wrong.json()
    if not data.get("success"):
        print("✅ Login correctly rejected wrong password.")
    else:
        print("❌ Login incorrectly accepted password.")

def test_threat_intel_endpoints():
    print("\nTesting Threat Intel Reputation Endpoints...")
    # Get token first
    login_resp = requests.post(f"{BASE_URL}/auth/login", json={"email": "super@omni.ai", "password": "password123"})
    token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Test IP reputation
    resp_ip = requests.get(f"{BASE_URL}/ai/reputation/ip/8.8.8.8", headers=headers)
    if resp_ip.status_code == 200:
        print(f"✅ IP Reputation: {resp_ip.json().get('verdict')}")
    else:
        print(f"❌ IP Reputation failed: {resp_ip.text}")

    # Test Domain reputation
    resp_domain = requests.get(f"{BASE_URL}/ai/reputation/domain/google.com", headers=headers)
    if resp_domain.status_code == 200:
        print(f"✅ Domain Reputation: {resp_domain.json().get('verdict')}")
    else:
        print(f"❌ Domain Reputation failed: {resp_domain.text}")

if __name__ == "__main__":
    test_login_hardening()
    test_threat_intel_endpoints()
