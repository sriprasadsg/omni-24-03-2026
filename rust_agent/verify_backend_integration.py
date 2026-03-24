import json
import os
import datetime

# 1. Load Rust Agent Report
try:
    with open("d:/Downloads/enterprise-omni-agent-ai-platform/rust_agent/compliance_report.json", "r") as f:
        report = json.load(f)
        print("Loaded compliance_report.json")
except Exception as e:
    print(f"Error loading report: {e}")
    exit(1)

# 2. Replicate Backend Mappings (Updated)
MAPPINGS = {
    # Windows Checks (28 checks)
    "Windows Firewall Profiles": ["pci-dss-PCI-1.1.1", "nistcsf-PR.AC-1", "CC6.6", "PCI-1.1", "iso27001-A.13.1"],
    "Windows Defender Antivirus": ["iso27001-A.12.2.1", "pci-dss-PCI-5.1", "CC6.8", "iso27001-A.8.7", "nistcsf-DE.CM-4"],
    "Password Policy (Min Length)": ["iso27001-A.9.4.3", "pci-dss-PCI-8.1.1", "nistcsf-PR.AC-1", "iso27001-A.9.4.1", "CC6.1", "nistcsf-IA-5"],
    "Password Policy": ["iso27001-A.9.4.3", "pci-dss-PCI-8.1.1", "nistcsf-PR.AC-1", "iso27001-A.9.4.1", "CC6.1"],
    "Guest Account Disabled": ["iso27001-A.9.2.1", "pci-dss-PCI-8.1.1", "nistcsf-PR.AC-4", "CC6.1"],
    "Guest Account Status": ["iso27001-A.9.2.1", "pci-dss-PCI-8.1.1"],
    "RDP NLA Required": ["pci-dss-PCI-2.2.4", "nistcsf-PR.AC-1", "CC6.6", "iso27001-A.9.4.2"],
    "RDP Security": ["pci-dss-PCI-2.2.4", "nistcsf-PR.AC-1", "CC6.6"],
    "BitLocker Encryption": ["hipaa-164.312(a)(2)(iv)", "pci-dss-PCI-3.4", "iso27001-A.8.12", "nistcsf-PR.DS-1", "PCI-3.4", "CC6.1"],
    "Secure Boot": ["nistcsf-ID.AM-1", "iso27001-A.12.1.2", "CC7.2"],
    "Windows Update Service": ["pci-dss-PCI-6.2", "iso27001-A.12.6.1", "nistcsf-ID.AM-1", "CC7.3", "nistcsf-DE.CM-8"],
    "User Access Control": ["nistcsf-PR.AC-1", "iso27001-A.9.4.1", "CC6.1"],
    "Audit Logging Policy": ["pci-dss-PCI-10.1", "nistcsf-DE.AE-1", "iso27001-A.12.4.1", "CC9.2", "PCI-10.1", "nistcsf-DE.CM-1", "nistcsf-AU-2"],
    "Risky Network Ports": ["pci-dss-PCI-1.1", "iso27001-A.13.1", "CC6.6", "nistcsf-PR.AC-5"],
    "Risky Ports (Telnet)": ["pci-dss-PCI-1.1", "iso27001-A.13.1", "CC6.6", "nistcsf-PR.AC-5"],
    "Risky Ports (FTP)": ["pci-dss-PCI-1.1", "iso27001-A.13.1", "CC6.6", "nistcsf-PR.AC-5"],
    "TLS Security Config": ["pci-dss-PCI-4.1", "hipaa-164.312(a)(2)(iv)", "CC6.7", "PCI-4.1", "nistcsf-PR.DS-2", "iso27001-A.10.1"],
    "TLS Security Configuration": ["pci-dss-PCI-4.1", "hipaa-164.312(a)(2)(iv)", "CC6.7", "PCI-4.1", "nistcsf-PR.DS-2", "iso27001-A.10.1"],
    "Prohibited Software": ["iso27001-A.12.5", "iso27001-A.12.6.2", "nistcsf-ID.AM-1", "CC6.8"],
    "Maximum Password Age": ["nistcsf-IA-5", "iso27001-A.8.5", "pci-dss-PCI-8.2.4", "CC6.1"],
    "Account Lockout Policy": ["nistcsf-PR.AC-7", "pci-dss-PCI-8.1.6", "iso27001-A.9.4.2", "CC6.1", "nistcsf-AC-7"],
    "Password Complexity": ["nistcsf-IA-5", "iso27001-A.8.5", "pci-dss-PCI-8.2.3", "CC6.1"],
    "Password History": ["pci-dss-PCI-8.2.5", "nistcsf-IA-5", "iso27001-A.8.5", "CC6.1"],
    "Minimum Password Age": ["nistcsf-IA-5", "iso27001-A.8.5", "CC6.1"],
    "Remote Desktop Service": ["pci-dss-PCI-2.2.2", "nistcsf-PR.AC-3", "CC6.6"],
    "SMBv1 Protocol Disabled": ["CVE-2017-0143", "nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.6.1"],
    "SMBv1 Protocol Status": ["CVE-2017-0143", "nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.6.1"],
    "LLMNR/NetBIOS Protection": ["nistcsf-PR.AC-5", "iso27001-A.13.1", "CC6.7"],
    "LLMNR Protection": ["nistcsf-PR.AC-5", "iso27001-A.13.1", "CC6.7"],
    "PowerShell Script Block Logging": ["nistcsf-DE.CM-1", "iso27001-A.12.4.1", "CC9.2", "nistcsf-AU-2"],
    "PowerShell Logging": ["nistcsf-DE.CM-1", "iso27001-A.12.4.1", "CC9.2", "nistcsf-AU-2"],
    "WinRM Service Status": ["pci-dss-PCI-2.2.2", "nistcsf-PR.AC-3"],
    "WinRM Status": ["pci-dss-PCI-2.2.2", "nistcsf-PR.AC-3"],
    "Credential Guard": ["nistcsf-PR.AC-1", "CC6.1", "iso27001-A.9.4.1"],
    "Device Guard/WDAC": ["nistcsf-PR.IP-1", "iso27001-A.12.5", "CC7.2"],
    "Device Guard": ["nistcsf-PR.IP-1", "iso27001-A.12.5", "CC7.2"],
    "Exploit Protection (DEP/ASLR)": ["nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.6.1"],
    "Exploit Protection (DEP)": ["nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.6.1"],
    "Exploit Protection": ["nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.6.1"],
    "Attack Surface Reduction": ["nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.2.1"],
    "Controlled Folder Access": ["nistcsf-PR.DS-1", "CC6.1", "iso27001-A.12.3.1"],
    "DPDP-5.1 Consent Artifacts": ["dpdp-DPDP-5.1"],
    "DPDP-8.4 Data Retention Policy": ["dpdp-DPDP-8.4"],
    "DPDP-8.5 Breach Notification": ["dpdp-DPDP-8.5"],
    "DPDP-9.1 Child Data Age-Gating": ["dpdp-DPDP-9.1"],
    "DPDP-10.1 SDF Audit Status": ["dpdp-DPDP-10.1"],
}

generated_evidence = []
agent_hostname = "test-agent-host"
timestamp = datetime.datetime.now().isoformat()

os.makedirs("evidence_proof", exist_ok=True)

# 3. Process Logic
for check in report.get("compliance_checks", []):
    check_name = check.get('check')
    status = check.get('status')
    details = check.get('details')
    
    target_controls = MAPPINGS.get(check_name, [])
    
    if not target_controls:
        print(f"Skipping unmapped check: {check_name}")
        continue
        
    for raw_control_id in target_controls:
        control_id = raw_control_id
        for prefix in ["nistcsf-", "pci-dss-", "iso27001-", "hipaa-", "gdpr-", "dpdp-"]:
            if control_id.startswith(prefix):
                control_id = control_id[len(prefix):]
                break
        
        # Generate Markdown
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
        raw_content = check.get('evidence_content', "")
        lang = "json" if raw_content.strip().startswith("{") or raw_content.strip().startswith("[") else "text"
        evidence_content += f"```{lang}\n{raw_content}\n```"
        
        evidence_content += "\n\n## 3. Evidence Integrity\n*Integrity hash not provided by agent.*"
        
        filename = f"evidence_proof/{control_id}_{check_name.replace(' ', '_').replace('/', '-')}.md"
        with open(filename, "w") as f:
            f.write(evidence_content)
            
        generated_evidence.append({
            "control": control_id,
            "check": check_name,
            "file": filename,
            "status": status
        })

print(f"Generated {len(generated_evidence)} evidence files.")

# 4. Generate HTML Index
html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Evidence Attachment Verification</title>
    <style>
        body { font-family: sans-serif; padding: 20px; }
        .evidence-item { border: 1px solid #ccc; padding: 10px; margin: 10px 0; border-radius: 5px; }
        .Pass { border-left: 5px solid green; }
        .Fail { border-left: 5px solid red; }
        .Warning { border-left: 5px solid orange; }
        a { text-decoration: none; color: #007bff; font-weight: bold; }
    </style>
</head>
<body>
    <h1>Generated Compliance Evidence Attachments</h1>
    <p>This page simulates the backend integration, showing the Markdown attachments generated for each control.</p>
"""

for item in generated_evidence:
    rel_path = item['file']
    html_content += f"""
    <div class="evidence-item {item['status']}">
        <h3>Control: {item['control']}</h3>
        <p>Check: {item['check']}</p>
        <p>Startus: {item['status']}</p>
        <a href="{rel_path}" target="_blank">View Attachment ({os.path.basename(rel_path)})</a>
    </div>
    """

html_content += "</body></html>"

with open("evidence_integration_test.html", "w") as f:
    f.write(html_content)

print("Created evidence_integration_test.html")
