import asyncio
import os
import sys

# Add backend to sys.path to import get_database if needed
sys.path.append(os.getcwd())

from motor.motor_asyncio import AsyncIOMotorClient

async def check_db():
    print("--- DEEP DIVE DIAGNOSTICS: DATABASE CHECK ---")
    try:
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client["omni_platform"]
        
        # 1. Check Compliance Frameworks
        print("\n1. Frameworks Status:")
        cursor = db.compliance_frameworks.find({}, {"id": 1, "name": 1, "progress": 1})
        async for fw in cursor:
            print(f" - [{fw['id']}] {fw['name']}: {fw.get('progress')}%")
            
        # 2. Check AI Auditor Results
        print("\n2. AI Auditor Evaluation Results (Asset Compliance):")
        cursor = db.asset_compliance.find({"ai_evaluation": {"$exists": True}})
        results = await cursor.to_list(length=10)
        if not results:
            print(" [!] No AI evaluation records found in DB.")
        else:
            for r in results:
                eval_data = r["ai_evaluation"]
                print(f" - Control: {r['controlId']} | Asset: {r['assetId']} | Verdict: {'PASS' if eval_data['verified'] else 'FAIL'}")
                print(f"   Reasoning: {eval_data['reasoning'][:100]}...")

        # 3. Check Users & RBAC
        print("\n3. Users & Roles:")
        cursor = db.users.find({}, {"email": 1, "role": 1})
        async for user in cursor:
            print(f" - {user['email']} ({user['role']})")

        # 4. Check Agents
        print("\n4. Registered Agents:")
        count = await db.agents.count_documents({})
        print(f" - Found {count} agents registered.")

        client.close()
    except Exception as e:
        print(f"Error checking DB: {e}")

if __name__ == "__main__":
    asyncio.run(check_db())
