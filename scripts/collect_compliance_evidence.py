import asyncio
import os
import json
import logging
from datetime import datetime, timezone

# Adjust path to import backend modules if needed
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from database import get_database, connect_to_mongo, close_mongo_connection

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

ENTITY_NAME = "Enterprise Omni Agent Platform"

async def collect_user_entitlements(db):
    logging.info("Collecting User Entitlements...")
    users = await db.users.find({}, {"_id": 0, "password": 0}).to_list(length=1000)
    roles = await db.roles.find({}, {"_id": 0}).to_list(length=100)
    return {
        "users": users,
        "roles": roles,
        "summary": f"Found {len(users)} users and {len(roles)} defined roles."
    }

async def collect_asset_compliance(db):
    logging.info("Collecting Asset Compliance Status...")
    assets = await db.assets.find({}, {"_id": 0}).to_list(length=1000)
    
    # Process basic metrics
    total_assets = len(assets)
    patched_count = sum(1 for a in assets if not any(sw.get('updateAvailable') for sw in a.get('installedSoftware', [])))
    
    return {
        "total_assets": total_assets,
        "fully_patched_count": patched_count,
        "patch_compliance_rate": f"{(patched_count/total_assets)*100:.1f}%" if total_assets > 0 else "N/A",
        "assets": assets
    }

async def collect_audit_trail(db):
    logging.info("Collecting Audit Logs (Last 100)...")
    logs = await db.audit_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(100).to_list(length=100)
    return {
        "count": len(logs),
        "logs": logs
    }

async def collect_vulnerabilities(db):
    logging.info("Collecting Vulnerability Summary...")
    vulns = await db.vulnerabilities.find({}, {"_id": 0}).to_list(length=1000)
    
    open_vulns = [v for v in vulns if v.get('status') == 'Open']
    critical = [v for v in open_vulns if v.get('severity') == 'Critical']
    
    return {
        "total_open": len(open_vulns),
        "critical_open": len(critical),
        "details": vulns
    }

async def collect_dpdp_evidence(db):
    logging.info("Collecting DPDP Compliance Evidence...")
    # Simulate checks for DPDP components
    
    # 1. Consent Artifacts (Dummy check for now)
    consent_count = await db.consents.count_documents({})
    
    # 2. Data Retention Policy Check (Check if policy exists)
    retention_policy = await db.policies.find_one({"type": "data_retention"})
    
    # 3. Breach Notification Config
    breach_config = await db.config.find_one({"type": "breach_notification"})
    
    return {
        "consent_records_count": consent_count,
        "retention_policy_active": bool(retention_policy),
        "breach_notification_enabled": bool(breach_config and breach_config.get("enabled", False)), 
        "data_fiduciary_status": "Significant" # Placeholder
    }

async def main():
    logging.info("Starting Compliance Evidence Collection...")
    
    # Connect
    await connect_to_mongo()
    db = get_database()
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    evidence_package = {
        "meta": {
             "generated_at": datetime.now(timezone.utc).isoformat(),
             "system": ENTITY_NAME,
             "version": "1.0.0"
        },
        "access_control": {},
        "assets": {},
        "audit_logs": {},
        "vulnerabilities": {},
        "dpdp": {}
    }

    try:
        evidence_package["access_control"] = await collect_user_entitlements(db)
        evidence_package["assets"] = await collect_asset_compliance(db)
        evidence_package["audit_logs"] = await collect_audit_trail(db)
        evidence_package["vulnerabilities"] = await collect_vulnerabilities(db)
        evidence_package["dpdp"] = await collect_dpdp_evidence(db)
        
        # Save JSON
        json_filename = f"compliance_evidence_{timestamp}.json"
        with open(json_filename, "w") as f:
            json.dump(evidence_package, f, indent=2, default=str)
        logging.info(f"Evidence JSON saved to {json_filename}")
        
        # Generate Markdown Report
        md_filename = f"compliance_audit_report_{timestamp}.md"
        with open(md_filename, "w") as f:
            f.write(f"# Compliance Audit Evidence Report\n")
            f.write(f"**Date:** {evidence_package['meta']['generated_at']}\n")
            f.write(f"**System:** {ENTITY_NAME}\n\n")
            
            f.write("## 1. Executive Summary\n")
            f.write(f"- **Total Assets:** {evidence_package['assets']['total_assets']}\n")
            f.write(f"- **Patch Compliance:** {evidence_package['assets']['patch_compliance_rate']}\n")
            f.write(f"- **Open Critical Vulnerabilities:** {evidence_package['vulnerabilities']['critical_open']}\n")
            f.write(f"- **Active Users:** {len(evidence_package['access_control']['users'])}\n")
            f.write(f"- **Open Critical Vulnerabilities:** {evidence_package['vulnerabilities']['critical_open']}\n")
            f.write(f"- **Active Users:** {len(evidence_package['access_control']['users'])}\n")
            f.write(f"- **Audit Records Captured:** {evidence_package['audit_logs']['count']}\n")
            f.write(f"- **DPDP Consent Records:** {evidence_package['dpdp']['consent_records_count']}\n\n")
            
            f.write("## 2. Access Control Review\n")
            f.write("| User | Role | Status |\n|---|---|---|\n")
            for u in evidence_package['access_control']['users']:
                f.write(f"| {u.get('email')} | {u.get('role')} | {u.get('status', 'Active')} |\n")
            
            # Additional sections could be added...
            logging.info(f"Audit Report Markdown saved to {md_filename}")

    finally:
        await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
