
import asyncio
from database import connect_to_mongo, get_database

async def verify():
    print("🔍 Verify Compliance Expansion...")
    await connect_to_mongo()
    db = get_database()
    
    # 1. Check Frameworks
    fedramp = await db.compliance_frameworks.find_one({"id": "fedramp_moderate"})
    print(f"Framework FedRAMP: {'✅ Found' if fedramp else '❌ Missing'}")
    
    ccpa = await db.compliance_frameworks.find_one({"id": "ccpa"})
    print(f"Framework CCPA: {'✅ Found' if ccpa else '❌ Missing'}")
    
    # 2. Check Evidence for Simulated Agent
    # Asset ID is derived from hostname in agent_endpoints.py -> asset-{hostname}
    asset_id = "asset-agent-sim-compliance-xp"
    
    evidence = await db.asset_compliance.find({"assetId": asset_id}).to_list(100)
    print(f"\nFound {len(evidence)} compliance records for {asset_id}")
    
    expected_controls = [
        "fedramp-AC-3", 
        "csa-IVS-06", 
        "ccpa-Privacy-1", 
        "cmmc-SI.L2-3.14.1"
    ]
    
    found_controls = [e.get("controlId") for e in evidence]
    
    for expected in expected_controls:
        # We strip prefixes in the endpoint, so expected "fedramp-AC-3" is stored as "AC-3"
        # But wait, logic says: control_id = control_id[len(prefix):]
        # So "fedramp-AC-3" -> "AC-3"
        
        # Let's check what's actually there
        stripped = expected.split("-", 1)[1] if "-" in expected else expected
        # Actually logic is: if startswith("fedramp-") -> strip "fedramp-"
        # So "fedramp-AC-3" -> "AC-3"
        pass
        
    for e in evidence:
        print(f"- Control: {e.get('controlId')} | Status: {e.get('status')} | Check: {e.get('checkName')}")

if __name__ == "__main__":
    asyncio.run(verify())
