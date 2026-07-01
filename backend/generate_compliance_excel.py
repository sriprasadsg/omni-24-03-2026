import pandas as pd
import sys
import os

# Add parent directory to access backend modules
sys.path.insert(0, os.path.abspath('.'))

try:
    from compliance_endpoints import process_automated_evidence
    import inspect
    
    # Extract the MAPPINGS dictionary from the source code of process_automated_evidence
    source = inspect.getsource(process_automated_evidence)
    mappings_str = source.split('MAPPINGS = {')[1].split('}')[0]
    
    # Alternatively, just hardcode the enrichment for the Excel generation to be foolproof
    # We will enrich our existing list with the exact IDs from the codebase
    control_mappings = {
        "Windows Firewall Profiles": ["pci-dss-PCI-1.1.1", "nistcsf-PR.AC-1", "CC6.6", "PCI-1.1", "iso27001-A.13.1"],
        "Windows Defender Antivirus": ["iso27001-A.12.2.1", "pci-dss-PCI-5.1", "CC6.8", "iso27001-A.8.7", "nistcsf-DE.CM-4"],
        "Password Policy (Min Length)": ["iso27001-A.9.4.3", "pci-dss-PCI-8.1.1", "nistcsf-PR.AC-1", "iso27001-A.9.4.1", "CC6.1", "nistcsf-IA-5"],
        "Maximum Password Age": ["nistcsf-IA-5", "iso27001-A.8.5", "pci-dss-PCI-8.2.4", "CC6.1"],
        "Minimum Password Age": ["nistcsf-IA-5", "iso27001-A.8.5", "CC6.1"],
        "Password History": ["pci-dss-PCI-8.2.5", "nistcsf-IA-5", "iso27001-A.8.5", "CC6.1"],
        "Account Lockout Policy": ["nistcsf-PR.AC-7", "pci-dss-PCI-8.1.6", "iso27001-A.9.4.2", "CC6.1", "nistcsf-AC-7"],
        "Guest Account Disabled": ["iso27001-A.9.2.1", "pci-dss-PCI-8.1.1", "nistcsf-PR.AC-4", "CC6.1"],
        "RDP NLA Required": ["pci-dss-PCI-2.2.4", "nistcsf-PR.AC-1", "CC6.6", "iso27001-A.9.4.2"],
        "Remote Desktop Service": ["pci-dss-PCI-2.2.2", "nistcsf-PR.AC-3", "CC6.6"],
        "BitLocker Encryption": ["hipaa-164.312(a)(2)(iv)", "pci-dss-PCI-3.4", "iso27001-A.8.12", "nistcsf-PR.DS-1", "PCI-3.4", "CC6.1"],
        "Secure Boot": ["nistcsf-ID.AM-1", "iso27001-A.12.1.2", "CC7.2"],
        "Windows Update Service": ["pci-dss-PCI-6.2", "iso27001-A.12.6.1", "nistcsf-ID.AM-1", "CC7.3", "nistcsf-DE.CM-8"],
        "User Access Control": ["nistcsf-PR.AC-1", "iso27001-A.9.4.1", "CC6.1"],
        "Audit Logging Policy": ["pci-dss-PCI-10.1", "nistcsf-DE.AE-1", "iso27001-A.12.4.1", "CC9.2", "PCI-10.1", "nistcsf-DE.CM-1", "nistcsf-AU-2"],
        "Risky Network Ports": ["pci-dss-PCI-1.1", "iso27001-A.13.1", "CC6.6", "nistcsf-PR.AC-5"],
        "TLS Security Config": ["pci-dss-PCI-4.1", "hipaa-164.312(a)(2)(iv)", "CC6.7", "PCI-4.1", "nistcsf-PR.DS-2", "iso27001-A.10.1"],
        "SMBv1 Protocol Disabled": ["CVE-2017-0143", "nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.6.1"],
        "LLMNR/NetBIOS Protection": ["nistcsf-PR.AC-5", "iso27001-A.13.1", "CC6.7"],
        "PowerShell Script Block Logging": ["nistcsf-DE.CM-1", "iso27001-A.12.4.1", "CC9.2", "nistcsf-AU-2"],
        "WinRM Service Status": ["pci-dss-PCI-2.2.2", "nistcsf-PR.AC-3"],
        "Credential Guard": ["nistcsf-PR.AC-1", "CC6.1", "iso27001-A.9.4.1"],
        "Device Guard/WDAC": ["nistcsf-PR.IP-1", "iso27001-A.12.5", "CC7.2"],
        "Exploit Protection (DEP/ASLR)": ["nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.6.1"],
        "Attack Surface Reduction": ["nistcsf-PR.IP-1", "CC7.2", "iso27001-A.12.2.1"],
        "Controlled Folder Access": ["nistcsf-PR.DS-1", "CC6.1", "iso27001-A.12.3.1"],
        "Idle Timeout (Screensaver)": ["pci-dss-PCI-8.1.8", "nistcsf-PR.AC-7", "iso27001-A.11.2.8", "CC6.1"],
        "USB Mass Storage Access": ["iso27001-A.8.3", "pci-dss-PCI-3.4", "nistcsf-PR.PT-2", "CC6.6"],
        "Local Administrator Auditing": ["nistcsf-PR.AC-4", "pci-dss-PCI-7.1", "iso27001-A.9.2.2", "CC6.1"],
        "Prohibited Software": ["iso27001-A.12.5", "iso27001-A.12.6.2", "nistcsf-ID.AM-1", "CC6.8"],
        "DPDP-5.1 Consent Artifacts": ["dpdp-5.1"],
        "DPDP-8.4 Data Retention Policy": ["dpdp-8.4"],
        "DPDP-8.5 Breach Notification": ["dpdp-8.5"],
        "DPDP-9.1 Child Data Age-Gating": ["dpdp-9.1"],
        "DPDP-10.1 SDF Audit Status": ["dpdp-10.1"],
        "Cloud Instance Metadata": ["FedRAMP-AC-2"],
        "PII Data Discovery": ["gdpr-Art32", "ccpa-1798.150"],
        "UFW Firewall Enabled": ["pci-dss-PCI-1.1.1", "nistcsf-PR.AC-5", "CC6.6", "iso27001-A.13.1"],
        "SSH Root Login Disabled": ["pci-dss-PCI-2.2.4", "nistcsf-PR.AC-4", "CC6.1", "iso27001-A.9.4.3"],
        "Automatic Security Updates": ["pci-dss-PCI-6.2", "iso27001-A.12.6.1", "nistcsf-DE.CM-8", "CC7.3"],
        
        # Organizational mappings manually defined
        "Security Awareness Training": ["iso27001-A.7.2.2", "pci-dss-PCI-12.6", "nistcsf-PR.AT-1", "CC2.2"],
        "Physical Access Controls (Badges/Cameras)": ["pci-dss-PCI-9.1.1", "iso27001-A.11.1.2", "CC6.4"],
        "Third-Party Penetration Test": ["pci-dss-PCI-11.4.1", "SOC2-CC4.1"],
        "Incident Response Plan Documentation": ["pci-dss-PCI-12.10.1", "iso27001-A.16.1.1", "CC7.3"],
        "Information Security Policy Review": ["pci-dss-PCI-12.1.2", "iso27001-A.5.1.2", "CC2.1"]
    }

except Exception as e:
    print(f"Failed to load dynamic mappings: {e}")
    control_mappings = {}

# Define the comprehensive list of controls
controls = [
    # Windows Technical Controls
    {"Control": "Windows Firewall Profiles", "Type": "Technical", "Evidence Collected": "Active Firewall Profiles (Domain, Private, Public)", "How to Update": "Automatically updated via Agent scanning system firewall state."},
    {"Control": "Windows Defender Antivirus", "Type": "Technical", "Evidence Collected": "RealTimeProtectionEnabled status via WMI", "How to Update": "Automatically updated via Agent scanning Antivirus status."},
    {"Control": "Password Policy (Min Length)", "Type": "Technical", "Evidence Collected": "net accounts minimum password length", "How to Update": "Automatically updated via Agent scanning local security policy."},
    {"Control": "Maximum Password Age", "Type": "Technical", "Evidence Collected": "net accounts maximum password age", "How to Update": "Automatically updated via Agent scanning local security policy."},
    {"Control": "Minimum Password Age", "Type": "Technical", "Evidence Collected": "net accounts minimum password age", "How to Update": "Automatically updated via Agent scanning local security policy."},
    {"Control": "Password History", "Type": "Technical", "Evidence Collected": "net accounts password history length", "How to Update": "Automatically updated via Agent scanning local security policy."},
    {"Control": "Account Lockout Policy", "Type": "Technical", "Evidence Collected": "Lockout threshold limit via net accounts", "How to Update": "Automatically updated via Agent scanning local security policy."},
    {"Control": "Guest Account Disabled", "Type": "Technical", "Evidence Collected": "Get-LocalUser Guest status", "How to Update": "Automatically updated via Agent scanning local users."},
    {"Control": "RDP NLA Required", "Type": "Technical", "Evidence Collected": "Registry check for Network Level Authentication", "How to Update": "Automatically updated via Agent scanning RDP configuration."},
    {"Control": "Remote Desktop Service", "Type": "Technical", "Evidence Collected": "TermService Windows Service Status", "How to Update": "Automatically updated via Agent scanning Windows services."},
    {"Control": "BitLocker Encryption", "Type": "Technical", "Evidence Collected": "manage-bde -status output for C: Drive", "How to Update": "Automatically updated via Agent scanning volume encryption."},
    {"Control": "Secure Boot", "Type": "Technical", "Evidence Collected": "Confirm-SecureBootUEFI PowerShell output", "How to Update": "Automatically updated via Agent query."},
    {"Control": "Windows Update Service", "Type": "Technical", "Evidence Collected": "wuauserv Windows Service Status", "How to Update": "Automatically updated via Agent scanning Windows services."},
    {"Control": "User Access Control", "Type": "Technical", "Evidence Collected": "Registry value of EnableLUA", "How to Update": "Automatically updated via Agent registry query."},
    {"Control": "Audit Logging Policy", "Type": "Technical", "Evidence Collected": "auditpol Logon/Logoff event status", "How to Update": "Automatically updated via Agent query."},
    {"Control": "Risky Network Ports", "Type": "Technical", "Evidence Collected": "netstat -an open ports list", "How to Update": "Automatically updated via Agent scanning active listening TCP/UDP ports."},
    {"Control": "TLS Security Config", "Type": "Technical", "Evidence Collected": "Registry key confirming TLS 1.0/1.1 disabled", "How to Update": "Automatically updated via Agent registry query."},
    {"Control": "SMBv1 Protocol Disabled", "Type": "Technical", "Evidence Collected": "Get-SmbServerConfiguration EnableSMB1Protocol", "How to Update": "Automatically updated via Agent query."},
    {"Control": "LLMNR/NetBIOS Protection", "Type": "Technical", "Evidence Collected": "Group policy registry checks for LLMNR", "How to Update": "Automatically updated via Agent registry query."},
    {"Control": "PowerShell Script Block Logging", "Type": "Technical", "Evidence Collected": "EnableScriptBlockLogging Registry Value", "How to Update": "Automatically updated via Agent registry query."},
    {"Control": "WinRM Service Status", "Type": "Technical", "Evidence Collected": "WinRM Windows Service Status", "How to Update": "Automatically updated via Agent scanning Windows services."},
    {"Control": "Credential Guard", "Type": "Technical", "Evidence Collected": "DeviceGuard SecurityServicesRunning status", "How to Update": "Automatically updated via Agent DeviceGuard queries."},
    {"Control": "Device Guard/WDAC", "Type": "Technical", "Evidence Collected": "CodeIntegrityPolicyEnforcementStatus", "How to Update": "Automatically updated via Agent WDAC queries."},
    {"Control": "Exploit Protection (DEP/ASLR)", "Type": "Technical", "Evidence Collected": "Get-ProcessMitigation DEP/ASLR Status", "How to Update": "Automatically updated via Agent exploit mitigation query."},
    {"Control": "Attack Surface Reduction", "Type": "Technical", "Evidence Collected": "AttackSurfaceReductionRules_Ids via PowerShell", "How to Update": "Automatically updated via Agent ASR rules query."},
    {"Control": "Controlled Folder Access", "Type": "Technical", "Evidence Collected": "EnableControlledFolderAccess via PowerShell", "How to Update": "Automatically updated via Agent CFA query."},
    {"Control": "Idle Timeout (Screensaver)", "Type": "Technical", "Evidence Collected": "Registry ScreenSaveActive and ScreenSaveTimeOut", "How to Update": "Automatically updated via Agent querying Idle Timeout registry keys."},
    {"Control": "USB Mass Storage Access", "Type": "Technical", "Evidence Collected": "Registry Start value of USBSTOR service", "How to Update": "Automatically updated via Agent USBSTOR registry query."},
    {"Control": "Local Administrator Auditing", "Type": "Technical", "Evidence Collected": "Get-LocalGroupMember Administrators list", "How to Update": "Automatically updated via Agent querying local administrators."},
    {"Control": "Prohibited Software", "Type": "Technical", "Evidence Collected": "wmic product list filtered against blacklist", "How to Update": "Automatically updated via Agent software scan."},
    {"Control": "DPDP-5.1 Consent Artifacts", "Type": "Technical", "Evidence Collected": "Directory existence and file count check", "How to Update": "Automatically updated via Agent filesystem check."},
    {"Control": "DPDP-8.4 Data Retention Policy", "Type": "Technical", "Evidence Collected": "Internal policy value verification", "How to Update": "Automatically updated via Agent config check."},
    {"Control": "DPDP-8.5 Breach Notification", "Type": "Technical", "Evidence Collected": "Admin notification email setting check", "How to Update": "Automatically updated via Agent config check."},
    {"Control": "DPDP-9.1 Child Data Age-Gating", "Type": "Technical", "Evidence Collected": "Module activation registry status", "How to Update": "Automatically updated via Agent config check."},
    {"Control": "DPDP-10.1 SDF Audit Status", "Type": "Technical", "Evidence Collected": "Independent audit log status", "How to Update": "Automatically updated via Agent config check."},
    {"Control": "Cloud Instance Metadata", "Type": "Technical", "Evidence Collected": "IMDS metadata from AWS/Azure environment", "How to Update": "Automatically updated via Agent HTTP request to IMDS."},
    {"Control": "PII Data Discovery", "Type": "Technical", "Evidence Collected": "Regex matches for SSN, Email, CC in documents", "How to Update": "Automatically updated via Agent running pii_scanner.py."},
    
    # Linux Technical Controls
    {"Control": "UFW Firewall Enabled", "Type": "Technical", "Evidence Collected": "ufw status verbose output", "How to Update": "Automatically updated via Agent executing UFW checks on Linux endpoints."},
    {"Control": "SSH Root Login Disabled", "Type": "Technical", "Evidence Collected": "sshd_config PermitRootLogin verify", "How to Update": "Automatically updated via Agent executing SSH config checks on Linux endpoints."},
    {"Control": "Automatic Security Updates", "Type": "Technical", "Evidence Collected": "unattended-upgrades conf verify", "How to Update": "Automatically updated via Agent checking update config on Linux endpoints."},

    # Non-Technical / Organizational Controls
    {"Control": "Security Awareness Training", "Type": "Organizational", "Evidence Collected": "Manual Upload (PDF Certificates, Roster)", "How to Update": "Log into the Web UI -> Navigate to Compliance Dashboard -> Select Control -> Click 'Upload Evidence' and submit PDF training logs."},
    {"Control": "Physical Access Controls (Badges/Cameras)", "Type": "Organizational", "Evidence Collected": "Manual Upload (Visitor Logs, Badge Access Reports)", "How to Update": "Log into the Web UI -> Navigate to Compliance Dashboard -> Select Control -> Click 'Upload Evidence' and submit facility logs."},
    {"Control": "Third-Party Penetration Test", "Type": "Organizational", "Evidence Collected": "Manual Upload (Pen Test Report PDF)", "How to Update": "Log into the Web UI -> Navigate to Compliance Dashboard -> Select Control -> Click 'Upload Evidence' and submit pen test assessment."},
    {"Control": "Incident Response Plan Documentation", "Type": "Organizational", "Evidence Collected": "Manual Upload (IRP Word/PDF Document)", "How to Update": "Log into the Web UI -> Navigate to Compliance Dashboard -> Select Control -> Click 'Upload Evidence' and submit incident response policy."},
    {"Control": "Information Security Policy Review", "Type": "Organizational", "Evidence Collected": "Manual Upload (Signed Management Review PDF)", "How to Update": "Log into the Web UI -> Navigate to Compliance Dashboard -> Select Control -> Click 'Upload Evidence' and submit signed policy."}
]

# Enrich the controls list with exact Control IDs
for item in controls:
    ids = control_mappings.get(item["Control"], [])
    item["Control Numbers (IDs)"] = ", ".join(ids) if ids else "N/A"

# Reorder columns to make 'Control Numbers (IDs)' the second column
df = pd.DataFrame(controls)
cols = ['Control', 'Control Numbers (IDs)', 'Type', 'Evidence Collected', 'How to Update']
df = df[cols]

df = pd.DataFrame(controls)

# Save to Excel
output_path = r'd:\Downloads\enterprise-omni-agent-ai-platform\Compliance_Controls_Matrix.xlsx'
df.to_excel(output_path, index=False, sheet_name="Compliance Mapping")

print(f"Compliance Controls Excel report generated at: {output_path}")
