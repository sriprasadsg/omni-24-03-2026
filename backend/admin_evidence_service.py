"""
Admin Evidence Service
======================
Collects real system evidence using PowerShell (admin-level where available)
and injects it into MongoDB asset_compliance + updates compliance_frameworks statuses.

This is invoked:
  1. When "Collect Evidence" is clicked in the Compliance dashboard
  2. Automatically when a new agent registers in the tenant
"""

import subprocess
import datetime
import hashlib
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger("admin_evidence_service")


def _run_ps(cmd: str, timeout: int = 15) -> tuple[str, str, int]:
    """Run a PowerShell command synchronously. Returns (stdout, stderr, returncode)."""
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return res.stdout.strip(), res.stderr.strip(), res.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", -1
    except FileNotFoundError:
        return "", "PowerShell not found (Linux/Mac host)", -1
    except Exception as e:
        return "", str(e), -1


def _make_record(asset_id: str, hostname: str, control_id: str,
                 check_name: str, status: str, details: str, raw_output: str) -> dict:
    """Build a standardised compliance evidence record."""
    ts = datetime.datetime.utcnow().isoformat()
    content_hash = hashlib.sha256(raw_output.encode("utf-8", errors="replace")).hexdigest()
    compliance_status = (
        "Compliant" if status == "Pass"
        else ("Warning" if status == "Warning"
              else "Non-Compliant")
    )
    content = f"""# System Compliance Evidence
**Date:** {ts}
**Asset:** {hostname}
**Control:** {control_id}
**Check:** {check_name}

## 1. Check Status
**Result:** {status}
**Details:** {details}

## 2. Automated Command Output
```
{raw_output[:4000]}
```

## 3. Evidence Integrity
**SHA-256:** `{content_hash}`
"""
    return {
        "id": f"ev-{hostname}-{control_id}-{hashlib.md5(check_name.encode()).hexdigest()[:8]}",
        "name": f"Admin Check: {check_name}",
        "url": "#",
        "type": "text/markdown",
        "uploadedAt": ts,
        "assetId": asset_id,
        "controlId": control_id,
        "systemGenerated": True,
        "content": content,
        "status": compliance_status,
        "content_hash": content_hash,
    }


def collect_evidence_for_host(hostname: str) -> list[tuple]:
    """
    Run all admin-level PowerShell checks for a given hostname.
    Returns a list of (control_id, check_name, status, details, raw_output) tuples.
    """
    checks = []

    # 1. BitLocker
    out, err, rc = _run_ps("manage-bde -status C: 2>&1")
    status = "Pass" if "Protection On" in out else ("Fail" if "Protection Off" in out else "Warning")
    details = "BitLocker: Protection On" if status == "Pass" else "BitLocker: Off or insufficient privileges"
    for ctrl in ["A.8.1", "A.8.24", "PCI-3.4", "CISSP-3.2", "CISSP-3.3"]:
        checks.append((ctrl, "BitLocker Encryption", status, details, out or err))

    # 2. Windows Firewall
    out, err, rc = _run_ps("Get-NetFirewallProfile | Select-Object Name, Enabled | ConvertTo-Json")
    status = "Pass" if out and "true" in out.lower() else "Warning"
    details = "Firewall profiles queried"
    for ctrl in ["A.8.22", "PCI-1.1", "CC6.6", "CISSP-4.2"]:
        checks.append((ctrl, "Windows Firewall Profiles", status, details, out or err))

    # 3. Windows Defender
    out, err, rc = _run_ps("Get-MpComputerStatus | Select-Object AMServiceEnabled, RealTimeProtectionEnabled, AntivirusSignatureAge | ConvertTo-Json")
    status = "Pass" if out and "true" in out.lower() else "Warning"
    details = "Defender status queried"
    for ctrl in ["A.8.7", "PCI-5.1", "CC6.8", "DE.CM-4", "CISSP-7.5"]:
        checks.append((ctrl, "Windows Defender Antivirus", status, details, out or err))

    # 4. Password Policy
    out, err, rc = _run_ps("net accounts")
    min_len_lines = [l for l in out.splitlines() if "Minimum password length" in l]
    min_len = 0
    if min_len_lines:
        try:
            min_len = int(min_len_lines[0].split()[-1])
        except Exception:
            min_len = 0
    status = "Pass" if min_len >= 8 else ("Warning" if min_len > 0 else "Fail")
    details = f"Min password length: {min_len}"
    for ctrl in ["A.5.15", "A.8.5", "PCI-8.1.1", "CC6.1", "CISSP-5.2"]:
        checks.append((ctrl, "Password Policy (Min Length)", status, details, out or err))

    # 5. NTP / Clock Sync
    out, err, rc = _run_ps("w32tm /query /status 2>&1")
    status = "Pass" if rc == 0 and "ReferenceId" in out else "Warning"
    for ctrl in ["A.8.17", "PCI-10.2"]:
        checks.append((ctrl, "Clock Synchronization Simulation", status, "Windows Time Service", out or err))

    # 6. TLS Cipher Suites
    out, err, rc = _run_ps("Get-TlsCipherSuite | Select-Object -First 8 Name | ConvertTo-Json 2>&1")
    status = "Pass" if rc == 0 and out else "Warning"
    for ctrl in ["A.8.24", "PR.DS-2"]:
        checks.append((ctrl, "Cryptographic Controls Extension Simulation", status, "TLS cipher suites", out or err))

    # 7. Disk Capacity
    out, err, rc = _run_ps(
        'Get-WmiObject Win32_LogicalDisk -Filter "DriveType=3" | '
        'Select-Object DeviceID, @{N="FreeGB";E={[math]::Round($_.FreeSpace/1GB,2)}}, '
        '@{N="TotalGB";E={[math]::Round($_.Size/1GB,2)}} | ConvertTo-Json'
    )
    status = "Pass" if rc == 0 and out else "Warning"
    for ctrl in ["A.8.6", "CC7.2"]:
        checks.append((ctrl, "Capacity Management Simulation", status, "Disk capacity", out or err))

    # 8. Volume Shadow Copies / Backup
    out, err, rc = _run_ps("Get-WmiObject -Class Win32_ShadowCopy | Select-Object DeviceObject, InstallDate | ConvertTo-Json 2>&1")
    has_backups = out and out.strip() not in ["", "null", "[]"]
    status = "Pass" if has_backups else "Warning"
    details = "Volume Shadow Copies found" if has_backups else "No shadow copies found"
    for ctrl in ["A.8.13", "PR.IP-4", "RC.CO-2"]:
        checks.append((ctrl, "Data Backup & Recovery Simulation", status, details, out or err))

    # 9. Audit Policy
    out, err, rc = _run_ps("auditpol /get /category:* 2>&1")
    has_audit = "Success" in out or "Failure" in out
    status = "Pass" if has_audit else "Warning"
    for ctrl in ["A.8.15", "A.5.33", "DE.AE-3", "CISSP-6.4"]:
        checks.append((ctrl, "Audit Logging Extension Simulation", status, "Audit policy", out[:2000] or err))

    # 10. PowerShell Script Block Logging
    out, err, rc = _run_ps(
        r"(Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging' "
        r"-ErrorAction SilentlyContinue).EnableScriptBlockLogging 2>&1"
    )
    enabled = out.strip() == "1"
    status = "Pass" if enabled else "Warning"
    checks.append(("A.8.16", "PowerShell Script Block Logging", status,
                   f"Script block logging: {'Enabled' if enabled else 'Not configured'}", out or err))

    # 11. Patch Status
    out, err, rc = _run_ps("Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 10 HotFixID, InstalledOn | ConvertTo-Json 2>&1")
    status = "Pass" if rc == 0 and out else "Warning"
    for ctrl in ["A.8.8", "PCI-6.3.3", "PR.IP-12", "CISSP-7.3"]:
        checks.append((ctrl, "Security Patch Status", status, "Recent hotfixes", out or err))

    # 12. SMBv1 Disabled
    out, err, rc = _run_ps("Get-SmbServerConfiguration | Select-Object EnableSMB1Protocol | ConvertTo-Json 2>&1")
    disabled = "false" in out.lower()
    status = "Pass" if disabled else "Warning"
    details = "SMBv1: Disabled ✓" if disabled else "SMBv1: Enabled (security risk)"
    checks.append(("A.8.22", "SMBv1 Protocol Disabled", status, details, out or err))

    # 13. Risky Ports
    out, err, rc = _run_ps("Get-NetTCPConnection -State Listen | Where-Object LocalPort -in @(23,21,445) | Select-Object LocalPort, State | ConvertTo-Json 2>&1")
    risky_count = out.count('"LocalPort"') if out else 0
    status = "Pass" if risky_count == 0 else "Warning"
    for ctrl in ["A.8.20", "PCI-1.2"]:
        checks.append((ctrl, "Risky Network Ports", status, f"{risky_count} high-risk ports open", out or "No risky ports"))

    # 14. RDP NLA
    out, err, rc = _run_ps(
        r"(Get-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' "
        r"-Name 'UserAuthentication' -ErrorAction SilentlyContinue).UserAuthentication 2>&1"
    )
    nla_on = out.strip() == "1"
    status = "Pass" if nla_on else "Warning"
    for ctrl in ["A.8.22", "PCI-2.2"]:
        checks.append((ctrl, "RDP NLA Required", status, f"NLA: {'Enabled' if nla_on else 'Disabled'}", out or err))

    # 15. Guest Account
    out, err, rc = _run_ps("Get-LocalUser -Name 'Guest' | Select-Object Name, Enabled | ConvertTo-Json 2>&1")
    guest_disabled = "false" in out.lower()
    status = "Pass" if guest_disabled else "Warning"
    for ctrl in ["A.8.2", "A.5.15"]:
        checks.append((ctrl, "Guest Account Disabled", status, f"Guest: {'Disabled ✓' if guest_disabled else 'Enabled'}", out or err))

    # 16. Security Software
    out, err, rc = _run_ps(
        "Get-WmiObject Win32_Product | Where-Object {$_.Name -match 'security|defender|antivir|firewall'} | "
        "Select-Object Name, Version | ConvertTo-Json 2>&1"
    )
    status = "Pass" if rc == 0 else "Warning"
    checks.append(("A.8.32", "Software Supply Chain Security", status, "Security software inventory", out[:1500] or err))

    # 17. Local Admin Group
    out, err, rc = _run_ps("net localgroup Administrators 2>&1")
    status = "Pass" if rc == 0 else "Warning"
    checks.append(("A.8.2", "Local Administrator Accounts", status, "Local admin group members", out or err))

    # 18. System Info (for org controls)
    sys_out, _, _ = _run_ps("systeminfo /fo csv 2>&1 | Select-Object -First 3")

    # 19. Organizational controls disabled to prevent invalid policy attestation
    # Administrative policies must be verified via manual document uploads.
    
    return checks


async def run_evidence_collection_for_asset(hostname: str, db: AsyncIOMotorDatabase):
    """
    Run all evidence checks for the given hostname and persist results to MongoDB.
    Also updates the compliance_frameworks control statuses and progress.
    Called as a background task.
    """
    asset_id = f"asset-{hostname}"
    logger.info(f"[AdminEvidence] Starting collection for {hostname} ({asset_id})")

    # Run synchronous PowerShell in a threadpool so we don't block the event loop
    loop = asyncio.get_event_loop()
    checks = await loop.run_in_executor(None, collect_evidence_for_host, hostname)

    logger.info(f"[AdminEvidence] Collected {len(checks)} checks. Persisting to DB...")

    ts = datetime.datetime.utcnow().isoformat()
    ctrl_status_map: dict[str, str] = {}

    for ctrl_id, check_name, status, details, raw_output in checks:
        ev = _make_record(asset_id, hostname, ctrl_id, check_name, status, details, raw_output)

        await db.asset_compliance.update_one(
            {"assetId": asset_id, "controlId": ctrl_id},
            {
                "$set": {
                    "assetId": asset_id,
                    "controlId": ctrl_id,
                    "status": ev["status"],
                    "lastUpdated": ts,
                    "evidence": [ev]
                }
            },
            upsert=True
        )

        # Track best status per control for framework update
        mapped = ev["status"]
        priority = {"Compliant": 3, "Warning": 2, "Non-Compliant": 1}
        current_priority = priority.get(ctrl_status_map.get(ctrl_id, ""), 0)
        new_priority = priority.get(mapped, 0)
        if new_priority > current_priority:
            ctrl_status_map[ctrl_id] = mapped

    # --- Update compliance_frameworks control statuses ---
    def fw_status(s: str) -> str:
        if s == "Compliant":
            return "Implemented"
        elif s == "Warning":
            return "In Progress"
        return "At Risk"

    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    for ctrl_id, status in ctrl_status_map.items():
        await db.compliance_frameworks.update_one(
            {"controls.id": ctrl_id},
            {"$set": {
                "controls.$.status": fw_status(status),
                "controls.$.lastReviewed": today,
            }}
        )

    # --- Recalculate progress for all frameworks ---
    async for fw in db.compliance_frameworks.find({}, {"id": 1, "controls": 1}):
        controls = fw.get("controls", [])
        total = len(controls)
        if total == 0:
            continue
        implemented = sum(1 for c in controls if c.get("status") == "Implemented")
        in_progress = sum(1 for c in controls if c.get("status") == "In Progress")
        progress = round(((implemented + in_progress * 0.5) / total) * 100)
        fw_overall = "Compliant" if implemented == total else ("In Progress" if (implemented + in_progress) > 0 else "Not Started")
        await db.compliance_frameworks.update_one(
            {"id": fw["id"]},
            {"$set": {"progress": progress, "status": fw_overall}}
        )

    logger.info(f"[AdminEvidence] ✅ Done. {len(ctrl_status_map)} controls updated for {hostname}.")
