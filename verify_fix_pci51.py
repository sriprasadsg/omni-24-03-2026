
import sys
import os

# Add agent directory to sys.path
sys.path.append(os.path.join(os.getcwd(), 'agent'))

try:
    from capabilities.compliance import ComplianceEnforcementCapability
    
    print("Instantiating ComplianceEnforcementCapability...")
    # BaseCapability might require init args? Let's assume default or no args based on typical pattern.
    # If it fails, we'll see.
    cap = ComplianceEnforcementCapability()
    
    print("Running collect()...")
    scan_results = cap.collect()
    
    # scan_results should have 'compliance_checks'
    found = False
    for check in scan_results.get('compliance_checks', []):
        if check['check'] == 'Windows Defender Antivirus':
            print(f"Check Found: {check['check']}")
            print(f"Status: {check['status']}")
            print(f"Details: {check['details']}")
            if check['status'] == 'Pass':
                print("✅ TEST PASSED: Check passed.")
                found = True
            else:
                print("❌ TEST FAILED: Check still failed.")
            
            # Print evidence for debugging
            # print("Evidence:", check.get('evidence_content'))
    
    if not found:
        print("❌ TEST FAILED: 'Windows Defender Antivirus' check not found in results.")

except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error during verification: {e}")
    import traceback
    traceback.print_exc()

