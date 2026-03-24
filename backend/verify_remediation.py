import asyncio
import os
import sys

# Ensure backend directory is in path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from remediation_service import RemediationService
from models import RemediationRequest
from tenant_context import set_tenant_id

async def test_remediation_flow():
    print("🧪 Starting AI Auto-Remediation Test...")
    
    tenant_id = "tenant_test_123"
    asset_id = "asset_win_01"
    
    # 1. Simulate AI Generation
    print("\n--- 1. Testing AI Fix Generation ---")
    cve_id = "CVE-2021-44228" # Log4j
    proposal = await RemediationService.generate_fix_proposal(tenant_id, asset_id, "vuln_1", cve_id)
    
    print(f"✅ Generated Proposal: {proposal.id}")
    print(f"   Action: {proposal.proposedAction}")
    print(f"   Script: {proposal.scriptContent[:50]}...")
    
    if proposal.status != "Pending":
        print("❌ Error: Status should be Pending")
        return

    # 2. Simulate Approval & Execution
    print("\n--- 2. Testing Approval & Execution ---")
    try:
        updated_request = await RemediationService.approve_and_execute(proposal)
        print(f"✅ Execution Dispatched. New Status: {updated_request.status}")
        
        if updated_request.status == "In Progress":
            print("🚀 SUCCESS: Remediation is now In Progress (assigned to Celery)")
        else:
            print(f"❌ Error: Unexpected status {updated_request.status}")
            
    except Exception as e:
        print(f"❌ Execution Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_remediation_flow())
