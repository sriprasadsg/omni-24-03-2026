"""
Automated Compliance Evaluation Script
Evaluates all assets for a tenant against compliance controls and updates status
"""

import asyncio
import sys
from datetime import datetime, timezone
from typing import Dict, Any
from database import get_database
import argparse
from compliance_evidence_processor import COMPLIANCE_CHECK_MAPPINGS as COMPLETE_MAPPINGS


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
            print("   ⏭️  Skipping - no compliance data available")
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
    print("📊 EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"Assets Evaluated: {stats['assets_evaluated']}")
    print(f"Controls Checked: {stats['controls_checked']}")
    print(f"Evidence Generated: {stats['evidence_generated']}")
    print("\nCompliance Results:")
    print(f"  ✅ Compliant: {stats['compliant_count']}")
    print(f"  ❌ Non-Compliant: {stats['non_compliant_count']}")
    print("\nAsset Classification:")
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
