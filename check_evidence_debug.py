import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import get_database, connect_to_mongo, close_mongo_connection

async def check_evidence():
    await connect_to_mongo()
    db = get_database()
    cursor = db.asset_compliance.find({"controlId": {"$regex": "^DPDP-"}})
    
    print("Checking for DPDP Evidence in DB...")
    found = False
    async for doc in cursor:
        found = True
        control = doc.get('controlId')
        evidence_list = doc.get('evidence', [])
        count = len(evidence_list)
        print(f"Control: {control} | Status: {doc.get('status')} | Evidence Count: {count}")
        if count > 0:
            print(f" - First Evidence: {evidence_list[0].get('name')} (Type: {evidence_list[0].get('type')})")

    if not found:
        print("No DPDP compliance records found.")

if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(check_evidence())
