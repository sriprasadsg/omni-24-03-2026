import asyncio
import sys
import os
import csv
import datetime

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database, close_mongo_connection

async def export_compliance_report():
    await connect_to_mongo()
    db = get_database()
    
    print("📂 Exporting Compliance Evidence Report...")
    
    # Fetch all compliance records
    docs = await db.asset_compliance.find({}).to_list(length=None)
    
    # Fetch frameworks to map control names if not in doc
    frameworks = await db.compliance_frameworks.find({}).to_list(length=None)
    control_map = {}
    for f in frameworks:
        fid = f.get("id", "unknown")
        for c in f.get("controls", []):
            control_map[f"{fid}-{c.get('id')}"] = {
                "name": c.get("name"),
                "framework": f.get("name")
            }
            # Also map without prefix for easier lookup
            control_map[c.get('id')] = {
                "name": c.get("name"),
                "framework": f.get("name")
            }

    filename = "compliance_evidence_report_v2.csv"
    filepath = os.path.join(os.getcwd(), filename)
    
    header = [
        "Framework", 
        "Control ID", 
        "Control Name", 
        "Asset ID", 
        "Status", 
        "Evidence Name", 
        "Evidence ID", 
        "Verification Status",
        "Last Updated"
    ]
    
    rows = []
    
    for doc in docs:
        control_id = doc.get("controlId", "unknown")
        asset_id = doc.get("assetId", "unknown")
        status = doc.get("status", "unknown")
        last_updated = doc.get("lastUpdated", "unknown")
        
        info = control_map.get(control_id, {"name": "Unknown Control", "framework": "ISO 27001 (Assumed)" if control_id.startswith("A.") else "Unknown"})
        
        evidence_list = doc.get("evidence", [])
        if not evidence_list:
            rows.append([
                info["framework"],
                control_id,
                info["name"],
                asset_id,
                status,
                "No Evidence Collected",
                "N/A",
                "N/A",
                last_updated
            ])
        else:
            for e in evidence_list:
                # Basic check for verification status in content if it's a markdown string
                content = e.get("content", "")
                verification = "N/A"
                if "✅ Verified" in content:
                    verification = "Verified"
                elif "❌ TAMPERING" in content:
                    verification = "Tampered"
                
                rows.append([
                    info["framework"],
                    control_id,
                    info["name"],
                    asset_id,
                    status,
                    e.get("name", "Unnamed Evidence"),
                    e.get("id", "N/A"),
                    verification,
                    e.get("uploadedAt", last_updated)
                ])
                
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
        
    print(f"✅ Report successfully generated: {filepath}")
    print(f"📊 Total Evidence Records Exported: {len(rows)}")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(export_compliance_report())
