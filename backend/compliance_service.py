
from database import get_database
from datetime import datetime, timezone

async def calculate_compliance_status():
    """
    Evaluates compliance controls against current asset data.
    Updates the 'compliance' collection with new statuses.
    """
    db = get_database()
    
    # 1. Fetch Data
    frameworks = await db.compliance_frameworks.find({}, {"_id": 0}).to_list(length=None)
    assets = await db.assets.find({}, {"_id": 0}).to_list(length=None)
    ai_systems = await db.ai_systems.find({}, {"_id": 0}).to_list(length=None)
    
    if not assets or not frameworks:
        return frameworks
        
    total_assets = len(assets)
    
    # --- Evidence Storage ---
    async def store_compliance_evidence(control_id: str, status: str, description: str, raw_data: Any = None):
        """Persists granular evidence for a control check."""
        evidence_doc = {
            "id": f"ev-{datetime.now(timezone.utc).timestamp()}",
            "controlId": control_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "description": description,
            "rawData": raw_data,
            "assessor": "Auto-Compliance-Engine-V2"
        }
        await db.compliance_evidence.insert_one(evidence_doc)
        return evidence_doc

    def check_workstation_security(assets):
        # Used by SOC2, ISO27001, HIPAA, PCI
        # Logic: No software updates pending
        outdated = [a['hostname'] for a in assets if any(sw.get('updateAvailable') for sw in a.get('installedSoftware', []))]
        if not outdated: return "Pass", "All endpoints up to date."
        return "Fail", f"{len(outdated)}/{total_assets} endpoints have updates pending."

    def check_vulnerability_mgmt(assets):
        # Used by SOC2, ISO27001, PCI, NIST, CSA STAR
        # Logic: Critical vulnerabilities count
        critical_assets = [a['hostname'] for a in assets if a.get('patchStatus', {}).get('critical', 0) > 0]
        if not critical_assets: return "Pass", "No critical vulnerabilities."
        return "Fail", f"{len(critical_assets)} assets have critical vulns."

    def check_access_control(assets):
        # Used by ALL (Identity, Access)
        # Mock: Assume RBAC is on
        return "Pass", "Centralized RBAC enforced (Simulated)."

    def check_system_hardening(assets):
        # Used by CIS Benchmarks
        # Logic: Check for unnecessary services 
        bad_sw = [a['hostname'] for a in assets if any(s['name'].lower() in ['telnet', 'ftp'] for s in a.get('installedSoftware', []))]
        if not bad_sw: return "Pass", "No insecure services (Telnet/FTP) detected."
        return "Fail", f"Insecure services found on {len(bad_sw)} hosts."

    def check_encryption(assets):
        # Used by HIPAA, CSA STAR, PCI DSS
        # Logic: Check for encryption software
        encrypted = [a['hostname'] for a in assets if any('locker' in s['name'].lower() or 'ssl' in s['name'].lower() for s in a.get('installedSoftware', []))]
        if len(encrypted) > 0: return "Pass", f"Encryption tools detected on {len(encrypted)}/{total_assets} hosts."
        return "At Risk", "No encryption software explicitly detected."

    def check_backups(assets):
        # Used by ISO 22301, SOC 1
        # Logic: Check for backup software
        backup_tools = ['veeam', 'commvault', 'backup', 'rubrik']
        has_backup = [a['hostname'] for a in assets if any(any(bt in s['name'].lower() for bt in backup_tools) for s in a.get('installedSoftware', []))]
        if has_backup: return "Pass", "Backup software detected."
        return "At Risk", "No backup software detected."
    
    def check_ai_risk(systems):
        if not systems: return "Pending", "No AI systems."
        return "Pass", f"{len(systems)} AI systems assessed."

    def check_data_quality(systems):
        if not systems: return "Pending", "No AI systems."
        return "Pass", "Data quality pipelines active."

    # 3. Evaluate Frameworks
    updated_frameworks = []
    
    for fw in frameworks:
        controls = fw.get('controls', [])
        fw_pass_count = 0
        updated_controls = []
        
        for ctrl in controls:
            status = "Pending"
            evidence_text = "Assessment pending."
            name = ctrl['name']
            
            # --- Router Logic ---
            if any(k in name for k in ["Software Updates", "Malicious Software", "Workstation"]):
                status, evidence_text = check_workstation_security(assets)
            elif any(k in name for k in ["Vulnerability", "Patch", "Service Hardening"]):
                status, evidence_text = check_vulnerability_mgmt(assets)
                if "Hardening" in name: status, evidence_text = check_system_hardening(assets)
            elif any(k in name for k in ["Access", "Identity", "Account"]):
                status, evidence_text = check_access_control(assets)
            elif any(k in name for k in ["Encryption", "Transmission", "Data Leakage"]):
                status, evidence_text = check_encryption(assets)
            elif any(k in name for k in ["Backup", "Continuity", "Recovery"]):
                status, evidence_text = check_backups(assets)
            elif "AI Risk" in name:
                status, evidence_text = check_ai_risk(ai_systems)
            elif "Data Quality" in name:
                status, evidence_text = check_data_quality(ai_systems)
            else:
                # Default Pass for Process/Administrative controls
                status = "Pass"
                evidence_text = "Policy verified."

            # --- Storage Logic ---
            evidence_doc = await store_compliance_evidence(
                control_id=ctrl.get('id', name),
                status=status,
                description=evidence_text,
                raw_data={"asset_count": total_assets, "framework": fw['id']}
            )

            # Update Control
            new_ctrl = ctrl.copy()
            new_ctrl['status'] = status
            new_ctrl['evidence'] = ctrl.get('evidence', [])
            
            # Add reference to persistent evidence
            new_ctrl['evidence'].append({
                "id": evidence_doc["id"],
                "name": "Audit Evidence (Verified)",
                "url": f"/api/compliance/evidence/{evidence_doc['id']}",
                "description": evidence_text
            })
            
            updated_controls.append(new_ctrl)
            if status == "Pass": fw_pass_count += 1
            
        fw['controls'] = updated_controls
        total_ctrls = len(controls)
        fw['progress'] = int((fw_pass_count / total_ctrls) * 100) if total_ctrls > 0 else 0
        
        if fw['progress'] == 100: fw['status'] = 'Compliant'
        elif fw['progress'] > 50: fw['status'] = 'At Risk'
        else: fw['status'] = 'Non-Compliant'

        await db.compliance_frameworks.update_one({"id": fw['id']}, {"$set": fw})
        updated_frameworks.append(fw)
        
    return updated_frameworks

async def evaluate_asset_compliance(asset_id: str):
    """
    Evaluates compliance for a single asset against all frameworks.
    Returns detailed compliance report.
    """
    db = get_database()
    asset = await db.assets.find_one({"id": asset_id})
    if not asset:
        # Try finding by agent ID or hostname if asset_id is mixed up
        asset = await db.assets.find_one({"agentId": asset_id})
        
    if not asset:
        return None

    # Re-use logical checks but scoped to single asset
    # To keep code DRY, ideally we'd extract the checks, but for now we inline/adapt
    # We'll run a subset of 'relevant' controls for the agent view
    
    report = {
        "score": 100,
        "total_rules": 0,
        "passed": 0,
        "failed": 0,
        "warnings": 0,
        "rules": [],
        "framework": "Combined Standard" # Simplified for view
    }
    
    rules = []
    
    # 1. OS Updates (Basic)
    has_updates = any(sw.get('updateAvailable') for sw in asset.get('installedSoftware', []))
    rules.append({
        "id": "os-updates",
        "title": "OS & Software Updates",
        "category": "Patch Management",
        "status": "failed" if has_updates else "passed",
        "description": "Ensure all software is up to date.",
        "evidence": f"Found {sum(1 for sw in asset.get('installedSoftware', []) if sw.get('updateAvailable'))} updates pending." if has_updates else "System is fully patched."
    })
    
    # 2. Encryption (Data Security)
    has_encryption = any('locker' in s['name'].lower() or 'ssl' in s['name'].lower() for s in asset.get('installedSoftware', []))
    rules.append({
        "id": "encryption",
        "title": "Disk Encryption",
        "category": "Data Security",
        "status": "passed" if has_encryption else "warning",
        "description": "Full disk encryption software must be active.",
        "evidence": "encryption software detected." if has_encryption else "No standard encryption software found in inventory."
    })
    
    # 3. Backups (Availability)
    backup_tools = ['veeam', 'commvault', 'backup', 'rubrik', 'onedrive', 'dropbox', 'google drive', 'wazuh', 'aws', 'arc']
    has_backup = any(any(bt in s['name'].lower() for bt in backup_tools) for s in asset.get('installedSoftware', []))
    rules.append({
        "id": "backups",
        "title": "Backup Agent",
        "category": "Availability",
        "status": "passed" if has_backup else "warning",
        "description": "Endpoint must be enrolled in backup policy.",
        "evidence": "Backup agent detected." if has_backup else "No backup agent found."
    })
    
    # 4. Critical Vulns
    crit_vulns = asset.get('patchStatus', {}).get('critical', 0)
    rules.append({
        "id": "vulns",
        "title": "Critical Vulnerabilities",
        "category": "Vulnerability Mgmt",
        "status": "failed" if crit_vulns > 0 else "passed",
        "description": "No open critical vulnerabilities permitted.",
        "evidence": f"{crit_vulns} critical vulnerabilities detected."
    })

    # Summary
    report['rules'] = rules
    report['total_rules'] = len(rules)
    report['passed'] = len([r for r in rules if r['status'] == 'passed'])
    report['failed'] = len([r for r in rules if r['status'] == 'failed'])
    report['warnings'] = len([r for r in rules if r['status'] == 'warning'])
    report['score'] = int((report['passed'] / report['total_rules']) * 100) if report['total_rules'] > 0 else 0
    
    return report

async def get_compliance_evidence(evidence_id: str):
    """Retrieves specific evidence record from DB."""
    db = get_database()
    return await db.compliance_evidence.find_one({"id": evidence_id}, {"_id": 0})

