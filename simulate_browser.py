import asyncio
import json
import urllib.request
import urllib.parse

# Config
BASE_URL = "http://127.0.0.1:5001"  # Backend URL (Test Port)
LOGIN_URL = f"{BASE_URL}/api/auth/login"
TENANTS_URL = f"{BASE_URL}/api/tenants"

async def simulate_browser_check():
    print("--- Simulating Browser Verification of FinOps Dashboard ---")
    
    # 1. Login (Simulate user entering credentials)
    print("Step 1: Logging in as admin@example.com...")
    login_data = json.dumps({"username": "admin@example.com", "password": "admin123"}).encode('utf-8')
    req = urllib.request.Request(LOGIN_URL, data=login_data, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req) as response:
            auth_resp = json.loads(response.read().decode())
            token = auth_resp.get("access_token")
            print("   [OK] Login successful. Access Token acquired.")
    except Exception as e:
        print(f"   [FAIL] Login failed: {e}")
        return

    # 2. Fetch Dashboard Data (Simulate dashboard loading)
    print("\nStep 2: Loading Dashboard Data (Tenants)...")
    headers = {'Authorization': f'Bearer {token}'}
    req = urllib.request.Request(TENANTS_URL, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            tenants = json.loads(response.read().decode())
            print(f"   [OK] Loaded {len(tenants)} tenants.")
    except Exception as e:
        print(f"   [FAIL] Failed to load dashboard data: {e}")
        return

    # 3. verify Content (Simulate user inspecting the table)
    print("\nStep 3: Inspecting 'Detailed Cost Breakdown' Table...")
    
    expected_rows = [
        "Compliance: CIS Benchmarks",
        "Compliance: CSA STAR", 
        "Compliance: ISO 22301",
        "Compliance: SOC 1",
        "Compliance: FedRAMP", 
        "Compliance: CMMC", 
        "Compliance: SOX", 
        "Compliance: COBIT"
    ]
    
    found_any = False
    for tenant in tenants:
        finops = tenant.get("finOpsData") or tenant.get("finopsData")
        if not finops: continue
        
        breakdown = finops.get("costBreakdown", [])
        services = [item["service"] for item in breakdown]
        
        if any(fw in services for fw in expected_rows):
            print(f"   [FOUND] Tenant '{tenant['name']}' has compliance data.")
            print("   ------------------------------------------------")
            print("   | Service Name                     | Status    |")
            print("   |----------------------------------|-----------|")
            for fw in expected_rows:
                status = "✅ Visible" if fw in services else "❌ Missing"
                print(f"   | {fw:<32} | {status:<9} |")
            print("   ------------------------------------------------")
            found_any = True
            break
            
    if found_any:
        print("\n[SUCCESS] Browser simulation confirms data is available for rendering.")
    else:
        print("\n[FAIL] No compliance data found in dashboard payload.")

if __name__ == "__main__":
    asyncio.run(simulate_browser_check())
