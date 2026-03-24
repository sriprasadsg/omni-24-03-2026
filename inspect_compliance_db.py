
import asyncio
import sys
import os

# Adjust path to import backend modules
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

from database import connect_to_mongo, get_database

async def main():
    await connect_to_mongo()
    db = get_database()
    
    print("--- Finding Asset EILT0197 ---")
    asset = await db.assets.find_one({"hostname": "EILT0197"})
    if not asset:
        print("Asset EILT0197 not found.")
        return

    with open("compliance_report.txt", "w", encoding="utf-8") as f:
        f.write(f"Asset ID: {asset.get('id')}\n")
        
        software = asset.get('installedSoftware', [])
        keywords = ['locker', 'ssl', 'veeam', 'backup', 'defender', 'firewall']
        found_keywords = []
        for sw in software:
            name = sw.get('name', '').lower()
            if any(k in name for k in keywords):
                found_keywords.append(f"{sw.get('name')} ({sw.get('version')})")

        f.write(f"\n--- Installed Software ({len(software)}) ---\n")
        if found_keywords:
            for k in found_keywords:
                f.write(f"  - Compliance SW found: {k}\n")
        else:
            f.write("  (No compliance-related software found)\n")

        f.write("\n--- Patch Status ---\n")
        patch_status = asset.get('patchStatus', {})
        f.write(f"  Critical: {patch_status.get('critical', 0)}\n")

        # Check Asset Compliance Evidence directly
        f.write("\n--- Asset Compliance Evidence ---\n")
        evidence_cursor = db.asset_compliance.find({"assetId": asset.get("id")})
        evidence_list = await evidence_cursor.to_list(length=None)
        f.write(f"Found {len(evidence_list)} compliance records.\n")
        for ev in evidence_list:
            f.write(f"  - Control: {ev.get('controlId')} | Status: {ev.get('status')} | Updated: {ev.get('lastUpdated')} | Check: {ev.get('checkName')}\n")
        
        # Check frameworks
        frameworks = await db.compliance_frameworks.find({}).to_list(length=None)
        f.write(f"\n--- Framework Statuses ({len(frameworks)}) ---\n")
        for fw in frameworks:
            f.write(f"Framework: {fw.get('name')}\n")
            f.write(f"  Status: {fw.get('status')}\n")
            controls = fw.get('controls', [])
            for ctrl in controls:
                if ctrl.get('status') != "Pass":
                    evidence_list = ctrl.get('evidence', [])
                    evidence_desc = evidence_list[0].get('description', 'No evidence') if evidence_list else 'No evidence'
                    f.write(f"  - Control '{ctrl.get('name')}' Failed/Pending: {evidence_desc}\n")

if __name__ == "__main__":
    asyncio.run(main())
