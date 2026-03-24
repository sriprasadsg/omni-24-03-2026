"""
Simple script to list all control IDs with evidence
"""
import asyncio
from database import connect_to_mongo, get_database

async def list_controls():
    await connect_to_mongo()
    db = get_database()
    
    # Get all distinct control IDs
    control_ids = await db.asset_compliance.distinct("controlId")
    control_ids.sort()
    
    print(f"\n✅ Found evidence for {len(control_ids)} control IDs:\n")
    print("="*70)
    
    # Group by framework
    soc2 = [c for c in control_ids if c.startswith("CC")]
    iso = [c for c in control_ids if c.startswith("iso27001-") or c.startswith("A.")]
    pci = [c for c in control_ids if c.startswith("pci-dss-") or c.startswith("PCI-")]
    nist = [c for c in control_ids if c.startswith("nistcsf-") or c in [
        "PR.AC-1", "PR.AC-3", "PR.AC-4", "PR.AC-5", "PR.AC-7", 
        "PR.DS-1", "PR.DS-2", "PR.IP-1", "DE.AE-1", "DE.CM-1", 
        "DE.CM-4", "DE.CM-8", "ID.AM-1", "IA-5", "AC-7", "AU-2"
    ]]
    hipaa = [c for c in control_ids if c.startswith("hipaa-")]
    cve = [c for c in control_ids if c.startswith("CVE-")]
    
    if soc2:
        print(f"\n📋 SOC 2 Trust Services ({len(soc2)} controls):")
        for c in soc2:
            print(f"   • {c}")
    
    if iso:
        print(f"\n📋 ISO 27001 ({len(iso)} controls):")
        for c in iso:
            print(f"   • {c}")
    
    if pci:
        print(f"\n📋 PCI-DSS ({len(pci)} controls):")
        for c in pci:
            print(f"   • {c}")
    
    if nist:
        print(f"\n📋 NIST Cybersecurity Framework ({len(nist)} controls):")
        for c in nist:
            print(f"   • {c}")
    
    if hipaa:
        print(f"\n📋 HIPAA ({len(hipaa)} controls):")
        for c in hipaa:
            print(f"   • {c}")
    
    if cve:
        print(f"\n📋 CVE References ({len(cve)} controls):")
        for c in cve:
            print(f"   • {c}")
    
    print("\n" + "="*70)
    print(f"\n✅ TOTAL: {len(control_ids)} unique control IDs with evidence\n")

asyncio.run(list_controls())
