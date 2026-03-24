import requests
import json

BASE_URL = "http://localhost:5000"

def verify():
    # 1. Login
    login_url = f"{BASE_URL}/api/auth/login"
    creds = {
        "email": "super@omni.ai",
        "password": "password123"
    }
    
    print(f"Logging in as {creds['email']}...")
    try:
        resp = requests.post(login_url, json=creds)
        data = resp.json()
    except Exception as e:
        print(f"Login failed to connect: {e}")
        return

    if not data.get("success"):
        print(f"Login failed: {data}")
        return

    token = data["access_token"]
    tenant_id = data["user"]["tenantId"]
    print(f"Login Success. Token obtained. Tenant: {tenant_id}")

    # 2. Get Vulnerabilities
    vuln_url = f"{BASE_URL}/api/vulnerabilities"
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"Fetching vulnerabilities from {vuln_url}...")
    resp = requests.get(vuln_url, headers=headers)
    
    if resp.status_code != 200:
        print(f"Error fetching vulns: {resp.status_code} - {resp.text}")
        return

    vulns = resp.json()
    print(f"Vulnerabilities found: {len(vulns)}")
    for v in vulns:
        print(f" - {v.get('cveId')} ({v.get('severity')}) [Status: {v.get('status')}]")
        
    if len(vulns) == 0:
        print("WARNING: No vulnerabilities returned!")

if __name__ == "__main__":
    verify()
