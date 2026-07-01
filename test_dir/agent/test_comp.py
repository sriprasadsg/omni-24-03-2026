import json
import sys
import os

# Add parent directory to path to import agent modules
sys.path.insert(0, os.path.abspath('.'))

try:
    from capabilities.compliance import ComplianceEnforcementCapability
    
    cap = ComplianceEnforcementCapability()
    result = cap.collect()
    
    with open('compliance_test_output.json', 'w') as f:
        json.dump(result, f, indent=4)
        
    print(f"Successfully ran compliance checks. Total checks: {result.get('total_checks')}")
    print(f"Passed: {result.get('passed')}, Failed: {result.get('failed')}")
except Exception as e:
    print(f"Error: {e}")
