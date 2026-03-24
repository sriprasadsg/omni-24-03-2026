
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'agent'))

try:
    from capabilities.compliance import ComplianceEnforcementCapability
    
    cap = ComplianceEnforcementCapability()
    print("Running collect()...")
    results = cap.collect()
    
    found = False
    for check in results.get('compliance_checks', []):
        if check['check'] == 'Password Complexity':
            print(f"Check Found: {check['check']}")
            print(f"Status: {check['status']}")
            print(f"Details: {check['details']}")
            
            if check['status'] == 'Warning' and "requires Admin" in check['details']:
                print("✅ TEST PASSED: Permission issue handled safely as Warning.")
                found = True
            elif check['status'] == 'Pass':
                print("✅ TEST PASSED: Check passed (Admin likely available).")
                found = True
            else:
                print(f"❌ TEST FAILED: Unexpected status: {check['status']}")
            
    if not found:
        print("❌ TEST FAILED: Check not found.")

except Exception as e:
    print(f"Error: {e}")
