"""
List all control IDs that have evidence records
"""
import asyncio
from database import connect_to_mongo, get_database

async def list_controls_with_evidence():
    await connect_to_mongo()
    db = get_database()
    
    print("📊 Querying asset_compliance collection...\n")
    
    # Get all unique control IDs
    pipeline = [
        {"$group": {"_id": "$controlId", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    
    results = await db.asset_compliance.aggregate(pipeline).to_list(length=1000)
    
    if not results:
        print("❌ No compliance records found")
        return
    
    print(f"✅ Found evidence for {len(results)} control IDs:\n")
    print("="*70)
    
    # Group by framework
    frameworks = {
        "SOC 2": [],
        "ISO 27001": [],
        "PCI-DSS": [],
        "NIST CSF": [],
        "HIPAA": [],
        "CVE": [],
        "Other": []
    }
    
    for result in results:
        control_id = result["_id"]
        count = result["count"]
        
        # Classify by framework
        if control_id.startswith("CC"):
            frameworks["SOC 2"].append((control_id, count))
        elif control_id.startswith("iso27001-") or control_id.startswith("A."):
            frameworks["ISO 27001"].append((control_id, count))
        elif control_id.startswith("pci-dss-") or control_id.startswith("PCI-"):
            frameworks["PCI-DSS"].append((control_id, count))
        elif control_id.startswith("nistcsf-") or control_id in ["PR.AC-1", "PR.AC-3", "PR.AC-4", "PR.AC-5", "PR.AC-7", "PR.DS-1", "PR.DS-2", "PR.IP-1", "DE.AE-1", "DE.CM-1", "DE.CM-4", "DE.CM-8", "ID.AM-1", "IA-5", "AC-7", "AU-2"]:
            frameworks["NIST CSF"].append((control_id, count))
        elif control_id.startswith("hipaa-"):
            frameworks["HIPAA"].append((control_id, count))
        elif control_id.startswith("CVE-"):
            frameworks["CVE"].append((control_id, count))
        else:
            frameworks["Other"].append((control_id, count))
    
    # Print by framework
    total_controls = 0
    for framework, controls in frameworks.items():
        if controls:
            print(f"\n📋 {framework} ({len(controls)} controls)")
            print("-" * 70)
            for control_id, count in sorted(controls):
                print(f"   {control_id:<30} ({count} evidence records)")
                total_controls += 1
    
    print("\n" + "="*70)
    print(f"\n✅ Total: {total_controls} unique control IDs with evidence")
    print(f"✅ Total: {sum(r['count'] for r in results)} evidence records\n")

if __name__ == "__main__":
    asyncio.run(list_controls_with_evidence())
