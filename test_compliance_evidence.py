import requests
import json
import time
from datetime import datetime

print("="*80)
print("COMPLIANCE EVIDENCE COLLECTION TEST")
print("="*80)
print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# Wait for backend to be ready
print("⏳ Waiting for backend to be ready...")
max_retries = 5
for i in range(max_retries):
    try:
        health = requests.get('http://localhost:5000/health', timeout=5)
        if health.status_code == 200:
            print("✅ Backend is ready!\n")
            break
    except:
        if i < max_retries - 1:
            print(f"   Attempt {i+1}/{max_retries} failed, retrying...")
            time.sleep(2)
        else:
            print("❌ Backend not responding. Please ensure it's running.")
            exit(1)

# Get asset data
print("📡 Fetching compliance data from agent EILT0197...")
try:
    response = requests.get('http://localhost:5000/api/assets/agent-EILT0197', timeout=10)
    
    if response.status_code != 200:
        print(f"❌ Error: HTTP {response.status_code}")
        print(response.text)
        exit(1)
    
    asset_data = response.json()
    compliance_data = asset_data.get('meta', {}).get('compliance_enforcement', {})
    
    if not compliance_data:
        print("⚠️  No compliance data found yet. Agent may need more time to collect data.")
        print("   Please wait 60-90 seconds and run this test again.")
        exit(0)
    
    print("✅ Compliance data retrieved!\n")
    
    # Display Summary
    print("="*80)
    print("COMPLIANCE SUMMARY")
    print("="*80)
    print(f"Total Checks: {compliance_data.get('total_checks', 0)}")
    print(f"Passed: {compliance_data.get('passed', 0)}")
    print(f"Failed: {compliance_data.get('failed', 0)}")
    print(f"Compliance Score: {compliance_data.get('compliance_score', 0)}%")
    print()
    
    # Display All Checks
    checks = compliance_data.get('compliance_checks', [])
    
    if not checks:
        print("⚠️  No individual checks found.")
        exit(0)
    
    print("="*80)
    print(f"DETAILED CHECK RESULTS ({len(checks)} checks)")
    print("="*80)
    
    # Group by status
    passed = [c for c in checks if c.get('status') == 'Pass']
    failed = [c for c in checks if c.get('status') == 'Fail']
    warnings = [c for c in checks if c.get('status') == 'Warning']
    errors = [c for c in checks if c.get('status') == 'Error']
    unknown = [c for c in checks if c.get('status') not in ['Pass', 'Fail', 'Warning', 'Error']]
    
    # Display Passed Checks
    if passed:
        print(f"\n✅ PASSED CHECKS ({len(passed)}):")
        print("-" * 80)
        for i, check in enumerate(passed, 1):
            print(f"{i}. {check.get('check', 'Unknown')}")
            print(f"   Details: {check.get('details', 'N/A')}")
    
    # Display Failed Checks
    if failed:
        print(f"\n❌ FAILED CHECKS ({len(failed)}):")
        print("-" * 80)
        for i, check in enumerate(failed, 1):
            print(f"{i}. {check.get('check', 'Unknown')}")
            print(f"   Details: {check.get('details', 'N/A')}")
    
    # Display Warning Checks
    if warnings:
        print(f"\n⚠️  WARNING CHECKS ({len(warnings)}):")
        print("-" * 80)
        for i, check in enumerate(warnings, 1):
            print(f"{i}. {check.get('check', 'Unknown')}")
            print(f"   Details: {check.get('details', 'N/A')}")
    
    # Display Error Checks
    if errors:
        print(f"\n🔴 ERROR CHECKS ({len(errors)}):")
        print("-" * 80)
        for i, check in enumerate(errors, 1):
            print(f"{i}. {check.get('check', 'Unknown')}")
            print(f"   Details: {check.get('details', 'N/A')}")
    
    # Display Unknown Status
    if unknown:
        print(f"\n❓ UNKNOWN STATUS ({len(unknown)}):")
        print("-" * 80)
        for i, check in enumerate(unknown, 1):
            print(f"{i}. {check.get('check', 'Unknown')}")
            print(f"   Status: {check.get('status', 'N/A')}")
            print(f"   Details: {check.get('details', 'N/A')}")
    
    # Phase 1 Verification
    print("\n" + "="*80)
    print("PHASE 1 NEW CHECKS VERIFICATION")
    print("="*80)
    
    phase1_checks = [
        "Maximum Password Age",
        "Account Lockout Policy",
        "Password Complexity",
        "Password History",
        "Minimum Password Age",
        "Remote Desktop Service",
        "SMBv1 Protocol Disabled",
        "LLMNR/NetBIOS Protection",
        "PowerShell Script Block Logging",
        "WinRM Service Status",
        "Credential Guard",
        "Device Guard/WDAC",
        "Exploit Protection (DEP/ASLR)",
        "Attack Surface Reduction",
        "Controlled Folder Access"
    ]
    
    check_names = [c.get('check', '') for c in checks]
    found_phase1 = []
    missing_phase1 = []
    
    for phase1_check in phase1_checks:
        if any(phase1_check in name for name in check_names):
            found_phase1.append(phase1_check)
        else:
            missing_phase1.append(phase1_check)
    
    print(f"\n✅ Phase 1 Checks Found: {len(found_phase1)}/15")
    if found_phase1:
        for check in found_phase1:
            print(f"   ✓ {check}")
    
    if missing_phase1:
        print(f"\n⚠️  Phase 1 Checks Not Found: {len(missing_phase1)}/15")
        for check in missing_phase1:
            print(f"   ✗ {check}")
    
    # Final Assessment
    print("\n" + "="*80)
    print("ASSESSMENT")
    print("="*80)
    
    expected_total = 36 if 'Windows' in asset_data.get('asset', {}).get('os', '') else 8
    actual_total = len(checks)
    
    if actual_total >= expected_total:
        print(f"✅ SUCCESS: All {actual_total} compliance checks are being collected!")
        print(f"   Phase 1 implementation is working correctly.")
    elif actual_total >= 16:
        print(f"⚠️  PARTIAL: {actual_total} checks collected (expected {expected_total})")
        print(f"   Some Phase 1 checks may still be initializing.")
    else:
        print(f"❌ INCOMPLETE: Only {actual_total} checks collected (expected {expected_total})")
        print(f"   Agent may need to be restarted or Phase 1 checks failed.")
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
    
except requests.exceptions.ConnectionError:
    print("❌ Cannot connect to backend at http://localhost:5000")
    print("   Please ensure the backend is running: cd backend; python -m uvicorn app:app --reload --port 5000")
except requests.exceptions.Timeout:
    print("❌ Request timed out. Backend may be overloaded.")
except Exception as e:
    print(f"❌ Unexpected error: {str(e)}")
    import traceback
    traceback.print_exc()
