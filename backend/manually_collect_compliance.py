"""
Manually collect and inject compliance data into asset metadata
This simulates what the agent would do during heartbeat
"""

import asyncio
import sys
import os

# Add agent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))

from database import connect_to_mongo, get_database
from datetime import datetime, timezone

async def manually_collect_compliance():
    await connect_to_mongo()
    db = get_database()
    
    hostname = "EILT0197"
    
    print(f"🔍 Collecting compliance data for {hostname}...")
    
    # Import and run the compliance capability
    try:
        from capabilities.compliance import ComplianceEnforcementCapability
        
        print("✅ Loaded ComplianceEnforcementCapability")
        
        # Create instance and collect data
        compliance_cap = ComplianceEnforcementCapability()
        compliance_data = compliance_cap.collect()
        
        print(f"✅ Collected {compliance_data.get('total_checks', 0)} compliance checks")
        print(f"   - Passed: {compliance_data.get('passed', 0)}")
        print(f"   - Failed: {compliance_data.get('failed', 0)}")
        print(f"   - Score: {compliance_data.get('compliance_score', 0)}%")
        
        # Update asset metadata - ensure meta exists first
        # First, initialize meta if it doesn't exist
        await db.assets.update_one(
            {"hostname": hostname},
            {"$set": {"meta": {}}},
            upsert=False
        )
        
        # Now update compliance data
        result = await db.assets.update_one(
            {"hostname": hostname},
            {
                "$set": {
                    "meta.compliance_enforcement": {
                        **compliance_data,
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                }
            }
        )
        
        if result.modified_count > 0:
            print(f"\n✅ Successfully updated asset metadata with compliance data")
        else:
            print(f"\n⚠️  Asset not found or already had this data")
        
        # Also update agent metadata
        await db.agents.update_one(
            {"hostname": hostname},
            {
                "$set": {
                    f"meta.compliance_enforcement": compliance_data,
                    "lastSeen": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        print(f"\n✅ Data injection complete!")
        print(f"\n📋 Now run the evaluation script:")
        print(f"   python backend/trigger_compliance_check.py --tenant_id all")
        
    except ImportError as e:
        print(f"❌ Error importing compliance capability: {e}")
        print(f"\n💡 Make sure you're running from the backend directory")
        print(f"   cd backend")
        print(f"   python manually_collect_compliance.py")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(manually_collect_compliance())
