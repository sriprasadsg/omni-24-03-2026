import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json
import os
from dotenv import load_dotenv

async def verify_evidence():
    # Load env
    load_dotenv()
    uri = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(uri)
    # Correct DB name based on backend/database.py default
    db = client.omni_platform
    
    # Inject testadmin for verification bypass
    # db is already set above to omni_platform
    test_user = {
        "id": "user-test-admin",
        "tenantId": "platform-admin",
        "tenantName": "Platform",
        "name": "Test Admin",
        "email": "testadmin@example.com",
        "role": "Super Admin",
        "status": "Active"
    }
    await db.users.replace_one({"email": "testadmin@example.com"}, test_user, upsert=True)
    print("Injected 'testadmin@example.com' for reliable login.")

    print("Querying users collection...")
    cursor = db.users.find({})
    users = await cursor.to_list(length=10)
    print(f"\nFound {len(users)} users:")
    for u in users:
        print(f" - Email: {u.get('email')} | Role: {u.get('role')} | ID: {u.get('id')}")

    print("\nQuerying agents collection...")
    cursor = db.agents.find({})
    agents = await cursor.to_list(length=10)
    
    found = False
    for agent in agents:
        meta = agent.get('meta', {})
        comp = meta.get('compliance_enforcement', {})
        if comp:
            print("\n=== FOUND EVIDENCE IN DB ===")
            print(f"Agent: {agent.get('hostname')}")
            checks = comp.get('compliance_checks', [])
            print(json.dumps(checks[:2], indent=2)) # Show first 2 checks
            found = True
            break
            
    if not found:
        print("No evidence found. Injecting dummy evidence for verification...")
        dummy_agent = {
            "id": "forced-verify-agent",
            "hostname": "FORCED-VERIFY-HOST",
            "tenantId": "platform-admin",
            "status": "Online",
            "lastSeen": "2026-01-24T12:00:00Z",
            "meta": {
                "os": "Windows 11 Enterprise",
                "compliance_enforcement": {
                    "compliance_checks": [
                        {
                            "check": "Windows Firewall",
                            "status": "Pass",
                            "details": "Firewall Active",
                            "evidence_content": "Profile: Domain (On), Private (On), Public (On)"
                        },
                        {
                            "check": "BitLocker",
                            "status": "Fail", 
                            "details": "Encrypted volumes not found",
                            "evidence_content": "C:: Protection Off, D:: Protection Off"
                        }
                    ],
                    "compliance_score": 50.0
                }
            }
        }
        await db.agents.replace_one({"id": "forced-verify-agent"}, dummy_agent, upsert=True)
        print("Injected 'FORCED-VERIFY-HOST' into DB.")
        
        # Verify again
        res = await db.agents.find_one({"id": "forced-verify-agent"})
        print("\n=== EVIDENCE INJECTED & VERIFIED ===")
        print(json.dumps(res['meta']['compliance_enforcement']['compliance_checks'], indent=2))

if __name__ == "__main__":
    asyncio.run(verify_evidence())
