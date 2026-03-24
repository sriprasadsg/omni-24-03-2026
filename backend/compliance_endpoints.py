from fastapi import APIRouter, File, UploadFile, HTTPException, Form, BackgroundTasks
from typing import List, Optional
import shutil
import os
from datetime import datetime, timezone
from database import get_database


router = APIRouter()

UPLOAD_DIR = "static/evidence"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/api/assets/{asset_id}/compliance/evidence")
async def upload_compliance_evidence(
    asset_id: str,
    file: UploadFile = File(...),
    control_id: str = Form(...)
):
    try:
        # Save file to disk
        file_ext = os.path.splitext(file.filename)[1]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_filename = f"{asset_id}_{control_id}_{timestamp}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # File URL (assuming static mount)
        file_url = f"http://localhost:5000/static/evidence/{safe_filename}"
        
        # Create Evidence Record
        evidence_record = {
            "id": f"ev-{timestamp}",
            "name": file.filename,
            "url": file_url,
            "type": file.content_type,
            "uploadedAt": datetime.now(timezone.utc).isoformat(),
            "assetId": asset_id,
            "controlId": control_id
        }
        
        # Determine Status based on upload (Simple rule: Uploading evidence makes it "Pending Review" or "Compliant")
        # For now, let's mark as "Pending_Evidence_Review"
        
        db = get_database()
        
        # Update AssetCompliance document in DB
        # We need to find the specific compliance record for this asset + control
        # Since we don't have a dedicated collection for AssetCompliance yet (it's often in Asset or computed),
        # we will store it in a new collection 'compliance_evidence' OR update the Asset's meta.
        
        # Let's verify how frontend expects it. Frontend expects `complianceData` array.
        # We will update/insert into 'asset_compliance' collection.
        
        await db.asset_compliance.update_one(
            {"assetId": asset_id, "controlId": control_id},
            {
                "$set": {
                    "status": "Pending_Review",
                    "lastUpdated": datetime.now(timezone.utc).isoformat()
                },
                "$push": {
                    "evidence": evidence_record
                }
            },
            upsert=True
        )
        
        return {"success": True, "evidence": evidence_record}
        
    except Exception as e:
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/compliance/evidence")
async def get_all_compliance_evidence():
    """
    Fetch all AssetCompliance records from the database.
    Used to populate the dashboard with real data.
    """
    db = get_database()
    cursor = db.asset_compliance.find({})
    records = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        records.append(doc)
    return records

@router.post("/api/compliance/{framework_id}/scan")
async def trigger_framework_scan(framework_id: str, background_tasks: BackgroundTasks):
    """
    Broadcast 'Run Compliance Scan' instruction to all online agents AND
    run the server-side admin evidence collection immediately as a background task.
    """
    from datetime import datetime
    db = get_database()
    
    # 1. Find all online agents
    cursor = db.agents.find({"status": "Online"})
    online_agents = await cursor.to_list(length=1000)
    
    count = 0
    instruction_text = "Run Compliance Scan"
    timestamp = datetime.now(timezone.utc).isoformat()
    
    new_instructions = []
    for agent in online_agents:
        new_instructions.append({
            "agent_id": agent["id"],
            "instruction": instruction_text,
            "status": "pending",
            "created_at": timestamp,
            "created_by": "system_broadcast",
            "framework_target": framework_id
        })
        count += 1
        
    if new_instructions:
        await db.agent_instructions.insert_many(new_instructions)
    
    print(f"[BROADCAST] Run Compliance Scan to {count} agents for framework {framework_id}")

    # 2. ALSO run admin-level evidence collection for every registered asset
    #    as a background task so the UI gets real data immediately.
    try:
        from admin_evidence_service import run_evidence_collection_for_asset
        hostnames = [a.get("hostname") for a in online_agents if a.get("hostname")]
        
        # If no online agents, fall back to ALL registered assets
        if not hostnames:
            async for asset in db.assets.find({}, {"hostname": 1}):
                h = asset.get("hostname")
                if h:
                    hostnames.append(h)

        for hostname in set(hostnames):
            background_tasks.add_task(run_evidence_collection_for_asset, hostname, db)
            print(f"[AdminEvidence] Queued admin evidence collection for: {hostname}")
    except Exception as e:
        print(f"[WARNING] Could not queue admin evidence collection: {e}")
    
    return {
        "success": True, 
        "message": f"Scan initiated for {max(count,1)} agent(s). Admin evidence collection running in background.", 
        "agent_count": count
    }

@router.post("/api/agents/{agent_id}/compliance/scan")
async def trigger_agent_scan(agent_id: str):
    """
    Send 'Run Compliance Scan' instruction to a single agent.
    """
    from datetime import datetime
    db = get_database()
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    instruction = {
        "agent_id": agent_id,
        "instruction": "Run Compliance Scan",
        "status": "pending",
        "created_at": timestamp,
        "created_by": "user_manual_refresh",
        "priority": "high"
    }
    
    result = await db.agent_instructions.insert_one(instruction)
    
    print(f"📡 Sent 'Run Compliance Scan' to agent {agent_id}")
    
    return {
        "success": True,
        "message": "Scan instruction sent to agent",
        "instruction_id": str(result.inserted_id)
    }

@router.post("/api/agents/{agent_id}/compliance/fix")
async def trigger_compliance_fix(agent_id: str, check_name: str = Form(...)):
    """
    Send a 'Fix Compliance' instruction to a specific agent.
    """
    db = get_database()
    timestamp = datetime.now(timezone.utc).isoformat()
    
    instruction = {
        "agent_id": agent_id,
        "instruction": f"Fix Compliance: {check_name}",
        "status": "pending",
        "created_at": timestamp,
        "created_by": "user_action",
        "priority": "high"
    }
    
    await db.agent_instructions.insert_one(instruction)
    print(f"🔧 Sent Fix Instruction to {agent_id}: {check_name}")
    
    return {"success": True, "message": f"Fix instruction sent for {check_name}"}

async def process_automated_evidence(agent_hostname: str, compliance_data: dict, db):
    """
    Called by Agent Heartbeat.
    Maps agent compliance checks to Control IDs and auto-generates evidence.
    """
    print(f"🤖 Processing Auto-Compliance for {agent_hostname}...")
    
    # 1. Resolve Asset ID (assuming asset-{hostname})
    asset_id = f"asset-{agent_hostname}"
    
    # 2. Define Mappings: Check Name -> [Control IDs]
    # Check names come from agent/capabilities/compliance.py
    # EXPANDED: Now covers ALL 36 agent checks (28 Windows + 8 Linux)
    MAPPINGS = {
        # Windows Checks
        "Windows Firewall Profiles": ["A.8.22", "PCI-1.1", "PR.AC-1", "CC6.6"],
        "Windows Defender Antivirus": ["A.8.7", "PCI-5.1", "CC6.8", "DE.CM-4", "hitrust-01.0"],
        "Password Policy (Min Length)": ["A.5.15", "A.8.2", "A.8.5", "PCI-8.1.1", "PR.AC-1", "CC6.1"],
        "Password Policy": ["A.5.15", "A.8.2", "A.8.5", "PCI-8.1.1", "PR.AC-1", "CC6.1"],
        "Guest Account Disabled": ["A.5.15", "A.8.2", "PCI-8.1.1", "PR.AC-4", "CC6.1"],
        "Guest Account Status": ["A.5.15", "A.8.2"],
        "RDP NLA Required": ["A.5.15", "A.8.22", "PCI-2.2", "PR.AC-1", "CC6.6"],
        "RDP Security": ["A.5.15", "A.8.22", "PCI-2.2", "PR.AC-1"],
        "BitLocker Encryption": ["A.8.1", "A.8.24", "164.312(a)(2)(iv)", "PCI-3.4", "PR.DS-1", "CC6.1"],
        "Secure Boot": ["A.8.1", "A.8.27", "ID.AM-1", "CC7.2"],
        "Windows Update Service": ["A.8.8", "PCI-6.2", "ID.AM-1", "CC7.3", "DE.CM-6"],
        "User Access Control": ["A.5.15", "A.8.2", "PR.AC-1", "CC6.1"],
        "Audit Logging Policy": ["A.8.15", "A.8.16", "PCI-10.1", "DE.AE-1", "CC9.2", "fedramp-AU-2"],
        "Risky Network Ports": ["A.8.22", "PCI-1.1", "CC6.6", "PR.AC-5"],
        "Risky Ports (Telnet)": ["A.8.22", "PCI-1.1", "CC6.6"],
        "Risky Ports (FTP)": ["A.8.22", "PCI-1.1", "CC6.6"],
        "TLS Security Config": ["A.8.24", "PCI-4.1", "164.312(a)(2)(iv)", "CC6.7", "PR.DS-2"],
        "TLS Security Configuration": ["A.8.24", "PCI-4.1", "164.312(a)(2)(iv)", "CC6.7"],
        "Prohibited Software": ["A.8.1", "A.8.19", "ID.AM-1", "CC6.8"],
        "Maximum Password Age": ["A.8.5", "PCI-8.2", "CC6.1"],
        "Account Lockout Policy": ["A.5.15", "A.8.5", "PCI-8.1.1", "CC6.1", "PR.AC-1"],
        "Password Complexity": ["A.8.5", "PCI-8.2", "CC6.1"],
        "Password History": ["A.8.5", "PCI-8.2", "CC6.1"],
        "Minimum Password Age": ["A.8.5", "CC6.1"],
        "Remote Desktop Service": ["A.8.22", "PCI-2.2", "PR.AC-3", "CC6.6"],
        "SMBv1 Protocol Disabled": ["A.8.8", "A.8.22", "PR.IP-1", "CC7.2"],
        "SMBv1 Protocol Status": ["A.8.8", "A.8.22"],
        "LLMNR/NetBIOS Protection": ["A.8.22", "PR.AC-5", "CC6.7"],
        "LLMNR Protection": ["A.8.22", "PR.AC-5", "CC6.7"],
        "PowerShell Script Block Logging": ["A.8.15", "DE.CM-1", "CC9.2", "fedramp-AU-2"],
        "PowerShell Logging": ["A.8.15", "DE.CM-1", "CC9.2", "fedramp-AU-2"],
        "WinRM Service Status": ["A.8.22", "PCI-2.2", "PR.AC-3"],
        "WinRM Status": ["A.8.22", "PCI-2.2", "PR.AC-3"],
        "Credential Guard": ["A.5.15", "A.8.1", "PR.AC-1", "CC6.1"],
        "Device Guard/WDAC": ["A.8.1", "A.8.3", "PR.IP-1", "CC7.2"],
        "Device Guard": ["A.8.1", "A.8.3", "PR.IP-1", "CC7.2"],
        "Exploit Protection (DEP/ASLR)": ["A.8.1", "A.8.8", "PR.IP-1", "CC7.2"],
        "Exploit Protection (DEP)": ["A.8.1", "A.8.8", "PR.IP-1", "CC7.2"],
        "Exploit Protection": ["A.8.1", "A.8.8", "PR.IP-1", "CC7.2"],
        "Attack Surface Reduction": ["A.8.1", "A.8.7", "PR.IP-1", "CC7.2"],
        "Controlled Folder Access": ["A.8.1", "A.8.23", "PR.DS-1", "CC6.1"],
        "Idle Timeout (Screensaver)": ["A.7.7", "A.8.11", "PR.AC-1", "CC6.1"],
        "USB Mass Storage Access": ["A.7.10", "A.8.3", "PCI-3.4", "CC6.6"],
        "Local Administrator Auditing": ["A.5.15", "A.8.2", "PR.AC-4", "PCI-7.1", "CC6.1"],
        
        # Linux Checks
        "UFW Firewall Enabled": ["A.8.22", "PCI-1.1", "PR.AC-5", "CC6.6"],
        "Firewall Status": ["A.8.22", "PCI-1.1", "PR.AC-5", "CC6.6"],
        "SSH Root Login Disabled": ["A.5.15", "A.8.22", "PCI-2.2", "PR.AC-4", "CC6.1"],
        "SSH Configuration": ["A.5.15", "A.8.22", "PCI-2.2", "PR.AC-4", "CC6.1"],
        "Automatic Security Updates": ["A.8.8", "PCI-6.2", "CC7.3"],
        "Automatic Updates": ["A.8.8", "PCI-6.2", "CC7.3"],
        "SELinux Status": ["A.5.15", "A.8.1", "PR.AC-4", "CC6.1"],
        "AppArmor Status": ["A.5.15", "A.8.1", "PR.AC-4", "CC6.1"],
        "MAC (SELinux/AppArmor)": ["A.5.15", "A.8.1", "PR.AC-4", "CC6.1"],
        "MAC Status": ["A.5.15", "A.8.1", "PR.AC-4", "CC6.1"],
        "Sudo Configuration": ["A.5.15", "A.8.2", "PR.AC-4", "CC6.1"],
        "Cron Security": ["A.8.11", "A.8.2", "PR.AC-4", "CC6.1"],
        "SSHD Hardening": ["A.8.22", "PCI-2.2", "PR.AC-5", "CC6.6"],
        "Filesystem Permissions": ["A.5.15", "A.8.3", "PR.AC-4", "CC6.1"],
        
        # DPDP Checks
        "DPDP-5.1 Consent Artifacts": ["DPDP-5.1"],
        "DPDP-8.4 Data Retention Policy": ["DPDP-8.4"],
        "DPDP-8.5 Breach Notification": ["DPDP-8.5"],
        "DPDP-9.1 Child Data Age-Gating": ["DPDP-9.1"],
        "DPDP-10.1 SDF Audit Status": ["DPDP-10.1"],
        
        # CSA STAR / FedRAMP
        "Cloud Instance Metadata": ["csa-IVS-06", "fedramp-AC-3"],
        "Public IP Exposure": ["csa-IVS-06", "fedramp-AC-3", "ccpa-Security-1"],
        
        # CCPA / GDPR / HIPAA
        "PII Data Discovery": ["A.5.34", "ccpa-Privacy-1", "Art.5(1)(c)", "164.312(a)(2)(iv)"],
        "Unencrypted PII": ["A.5.34", "ccpa-Security-1", "164.312(a)(2)(iv)", "fedramp-SI-2"],
        
        # CMMC / PCI
        "File Integrity Monitoring": ["A.8.16", "cmmc-SI.L2-3.14.1", "PCI-11.2"],
        "FIM Status": ["A.8.16", "cmmc-SI.L2-3.14.1", "PCI-11.2"],
        
        # DORA / FedRAMP
        "Log Shipping Status": ["A.8.15", "dora-Art9", "fedramp-AU-2", "PCI-10.1"],
        "SIEM Forwarding": ["A.8.15", "dora-Art9", "fedramp-AU-2", "DE.AE-1"],
        
        # COBIT / General
        "Configuration Audit": ["A.8.9", "cobit-DSS05", "fedramp-CM-6"],
        "Registry Baseline": ["A.8.9", "cobit-DSS05", "fedramp-CM-6"],
        
        # --- COMPREHENSIVE THEME CHECKS ---
        "Data Backup & Recovery Simulation": ["iso9001-7.5", "RC.CO-2", "PR.IP-4", "A.8.13", "hitrust-09.0", "RC.CO-3", "RC.CO-1", "A.8.14", "PCI-9.5"],
        "Information Deletion & Disposal Simulation": ["A.8.10", "ccpa-Privacy-2", "ccpa-Privacy-3", "PCI-9.1", "PR.DS-3", "PCI-3.1"],
        "Cryptographic Controls Extension Simulation": ["hitrust-06.0", "PR.DS-2", "Art.32(1)(b)", "CC6.1", "Art.32(1)(a)", "PR.DS-1", "CC6.7", "A.8.24"],
        "Secure Development & Coding Simulation": ["A.8.29", "A.8.30", "A.8.26", "A.8.25", "PR.IP-2", "CC7.1", "PCI-6.1", "PCI-6.3", "CC8.1", "A.8.31", "A.8.28"],
        "Change Management Simulation": ["A.8.32", "PCI-6.4", "CC8.1", "PR.IP-3"],
        "Clock Synchronization Simulation": ["A.8.17", "PCI-10.2", "PR.PT-1"],
        "Capacity Management Simulation": ["CC7.2", "A.8.6", "PR.DS-4"],
        "Network Security & Segregation Simulation": ["A.8.21", "PCI-1.3", "A.8.22", "A.8.20", "PCI-1.2", "PR.AC-5"],
        "Access to Source Code Simulation": ["PR.AC-4", "A.8.4"],
        "Utility Programs & Audit Tools Simulation": ["A.8.34", "PR.PT-3", "A.8.18"],
        "Data Leakage Prevention Simulation": ["PCI-12.1", "PR.DS-5", "A.8.12"],
    
        
        # ── CISSP-specific check mappings ──────────────────────────────────────
        # Domain 1: Security & Risk Management
        "Admin Check: BitLocker Encryption":          ["CISSP-3.3"],
        "Admin Check: Windows Firewall Profiles":     ["CISSP-4.2"],
        "Admin Check: Windows Defender Antivirus":    ["CISSP-7.5"],
        "Admin Check: Password Policy (Min Length)": ["CISSP-5.2"],
        "Admin Check: Clock Synchronization Simulation": ["CISSP-7.2"],
        "Admin Check: Cryptographic Controls Extension Simulation": ["CISSP-3.3"],
        "Admin Check: Capacity Management Simulation": ["CISSP-7.4"],
        "Admin Check: Data Backup & Recovery Simulation": ["CISSP-7.4"],
        "Admin Check: Audit Logging Extension Simulation": ["CISSP-6.4", "CISSP-7.2"],
        "Admin Check: PowerShell Script Block Logging": ["CISSP-6.4", "CISSP-7.2"],
        "Admin Check: Security Patch Status":         ["CISSP-3.6", "CISSP-6.2", "CISSP-7.3"],
        "Admin Check: SMBv1 Protocol Disabled":       ["CISSP-3.2", "CISSP-4.3"],
        "Admin Check: Risky Network Ports":           ["CISSP-4.2", "CISSP-4.4"],
        "Admin Check: RDP NLA Required":              ["CISSP-4.3", "CISSP-5.2"],
        "Admin Check: Guest Account Disabled":        ["CISSP-5.1", "CISSP-5.4"],
        "Admin Check: Local Administrator Accounts":  ["CISSP-5.4"],
        "Admin Check: Software Supply Chain Security": ["CISSP-8.4"],
    }

    timestamp = datetime.now(timezone.utc).isoformat()
    
    for check in compliance_data.get('compliance_checks', []):
        check_name = check.get('check')
        status = check.get('status') # Pass / Fail
        details = check.get('details')
        
        # Determine Compliance Status
        if status == "Pass":
            compliance_status = "Compliant"
        elif status == "Warning":
            compliance_status = "Warning"
        else:
            compliance_status = "Non-Compliant"
        
        # See if this check maps to any controls
        target_controls = MAPPINGS.get(check_name, [])
        
        if not target_controls:
            continue
            
        for raw_control_id in target_controls:
            # Strip framework prefixes to match frontend expectations
            control_id = raw_control_id
            # Strip framework prefixes to match frontend expectations
            control_id = raw_control_id
            for prefix in ["nistcsf-", "pci-dss-", "iso27001-", "hipaa-", "gdpr-", "dpdp-", "fedramp-", "ccpa-", "hitrust-", "cmmc-", "csa-", "cobit-", "dora-"]:
                if control_id.startswith(prefix):
                    control_id = control_id[len(prefix):]
                    break
                if control_id.startswith(prefix):
                    control_id = control_id[len(prefix):]
                    break
            
            # Generate Evidence Record
            evidence_id = f"auto-ev-{agent_hostname}-{control_id}-{timestamp}"
            
            # Create Markdown formatted evidence matching user request
            evidence_content = f"""# System Compliance Evidence
**Date:** {timestamp}
**Asset:** {agent_hostname}
**Control:** {control_id}
**Check Name:** {check_name}

## 1. Check Status
**Result:** {status}
**Details:** {details}

## 2. Automated Command Output
"""
            
            # Enrich with raw content if available (from agent enhancement)
            raw_content = check.get('evidence_content')
            if raw_content:
                # Simple heuristic for code block type
                lang = "json" if raw_content.strip().startswith("{") or raw_content.strip().startswith("[") else "text"
                evidence_content += f"```{lang}\n{raw_content}\n```"
            else:
                evidence_content += "*No raw command output captured.*"
            
            # --- Integrity Verification ---
            agent_hash = check.get('content_hash')
            if agent_hash:
                import hashlib
                # Verify
                server_hash = hashlib.sha256(raw_content.encode('utf-8')).hexdigest() if raw_content else "N/A"
                match = (agent_hash == server_hash)
                
                verification_text = "✅ Verified (Content Matches Agent Hash)" if match else f"❌ TAMPERING DETECTED (Agent: {agent_hash[:8]}... vs Server: {server_hash[:8]}...)"
                
                evidence_content += f"""

## 3. Evidence Integrity
**Agent Hash (SHA256):** `{agent_hash}`
**Backend Verification:** {verification_text}
"""
            else:
                 evidence_content += "\n\n## 3. Evidence Integrity\n*Integrity hash not provided by agent.*"
            
            evidence_record = {
                "id": evidence_id,
                "name": f"System Check: {check_name}",
                "url": "#", # System evidence doesn't necessarily have a file URL, or could generate one
                "type": "application/json",
                "uploadedAt": timestamp,
                "assetId": asset_id,
                "controlId": control_id,
                "systemGenerated": True,
                "content": evidence_content
            }
            
            # Deduplication: Remove existing evidence for this specific check name before adding the new one.
            # This ensures we only keep the latest result for "System Check: X"
            await db.asset_compliance.update_one(
                {"assetId": asset_id, "controlId": control_id},
                {"$pull": {"evidence": {"name": f"System Check: {check_name}"}}}
            )
            
            # Upsert into DB
            await db.asset_compliance.update_one(
                {"assetId": asset_id, "controlId": control_id},
                {
                    "$set": {
                        "status": compliance_status,
                        "checkName": check_name,  # Store original check name for remediation
                        "lastUpdated": timestamp,
                        "lastAutomatedCheck": timestamp
                    },
                    "$push": {
                        "evidence": evidence_record
                    }
                },
                upsert=True
            )
            print(f"✅ Auto-mapped {check_name} -> {control_id} ({compliance_status})")
@router.get("/api/compliance")
async def get_compliance_frameworks():
    """
    Fetch all compliance frameworks
    
    Note: Frameworks are treated as public configuration data (ISO 27001, SOC 2, etc.)
    Individual controls and evidence access remain protected via other endpoints
    """
    db = get_database()
    
    # Frameworks are global/shared across all tenants
    from tenant_context import get_tenant_id
    tid = get_tenant_id()
    print(f"[DEBUG] get_compliance_frameworks - Tenant ID: {tid}")
    frameworks = await db.compliance_frameworks.find({}, {"_id": 0}).to_list(length=100)
    
    # Sort alphabetically by name
    frameworks.sort(key=lambda x: x.get("name", ""))
    
    print(f"[DEBUG] GET /api/compliance - returning {len(frameworks)} frameworks for {tid}")
    
    # If no frameworks exist, return empty list
    # Admin should run seed_compliance.py to populate frameworks
    if not frameworks:
        print("[WARNING] No compliance frameworks found in database. Run: python backend/seed_compliance.py")
        
    return frameworks

@router.post("/api/compliance/{framework_id}/controls")
async def add_compliance_control(framework_id: str, control: dict):
    """Add a new control to a framework"""
    db = get_database()
    
    # Validate payload
    if not control.get("id") or not control.get("name"):
        raise HTTPException(status_code=400, detail="Control ID and Name are required")
        
    # Ensure control has necessary fields
    new_control = {
        "id": control["id"],
        "name": control["name"],
        "description": control.get("description", ""),
        "category": control.get("category", "General"),
        "status": "Not Implemented",
        "lastReviewed": datetime.now(timezone.utc).date().isoformat(),
        "evidence": []
    }
    
    result = await db.compliance_frameworks.update_one(
        {"id": framework_id},
        {"$push": {"controls": new_control}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Framework not found")
        
    return new_control

@router.post("/api/compliance/{framework_id}/import")
async def import_compliance_controls_csv(framework_id: str, file: UploadFile = File(...)):
    """Import controls from a CSV file"""
    import csv
    import io
    
    db = get_database()
    
    # 1. Read file
    content = await file.read()
    decoded = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))
    
    new_controls = []
    
    for row in reader:
        # Expected headers: ID, Name, Description, Category
        # Allow some flexibility
        cid = row.get("ID") or row.get("id")
        name = row.get("Name") or row.get("name")
        desc = row.get("Description") or row.get("description") or ""
        cat = row.get("Category") or row.get("category") or "Imported"
        
        if cid and name:
            new_controls.append({
                "id": cid.strip(),
                "name": name.strip(),
                "description": desc.strip(),
                "category": cat.strip(),
                "status": "Not Implemented",
                "lastReviewed": datetime.now(timezone.utc).date().isoformat(),
                "evidence": []
            })
            
    if not new_controls:
        raise HTTPException(status_code=400, detail="No valid controls found in CSV")
        
    # 2. Update DB
    result = await db.compliance_frameworks.update_one(
        {"id": framework_id},
        {"$push": {"controls": {"$each": new_controls}}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Framework not found")
        
    return {"status": "success", "count": len(new_controls)}

 

from compliance_reporting_service import compliance_reporting_service
from fastapi import Request
from tenant_context import get_tenant_id

@router.post("/api/compliance/reports/generate")
async def generate_compliance_report(
    framework_id: str = Form(...)
):
    """Generate CSV compliance report"""
    tenant_id = get_tenant_id() or "platform-admin"
    
    try:
        report = await compliance_reporting_service.generate_report(tenant_id, framework_id)
        return {"success": True, "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/compliance/reports/generate/excel")
async def generate_excel_compliance_report(
    framework_id: str = Form(...)
):
    """Generate Excel compliance report with professional formatting"""
    tenant_id = get_tenant_id() or "platform-admin"
    
    try:
        report = await compliance_reporting_service.generate_excel_report(tenant_id, framework_id)
        return {"success": True, "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/compliance/reports/generate/pdf")
async def generate_pdf_compliance_report(
    framework_id: str = Form(...)
):
    """Generate PDF compliance report"""
    tenant_id = get_tenant_id() or "platform-admin"
    
    try:
        report = await compliance_reporting_service.generate_pdf_report(tenant_id, framework_id)
        return {"success": True, "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/compliance/reports/download/{filename}")
async def download_compliance_report(filename: str):
    """Download compliance report with proper Content-Disposition header"""
    from fastapi.responses import FileResponse
    
    reports_dir = "static/reports"
    file_path = os.path.join(reports_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Determine media type based on file extension
    if filename.endswith('.pdf'):
        media_type = 'application/pdf'
    elif filename.endswith('.xlsx'):
        media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif filename.endswith('.csv'):
        media_type = 'text/csv'
    else:
        media_type = 'application/octet-stream'
    
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/api/compliance/reports")
async def list_compliance_reports():
    """List all compliance reports (CSV, Excel, PDF)"""
    reports_dir = "static/reports"
    if not os.path.exists(reports_dir):
        return []
        
    files = os.listdir(reports_dir)
    reports = []
    for f in files:
        if f.endswith((".csv", ".xlsx", ".pdf")):
            reports.append({
                "filename": f,
                "url": f"/api/compliance/reports/download/{f}",
                "created": datetime.fromtimestamp(os.path.getctime(os.path.join(reports_dir, f))).isoformat()
            })
    reports.sort(key=lambda x: x["created"], reverse=True)
    return reports


@router.get("/api/compliance/evidence/download/{evidence_id}")
async def download_compliance_evidence(evidence_id: str):
    """
    Download a specific piece of evidence.
    - If file-based: Serves the file with Content-Disposition.
    - If system-generated: Generates a text file with the evidence content.
    """
    from fastapi.responses import FileResponse, Response
    db = get_database()
    
    # 1. Find the evidence record
    # Evidence is embedded in asset_compliance documents.
    # We need to search for the doc containing this evidence ID.
    pipeline = [
        {"$unwind": "$evidence"},
        {"$match": {"evidence.id": evidence_id}},
        {"$project": {"evidence": 1, "_id": 0}}
    ]
    
    cursor = db.asset_compliance.aggregate(pipeline)
    result = await cursor.to_list(length=1)
    
    if not result:
        raise HTTPException(status_code=404, detail="Evidence not found")
        
    evidence = result[0]['evidence']
    
    # 2. Handle System Generated Evidence
    if evidence.get('systemGenerated') or evidence.get('url') == '#':
        content = evidence.get('content') or evidence.get('details') or "No details available."
        content = evidence.get('content') or evidence.get('details') or "No details available."
        filename = f"{evidence['name'].replace(' ', '_').replace(':', '')}.md"
        
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
        
    # 3. Handle File Uploads
    # Try to extract filename from URL or use name
    file_url = evidence.get('url', '')
    filename = os.path.basename(file_url) if file_url.startswith('http') else evidence.get('name')
    
    # We assume standard upload location
    # If URL is http://localhost:5000/static/evidence/filename.ext
    # We look in static/evidence/filename.ext
    
    possible_filename = os.path.basename(file_url)
    file_path = os.path.join(UPLOAD_DIR, possible_filename)
    
    if not os.path.exists(file_path):
        # Fallback: try using the 'name' field if the URL path doesn't exist
        fallback_path = os.path.join(UPLOAD_DIR, evidence.get('name'))
        if os.path.exists(fallback_path):
            file_path = fallback_path
        else:
            raise HTTPException(status_code=404, detail="Evidence file not found on server")
            
    return FileResponse(
        file_path,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("/api/assets/{asset_id}/compliance")
async def get_asset_compliance(asset_id: str):
    """
    Get compliance evidence for a specific asset
    """
    db = get_database()
    
    # Allow querying by assetId (CamelCase) or asset_id (snake_case)
    # The DB seems to use assetId based on scan_out.txt
    cursor = db.asset_compliance.find(
        {"$or": [
            {"assetId": asset_id}, 
            {"asset_id": asset_id},
            {"assetId": f"asset-{asset_id}"} # Handle prefix mismatch
        ]},
        {"_id": 0}
    )
    
    results = await cursor.to_list(length=1000)
    return results
