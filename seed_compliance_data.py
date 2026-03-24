import sys
import os
import datetime
import random
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from backend.database import connect_to_mongo, get_database
import asyncio

async def seed_data():
    await connect_to_mongo()
    db = get_database()
    
    agent_id = "agent-EILT0197"
    hostname = "EILT0197"
    asset_id = f"asset-{hostname}"
    
    timestamp = datetime.datetime.utcnow().isoformat()
    
    # 1. Update Agent with Asset ID
    agent = await db.agents.find_one({"id": agent_id})
    tenant_id = agent.get("tenantId", "default")
    print(f"✅ Found tenantId: {tenant_id}")
    
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {"assetId": asset_id, "asset_id": asset_id}} 
    )
    print(f"✅ Linked agent {agent_id} to asset {asset_id}")
    
    # 2. Seed Asset Compliance (for API fetch)
    # We'll seed a mix of passed, failed, warning
    
    controls = [
        # PCI DSS (Valid IDs from seed_compliance.py)
        ("PCI-1.1", "Windows Firewall Profiles", "failed"),      # Was PCI-1.1.1
        ("PCI-5.1", "Windows Defender Antivirus", "passed"),
        ("PCI-8.2", "Password Policy", "passed"),                # Was PCI-8.1.1 (Unique IDs) -> PCI-8.2 (Auth Methods) or A.9.4.1
        ("PCI-2.2", "RDP NLA Required", "warning"),              # Was PCI-2.2.4 -> PCI-2.2 (Config Standards)
        ("PCI-3.4", "BitLocker Encryption", "failed"),
        ("PCI-6.2", "Windows Update Service", "passed"),
        ("PCI-10.1", "Audit Logging Policy", "passed"),
        
        # DPDP Controls (Valid)
        ("DPDP-5.1", "Consent Artifacts Present", "failed"),
        ("DPDP-8.4", "Data Retention Pruning Logic", "passed"),
        ("DPDP-8.5", "Personal Data Breach Notification Ops", "warning"),
        ("DPDP-9.1", "Child Data Age-Gating", "passed"),
        ("DPDP-10.1", "Significant Data Fiduciary Audits", "failed"),
        
        # NIST CSF (Mapped from "New Enterprise Frameworks")
        ("ID.AM-1", "CIS: Enterprise Asset Inventory (Mapped to NIST)", "passed"), # Was CIS-1.1
        ("PR.AC-1", "CMMC: Access Control (Mapped to NIST)", "passed"),            # Was CMMC-AC.1.001
        
        # SOC 2 (Mapped)
        ("CC6.1", "Logical Access Security", "passed"),
        ("CC7.2", "Vulnerability Management", "failed"), 
        
        # ISO 27001 (Mapped)
        ("A.5.1", "Policies for InfoSec", "passed"),
        ("A.12.6.1", "Technical Vulnerability Management", "warning"),
    ]

    for cid, name, status in controls:
        compliance_status = "Compliant" if status == "passed" else "Non-Compliant" if status == "failed" else "Warning"
        
        # Evidence Record
        evidence = {
            "id": f"seed-ev-{cid}",
            "name": f"System Check: {name}",
            "url": "#",
            "type": "application/json",
            "uploadedAt": timestamp,
            "assetId": asset_id,
            "tenantId": tenant_id, # Crucial
            "controlId": cid,
            "systemGenerated": True,
            "content": f"# System Check: {name}\n**Status:** {compliance_status}\n\nAutomated verify."
        }
        
        await db.asset_compliance.update_one(
            {"assetId": asset_id, "controlId": cid},
            {
                "$set": {
                    "tenantId": tenant_id, # Crucial
                    "status": compliance_status,
                    "lastUpdated": timestamp,
                    "lastAutomatedCheck": timestamp
                },
                "$push": {
                    "evidence": evidence
                }
            },
            upsert=True
        )
    
    print(f"✅ Seeded {len(controls)} compliance records in 'asset_compliance' collection")
    
    # 3. Seed Agent Meta (Fallback)
    # AgentDetailModal.tsx expects: 
    # { score, total_rules, passed, failed, warnings, rules: [], framework }
    
    meta_rules = []
    for cid, name, status in controls:
        meta_rules.append({
            "id": cid,
            "title": name,
            "status": status,
            "category": "Security",
            "description": f"Control ID: {cid}",
            "remediation": "Enable feature..." if status == "failed" else None
        })
        
    meta_data = {
        "score": 58, # Re-calculated roughly
        "total_rules": len(controls),
        "passed": 7,
        "failed": 4, 
        "warnings": 2,
        "rules": meta_rules,
        "framework": "Mixed (PCI-DSS, DPDP)"
    }
    
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {"meta.compliance_enforcement": meta_data}}
    )
    print("✅ Seeded agent.meta.compliance_enforcement")

if __name__ == "__main__":
    asyncio.run(seed_data())
