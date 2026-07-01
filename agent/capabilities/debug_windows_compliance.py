import sys
import os
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from agent.capabilities.compliance import ComplianceEnforcementCapability

def run_checks():
    print("Initializing Compliance Capability...")
    cap = ComplianceEnforcementCapability(config={})
    
    print("Running collect()...")
    result = cap.collect()
    
    # Validation Code
    print("\n" + "="*50)
    print("VALIDATION SUMMARY")
    print("="*50)
    checks = result.get("compliance_checks", [])
    issues = []
    
    for check in checks:
        name = check['check']
        status = check['status']
        evidence = check.get('evidence_content', '')
        
        # Check 1: Is Evidence Present?
        if not evidence:
            issues.append(f"[{name}] MISSING EVIDENCE CONTENT")
        
        # Check 2: Is Evidence a "Simulation"?
        if "Simulated Fix" in check.get('details', '') or "Simulated Fix" in evidence:
             issues.append(f"[{name}] DETECTED SIMULATED/FAKE DATA")
             
        # Check 3: Error state?
        if status == "Error":
             issues.append(f"[{name}] EXECUTION ERROR: {check.get('details')}")

    if issues:
        print(f"FOUND {len(issues)} ISSUES:")
        for i in issues:
            print(" - " + i)
    else:
        print("SUCCESS: No structural issues or simulations found.")
        print(f"Verified {len(checks)} checks.")

if __name__ == "__main__":
    run_checks()
