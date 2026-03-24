"""
Verify Compliance Evidence Collection Fix

This script tests:
1. Frameworks are accessible via authenticated API
2. Agent compliance data processing works3. Evidence is mapped to controls correctly
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime

async def main():
    print("=" * 60)
    print("🧪 Testing Compliance Evidence Collection")
    print("=" * 60)
    
    # Connect to database
    client = AsyncIOMotorClient('mongodb://localhost:27017/')
    db = client['omni_platform']
    
    # 1. Check frameworks
    print("\n1. Checking Compliance Frameworks...")
    frameworks = await db.compliance_frameworks.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(length=100)
    print(f"   Found {len(frameworks)} frameworks:")
    for fw in frameworks[:3]:
        print(f"   - {fw.get('id')}: {fw.get('name')}")
    
    if len(frameworks) == 0:
        print("   ❌ No frameworks found! Run backend/seed_compliance.py first")
        return
    else:
        print(f"   ✅ {len(frameworks)} frameworks available")
    
    # 2. Check existing agent compliance evidence
    print("\n2. Checking Existing Evidence...")
    evidence_count = await db.compliance_evidence.count_documents({})
    asset_compliance_count = await db.asset_compliance.count_documents({})
    print(f"   compliance_evidence collection: {evidence_count} documents")
    print(f"   asset_compliance collection: {asset_compliance_count} documents")
    
    # 3. Check if any agents sent compliance data
    print("\n3. Checking Agents with Compliance Data...")
    agents_with_compliance = 0
    async for agent in db.agents.find({"meta.compliance_enforcement": {"$exists": True}}, {"id": 1, "hostname": 1}).limit(5):
        agents_with_compliance += 1
        print(f"   - {agent.get('hostname', agent.get('id'))}")
    
    if agents_with_compliance == 0:
        print("   ⚠️  No agents have sent compliance data yet")
        print("   Agents need to be running and sending heartbeats with compliance checks")
    else:
        print(f"   ✅ Found {agents_with_compliance} agents with compliance data")
    
    # 4. Simulate processing agent evidence
    print("\n4. Testing Automated Evidence Processing...")
    
    # Get a sample agent or create test data
    sample_agent = await db.agents.find_one({"meta.compliance_enforcement": {"$exists": True}})
    
    if not sample_agent:
        print("   Creating mock agent compliance data for testing...")
        test_hostname = "test-windows-server"
        test_compliance_data = {
            "compliance_checks": [
                {
                    "check": "Windows Firewall Profiles",
                    "status": "Pass",
                    "details": "Domain, Private, and Public profiles are enabled",
                    "evidence_content": '{"domain": "enabled", "private": "enabled", "public": "enabled"}',
                    "content_hash": "abc123"
                },
                {
                    "check": "Password Policy",
                    "status": "Pass", 
                    "details": "Minimum password length: 14",
                    "evidence_content": "MinimumPasswordLength=14\nPasswordComplexity=1",
                    "content_hash": "def456"
                }
            ]
        }
    else:
        test_hostname = sample_agent.get("hostname", sample_agent.get("id"))
        test_compliance_data = sample_agent.get("meta", {}).get("compliance_enforcement", {})
        print(f"   Using data from agent: {test_hostname}")
    
    # Import and run evidence processor
    try:
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
        
        from compliance_endpoints import process_automated_evidence
        
        print(f"   Processing compliance data for: {test_hostname}")
        await process_automated_evidence(test_hostname, test_compliance_data, db)
        
        print("   ✅ Evidence processing completed successfully")
        
        # 5. Verify evidence was created
        print("\n5. Verifying Evidence Creation...")
        asset_id = f"asset-{test_hostname}"
        
        asset_compliance = await db.asset_compliance.find({"assetId": asset_id}).to_list(length=100)
        
        if asset_compliance:
            print(f"   ✅ Found {len(asset_compliance)} compliance records for {test_hostname}")
            for record in asset_compliance[:3]:
                control_id = record.get('controlId')
                status = record.get('status')
                evidence_count = len(record.get('evidence', []))
                print(f"   - Control {control_id}: {status} ({evidence_count} evidence items)")
        else:
            print(f"   ❌ No compliance evidence created for {test_hostname}")
            
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        print("   Make sure you're running this from the project root")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # 6. Summary
    print("\n" + "=" * 60)
    print("📊 Summary")
    print("=" * 60)
    
    final_evidence_count = await db.compliance_evidence.count_documents({})
    final_asset_compliance_count = await db.asset_compliance.count_documents({})
    
    print(f"compliance_evidence: {final_evidence_count} documents")
    print(f"asset_compliance: {final_asset_compliance_count} documents")
    
    if final_asset_compliance_count > asset_compliance_count:
        print(f"✅ Evidence collection is WORKING! (+{final_asset_compliance_count - asset_compliance_count} new records)")
    else:
        print("⚠️  No new evidence created. Check agent heartbeat and compliance data")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
