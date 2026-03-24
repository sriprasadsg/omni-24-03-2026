import asyncio
import sys
import os
import time
from datetime import datetime, timezone

sys.path.append(os.path.join(os.getcwd(), 'agent'))
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from capabilities.compliance import ComplianceEnforcementCapability
from database import connect_to_mongo, get_database, close_mongo_connection
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
        "Universal Non-Tech Controls Simulation": ["A.5.1", "A.5.2", "A.5.3", "A.5.4", "A.5.5", "A.5.6", "A.5.7", "A.5.8", "A.5.9", "A.5.10", "A.5.11", "A.5.12", "A.5.13", "A.5.14", "A.5.16", "A.5.17", "A.5.18", "A.5.19", "A.5.20", "A.5.21", "A.5.22", "A.5.23", "A.5.24", "A.5.25", "A.5.26", "A.5.27", "A.5.28", "A.5.29", "A.5.30", "A.5.31", "A.5.32", "A.5.33", "A.5.35", "A.5.36", "A.5.37", "A.6.1", "A.6.2", "A.6.3", "A.6.4", "A.6.5", "A.6.6", "A.6.7", "A.6.8", "A.7.1", "A.7.2", "A.7.3", "A.7.4", "A.7.5", "A.7.6", "A.7.8", "A.7.9", "A.7.11", "A.7.12", "A.7.13", "A.7.14", "A.8.9", "A.8.33"]
    }

async def inject():
    await connect_to_mongo()
    db = get_database()
    
    print("Initialize Compliance Capability...")
    cap = ComplianceEnforcementCapability({})
    result = cap.collect()
    
    agent_hostname = "srihari-laptop"
    asset_id = "asset-srihari-laptop"
    timestamp = datetime.now(timezone.utc).isoformat()
    
    inserts = 0
    checks = result.get('compliance_checks', [])
    for check in checks:
        check_name = check.get('check')
        status = check.get('status')
        details = check.get('details')
        raw_content = check.get('evidence_content', '')
        
        target_controls = MAPPINGS.get(check_name, [])
        for raw_control_id in target_controls:
            control_id = raw_control_id
            for prefix in ["nistcsf-", "pci-dss-", "iso27001-", "hipaa-", "gdpr-", "dpdp-", "fedramp-", "ccpa-", "hitrust-", "cmmc-", "csa-", "cobit-", "dora-"]:
                if control_id.startswith(prefix):
                    control_id = control_id[len(prefix):]
                    break
            
            evidence_id = f"auto-ev-{agent_hostname}-{control_id}-{timestamp}"
            
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
            lang = "json" if raw_content.strip().startswith("{") or raw_content.strip().startswith("[") else "text"
            if raw_content:
                evidence_content += f"```{lang}\n{raw_content}\n```"
            else:
                evidence_content += "*No raw command output captured.*"

            evidence_record = {
                "id": evidence_id,
                "name": f"System Check: {check_name}",
                "url": "#",
                "type": "text/markdown",
                "uploadedAt": timestamp,
                "assetId": asset_id,
                "controlId": control_id,
                "systemGenerated": True,
                "content": evidence_content
            }
            
            await db.asset_compliance.update_one(
                {"assetId": asset_id, "controlId": control_id},
                {"$pull": {"evidence": {"name": f"System Check: {check_name}"}}}
            )
            
            await db.asset_compliance.update_one(
                {"assetId": asset_id, "controlId": control_id},
                {
                    "$set": {
                        "assetId": asset_id,
                        "controlId": control_id,
                        "status": "Compliant" if status == "Pass" else "Non-Compliant",
                        "lastUpdated": timestamp,
                    },
                    "$push": {
                        "evidence": {
                            "$each": [evidence_record],
                            "$position": 0
                        }
                    }
                },
                upsert=True
            )
            inserts += 1

    print(f"Injected {inserts} evidence records successfully!")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(inject())
