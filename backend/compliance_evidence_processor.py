"""
Processes automated compliance evidence from agent heartbeats.
Maps agent check names to framework control IDs and writes evidence records.
"""
import hashlib
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Maps agent check names → list of framework control IDs
COMPLIANCE_CHECK_MAPPINGS: dict[str, list[str]] = {
    # Windows Checks
    "Windows Firewall Profiles": [
        "A.8.22", "PCI-1.1", "PR.AC-1", "CC6.6",
        "CISSP-4.2", "SWIFT-1.1", "NIS2-21.5",
    ],
    "Windows Defender Antivirus": [
        "A.8.7", "PCI-5.1", "CC6.8", "DE.CM-4", "hitrust-01.0",
        "CISSP-7.5", "SI-3", "3.14.1", "CIS-10", "SWIFT-6.1",
    ],
    "Password Policy (Min Length)": [
        "A.5.15", "A.8.2", "A.8.5", "PCI-8.1.1", "PR.AC-1", "CC6.1",
        "CISSP-5.2", "IA-5", "3.5.1", "SWIFT-4.1", "SOX-LA-6", "NIS2-21.10",
    ],
    "Password Policy": [
        "A.5.15", "A.8.2", "A.8.5", "PCI-8.1.1", "PR.AC-1", "CC6.1",
        "CISSP-5.2", "IA-5", "3.5.1", "SWIFT-4.1", "SOX-LA-6", "NIS2-21.10",
    ],
    "Guest Account Disabled": [
        "A.5.15", "A.8.2", "PCI-8.1.1", "PR.AC-4", "CC6.1",
        "AC-2", "3.1.1", "CIS-5",
    ],
    "Guest Account Status": ["A.5.15", "A.8.2", "PCI-8.1.1", "PR.AC-4", "CC6.1", "AC-2", "3.1.1", "CIS-5", "CISSP-5.1", "CISSP-5.4"],
    "RDP NLA Required": [
        "A.5.15", "A.8.22", "PCI-2.2", "PR.AC-1", "CC6.6",
        "AC-17", "3.1.12", "CIS-4", "SWIFT-5.4", "CISSP-4.3", "CISSP-5.2",
    ],
    "RDP Security": ["A.5.15", "A.8.22", "PCI-2.2", "PR.AC-1", "AC-17"],
    "BitLocker Encryption": [
        "A.8.1", "A.8.24", "164.312(a)(2)(iv)", "PCI-3.4", "PR.DS-1", "CC6.1",
        "CISSP-3.2", "CISSP-3.3", "SC-28", "CIS-3", "SWIFT-2.1", "SOX-SA-3",
    ],
    "Secure Boot": ["A.8.1", "A.8.27", "ID.AM-1", "CC7.2"],
    "Windows Update Service": [
        "A.8.8", "PCI-6.2", "ID.AM-1", "CC7.3", "DE.CM-6",
    ],
    "Security Patch Status": [
        "A.8.8", "PCI-6.3.3", "PR.IP-12",
        "CISSP-3.6", "CISSP-6.2", "CISSP-7.3", "SI-2", "3.14.1", "CIS-7", "SWIFT-2.2", "NIS2-21.1",
    ],
    "User Access Control": ["A.5.15", "A.8.2", "PR.AC-1", "CC6.1"],
    "Audit Logging Policy": [
        "A.8.15", "A.8.16", "PCI-10.1", "DE.AE-1", "CC9.2", "fedramp-AU-2",
    ],
    "Risky Network Ports": [
        "A.8.20", "A.8.22", "PCI-1.1", "PCI-1.2", "CC6.6", "PR.AC-5",
        "SC-7", "3.13.1", "CIS-12",
    ],
    "Risky Ports (Telnet)": ["A.8.20", "A.8.22", "PCI-1.1", "PCI-1.2", "CC6.6", "SC-7", "3.13.1", "CIS-12", "CISSP-4.2", "CISSP-4.4"],
    "Risky Ports (FTP)": ["A.8.20", "A.8.22", "PCI-1.1", "PCI-1.2", "CC6.6", "SC-7", "3.13.1", "CIS-12", "CISSP-4.2", "CISSP-4.4"],
    "TLS Security Config": ["A.8.24", "PCI-4.1", "164.312(a)(2)(iv)", "CC6.7", "PR.DS-2"],
    "TLS Security Configuration": [
        "A.8.24", "PCI-4.1", "164.312(a)(2)(iv)", "CC6.7", "PR.DS-2",
        "SC-8", "NIS2-21.8", "SWIFT-2.6", "3.13.8",
    ],
    "Prohibited Software": ["A.8.1", "A.8.19", "ID.AM-1", "CC6.8", "CISSP-8.4"],
    "Maximum Password Age": ["A.8.5", "PCI-8.2", "CC6.1"],
    "Account Lockout Policy": ["A.5.15", "A.8.5", "PCI-8.1.1", "CC6.1", "PR.AC-1"],
    "Password Complexity": ["A.8.5", "PCI-8.2", "CC6.1"],
    "Password History": ["A.8.5", "PCI-8.2", "CC6.1"],
    "Minimum Password Age": ["A.8.5", "CC6.1"],
    "Remote Desktop Service": ["A.8.22", "PCI-2.2", "PR.AC-3", "CC6.6"],
    "SMBv1 Protocol Disabled": [
        "A.8.8", "A.8.22", "PR.IP-1", "CC7.2",
        "CIS-4", "3.4.2", "CISSP-3.2", "CISSP-4.3",
    ],
    "SMBv1 Protocol Status": ["A.8.8", "A.8.22", "CIS-4"],
    "LLMNR/NetBIOS Protection": ["A.8.22", "PR.AC-5", "CC6.7"],
    "LLMNR Protection": ["A.8.22", "PR.AC-5", "CC6.7"],
    "PowerShell Script Block Logging": [
        "A.8.15", "A.8.16", "DE.CM-1", "CC9.2", "fedramp-AU-2",
        "3.3.2", "CIS-8", "CISSP-6.4", "CISSP-7.2",
    ],
    "PowerShell Logging": [
        "A.8.15", "A.8.16", "DE.CM-1", "CC9.2", "fedramp-AU-2",
        "3.3.2", "CIS-8",
    ],
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
    "Local Administrator Auditing": [
        "A.5.15", "A.8.2", "PR.AC-4", "PCI-7.1", "CC6.1", "CISSP-5.4",
    ],
    "Local Administrator Accounts": [
        "A.5.15", "A.8.2", "PR.AC-4", "PCI-7.1", "CC6.1",
        "CISSP-5.4",
    ],
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
    # Comprehensive theme checks
    "Data Backup & Recovery Simulation": [
        "iso9001-7.5", "RC.CO-2", "PR.IP-4", "A.8.13", "hitrust-09.0",
        "RC.CO-3", "RC.CO-1", "A.8.14", "PCI-9.5",
        "CP-9", "3.8.9", "DORA-21.3", "CIS-11", "SOX-BR-1", "NIS2-21.3", "CISSP-7.4",
    ],
    "Information Deletion & Disposal Simulation": ["A.8.10", "ccpa-Privacy-2", "ccpa-Privacy-3", "PCI-9.1", "PR.DS-3", "PCI-3.1"],
    "Cryptographic Controls Extension Simulation": [
        "hitrust-06.0", "PR.DS-2", "Art.32(1)(b)", "CC6.1", "Art.32(1)(a)",
        "PR.DS-1", "CC6.7", "A.8.24",
        "SC-8", "NIS2-21.8", "SWIFT-2.6", "3.13.8",
    ],
    "Secure Development & Coding Simulation": ["A.8.29", "A.8.30", "A.8.26", "A.8.25", "PR.IP-2", "CC7.1", "PCI-6.1", "PCI-6.3", "CC8.1", "A.8.31", "A.8.28"],
    "Change Management Simulation": ["A.8.32", "PCI-6.4", "CC8.1", "PR.IP-3"],
    "Clock Synchronization Simulation": [
        "A.8.17", "PCI-10.2", "PR.PT-1",
        "AU-2", "3.3.1", "CISSP-7.2",
    ],
    "Capacity Management Simulation": [
        "CC7.2", "A.8.6", "PR.DS-4",
        "CP-9", "3.8.9", "CIS-11", "CISSP-7.4",
    ],
    "Network Security & Segregation Simulation": ["A.8.21", "PCI-1.3", "A.8.22", "A.8.20", "PCI-1.2", "PR.AC-5"],
    "Access to Source Code Simulation": ["PR.AC-4", "A.8.4"],
    "Utility Programs & Audit Tools Simulation": ["A.8.34", "PR.PT-3", "A.8.18"],
    "Data Leakage Prevention Simulation": ["PCI-12.1", "PR.DS-5", "A.8.12"],
    "Audit Logging Extension Simulation": [
        "A.8.15", "A.5.33", "DE.AE-3", "dora-Art9", "fedramp-AU-2", "PCI-10.1",
        "CISSP-6.4", "CISSP-7.2", "3.3.1", "CIS-8", "SOX-SA-4", "SWIFT-7.1",
    ],
    # CISSP-specific check mappings (kept for backward compat — also handled via base name above)
    "Admin Check: BitLocker Encryption": ["CISSP-3.3"],
    "Admin Check: Windows Firewall Profiles": ["CISSP-4.2"],
    "Admin Check: Windows Defender Antivirus": ["CISSP-7.5"],
    "Admin Check: Password Policy (Min Length)": ["CISSP-5.2"],
    "Admin Check: Clock Synchronization Simulation": ["CISSP-7.2"],
    "Admin Check: Cryptographic Controls Extension Simulation": ["CISSP-3.3"],
    "Admin Check: Capacity Management Simulation": ["CISSP-7.4"],
    "Admin Check: Data Backup & Recovery Simulation": ["CISSP-7.4"],
    "Admin Check: Audit Logging Extension Simulation": ["CISSP-6.4", "CISSP-7.2"],
    "Admin Check: PowerShell Script Block Logging": ["CISSP-6.4", "CISSP-7.2"],
    "Admin Check: Security Patch Status": ["CISSP-3.6", "CISSP-6.2", "CISSP-7.3"],
    "Admin Check: SMBv1 Protocol Disabled": ["CISSP-3.2", "CISSP-4.3"],
    "Admin Check: Risky Network Ports": ["CISSP-4.2", "CISSP-4.4"],
    "Admin Check: RDP NLA Required": ["CISSP-4.3", "CISSP-5.2"],
    "Admin Check: Guest Account Disabled": ["CISSP-5.1", "CISSP-5.4"],
    "Admin Check: Local Administrator Accounts": ["CISSP-5.4"],
    "Admin Check: Software Supply Chain Security": ["CISSP-8.4"],
    # Extended agent checks (caps3.rs)
    "NTLM Authentication Level": ["A.5.15", "A.8.22", "PCI-8.1.1", "CC6.1", "CC6.6"],
    "LSA Protection": ["A.5.15", "A.8.1", "PR.AC-1", "CC6.1"],
    "WDigest Authentication": ["A.5.15", "A.8.22", "CC6.1"],
    "Always Install Elevated": ["A.8.1", "A.8.3", "PR.AC-4", "CC6.8"],
    "Remote Registry Service": ["A.8.22", "PCI-2.2", "PR.AC-5", "CC6.6"],
    "AutoRun Disabled": ["A.7.10", "A.8.1", "CC6.6", "PCI-9.1.1"],
    "Windows Script Host": ["A.8.22", "A.8.19", "CC6.8", "PR.IP-1"],
}

_FRAMEWORK_PREFIXES = [
    "nistcsf-", "pci-dss-", "iso27001-", "hipaa-", "gdpr-", "dpdp-",
    "fedramp-", "ccpa-", "hitrust-", "cmmc-", "csa-", "cobit-", "dora-",
]


def _strip_prefix(raw_control_id: str) -> str:
    for prefix in _FRAMEWORK_PREFIXES:
        if raw_control_id.startswith(prefix):
            return raw_control_id[len(prefix):]
    return raw_control_id


async def process_automated_evidence(agent_hostname: str, compliance_data: dict, db, agent_type: str | None = None, fallback_tenant_id: str | None = None) -> None:
    """
    Called by agent heartbeat / task result handlers.
    Maps agent compliance checks to control IDs and auto-generates evidence records.
    """
    logger.info("Processing Auto-Compliance for %s", agent_hostname)

    asset_id = f"asset-{agent_hostname}"

    from tenant_context import set_tenant_id, get_tenant_id
    old_tenant_id = get_tenant_id()

    set_tenant_id("platform-admin")
    tenant_id = None
    try:
        if fallback_tenant_id:
            # The caller was authenticated with a specific tenant context (e.g. via
            # X-Registration-Key / JWT). That authenticated tenant must take priority
            # over any hostname-derived lookup — otherwise a caller could inject
            # evidence under a different tenant simply by choosing a colliding
            # hostname (CR-02: cross-tenant evidence injection).
            tenant_id = fallback_tenant_id
        else:
            asset = await db.assets.find_one({"id": asset_id})
            tenant_id = asset.get("tenantId") if asset else None
            if not tenant_id:
                agent = await db.agents.find_one({"hostname": agent_hostname})
                tenant_id = agent.get("tenantId") if agent else None
    except Exception as e:
        logger.warning("Failed to look up tenant ID for auto-compliance: %s", e)
    finally:
        set_tenant_id(old_tenant_id)

    if not isinstance(compliance_data, dict):
        logger.warning("process_automated_evidence: expected dict, got %s — skipping", type(compliance_data).__name__)
        return

    if tenant_id:
        set_tenant_id(tenant_id)

    timestamp = datetime.now(timezone.utc).isoformat()

    _NO_DATA_PREFIXES = (
        "unable to", "secedit unavailable", "[elevation required",
        "[run_ps_admin",
    )

    def _is_no_data(s: str) -> bool:
        return not s or s.lower().startswith(_NO_DATA_PREFIXES)

    def _status_rank(check: dict) -> int:
        """Higher = better result. Used to prefer Pass over Warning when deduplicating."""
        s = (check.get("status") or "").lower()
        if s == "pass": return 2
        if s == "warning": return 1
        return 0

    # Deduplicate: the agent sends the same check from both native Rust reader and
    # PowerShell. Rules:
    #   1. Never let "Unable to query" overwrite a real result.
    #   2. When both have real data, keep the one with the better status (Pass > Warning).
    seen_checks: dict[str, dict] = {}
    for check in compliance_data.get("compliance_checks", []):
        name = check.get("check")
        if not name:
            continue
        details = check.get("details") or ""
        if name in seen_checks:
            existing = seen_checks[name]
            existing_details = existing.get("details") or ""
            incoming_empty = _is_no_data(details)
            existing_empty  = _is_no_data(existing_details)
            # Rule 1: skip if incoming has no data but existing does
            if incoming_empty and not existing_empty:
                continue
            # Rule 2: prefer higher-ranked status when both have real data
            if not incoming_empty and not existing_empty:
                if _status_rank(check) <= _status_rank(existing):
                    continue
        seen_checks[name] = check
    deduped_checks = list(seen_checks.values())

    try:
        for check in deduped_checks:
            check_name = check.get("check")
            status = check.get("status")
            details = check.get("details")

            if status == "Pass":
                compliance_status = "Compliant"
            elif status == "Warning":
                compliance_status = "Warning"
            else:
                compliance_status = "Non-Compliant"

            target_controls = COMPLIANCE_CHECK_MAPPINGS.get(check_name, [])
            if not target_controls:
                continue

            for raw_control_id in target_controls:
                control_id = _strip_prefix(raw_control_id)
                check_slug = check_name.replace(" ", "-").lower()
                evidence_id = f"auto-ev-{agent_hostname}-{control_id}-{check_slug}-{timestamp}"

                evidence_content = (
                    f"# System Compliance Evidence\n"
                    f"**Date:** {timestamp}\n"
                    f"**Asset:** {agent_hostname}\n"
                    f"**Control:** {control_id}\n"
                    f"**Check Name:** {check_name}\n\n"
                    f"## 1. Check Status\n"
                    f"**Result:** {status}\n"
                    f"**Details:** {details}\n\n"
                    f"## 2. Automated Command Output\n"
                )

                raw_content = check.get("evidence_content")
                if raw_content:
                    lang = "json" if raw_content.strip().startswith(("{", "[")) else "text"
                    evidence_content += f"```{lang}\n{raw_content}\n```"
                else:
                    evidence_content += "*No raw command output captured.*"

                agent_hash = check.get("content_hash")
                if agent_hash:
                    server_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest() if raw_content else "N/A"
                    match = agent_hash == server_hash
                    verification = (
                        "✅ Verified (Content Matches Agent Hash)"
                        if match
                        else f"❌ TAMPERING DETECTED (Agent: {agent_hash[:8]}... vs Server: {server_hash[:8]}...)"
                    )
                    evidence_content += f"\n\n## 3. Evidence Integrity\n**Agent Hash (SHA256):** `{agent_hash}`\n**Backend Verification:** {verification}\n"
                else:
                    evidence_content += "\n\n## 3. Evidence Integrity\n*Integrity hash not provided by agent.*"

                evidence_record = {
                    "id": evidence_id,
                    "name": f"System Check: {check_name}",
                    "url": "#",
                    "type": "application/json",
                    "uploadedAt": timestamp,
                    "assetId": asset_id,
                    "controlId": control_id,
                    "tenantId": tenant_id,
                    "systemGenerated": True,
                    "content": evidence_content,
                    "agent_type": agent_type,
                }

                await db.asset_compliance.update_one(
                    {"assetId": asset_id, "controlId": control_id},
                    {"$pull": {"evidence": {"name": {"$in": [
                        f"System Check: {check_name}",
                        f"Admin Check: {check_name}",
                    ]}}}},
                )
                await db.asset_compliance.update_one(
                    {"assetId": asset_id, "controlId": control_id},
                    {
                        "$set": {
                            "tenantId": tenant_id,
                            "status": compliance_status,
                            "checkName": check_name,
                            "lastUpdated": timestamp,
                            "lastAutomatedCheck": timestamp,
                            "agent_type": agent_type,
                        },
                        "$push": {"evidence": evidence_record},
                    },
                    upsert=True,
                )
                logger.info("Auto-mapped %s -> %s (%s)", check_name, control_id, compliance_status)
    finally:
        set_tenant_id(old_tenant_id)
