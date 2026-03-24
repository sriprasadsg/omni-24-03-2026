import requests
import time
import json

BASE_URL = "http://localhost:5000/api"

def run_verification():
    print("🚀 Starting Audit & Rollback Verification...")
    
    # 1. Get Initial State
    print("\n1. Fetching Automation Policies...")
    res = requests.get(f"{BASE_URL}/automation-policies")
    if res.status_code != 200:
        print(f"❌ Failed to fetch policies: {res.text}")
        return
    policies = res.json()
    if not policies:
        print("⚠️ No policies found. Creating a test policy...")
        # Create a dummy policy if needed (but usually seeded)
        test_policy = {
            "id": "policy-test-safe",
            "name": "Test Safe Policy",
            "description": "Safe to modify",
            "trigger": "agent.error",
            "action": "remediate.agent",
            "isEnabled": True
        }
        res = requests.put(f"{BASE_URL}/automation-policies", json=test_policy)
        policies = [test_policy]
    
    target_policy = policies[0]
    original_name = target_policy.get("name")
    policy_id = target_policy.get("id")
    print(f"   Target Policy: {original_name} ({policy_id})")

    # 2. Make a Change
    print(f"\n2. Modifying Policy Name to '{original_name} - MODIFIED'...")
    target_policy["name"] = f"{original_name} - MODIFIED"
    res = requests.put(f"{BASE_URL}/automation-policies", json=target_policy)
    if res.status_code != 200:
        print(f"❌ Modification failed: {res.text}")
        return
    print("   ✅ Modification applied.")

    # 3. Verify Log Exists
    print("\n3. Checking Audit Logs...")
    time.sleep(1) # Allow log to persist (in-memory is fast but good practice)
    res = requests.get(f"{BASE_URL}/audit/logs")
    logs = res.json()
    
    # Find our log
    audit_log = next((l for l in logs if l["resourceId"] == policy_id and l["action"] == "update.policy"), None)
    if not audit_log:
        print("❌ Audit Log NOT found!")
        return
    print(f"   ✅ Found Audit Log: {audit_log['id']} - {audit_log['details']}")
    
    # 4. Rollback
    print(f"\n4. Triggering Rollback for Log ID: {audit_log['id']}...")
    res = requests.post(f"{BASE_URL}/audit/rollback/{audit_log['id']}")
    if res.status_code != 200:
        print(f"❌ Rollback failed: {res.text}")
        return
    print("   ✅ Rollback request successful.")

    # 5. Verify Restoration
    print("\n5. Verifying State Restoration...")
    res = requests.get(f"{BASE_URL}/automation-policies")
    current_policies = res.json()
    restored_policy = next((p for p in current_policies if p["id"] == policy_id), None)
    
    if restored_policy["name"] == original_name:
        print(f"   ✅ SUCCESS! Policy name restored to '{original_name}'.")
    else:
        print(f"   ❌ FAILED! Name is '{restored_policy['name']}', expected '{original_name}'.")

if __name__ == "__main__":
    run_verification()
