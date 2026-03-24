import asyncio
from database import connect_to_mongo, get_database

async def check_vulnerabilities():
    await connect_to_mongo()
    db = get_database()
    
    vulns = await db.vulnerabilities.find({}).to_list(100)
    
    with open("vuln_check_output.txt", "w") as f:
        f.write(f"Found {len(vulns)} vulnerabilities in database:\n\n")
        
        for v in vulns:
            f.write(f"CVE ID: {v.get('cveId', 'N/A')}\n")
            f.write(f"Severity: {v.get('severity', 'N/A')}\n")
            f.write(f"Status: {v.get('status', 'N/A')}\n")
            f.write(f"Software: {v.get('affectedSoftware', 'N/A')}\n")
            f.write(f"Description: {v.get('description', 'N/A')}\n")
            f.write(f"Discovered: {v.get('discoveredAt', 'N/A')}\n")
            f.write(f"Asset ID: {v.get('assetId', 'N/A')}\n")
            f.write(f"Tenant ID: {v.get('tenantId', 'N/A')}\n")
            f.write("-" * 80 + "\n\n")
    
    print(f"Output written to vuln_check_output.txt")

if __name__ == "__main__":
    asyncio.run(check_vulnerabilities())
