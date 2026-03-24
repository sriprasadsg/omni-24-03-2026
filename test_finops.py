import requests
import json

BASE_URL = "http://localhost:5000"

def run_test():
    print("Starting FinOps Verification...")
    
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

    # 2. Check Cost Snapshot
    print("\n[2] Checking Cost Snapshot...")
    try:
        res = requests.get(f"{BASE_URL}/api/finops/costs", headers=headers)
        if res.status_code == 200:
            data = res.json()
            print(f"Total Spend: ${data['snapshot']['total_spend']}")
            print(f"Forecast: ${data['forecast']['forecast_total']}")
            print(f"Status: {data['forecast']['status']}")
            
            if len(data['history']) == 30:
                print("PASS: Retrieved 30-day cost history")
            else:
                print("FAIL: History length incorrect")
        else:
            print(f"Failed to get costs: {res.text}")
    except Exception as e:
        print(f"Cost check failed: {e}")

    # 3. Check Recommendations
    print("\n[3] Fetching Optimization Recommendations...")
    try:
        res = requests.get(f"{BASE_URL}/api/finops/recommendations", headers=headers)
        if res.status_code == 200:
            recs = res.json()
            print(f"Found {len(recs)} specific recommendations.")
            for rec in recs:
                print(f"- [{rec['severity']}] {rec['type']}: ${rec['potential_savings']} savings")
        else:
             print(f"Failed to get recommendations: {res.text}")
    except Exception as e:
        print(f"Recommendations check failed: {e}")

if __name__ == "__main__":
    run_test()
