import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection

async def check_all_frameworks():
    """Check how many controls each framework has"""
    await connect_to_mongo()
    db = get_database()
    
    frameworks = await db.compliance_frameworks.find({}, {'_id': 0, 'id': 1, 'name': 1, 'controls': 1}).to_list(length=None)
    
    print("\n" + "="*60)
    print("COMPLIANCE FRAMEWORK CONTROL COUNTS")
    print("="*60)
    
    total_controls = 0
    for fw in frameworks:
        control_count = len(fw.get('controls', []))
        total_controls += control_count
        print(f"{fw['name']:<40}: {control_count:>3} controls")
    
    print("="*60)
    print(f"{'TOTAL ACROSS ALL FRAMEWORKS':<40}: {total_controls:>3} controls")
    print("="*60 + "\n")
    
    # Show expected counts for reference
    print("\nEXPECTED CONTROL COUNTS (Full Coverage):")
    print("-" * 60)
    expected = {
        "SOC 2 Type II": "~30 controls (TSC)",
        "ISO/IEC 27001:2022": "93 controls (Annex A)",
        "PCI DSS": "~25 controls",
        "NIST CSF": "106 subcategories (v2.0)",
        "ISO 42001": "~12 controls (AI-specific)",
        "HIPAA": "~24 controls",
        "GDPR": "~17 articles"
    }
    
    for name, count in expected.items():
        print(f"{name:<40}: {count}")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check_all_frameworks())
