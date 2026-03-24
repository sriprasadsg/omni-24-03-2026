import json
import urllib.request
import urllib.error
import sys

BASE_URL = "http://localhost:5001/api"

def login(email, password):
    url = f"{BASE_URL}/auth/login"
    data = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                body = json.loads(response.read().decode("utf-8"))
                return body.get("access_token")
            else:
                print(f"Login failed: {response.status}")
                return None
    except urllib.error.HTTPError as e:
        print(f"Login error: {e.code} - {e.read()}")
        return None
    except Exception as e:
        print(f"Login exception: {e}")
        return None

def get_tenants(token):
    url = f"{BASE_URL}/tenants"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                body = json.loads(response.read().decode("utf-8"))
                return body
            else:
                print(f"Get Tenants failed: {response.status}")
                return None
    except Exception as e:
        print(f"Get Tenants exception: {e}")
        return None

def verify():
    print("1. Logging in as Admin...")
    token = login("admin@example.com", "admin123")
    if not token:
        print("[X] Failed to get access token.")
        sys.exit(1)
    print("[OK] Login successful. Token obtained.")

    print("\n2. Fetching Tenants Data from API...")
    tenants = get_tenants(token)
    if not tenants:
        print("[X] Failed to fetch tenants.")
        sys.exit(1)
    
    print(f"[OK] Fetched {len(tenants)} tenants.")
    
    found_dpdp_cost = False
    
    for tenant in tenants:
        if tenant['id'] == 'platform-admin':
            continue

        print(f"Checking Tenant: {tenant.get('name')} ({tenant['id']})")
        # print(f"   Keys: {list(tenant.keys())}") 
            
        finops = tenant.get('finOpsData') or tenant.get('finopsData')
        if not finops:
            print("   [WARN] No finOpsData/finopsData in API response object.")
            print(f"   Keys available: {list(tenant.keys())}")
            continue
            
        # Check for ALL 8 new frameworks
        breakdown = finops.get('costBreakdown', [])
        services = [item.get('service', '') for item in breakdown]
        
        expected_frameworks = [
            "Compliance: CIS Benchmarks",
            "Compliance: CSA STAR",
            "Compliance: ISO 22301",
            "Compliance: SOC 1",
            "Compliance: FedRAMP",
            "Compliance: CMMC",
            "Compliance: SOX",
            "Compliance: COBIT"
        ]
        
        missing = [fw for fw in expected_frameworks if fw not in services]
        
        if not missing:
            print(f"\n[SUCCESS] Tenant '{tenant.get('name')}' has ALL 8 compliance frameworks.")
            for fw in expected_frameworks:
                print(f"   ✅ {fw}")
            found_dpdp_cost = True
        else:
            print(f"\n[PARTIAL] Tenant '{tenant.get('name')}' missing: {missing}")
            print(f"   Found: {[s for s in services if 'Compliance' in s]}")
                
    if found_dpdp_cost:
        print("\n[PASS] API Verification PASSED: Backend is serving compliance costs to frontend.")
    else:
        print("\n[FAIL] API Verification FAILED: No DPDP costs found in API response.")
        sys.exit(1)

if __name__ == "__main__":
    verify()
