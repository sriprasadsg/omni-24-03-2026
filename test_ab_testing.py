import requests
import json
import uuid

BASE_URL = "http://localhost:5000"

def run_test():
    print("Starting A/B Testing Verification...")
    
    # 1. Login
    try:
        auth = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "testadmin@example.com", 
            "password": "password123"
        })
        token = auth.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("[1] Login successful.")
    except Exception as e:
        print(f"Login failed: {e}")
        return

    # 2. Create Experiment
    print("\n[2] Creating Experiment 'Checkout Redesign'...")
    try:
        exp_data = {
            "name": "Checkout Redesign",
            "description": "Button color vs Text color",
            "variants": ["Control", "Treatment"]
        }
        res = requests.post(f"{BASE_URL}/api/experiments", json=exp_data, headers=headers)
        exp_id = res.json()["experiment_id"]
        print(f"Experiment Created: {exp_id}")
    except Exception as e:
        print(f"Creation failed: {e}")
        return

    # 3. Check Deterministic Assignment
    print("\n[3] Checking Deterministic Assignment...")
    user_a = "user-123"
    try:
        res1 = requests.get(f"{BASE_URL}/api/experiments/{exp_id}/variant?user_id={user_a}")
        var1 = res1.json()["variant"]
        print(f"User {user_a} assigned to: {var1}")
        
        # Check again
        res2 = requests.get(f"{BASE_URL}/api/experiments/{exp_id}/variant?user_id={user_a}")
        var2 = res2.json()["variant"]
        
        if var1 == var2:
            print("PASS: Assignment is consistent.")
        else:
            print(f"FAIL: Inconsistent assignment ({var1} vs {var2})")
    except Exception as e:
        print(f"Assignment check failed: {e}")

    # 4. Simulate Traffic & Track Conversions
    print("\n[4] Simulating Traffic (50 users)...")
    try:
        control_conv = 0
        treatment_conv = 0
        
        for i in range(50):
            uid = f"sim-user-{i}"
            # Assign
            v_res = requests.get(f"{BASE_URL}/api/experiments/{exp_id}/variant?user_id={uid}").json()
            variant = v_res["variant"]
            
            # Simulate Treatment converting more often
            should_convert = False
            if variant == "Treatment":
                should_convert = (i % 2 == 0) # 50% conversion
            else:
                should_convert = (i % 4 == 0) # 25% conversion
                
            if should_convert:
                requests.post(f"{BASE_URL}/api/experiments/{exp_id}/track", json={"user_id": uid})
    
        # Get Results
        res_stats = requests.get(f"{BASE_URL}/api/experiments/{exp_id}/results", headers=headers).json()
        print("\nResults:")
        for r in res_stats["data"]:
            print(f"- {r['variant']}: {r['conversions']}/{r['impressions']} ({r['conversion_rate']*100}%) [Lift: {r.get('lift', 0)*100}%]")
            
        print("PASS: Traffic tracked and results calculated.")
            
    except Exception as e:
        print(f"Simulation failed: {e}")

if __name__ == "__main__":
    run_test()
