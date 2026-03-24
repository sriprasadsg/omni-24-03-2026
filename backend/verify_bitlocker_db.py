
import sys
import os
import asyncio
from datetime import datetime

# Adjust path to find backend modules
sys.path.append(os.getcwd())

from backend.database import connect_to_mongo, get_database

async def check():
    await connect_to_mongo()
    db = get_database()
    
    # Check BitLocker (PCI-3.4)
    doc = await db.asset_compliance.find_one({
        "assetId": "asset-EILT0197",
        "controlId": "PCI-3.4"
    })
    
    if doc:
        print(f"BitLocker Record Found:")
        print(f"Status: {doc.get('status')}")
        print(f"Last Updated: {doc.get('lastUpdated')}")
        print(f"Check Name: {doc.get('checkName')}")
        
        # Check if updated recently (today)
        scan_time = doc.get('lastUpdated')
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if scan_time and scan_time.startswith(today):
             print("✅ BitLocker updated TODAY.")
        else:
             print("❌ BitLocker NOT updated today.")
             
        # Inspect Evidence
        evidence_list = doc.get('evidence', [])
        print(f"\nEvidence Count: {len(evidence_list)}")
        for i, ev in enumerate(evidence_list):
             print(f"Evidence [{i}]:")
             print(f"  Name: {ev.get('name')}")
             content = ev.get('content', '')
             # Extract Date from markdown check
             import re
             date_match = re.search(r'\*\*Date:\*\* ([\d\-\:T\.]+)', content)
             if date_match:
                 print(f"  Extracted Date: {date_match.group(1)}")
             else:
                 print(f"  Date not found in content.")
             print("  Full Content:")
             print(content)
             print("-" * 40)

if __name__ == "__main__":
    asyncio.run(check())
