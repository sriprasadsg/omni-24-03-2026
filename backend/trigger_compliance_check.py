"""
Automated Compliance Evaluation Script
Evaluates all assets for a tenant against compliance controls and updates status
"""

import asyncio
import sys
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from database import get_database
import argparse


# Comprehensive mapping of all 36 agent checks to compliance control IDs
COMPLETE_MAPPINGS = {
    # Windows Checks (28 checks)
    "Windows Firewall Profiles": ["pci-dss-PCI-1.1.1", "nistcsf-PR.AC-1", "CC6.6", "PCI-1.1", "iso27001-A.13.1"],
    "Windows Defender Antivirus": ["iso27001-A.12.2.1", "pci-dss-PCI-5.1", "CC6.8", "iso27001-A.8.7", "nistcsf-DE.CM-4"],
    "Password Policy (Min Length)": ["iso27001-A.9.4.3", "pci-dss-PCI-8.1.1", "nistcsf-PR.AC-1", "iso27001-A.9.4.1", "CC6.1", "nistcsf-IA-5"],
    "Guest Account Disabled": ["iso27001-A.9.2.1", "pci-dss-PCI-8.1.1", "nistcsf-PR.AC-4", "CC6.1"],
    "RDP NLA Required": ["pci-dss-PCI-2.2.4", "nistcsf-PR.AC-1", "CC6.6", "iso27001-A.9.4.2"],
    "BitLocker Encryption": ["hipaa-164.312(a)(2)(iv)", "pci-dss-PCI-3.4", "iso27001-A.8.12", "nistcsf-PR.DS-1", "PCI-3.4", "CC6.1"],
    "Secure Boot": ["nistcsf-ID.AM-1", "iso27001-A.12.1.2", "CC7.2"],
    "Windows Update Service": ["pci-dss-PCI-6.2", "iso27001-A.12.6.1", "nistcsf-ID.AM-1", "CC7.3", "iso27001-A.12.6.1", "nistcsf-DE.CM-8"],
    "User Access Control": ["nistcsf-PR.AC-1", "iso27001-A.9.4.1", "CC6.1"],
    "Audit Logging Policy": ["pci-dss-PCI-10.1", "nistcsf-DE.AE-1", "iso27001-A.12.4.1", "CC9.2", "PCI-10.1", "nistcsf-DE.CM-1", "nistcsf-AU-2"],
    "Risky Network Ports": ["pci-dss-PCI-1.1", "iso27001-A.13.1", "CC6.6", "nistcsf-PR.AC-5"],
    "TLS Security Config": ["pci-dss-PCI-4.1", "hipaa-164.312(a)(2)(iv)", "CC6.7", "PCI-4.1", "nistcsf-PR.DS-2", "iso27001-A.10.1"],
    "Prohibited Software": ["iso27001-A.12.5", "iso27001-A.12.6.2", "nistcsf-ID.AM-1", "CC6.8"],
    "Maximum Password Age": ["nistcsf-IA-5", "iso27001-A.8.5", "pci-dss-PCI-8.2.4", "CC6.1"],
    "Account Lockout Policy": ["nistcsf-PR.AC-7", "pci-dss-PCI-8.1.6", "iso27001-A.9.4.2", "CC6.1", "nistcsf-AC-7"],
    "Password Complexity": ["nistcsf-IA-5", "iso27001-A.8.5", "pci-dss-PCI-8.2.3", "CC6.1"],
    "Password History": ["pci-dss-PCI-8.2.5", "nistcsf-IA-5", "iso27001-A.8.5", "CC6.1"],
    "Minimum Password Age": ["nistcsf-IA-5", "iso27001-A.8.5", "CC6.1"],
    "Remote Desktop Service": ["pci-dss-PCI-2.2.2", "nistcsf-PR.AC-3", "CC6.6"],
    "SMBv1 Protocol Disabled": ["CVE-2017-0143", "nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.6.1"],
    "LLMNR/NetBIOS Protection": ["nistcsf-PR.AC-5", "iso27001-A.13.1", "CC6.7"],
    "PowerShell Script Block Logging": ["nistcsf-DE.CM-1", "iso27001-A.12.4.1", "CC9.2", "nistcsf-AU-2"],
    "WinRM Service Status": ["pci-dss-PCI-2.2.2", "nistcsf-PR.AC-3"],
    "Credential Guard": ["nistcsf-PR.AC-1", "CC6.1", "iso27001-A.9.4.1"],
    "Device Guard/WDAC": ["nistcsf-PR.IP-1", "iso27001-A.12.5", "CC7.2"],
    "Exploit Protection (DEP/ASLR)": ["nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.6.1"],
    "Attack Surface Reduction": ["nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.2.1"],
    "Controlled Folder Access": ["nistcsf-PR.DS-1", "CC6.1", "iso27001-A.12.3.1"],
    
    # Linux Checks (8 checks)
    "UFW Firewall Enabled": ["pci-dss-PCI-1.1.1", "nistcsf-PR.AC-5", "CC6.6", "iso27001-A.13.1"],
    "SSH Root Login Disabled": ["pci-dss-PCI-2.2.4", "nistcsf-PR.AC-4", "CC6.1", "iso27001-A.9.4.3"],
    "Automatic Security Updates": ["pci-dss-PCI-6.2", "iso27001-A.12.6.1", "nistcsf-DE.CM-8", "CC7.3"],
    "SELinux Status": ["nistcsf-PR.AC-4", "iso27001-A.9.4.1", "CC6.1"],
    "AppArmor Status": ["nistcsf-PR.AC-4", "iso27001-A.9.4.1", "CC6.1"],
    "Sudo Configuration": ["nistcsf-PR.AC-4", "iso27001-A.9.4.1", "CC6.1"],
    "Cron Security": ["iso27001-A.12.5.1", "nistcsf-PR.AC-4", "CC6.1"],
    "SSHD Hardening": ["pci-dss-PCI-2.2.4", "nistcsf-PR.AC-5", "CC6.6", "iso27001-A.13.1.1"],
    "Filesystem Permissions": ["nistcsf-PR.AC-4", "iso27001-A.9.4.5", "CC6.1"],
}


async def evaluate_all_tenant_assets(tenant_id: str, framework_id: str = "all") -> Dict[str, Any]:
    """
    Evaluate all assets for a tenant against compliance controls
    
    Args:
        tenant_id: Tenant ID to evaluate
        framework_id: Specific framework or "all" for all frameworks
        
    Returns:
        Summary dict with evaluation results
    """
    db = get_database()
    timestamp = datetime.now(timezone.utc).isoformat()
    
    print(f"\n{'='*60}")
    print(f"🔍 Starting Compliance Evaluation for Tenant: {tenant_id}")
    print(f"{'='*60}\n")
    
    # 1. Get all assets for tenant
    if tenant_id == "all":
        assets = await db.assets.find({}, {"_id": 0}).to_list(length=10000)
        print(f"📊 Processing ALL tenants: {len(assets)} total assets")
    else:
        assets = await db.assets.find({"tenantId": tenant_id}, {"_id": 0}).to_list(length=1000)
        print(f"📊 Found {len(assets)} assets for tenant {tenant_id}")
    
    if not assets:
        print("⚠️  No assets found!")
        return {
            "success": False,
            "message": "No assets found for tenant",
            "assets_evaluated": 0
        }
    
    # Statistics
    stats = {
        "assets_evaluated": 0,
        "controls_checked": 0,
        "compliant_count": 0,
        "non_compliant_count": 0,
        "evidence_generated": 0,
        "compliant_assets": 0,
        "partial_compliance_assets": 0,
        "non_compliant_assets": 0
    }
    
    # 2. Process each asset
    for asset in assets:
        asset_id = asset.get("id")
        hostname = asset.get("hostname", "unknown")
        
        print(f"\n📦 Processing Asset: {hostname} ({asset_id})")
        
        # Get compliance data from asset metadata
        meta = asset.get("meta", {})
        compliance_data = meta.get("compliance_enforcement", {})
        
        if not compliance_data or not compliance_data.get("compliance_checks"):
            print(f"   ⏭️  Skipping - no compliance data available")
            continue
        
        checks = compliance_data.get("compliance_checks", [])
        print(f"   ✅ Found {len(checks)} compliance checks")
        
        asset_stats = {"compliant": 0, "non_compliant": 0}
        
        # 3. Process each compliance check
        for check in checks:
            check_name = check.get("check")
            status = check.get("status")  # Pass / Fail / Warning / Error
            details = check.get("details", "")
            
            # Determine compliance status
            if status == "Pass":
                compliance_status = "Compliant"
                asset_stats["compliant"] += 1
                stats["compliant_count"] += 1
            else:
                compliance_status = "Non-Compliant"
                asset_stats["non_compliant"] += 1
                stats["non_compliant_count"] += 1
            
            # Get mapped control IDs
            target_controls = COMPLETE_MAPPINGS.get(check_name, [])
            
            if not target_controls:
                print(f"   ⚠️  No mapping for: {check_name}")
                continue
            
            # 4. Update compliance records for each control
            for raw_control_id in target_controls:
                # Strip framework prefixes to match frontend expectations
                control_id = raw_control_id
                for prefix in ["nistcsf-", "pci-dss-", "iso27001-", "hipaa-", "gdpr-"]:
                    if control_id.startswith(prefix):
                        control_id = control_id[len(prefix):]
                        break
                
                evidence_id = f"auto-ev-{hostname}-{control_id}-{int(datetime.now().timestamp())}"
                
                evidence_content = (
                    f"Automated Compliance Check\\n"
                    f"Check: {check_name}\\n"
                    f"Result: {status}\\n"
                    f"Details: {details}\\n"
                    f"Asset: {hostname} ({asset_id})\\n"
                    f"Timestamp: {timestamp}"
                )
                
                evidence_record = {
                    "id": evidence_id,
                    "name": f"System Check: {check_name}",
                    "url": "#",
                    "type": "application/json",
                    "uploadedAt": timestamp,
                    "assetId": asset_id,
                    "controlId": control_id,
                    "systemGenerated": True,
                    "content": evidence_content,
                    "checkResult": status
                }
                
                # Upsert into DB
                await db.asset_compliance.update_one(
                    {"assetId": asset_id, "controlId": control_id},
                    {
                        "$set": {
                            "status": compliance_status,
                            "lastUpdated": timestamp,
                            "lastAutomatedCheck": timestamp,
                            "tenantId": asset.get("tenantId", "unknown"),
                            "hostname": hostname
                        },
                        "$push": {
                            "evidence": {
                                "$each": [evidence_record],
                                "$slice": -10  # Keep only last 10 evidence records
                            }
                        }
                    },
                    upsert=True
                )
                
                stats["controls_checked"] += 1
                stats["evidence_generated"] += 1
        
        stats["assets_evaluated"] += 1
        
        # Classify asset compliance
        if asset_stats["non_compliant"] == 0 and asset_stats["compliant"] > 0:
            stats["compliant_assets"] += 1
            print(f"   ✅ COMPLIANT - {asset_stats['compliant']} checks passed")
        elif asset_stats["compliant"] > 0 and asset_stats["non_compliant"] > 0:
            stats["partial_compliance_assets"] += 1
            print(f"   ⚠️  PARTIAL - {asset_stats['compliant']} passed, {asset_stats['non_compliant']} failed")
        else:
            stats["non_compliant_assets"] += 1
            print(f"   ❌ NON-COMPLIANT - {asset_stats['non_compliant']} checks failed")
    
    # 5. Print summary
    print(f"\n{'='*60}")
    print(f"📊 EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"Assets Evaluated: {stats['assets_evaluated']}")
    print(f"Controls Checked: {stats['controls_checked']}")
    print(f"Evidence Generated: {stats['evidence_generated']}")
    print(f"\nCompliance Results:")
    print(f"  ✅ Compliant: {stats['compliant_count']}")
    print(f"  ❌ Non-Compliant: {stats['non_compliant_count']}")
    print(f"\nAsset Classification:")
    print(f"  ✅ Fully Compliant Assets: {stats['compliant_assets']}")
    print(f"  ⚠️  Partially Compliant: {stats['partial_compliance_assets']}")
    print(f"  ❌ Non-Compliant Assets: {stats['non_compliant_assets']}")
    print(f"{'='*60}\n")
    
    return {
        "success": True,
        "timestamp": timestamp,
        "tenant_id": tenant_id,
        **stats
    }


async def main():
    """Main entry point for CLI usage"""
    parser = argparse.ArgumentParser(description="Evaluate compliance for tenant assets")
    parser.add_argument("--tenant_id", type=str, required=True, help="Tenant ID to evaluate (or 'all' for all tenants)")
    parser.add_argument("--framework", type=str, default="all", help="Framework ID (default: all)")
    
    args = parser.parse_args()
    
    try:
        from database import connect_to_mongo
        await connect_to_mongo()
        
        result = await evaluate_all_tenant_assets(args.tenant_id, args.framework)
        
        if result["success"]:
            print("✅ Compliance evaluation completed successfully!")
        else:
            print(f"❌ Evaluation failed: {result.get('message')}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
