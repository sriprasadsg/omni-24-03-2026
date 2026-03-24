
import logging
import sys
import json
import os

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capabilities.compliance import ComplianceEnforcementCapability

logging.basicConfig(level=logging.INFO)

try:
    print(f"Module file: {ComplianceEnforcementCapability.__module__}")
    import inspect
    print(f"Source file: {inspect.getfile(ComplianceEnforcementCapability)}")
    print("Initializing ComplianceEnforcementCapability...")
    cap = ComplianceEnforcementCapability()
    print("Capability initialized.")
    
    print("Running collect_debug()...")
    if hasattr(cap, "collect_debug"):
        data = cap.collect_debug()
    else:
        print("collect_debug not found, calling collect()")
        data = cap.collect()
    print("Collection complete.")
    
    # Check for specific fields
    checks = data.get("compliance_checks", [])
    print(f"Collected {len(checks)} checks.")
    
    cloud_meta = next((c for c in checks if c["check"] == "Cloud Instance Metadata"), None)
    pii_meta = next((c for c in checks if c["check"] == "PII Data Discovery"), None)
    
    if cloud_meta:
        print(f"Cloud Metadata Check Found: {cloud_meta['status']}")
    else:
        print("Cloud Metadata Check NOT FOUND")
        
    if pii_meta:
        print(f"PII Data Discovery Check Found: {pii_meta['status']}")
    else:
        print("PII Data Discovery Check NOT FOUND")

except Exception as e:
    logging.exception("Failed to run compliance capability")
