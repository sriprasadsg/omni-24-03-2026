from fastapi import APIRouter, Depends, HTTPException, Query
from ingest_service import ingest_service
from tenant_context import get_tenant_id
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
import re
import logging


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/siem", tags=["SIEM"])

@router.post("/ingest")
async def ingest_log(source: str, payload: Dict[str, Any], tenant_id: str = Depends(get_tenant_id)):
    """
    Ingests a raw log from a security source and normalizes it to OCSF.
    """
    try:
        event_id = await ingest_service.ingest_raw_log(tenant_id, source, payload)
        return {"status": "Success", "event_id": event_id}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/events")
async def get_events(
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Retrieves normalized security events for the current tenant.
    """
    try:
        events = await ingest_service.get_security_events(tenant_id, limit, skip)
        return {"events": events}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

# ── SIEM Integration Config Management ───────────────────────────────────────

@router.get("/configs")
async def list_siem_configs(
    _current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """List all SIEM integration configurations for the current tenant."""
    try:
        db = get_database()
        configs = await db.siem_configs.find(
            {"tenant_id": tenant_id}, {"_id": 0, "aws_secret_key": 0, "api_token": 0}
        ).to_list(length=100)
        return {"configs": configs}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


_SIEM_CONFIG_FIELDS = {
    "aws_cloudtrail": {"account_id", "region", "bucket_name", "role_arn", "aws_access_key_id", "aws_secret_key"},
    "okta":           {"api_url", "api_key", "api_token"},
    "syslog":         {"host", "port", "protocol"},
}

@router.put("/configs/{provider}")
async def upsert_siem_config(
    provider: str,
    data: Dict[str, Any],
    current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Create or update a SIEM integration config.
    Providers: aws_cloudtrail, okta, syslog.
    Body fields vary by provider — see inline docs.
    """
    allowed = {"aws_cloudtrail", "okta", "syslog"}
    if provider not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown provider. Must be one of: {allowed}")
    try:
        db = get_database()
        allowed_fields = _SIEM_CONFIG_FIELDS.get(provider, set())
        safe_data = {k: v for k, v in data.items() if k in allowed_fields}
        update = {**safe_data, "provider": provider, "tenant_id": tenant_id,
                  "updated_at": datetime.now(timezone.utc).isoformat(),
                  "updated_by": getattr(current_user, "username", str(current_user))}
        await db.siem_configs.update_one(
            {"provider": provider, "tenant_id": tenant_id},
            {"$set": update},
            upsert=True,
        )
        safe = {k: v for k, v in update.items() if k not in ("aws_secret_key", "api_token")}
        return {"success": True, "config": safe}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/configs/{provider}")
async def delete_siem_config(
    provider: str,
    _current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """Remove a SIEM integration config."""
    try:
        db = get_database()
        result = await db.siem_configs.delete_one({"provider": provider, "tenant_id": tenant_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Config not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Log Explorer endpoints ─────────────────────────────────────────────────────

@router.get("/logs")
async def search_logs(
    q: str = Query("", description="Full-text / keyword search on log message"),
    source: str = Query("", description="Filter by source (metadata.product)"),
    limit: int = Query(200, ge=1, le=2000),
    _current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Full-text log search for the Log Explorer dashboard.
    Queries security_events with optional keyword and source filters.
    Returns flat records shaped for the frontend table.
    """
    try:
        db = get_database()
        query: Dict[str, Any] = {"tenantId": tenant_id} if tenant_id != "platform-admin" else {}
        if source:
            query["metadata.product"] = source
        if q:
            try:
                query["message"] = {"$regex": re.escape(q), "$options": "i"}
            except Exception as e:
                logger.debug("SIEM search query build failed: %s", e)

        cursor = db.security_events.find(query, {"_id": 0}).sort("time", -1).limit(limit)
        raw_events = await cursor.to_list(length=limit)

        logs = [
            {
                "id": e.get("id", ""),
                "timestamp": e.get("time") or e.get("ingestedAt", ""),
                "log_type": e.get("metadata", {}).get("product", "unknown"),
                "severity": e.get("severity", "Low"),
                "raw_message": e.get("message") or e.get("activity_name") or e.get("class_name") or "",
                "category": e.get("category_name", ""),
            }
            for e in raw_events
        ]
        return {"logs": logs, "total": len(logs)}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/aggregations")
async def get_log_aggregations(
    _current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Returns aggregated stats for the Log Explorer: source counts and hourly histogram.
    """
    try:
        db = get_database()
        match_filter: Dict[str, Any] = {"tenantId": tenant_id} if tenant_id != "platform-admin" else {}

        # Source distribution
        source_pipeline = [
            {"$match": match_filter},
            {"$group": {"_id": "$metadata.product", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 20},
        ]
        source_docs = await db.security_events.aggregate(source_pipeline).to_list(length=20)
        sources = {(d["_id"] or "unknown"): d["count"] for d in source_docs}

        # Hourly histogram for the past 24 hours (24 buckets)
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        since_iso = since.isoformat()

        histogram_pipeline = [
            {"$match": {**match_filter, "time": {"$gte": since_iso}}},
            {
                "$group": {
                    "_id": {
                        "$substr": ["$time", 0, 13]  # "YYYY-MM-DDTHH" bucket
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]
        hist_docs = await db.security_events.aggregate(histogram_pipeline).to_list(length=48)
        histogram = [{"time": d["_id"], "count": d["count"]} for d in hist_docs]

        # Severity breakdown
        sev_pipeline = [
            {"$match": match_filter},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
        ]
        sev_docs = await db.security_events.aggregate(sev_pipeline).to_list(length=10)
        severity_counts = {d["_id"]: d["count"] for d in sev_docs}

        total = await db.security_events.count_documents(match_filter)

        return {
            "sources": sources,
            "histogram": histogram,
            "severity_counts": severity_counts,
            "total": total,
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary")
async def get_siem_summary(tenant_id: str = Depends(get_tenant_id)):
    """
    Provides a high-level summary of security event distribution.
    """
    try:
        events: List[Dict[str, Any]] = await ingest_service.get_security_events(tenant_id, limit=500)
        summary: Dict[str, Any] = {
            "total_events": len(events),
            "severity_counts": {
                "Critical": 0, "High": 0, "Medium": 0, "Low": 0
            },
            "source_counts": {}
        }
        for e in events:
            sev = e.get("severity", "Low")
            if sev in summary["severity_counts"]:
                summary["severity_counts"][sev] += 1
            src = e.get("metadata", {}).get("product", "Unknown")
            summary["source_counts"][src] = summary["source_counts"].get(src, 0) + 1
            
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# ── SIEM Correlation Rules ─────────────────────────────────────────────────────

import uuid as _uuid

def _rule_tenant(current_user) -> str:
    return getattr(current_user, "tenant_id", None) or (
        current_user.get("tenant_id") if isinstance(current_user, dict) else None
    ) or ""


_SEED_RULES = [
    # ── Initial Access ──────────────────────────────────────────────────────────
    {
        "name": "Password Spray via Microsoft Entra / Azure AD",
        "description": "Single IP authenticating against more than 20 distinct Entra ID / Azure AD accounts within 10 minutes using identical passwords. Actively used by APT29 (Midnight Blizzard) in 2023-2024 campaigns against government and cloud tenants. Avoids per-account lockout by staying below the threshold for each account.",
        "severity": "Critical",
        "conditions": {"action": "login_failed", "idp": "entra_id", "threshold": "20_accounts/10m", "pattern": "password_spray"},
        "remediation": "Enforce Conditional Access requiring MFA for all sign-ins. Block the offending IP in Entra Named Locations. Run the Entra ID Sign-in audit to identify any successful logins. Reset passwords for accounts that received more than 3 failed attempts from this IP.",
        "mitre_tactic": "Initial Access",
        "mitre_technique": "T1110.003 — Password Spraying",
        "threat_actor": "APT29 / Midnight Blizzard",
        "match_count": 6,
    },
    {
        "name": "OAuth Device Code Flow Abuse",
        "description": "An OAuth 2.0 Device Authorization Grant flow was initiated for a non-interactive device and a token was issued after an unusually short user-approval window (< 30 s). APT29 exploits this flow by sending phishing emails containing a device code to trick users into approving attacker-controlled app registrations, granting persistent access without passwords.",
        "severity": "Critical",
        "conditions": {"action": "oauth_device_code_grant", "approval_window_seconds": "<30", "app_verified": False},
        "remediation": "Revoke all tokens issued in the session, remove the app registration from the tenant, block the client ID in Conditional Access, and audit all mail read / forwarding actions performed during the token lifetime.",
        "mitre_tactic": "Initial Access",
        "mitre_technique": "T1528 — Steal Application Access Token",
        "threat_actor": "APT29 / Midnight Blizzard",
        "match_count": 2,
    },
    {
        "name": "VPN Gateway Exploitation — CISA KEV CVE",
        "description": "Authentication bypass or pre-auth RCE attempt against Ivanti Connect Secure (CVE-2024-21887 / CVE-2023-46805), Fortinet FortiOS (CVE-2024-21762), or Cisco ASA/FTD (CVE-2023-20269). Observed in Volt Typhoon and UNC5221 campaigns. Attackers deploy lightweight web shells (e.g., GLASSTOKEN, BUSHWALK) immediately after exploitation.",
        "severity": "Critical",
        "conditions": {"action": "exploit_attempt", "target_product": "vpn_gateway", "cve_family": "ivanti_fortinet_cisco"},
        "remediation": "Apply vendor patches immediately (in CISA KEV). Perform factory reset per vendor guidance before reconnecting. Hunt for GLASSTOKEN / LIGHTWIRE web shell IOCs on the appliance. Rotate all credentials that traversed the VPN in the preceding 90 days.",
        "mitre_tactic": "Initial Access",
        "mitre_technique": "T1190 — Exploit Public-Facing Application",
        "threat_actor": "Volt Typhoon / UNC5221",
        "match_count": 1,
    },
    {
        "name": "Phishing — Microsoft Teams External Tenant Lure",
        "description": "Message received from an external Microsoft Teams tenant containing a URL or file attachment. APT29 has delivered phishing payloads via Teams by compromising a small business Microsoft 365 tenant and using it as a trusted relay, bypassing email gateways entirely.",
        "severity": "High",
        "conditions": {"action": "teams_message_received", "source": "external_tenant", "has_attachment_or_url": True},
        "remediation": "Disable external Teams federation for non-approved domains in Teams Admin Center. Isolate the endpoint that received the message, revoke the user's active sessions, and submit the URL/file to your threat intelligence platform.",
        "mitre_tactic": "Initial Access",
        "mitre_technique": "T1566.004 — Phishing via Service",
        "threat_actor": "APT29 / Midnight Blizzard",
        "match_count": 3,
    },
    {
        "name": "MFA Fatigue — Push Notification Flood",
        "description": "More than 10 MFA push notifications sent to the same user within 5 minutes with no corresponding legitimate login activity. Threat actors (Lapsus$, Scattered Spider) exploit user fatigue by flooding the authenticator app until the user accidentally or deliberately approves a request.",
        "severity": "High",
        "conditions": {"action": "mfa_push_sent", "threshold": "10/5m", "user_approved": False},
        "remediation": "Temporarily suspend the user's MFA pushes and switch to FIDO2 / number-matching. Verify the user has not approved any push. Block the source IP attempting the login. Educate the user on MFA fatigue attacks.",
        "mitre_tactic": "Initial Access",
        "mitre_technique": "T1621 — Multi-Factor Authentication Request Generation",
        "threat_actor": "Scattered Spider / Lapsus$",
        "match_count": 8,
    },
    # ── Execution / LOLBins ─────────────────────────────────────────────────────
    {
        "name": "Living-off-the-Land — Volt Typhoon Reconnaissance Commands",
        "description": "Sequential execution of multiple Windows built-in discovery commands (netstat, ipconfig, net user, net group, net localgroup, quser, wmic, tasklist) within 2 minutes from the same user context. Volt Typhoon uses only native OS binaries to blend into legitimate traffic and evade EDR behavioural rules.",
        "severity": "High",
        "conditions": {"action": "process_created", "pattern": "lotl_recon_sequence", "binaries": ["netstat","ipconfig","net","wmic","tasklist","quser"]},
        "remediation": "Isolate the endpoint and capture a memory image. Review process tree lineage — if commands originate from a non-interactive context (e.g., SYSTEM, web server process) treat as active compromise. Submit to Volt Typhoon IOC feeds for additional context.",
        "mitre_tactic": "Discovery",
        "mitre_technique": "T1069 / T1016 / T1049 — System & Network Discovery",
        "threat_actor": "Volt Typhoon",
        "match_count": 14,
    },
    {
        "name": "CertUtil Downloading Remote File",
        "description": "certutil.exe was invoked with -urlcache -split -f flags to download a file from an external URL. Certutil is a legitimate Windows binary routinely abused as a downloader by ransomware operators, APTs, and red teams to bypass application control.",
        "severity": "High",
        "conditions": {"action": "process_created", "process": "certutil.exe", "flags": "-urlcache"},
        "remediation": "Kill the certutil process, delete any downloaded files, quarantine the host, and investigate the parent process that launched certutil. Block the download URL at the proxy. Check for persistence mechanisms established after the download.",
        "mitre_tactic": "Defense Evasion",
        "mitre_technique": "T1105 — Ingress Tool Transfer (LOLBin)",
        "threat_actor": "Multiple ransomware operators",
        "match_count": 7,
    },
    {
        "name": "MSHTA / Regsvr32 Script Execution",
        "description": "mshta.exe or regsvr32.exe executed a remote script (scrobj.dll COM scriptlet via regsvr32 /s /n /u /i:http://..., or mshta http://...). Both are classic application-control bypass techniques used to run JScript/VBScript payloads without executing a script file on disk.",
        "severity": "Critical",
        "conditions": {"action": "process_created", "process": ["mshta.exe","regsvr32.exe"], "remote_script": True},
        "remediation": "Terminate the process, isolate the endpoint, capture memory before reboot. Decode and analyse the remote script. Block the hosting URL at the proxy and firewall. Search for any files dropped or registry keys modified by the script.",
        "mitre_tactic": "Defense Evasion",
        "mitre_technique": "T1218.005 / T1218.010 — Signed Binary Proxy Execution",
        "threat_actor": "FIN7 / Emotet / QakBot",
        "match_count": 4,
    },
    {
        "name": "Office Macro Spawning Script Interpreter",
        "description": "A Microsoft Office process (WINWORD.EXE, EXCEL.EXE, OUTLOOK.EXE) spawned cmd.exe, powershell.exe, wscript.exe, or cscript.exe. High-confidence indicator of malicious macro execution used by QakBot, Emotet, and multiple ransomware initial-access brokers.",
        "severity": "Critical",
        "conditions": {"action": "process_created", "parent": "office_process", "child": "script_interpreter"},
        "remediation": "Isolate the endpoint immediately. Preserve the document for forensic analysis (do not delete). Terminate all spawned child processes, run a full EDR scan, and block the document hash fleet-wide via application control.",
        "mitre_tactic": "Execution",
        "mitre_technique": "T1566.001 — Spearphishing Attachment / T1059",
        "threat_actor": "QakBot / Emotet / BazarLoader",
        "match_count": 5,
    },
    # ── Persistence ─────────────────────────────────────────────────────────────
    {
        "name": "Exchange / M365 Inbox Forwarding Rule to External Domain",
        "description": "A mail forwarding rule was created that silently forwards all incoming email to an external address. BEC actors and APT29 create these rules after gaining mailbox access to siphon sensitive communications without altering mail flow visible to the victim.",
        "severity": "Critical",
        "conditions": {"action": "mail_rule_created", "forward_to": "external_domain"},
        "remediation": "Disable the forwarding rule immediately, revoke all active sessions for the mailbox owner, enable Conditional Access requiring MFA, and perform a 90-day audit of all outbound mail forwarding in the tenant.",
        "mitre_tactic": "Collection",
        "mitre_technique": "T1114.003 — Email Forwarding Rule",
        "threat_actor": "APT29 / BEC actors",
        "match_count": 3,
    },
    {
        "name": "Suspicious Scheduled Task — Encoded Payload",
        "description": "A Windows scheduled task was created with a command line containing Base64-encoded content, -EncodedCommand, or a raw URL pointing to a remote script. Used by LockBit affiliates and other ransomware operators to maintain post-exploitation persistence and re-establish access after EDR detection.",
        "severity": "High",
        "conditions": {"action": "scheduled_task_created", "command_line": "encoded_or_url"},
        "remediation": "Delete the scheduled task, decode the payload for IOC extraction, quarantine the host, and check if the task has already executed. Hunt for matching task names or payloads across the fleet.",
        "mitre_tactic": "Persistence",
        "mitre_technique": "T1053.005 — Scheduled Task/Job",
        "threat_actor": "LockBit / BlackCat ALPHV",
        "match_count": 5,
    },
    {
        "name": "Azure AD / Entra New Credential Added to Service Principal",
        "description": "A client secret or certificate was added to an existing Service Principal or App Registration. This technique allows attackers who have achieved Application Administrator access to establish a backdoor credential that persists even after user password resets.",
        "severity": "Critical",
        "conditions": {"action": "service_principal_credential_added", "idp": "entra_id"},
        "remediation": "Audit the App Registration for other suspicious changes. Remove the credential immediately. Review the Service Principal's API permissions and recent sign-in logs. If the app has mail.read or similar sensitive permissions, treat as full tenant compromise.",
        "mitre_tactic": "Persistence",
        "mitre_technique": "T1098.001 — Account Manipulation: Additional Cloud Credentials",
        "threat_actor": "APT29 / Storm-0558",
        "match_count": 1,
    },
    {
        "name": "Registry Run Key — Persistence via Malicious Binary",
        "description": "A write to HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run or HKCU equivalent by a non-system process, establishing persistence that runs a binary or script at every user logon. Used by Emotet, TrickBot, and various RATs.",
        "severity": "High",
        "conditions": {"action": "registry_write", "key": "run_key", "user_type": "non_system"},
        "remediation": "Remove the registry value, scan and quarantine the referenced binary, check for other persistence mechanisms (services, startup folder), and sweep the fleet for the same key value.",
        "mitre_tactic": "Persistence",
        "mitre_technique": "T1547.001 — Registry Run Keys / Startup Folder",
        "threat_actor": "Emotet / TrickBot",
        "match_count": 7,
    },
    # ── Privilege Escalation ────────────────────────────────────────────────────
    {
        "name": "PrintNightmare / Windows Spooler Privilege Escalation",
        "description": "Attempt to load a DLL via the Windows Print Spooler service (CVE-2021-34527 / CVE-2021-1675) or a suspicious AddPrinterDriver call from a non-administrator account. Although patched, unpatched systems and variants continue to appear in the wild.",
        "severity": "Critical",
        "conditions": {"action": "spooler_dll_load", "cve": "CVE-2021-34527", "user_type": "non_admin"},
        "remediation": "Apply KB5004945 (or later cumulative update). Disable Print Spooler on Domain Controllers immediately. Investigate the process that triggered the DLL load and rotate credentials for any account involved.",
        "mitre_tactic": "Privilege Escalation",
        "mitre_technique": "T1068 — Exploitation for Privilege Escalation",
        "threat_actor": "Multiple ransomware affiliates",
        "match_count": 2,
    },
    {
        "name": "LSASS Memory Access — Credential Dumping",
        "description": "A non-whitelisted process opened a handle to LSASS.exe with PROCESS_VM_READ access. Mimikatz, Cobalt Strike (hashdump), and Impacket secretsdump all trigger this pattern. High-confidence credential theft indicator used by virtually every sophisticated threat actor.",
        "severity": "Critical",
        "conditions": {"action": "lsass_access", "process_type": "non_whitelisted", "access_mask": "PROCESS_VM_READ"},
        "remediation": "Quarantine the endpoint immediately. Rotate ALL credentials for accounts logged into the machine. Revoke all Kerberos TGTs (run klist purge on DCs). Enable Credential Guard on Windows 10/11 endpoints. Hunt for lateral movement using NTLM pass-the-hash.",
        "mitre_tactic": "Credential Access",
        "mitre_technique": "T1003.001 — LSASS Memory",
        "threat_actor": "Cobalt Strike / Mimikatz — used by most APT groups",
        "match_count": 2,
    },
    # ── Defense Evasion ─────────────────────────────────────────────────────────
    {
        "name": "Shadow Copy / Backup Deletion — Ransomware Pre-Stage",
        "description": "Execution of vssadmin.exe delete shadows, wbadmin delete catalog, or bcdedit /set recoveryenabled No. Deleting shadow copies is a near-universal ransomware pre-encryption step used by LockBit 3.0, BlackCat ALPHV, Play, and Cl0p to prevent file recovery.",
        "severity": "Critical",
        "conditions": {"action": "process_created", "process": ["vssadmin.exe","wbadmin.exe","bcdedit.exe"], "args": "delete_shadows_or_backup"},
        "remediation": "IMMEDIATELY isolate the endpoint from the network — encryption may be seconds away. Do NOT shut down (preserves memory for key recovery). Activate the ransomware incident response playbook. Notify legal, executives, and your cyber insurance carrier.",
        "mitre_tactic": "Defense Evasion",
        "mitre_technique": "T1490 — Inhibit System Recovery",
        "threat_actor": "LockBit 3.0 / BlackCat ALPHV / Play / Cl0p",
        "match_count": 1,
    },
    {
        "name": "Security Log Cleared",
        "description": "Windows Security Event Log (Event ID 1102) or System Log (Event ID 104) was cleared. Ransomware groups and APTs clear logs to remove evidence of lateral movement, credential theft, and initial exploitation prior to deploying their final payload.",
        "severity": "Critical",
        "conditions": {"action": "log_cleared", "event_id": ["1102","104"]},
        "remediation": "Treat the host as compromised. Collect all available telemetry from EDR, firewall, and proxy before evidence degrades. Initiate memory forensics, rebuild the host from a known-good baseline, and review upstream SIEM for events from this host in the preceding 72 hours.",
        "mitre_tactic": "Defense Evasion",
        "mitre_technique": "T1070.001 — Clear Windows Event Logs",
        "threat_actor": "LockBit / BlackCat ALPHV / multiple APTs",
        "match_count": 2,
    },
    {
        "name": "EDR / AV Disabled or Tampered",
        "description": "The endpoint protection agent process was killed, its service stopped, or real-time protection was disabled. Ransomware groups (LockBit, BlackCat) and the BYOVD (Bring Your Own Vulnerable Driver) technique are commonly used to terminate EDR before deploying the encryptor.",
        "severity": "Critical",
        "conditions": {"action": "av_disabled", "method": ["service_stop","process_kill","byovd"]},
        "remediation": "Force-reinstall the EDR agent via remote management, quarantine the host, investigate the driver or tool used (if BYOVD, check for CVE-2023-44976 or similar), and escalate to P1 incident.",
        "mitre_tactic": "Defense Evasion",
        "mitre_technique": "T1562.001 — Impair Defenses: Disable or Modify Tools",
        "threat_actor": "LockBit 3.0 / BlackCat ALPHV",
        "match_count": 3,
    },
    # ── Credential Access ───────────────────────────────────────────────────────
    {
        "name": "Kerberoasting — Bulk TGS Request",
        "description": "A single account requested Kerberos TGS tickets for more than 5 Service Principal Names within 2 minutes. Attackers (Impacket GetUserSPNs, Rubeus kerberoast) collect RC4-encrypted service tickets for offline cracking with Hashcat/John the Ripper. Widely used by ransomware affiliates after initial foothold.",
        "severity": "High",
        "conditions": {"action": "kerberos_tgs_request", "threshold": "5_spns/2m", "encryption": "RC4"},
        "remediation": "Rotate all targeted service account passwords to 30+ character random strings and enforce AES-only encryption (remove RC4 support where possible). Audit SPNs and remove unnecessary registrations. Investigate the requesting account for additional compromise indicators.",
        "mitre_tactic": "Credential Access",
        "mitre_technique": "T1558.003 — Steal or Forge Kerberos Tickets: Kerberoasting",
        "threat_actor": "Ransomware affiliates / Impacket",
        "match_count": 1,
    },
    # ── Discovery ───────────────────────────────────────────────────────────────
    {
        "name": "Internal Network Scan — Lateral Movement Recon",
        "description": "A host is scanning more than 50 internal IPs on ports 22, 135, 139, 445, 1433, 3389, 5985 within 60 seconds. Typical post-exploitation recon pattern seen with Cobalt Strike, Impacket, and Metasploit prior to lateral movement.",
        "severity": "High",
        "conditions": {"category": "network_scan", "scope": "internal", "threshold": "50_hosts/60s", "ports": [22,135,445,1433,3389,5985]},
        "remediation": "Isolate the scanning host, review how it was compromised (check EDR for prior LSASS access, lateral movement), and use the scan target list to identify additional at-risk assets. Block unnecessary port access via host-based firewall policies.",
        "mitre_tactic": "Discovery",
        "mitre_technique": "T1046 — Network Service Discovery",
        "threat_actor": "Multiple — Cobalt Strike / Impacket",
        "match_count": 8,
    },
    {
        "name": "LDAP / BloodHound-Style AD Enumeration",
        "description": "High-volume LDAP queries from a non-service account enumerating users, computers, group memberships, and ACLs in a pattern consistent with BloodHound or SharpHound collectors. APT groups and ransomware affiliates use AD graph data to identify paths to Domain Admin.",
        "severity": "High",
        "conditions": {"action": "ldap_query", "volume": "bulk", "query_types": ["samAccountName","memberOf","objectSid","nTSecurityDescriptor"]},
        "remediation": "Investigate the querying account for compromise indicators. Enable LDAP signing and channel binding on all DCs. Consider deploying a honeypot Admin account in AD to detect BloodHound enumeration. Review privileged group memberships for unexpected entries.",
        "mitre_tactic": "Discovery",
        "mitre_technique": "T1069.002 — Domain Groups / T1087.002 — Domain Accounts",
        "threat_actor": "BlackCat ALPHV / ransomware affiliates / red teams",
        "match_count": 9,
    },
    # ── Command & Control ───────────────────────────────────────────────────────
    {
        "name": "Cobalt Strike / C2 Beacon Detected",
        "description": "Network traffic with periodic, low-jitter outbound connections (interval 60 s, jitter < 10%) to an IP on port 443/80 with a self-signed TLS certificate or unusual JA3 fingerprint matching known Cobalt Strike team server profiles. One of the most common post-exploitation frameworks used across ransomware and APT operations.",
        "severity": "Critical",
        "conditions": {"category": "c2_communication", "pattern": "cobalt_strike_beacon", "ja3_match": True},
        "remediation": "Block the C2 IP/domain at all egress points. Isolate the endpoint and take a memory dump before rebooting (Cobalt Strike beacon artifacts are memory-resident). Submit the beacon config to JARM/C2 identification tools. Hunt for lateral movement that may have already occurred.",
        "mitre_tactic": "Command and Control",
        "mitre_technique": "T1071.001 — Web Protocols / T1573 — Encrypted Channel",
        "threat_actor": "Used by majority of ransomware groups and APTs",
        "match_count": 11,
    },
    {
        "name": "DNS Tunneling — Data Exfiltration via DNS",
        "description": "Excessive DNS TXT/NULL queries with subdomain labels > 50 characters sent to a single domain, or entropy-based detection of encoded data in DNS query names. Tools like iodine, dnscat2, and DNSExfiltrator encode data in DNS to bypass data loss prevention and firewall egress controls.",
        "severity": "High",
        "conditions": {"category": "dns_anomaly", "pattern": "tunneling", "subdomain_length": ">50", "query_rate": "high"},
        "remediation": "Block DNS resolution to the implicated domain. Capture a full PCAP for forensic reconstruction of exfiltrated data. Identify all endpoints querying the domain and check for the tunneling tool binary. Report the domain to your DNS provider for sinkholing.",
        "mitre_tactic": "Command and Control",
        "mitre_technique": "T1071.004 — DNS",
        "threat_actor": "APT / pen testers / data theft actors",
        "match_count": 4,
    },
    # ── Exfiltration ────────────────────────────────────────────────────────────
    {
        "name": "Cl0p / MOVEit-Style Mass Data Exfiltration",
        "description": "More than 500 MB of data transferred to an external IP or cloud storage service in under 30 minutes from a file-transfer server (MFT appliance, SharePoint, OneDrive). Pattern matches Cl0p's exploitation of MOVEit Transfer (CVE-2023-34362) and GoAnywhere MFT (CVE-2023-0669) where data was exfiltrated before ransomware deployment.",
        "severity": "Critical",
        "conditions": {"action": "large_upload", "threshold": "500MB/30m", "source_type": "file_transfer_server"},
        "remediation": "Block the outbound connection, preserve all web server and application logs for forensic analysis. Notify legal and compliance teams immediately — this likely triggers data breach notification obligations. Engage your incident response retainer and cyber insurance carrier.",
        "mitre_tactic": "Exfiltration",
        "mitre_technique": "T1048 — Exfiltration Over Alternative Protocol",
        "threat_actor": "Cl0p / TA505",
        "match_count": 3,
    },
    # ── Impact ──────────────────────────────────────────────────────────────────
    {
        "name": "Ransomware Deployment — Mass File Encryption",
        "description": "Rapid sequential file rename/overwrite with new extensions combined with dropped ransom notes (README.txt, DECRYPT.html). LockBit 3.0 can encrypt 25,000 files per minute; BlackCat ALPHV targets VMware ESXi hosts to maximise impact. This rule fires at the onset of encryption.",
        "severity": "Critical",
        "conditions": {"action": "mass_file_encryption", "ransom_note_dropped": True, "encryption_rate": ">500_files/min"},
        "remediation": "Isolate the host at the network switch level — do NOT reboot (preserves memory for potential key recovery). Activate the ransomware playbook. Contact CISA (1-888-282-0870) if critical infrastructure. Preserve memory image. Do not pay ransom without OFAC sanctions check.",
        "mitre_tactic": "Impact",
        "mitre_technique": "T1486 — Data Encrypted for Impact",
        "threat_actor": "LockBit 3.0 / BlackCat ALPHV / Play / Cl0p",
        "match_count": 0,
    },
    {
        "name": "Impossible Travel — Simultaneous Login from Two Geographies",
        "description": "Successful authentication events for the same user account from two geolocations that are more than 800 km apart within a 30-minute window (physically impossible travel). Strongly indicates credential theft, session cookie hijack (e.g., via Evilginx2 AiTM proxy), or VPN misconfiguration.",
        "severity": "High",
        "conditions": {"action": "login_success", "pattern": "impossible_travel", "distance_km": ">800", "window_minutes": 30},
        "remediation": "Revoke all active sessions for the account. Force re-authentication with MFA. Check for the presence of Evilginx2/Modlishka phishing domains in recent email or browser history. Enable Entra ID Risky Sign-in alerts and configure Identity Protection policies.",
        "mitre_tactic": "Initial Access",
        "mitre_technique": "T1078 — Valid Accounts",
        "threat_actor": "AiTM phishing kits / Storm-1167",
        "match_count": 7,
    },
]


def _build_seed_rules(tenant_id: str) -> list:
    now = datetime.now(timezone.utc).isoformat()
    rules = []
    for s in _SEED_RULES:
        rules.append({
            "id": f"rule-{_uuid.uuid4().hex[:10]}",
            "name": s["name"],
            "description": s["description"],
            "severity": s["severity"],
            "enabled": True,
            "conditions": s["conditions"],
            "remediation": s["remediation"],
            "mitre_tactic": s.get("mitre_tactic", ""),
            "mitre_technique": s.get("mitre_technique", ""),
            "threat_actor": s.get("threat_actor", ""),
            "tenant_id": tenant_id,
            "created_by": "system",
            "created_at": now,
            "match_count": s["match_count"],
        })
    return rules


_SEED_RULE_NAMES = {s["name"] for s in _SEED_RULES}


async def _upsert_seed_rules(db, tenant_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    # Remove stale system rules whose names are no longer in the current seed set
    await db.siem_rules.delete_many({
        "tenant_id": tenant_id,
        "created_by": "system",
        "name": {"$nin": list(_SEED_RULE_NAMES)},
    })
    for s in _SEED_RULES:
        await db.siem_rules.update_one(
            {"name": s["name"], "tenant_id": tenant_id, "created_by": "system"},
            {
                "$set": {
                    "description": s["description"],
                    "severity": s["severity"],
                    "conditions": s["conditions"],
                    "remediation": s["remediation"],
                    "mitre_tactic": s.get("mitre_tactic", ""),
                    "mitre_technique": s.get("mitre_technique", ""),
                    "threat_actor": s.get("threat_actor", ""),
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "id": f"rule-{_uuid.uuid4().hex[:10]}",
                    "enabled": True,
                    "tenant_id": tenant_id,
                    "created_by": "system",
                    "created_at": now,
                    "match_count": s["match_count"],
                },
            },
            upsert=True,
        )


@router.get("/rules")
async def list_siem_rules(
    current_user: TokenData = Depends(get_current_user),
):
    """List SIEM correlation rules for the current tenant."""
    try:
        tenant_id = _rule_tenant(current_user)
        db = get_database()
        await _upsert_seed_rules(db, tenant_id)
        rules = await db.siem_rules.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(length=500)
        return rules
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rules")
async def create_siem_rule(
    data: Dict[str, Any],
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new SIEM correlation rule."""
    try:
        tenant_id = _rule_tenant(current_user)
        db = get_database()
        rule = {
            "id": f"rule-{_uuid.uuid4().hex[:10]}",
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "severity": data.get("severity", "Medium"),
            "enabled": data.get("enabled", True),
            "conditions": data.get("conditions", {}),
            "remediation": data.get("remediation", ""),
            "tenant_id": tenant_id,
            "created_by": getattr(current_user, "username", "system"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "match_count": 0,
        }
        await db.siem_rules.insert_one(rule)
        rule.pop("_id", None)
        return rule
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/rules/{rule_id}")
async def update_siem_rule(
    rule_id: str,
    data: Dict[str, Any],
    current_user: TokenData = Depends(get_current_user),
):
    """Update an existing SIEM correlation rule."""
    try:
        tenant_id = _rule_tenant(current_user)
        db = get_database()
        allowed = {"name", "description", "severity", "enabled", "conditions", "remediation"}
        update = {k: v for k, v in data.items() if k in allowed}
        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await db.siem_rules.update_one(
            {"id": rule_id, "tenant_id": tenant_id},
            {"$set": update},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Rule not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/rules/{rule_id}/toggle")
async def toggle_siem_rule(
    rule_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Toggle a SIEM correlation rule's enabled state."""
    try:
        tenant_id = _rule_tenant(current_user)
        db = get_database()
        rule = await db.siem_rules.find_one({"id": rule_id, "tenant_id": tenant_id}, {"_id": 0, "enabled": 1})
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        new_state = not rule.get("enabled", True)
        await db.siem_rules.update_one(
            {"id": rule_id, "tenant_id": tenant_id},
            {"$set": {"enabled": new_state, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"rule_id": rule_id, "enabled": new_state}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/rules/{rule_id}")
async def delete_siem_rule(
    rule_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Delete a SIEM correlation rule."""
    try:
        tenant_id = _rule_tenant(current_user)
        db = get_database()
        result = await db.siem_rules.delete_one({"id": rule_id, "tenant_id": tenant_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Rule not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
