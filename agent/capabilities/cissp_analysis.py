"""
CISSP Analysis Capability
=========================
Provides CISSP (Certified Information Systems Security Professional) domain-based
security analysis for the Omni-Agent. Covers all 8 official domains:

  1. Security & Risk Management
  2. Asset Security
  3. Security Architecture & Engineering
  4. Communication & Network Security
  5. Identity & Access Management
  6. Security Assessment & Testing
  7. Security Operations
  8. Software Development Security

The analysis runs real system checks via PowerShell and generates a professional
CISSP-style risk assessment report with domain scores and findings.
"""

import subprocess
import datetime
import json
import platform
from typing import Any


def _run_ps(cmd: str, timeout: int = 10) -> tuple:
    """Execute a PowerShell command. Returns (stdout, returncode)."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip(), r.returncode
    except Exception as e:
        return f"[ERROR: {e}]", -1


def _score(passed: int, total: int) -> int:
    """Calculate a 0-100 domain score."""
    if total == 0:
        return 0
    return round((passed / total) * 100)


def _risk_level(score: int) -> str:
    if score >= 80:
        return "Low"
    elif score >= 60:
        return "Medium"
    elif score >= 40:
        return "High"
    return "Critical"


def _run_cissp_domain1() -> dict:
    """Domain 1: Security & Risk Management"""
    findings = []
    passed = 0
    total = 0

    # Check 1: Password policy exists
    out, rc = _run_ps("net accounts")
    total += 1
    has_policy = "Minimum password length" in out
    if has_policy:
        passed += 1
        findings.append({"check": "Password Policy Defined", "status": "Pass",
                          "detail": "Password policy is enforced via net accounts."})
    else:
        findings.append({"check": "Password Policy Defined", "status": "Fail",
                          "detail": "No password policy detected. Risk: credential-based attacks."})

    # Check 2: Account lockout configured
    total += 1
    lockout_lines = [l for l in out.splitlines() if "Lockout threshold" in l]
    lockout_val = 0
    if lockout_lines:
        try:
            lockout_val = int(lockout_lines[0].split()[-1])
        except Exception:
            pass
    if lockout_val > 0:
        passed += 1
        findings.append({"check": "Account Lockout Policy", "status": "Pass",
                          "detail": f"Lockout threshold: {lockout_val} attempts."})
    else:
        findings.append({"check": "Account Lockout Policy", "status": "Fail",
                          "detail": "No lockout threshold — susceptible to brute-force attacks."})

    # Check 3: Audit policy enabled
    out2, rc2 = _run_ps("auditpol /get /category:* 2>&1 | Select-Object -First 10")
    total += 1
    if "Success" in out2 or "Failure" in out2:
        passed += 1
        findings.append({"check": "Audit Policy Active", "status": "Pass",
                          "detail": "Security audit policies are configured."})
    else:
        findings.append({"check": "Audit Policy Active", "status": "Fail",
                          "detail": "No audit policy found. Compliance logging required."})

    return {"domain": "Security & Risk Management", "domain_id": 1, "score": _score(passed, total),
            "risk_level": _risk_level(_score(passed, total)), "passed": passed, "total": total, "findings": findings}


def _run_cissp_domain2() -> dict:
    """Domain 2: Asset Security"""
    findings = []
    passed = 0
    total = 0

    # Check 1: BitLocker encryption
    out, rc = _run_ps("manage-bde -status C: 2>&1")
    total += 1
    if "Protection On" in out:
        passed += 1
        findings.append({"check": "Data Encryption at Rest (BitLocker)", "status": "Pass",
                          "detail": "C: drive is BitLocker protected."})
    else:
        findings.append({"check": "Data Encryption at Rest (BitLocker)", "status": "Fail",
                          "detail": "BitLocker not enabled on C:. Data at risk if device is lost."})

    # Check 2: Disk inventory
    out2, rc2 = _run_ps(
        "Get-WmiObject Win32_LogicalDisk -Filter 'DriveType=3' | "
        "Select-Object DeviceID, @{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,2)}}, "
        "@{N='TotalGB';E={[math]::Round($_.Size/1GB,2)}} | ConvertTo-Json 2>&1"
    )
    total += 1
    if rc2 == 0 and out2:
        passed += 1
        findings.append({"check": "Asset Storage Inventory", "status": "Pass",
                          "detail": "Disk assets successfully inventoried."})
    else:
        findings.append({"check": "Asset Storage Inventory", "status": "Warning",
                          "detail": "Could not enumerate disk assets."})

    # Check 3: Installed software inventory
    out3, rc3 = _run_ps(
        "Get-WmiObject Win32_Product | Measure-Object | Select-Object -ExpandProperty Count"
    )
    total += 1
    try:
        sw_count = int(out3.strip())
        passed += 1
        findings.append({"check": "Software Asset Inventory", "status": "Pass",
                          "detail": f"{sw_count} software packages inventoried."})
    except Exception:
        findings.append({"check": "Software Asset Inventory", "status": "Warning",
                          "detail": "Unable to enumerate installed software."})

    return {"domain": "Asset Security", "domain_id": 2, "score": _score(passed, total),
            "risk_level": _risk_level(_score(passed, total)), "passed": passed, "total": total, "findings": findings}


def _run_cissp_domain3() -> dict:
    """Domain 3: Security Architecture & Engineering"""
    findings = []
    passed = 0
    total = 0

    # Check 1: Secure Boot
    out, rc = _run_ps("Confirm-SecureBootUEFI 2>&1")
    total += 1
    if "True" in out:
        passed += 1
        findings.append({"check": "Secure Boot Enabled", "status": "Pass", "detail": "Secure Boot is active."})
    else:
        findings.append({"check": "Secure Boot Enabled", "status": "Warning",
                          "detail": "Secure Boot may not be enabled or BIOS-mode system."})

    # Check 2: TLS cipher suites
    out2, rc2 = _run_ps("Get-TlsCipherSuite | Select-Object -First 5 Name | ConvertTo-Json 2>&1")
    total += 1
    if rc2 == 0 and out2:
        passed += 1
        findings.append({"check": "TLS Cipher Suite Inventory", "status": "Pass",
                          "detail": "TLS cipher suites enumerated. Verify no weak ciphers (RC4, DES, 3DES)."})
    else:
        findings.append({"check": "TLS Cipher Suite Inventory", "status": "Warning",
                          "detail": "Could not enumerate TLS cipher suites."})

    # Check 3: Exploit Protection
    out3, rc3 = _run_ps("Get-ProcessMitigation -System 2>&1 | Select-Object -First 5")
    total += 1
    if rc3 == 0 and out3 and "Error" not in out3:
        passed += 1
        findings.append({"check": "Exploit Protection (DEP/ASLR)", "status": "Pass",
                          "detail": "System exploit protections are configured."})
    else:
        findings.append({"check": "Exploit Protection (DEP/ASLR)", "status": "Warning",
                          "detail": "Exploit protection status could not be verified."})

    # Check 4: SMBv1 disabled
    out4, rc4 = _run_ps("Get-SmbServerConfiguration | Select-Object EnableSMB1Protocol | ConvertTo-Json 2>&1")
    total += 1
    if "false" in out4.lower():
        passed += 1
        findings.append({"check": "Legacy Protocol Disabled (SMBv1)", "status": "Pass",
                          "detail": "SMBv1 is disabled. EternalBlue vulnerability mitigated."})
    else:
        findings.append({"check": "Legacy Protocol Disabled (SMBv1)", "status": "Fail",
                          "detail": "SMBv1 may be enabled. Critical vulnerability risk (EternalBlue/WannaCry)."})

    return {"domain": "Security Architecture & Engineering", "domain_id": 3, "score": _score(passed, total),
            "risk_level": _risk_level(_score(passed, total)), "passed": passed, "total": total, "findings": findings}


def _run_cissp_domain4() -> dict:
    """Domain 4: Communication & Network Security"""
    findings = []
    passed = 0
    total = 0

    # Check 1: Firewall enabled
    out, rc = _run_ps("Get-NetFirewallProfile | Select-Object Name, Enabled | ConvertTo-Json")
    total += 1
    if out and "true" in out.lower():
        passed += 1
        findings.append({"check": "Host Firewall Active", "status": "Pass",
                          "detail": "Windows Firewall is enabled on at least one profile."})
    else:
        findings.append({"check": "Host Firewall Active", "status": "Fail",
                          "detail": "No firewall profiles are enabled. Critical exposure."})

    # Check 2: No risky ports listening
    out2, rc2 = _run_ps(
        "Get-NetTCPConnection -State Listen | Where-Object LocalPort -in @(23,21,445,135,139) | "
        "Select-Object LocalPort | ConvertTo-Json 2>&1"
    )
    total += 1
    risky = out2.count('"LocalPort"') if out2 else 0
    if risky == 0:
        passed += 1
        findings.append({"check": "Risky Ports Closed", "status": "Pass",
                          "detail": "No high-risk ports (Telnet/FTP/NetBIOS/RPC) detected."})
    else:
        findings.append({"check": "Risky Ports Closed", "status": "Fail",
                          "detail": f"{risky} high-risk listening ports detected. Immediate remediation required."})

    # Check 3: RDP with NLA
    out3, rc3 = _run_ps(
        r"(Get-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' "
        r"-Name 'UserAuthentication' -ErrorAction SilentlyContinue).UserAuthentication 2>&1"
    )
    total += 1
    if out3.strip() == "1":
        passed += 1
        findings.append({"check": "RDP Network Level Authentication", "status": "Pass",
                          "detail": "RDP NLA is required — pre-authentication enforced."})
    else:
        findings.append({"check": "RDP Network Level Authentication", "status": "Warning",
                          "detail": "RDP NLA not enforced. Vulnerable to credential attacks."})

    # Check 4: IPv6 redirect/routing
    out4, rc4 = _run_ps("Get-NetIPConfiguration | Select-Object InterfaceAlias, IPv4Address | ConvertTo-Json 2>&1")
    total += 1
    if rc4 == 0 and out4:
        passed += 1
        findings.append({"check": "Network Interface Inventory", "status": "Pass",
                          "detail": "Network interfaces successfully enumerated for review."})
    else:
        findings.append({"check": "Network Interface Inventory", "status": "Warning",
                          "detail": "Could not enumerate network interfaces."})

    return {"domain": "Communication & Network Security", "domain_id": 4, "score": _score(passed, total),
            "risk_level": _risk_level(_score(passed, total)), "passed": passed, "total": total, "findings": findings}


def _run_cissp_domain5() -> dict:
    """Domain 5: Identity & Access Management"""
    findings = []
    passed = 0
    total = 0

    # Check 1: Local admin group size  
    out, rc = _run_ps("net localgroup Administrators 2>&1")
    total += 1
    lines = [l.strip() for l in out.splitlines() if l.strip() and "---" not in l and "command" not in l.lower() and "members" not in l.lower()]
    admin_count = len([l for l in lines if l and not l.startswith("The command")])
    if admin_count <= 3:
        passed += 1
        findings.append({"check": "Minimal Admin Accounts", "status": "Pass",
                          "detail": f"Administrator group has {admin_count} member(s). Principle of least privilege maintained."})
    else:
        findings.append({"check": "Minimal Admin Accounts", "status": "Warning",
                          "detail": f"Administrator group has {admin_count} members. Review for excess privilege."})

    # Check 2: Guest account disabled
    out2, rc2 = _run_ps("Get-LocalUser -Name 'Guest' | Select-Object Name, Enabled | ConvertTo-Json 2>&1")
    total += 1
    if "false" in out2.lower():
        passed += 1
        findings.append({"check": "Guest Account Disabled", "status": "Pass",
                          "detail": "Guest account is disabled."})
    else:
        findings.append({"check": "Guest Account Disabled", "status": "Fail",
                          "detail": "Guest account is enabled — unauthorized access risk."})

    # Check 3: UAC Enabled
    out3, rc3 = _run_ps(
        r"(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' "
        r"-Name 'EnableLUA' -ErrorAction SilentlyContinue).EnableLUA 2>&1"
    )
    total += 1
    if out3.strip() == "1":
        passed += 1
        findings.append({"check": "User Account Control (UAC)", "status": "Pass",
                          "detail": "UAC is enabled — privilege escalation barrier active."})
    else:
        findings.append({"check": "User Account Control (UAC)", "status": "Fail",
                          "detail": "UAC is disabled. Administrative actions require no elevation prompt."})

    # Check 4: Credential Guard
    out4, rc4 = _run_ps(
        "Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\\Microsoft\\Windows\\DeviceGuard "
        "-ErrorAction SilentlyContinue | Select-Object SecurityServicesRunning | ConvertTo-Json 2>&1"
    )
    total += 1
    if out4 and "2" in out4:  # 2 = Credential Guard running
        passed += 1
        findings.append({"check": "Credential Guard Active", "status": "Pass",
                          "detail": "Credential Guard is running — LSASS credentials isolated."})
    else:
        findings.append({"check": "Credential Guard Active", "status": "Warning",
                          "detail": "Credential Guard not detected. Pass-the-Hash risk."})

    return {"domain": "Identity & Access Management", "domain_id": 5, "score": _score(passed, total),
            "risk_level": _risk_level(_score(passed, total)), "passed": passed, "total": total, "findings": findings}


def _run_cissp_domain6() -> dict:
    """Domain 6: Security Assessment & Testing"""
    findings = []
    passed = 0
    total = 0

    # Check 1: Recent hotfixes / patch history
    out, rc = _run_ps("Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 5 HotFixID, InstalledOn | ConvertTo-Json 2>&1")
    total += 1
    if rc == 0 and out and "HotFixID" in out:
        passed += 1
        findings.append({"check": "Patch History Available", "status": "Pass",
                          "detail": "Recent hotfixes found — patch management is active."})
    else:
        findings.append({"check": "Patch History Available", "status": "Warning",
                          "detail": "No recent hotfixes found. Verify patch management process."})

    # Check 2: Audit log access
    out2, rc2 = _run_ps("auditpol /get /category:* 2>&1")
    total += 1
    if "Success" in out2 or "Failure" in out2:
        passed += 1
        findings.append({"check": "Audit Log Configuration", "status": "Pass",
                          "detail": "Audit policies configured for security events."})
    else:
        findings.append({"check": "Audit Log Configuration", "status": "Fail",
                          "detail": "Security audit logging not configured — assessment blind spot."})

    # Check 3: Windows Event Log accessible
    out3, rc3 = _run_ps(
        "Get-EventLog -LogName Security -Newest 5 2>&1 | Measure-Object | Select-Object -ExpandProperty Count"
    )
    total += 1
    try:
        count = int(out3.strip())
        if count > 0:
            passed += 1
            findings.append({"check": "Security Event Log Access", "status": "Pass",
                              "detail": f"{count} recent security events accessible for review."})
        else:
            findings.append({"check": "Security Event Log Access", "status": "Warning",
                              "detail": "Security event log is empty or inaccessible."})
    except Exception:
        findings.append({"check": "Security Event Log Access", "status": "Warning",
                          "detail": "Could not access Windows Security Event Log."})

    return {"domain": "Security Assessment & Testing", "domain_id": 6, "score": _score(passed, total),
            "risk_level": _risk_level(_score(passed, total)), "passed": passed, "total": total, "findings": findings}


def _run_cissp_domain7() -> dict:
    """Domain 7: Security Operations"""
    findings = []
    passed = 0
    total = 0

    # Check 1: Windows Defender running
    out, rc = _run_ps(
        "Get-MpComputerStatus | Select-Object AMServiceEnabled, RealTimeProtectionEnabled, "
        "AntivirusSignatureAge | ConvertTo-Json 2>&1"
    )
    total += 1
    if out and "true" in out.lower():
        passed += 1
        findings.append({"check": "Anti-Malware Service Running", "status": "Pass",
                          "detail": "Windows Defender / anti-malware is active."})
    else:
        findings.append({"check": "Anti-Malware Service Running", "status": "Fail",
                          "detail": "Anti-malware service not running. Immediate risk."})

    # Check 2: Windows Update Service
    out2, rc2 = _run_ps("Get-Service wuauserv | Select-Object Status | ConvertTo-Json 2>&1")
    total += 1
    if "Running" in out2 or "running" in out2.lower():
        passed += 1
        findings.append({"check": "Windows Update Service", "status": "Pass",
                          "detail": "Windows Update (wuauserv) is running."})
    else:
        findings.append({"check": "Windows Update Service", "status": "Warning",
                          "detail": "Windows Update service is not running."})

    # Check 3: Volume shadow copies (DR/backup)
    out3, rc3 = _run_ps(
        "Get-WmiObject Win32_ShadowCopy | Measure-Object | Select-Object -ExpandProperty Count"
    )
    total += 1
    try:
        sc_count = int(out3.strip())
        if sc_count > 0:
            passed += 1
            findings.append({"check": "Backup / Shadow Copies Exist", "status": "Pass",
                              "detail": f"{sc_count} volume shadow copies available for disaster recovery."})
        else:
            findings.append({"check": "Backup / Shadow Copies Exist", "status": "Warning",
                              "detail": "No shadow copies found. DR capability may be insufficient."})
    except Exception:
        findings.append({"check": "Backup / Shadow Copies Exist", "status": "Warning",
                          "detail": "Could not enumerate shadow copies."})

    # Check 4: PowerShell Script Block logging (threat detection)
    out4, rc4 = _run_ps(
        r"(Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging' "
        r"-ErrorAction SilentlyContinue).EnableScriptBlockLogging 2>&1"
    )
    total += 1
    if out4.strip() == "1":
        passed += 1
        findings.append({"check": "PowerShell Script Block Logging", "status": "Pass",
                          "detail": "PS script block logging enabled. Threat hunting capability active."})
    else:
        findings.append({"check": "PowerShell Script Block Logging", "status": "Warning",
                          "detail": "Script block logging not enabled. PowerShell-based attacks harder to detect."})

    return {"domain": "Security Operations", "domain_id": 7, "score": _score(passed, total),
            "risk_level": _risk_level(_score(passed, total)), "passed": passed, "total": total, "findings": findings}


def _run_cissp_domain8() -> dict:
    """Domain 8: Software Development Security"""
    findings = []
    passed = 0
    total = 0

    # Check 1: Attack Surface Reduction rules
    out, rc = _run_ps(
        "Get-MpPreference | Select-Object AttackSurfaceReductionRules_Ids | ConvertTo-Json 2>&1"
    )
    total += 1
    if out and "null" not in out.lower() and len(out) > 10:
        passed += 1
        findings.append({"check": "Attack Surface Reduction Rules", "status": "Pass",
                          "detail": "ASR rules configured — reduces application attack surface."})
    else:
        findings.append({"check": "Attack Surface Reduction Rules", "status": "Warning",
                          "detail": "No ASR rules detected. Consider enabling via Defender for Endpoint."})

    # Check 2: AppLocker or WDAC policy
    out2, rc2 = _run_ps("Get-AppLockerPolicy -Effective 2>&1 | Select-Object -First 3")
    total += 1
    if rc2 == 0 and out2 and "Error" not in out2:
        passed += 1
        findings.append({"check": "Application Control (AppLocker)", "status": "Pass",
                          "detail": "AppLocker/WDAC policy is active — unauthorized code execution restricted."})
    else:
        findings.append({"check": "Application Control (AppLocker)", "status": "Warning",
                          "detail": "No AppLocker policy detected. Any executable can run."})

    # Check 3: DEP/ASLR system-wide
    out3, rc3 = _run_ps("Get-ProcessMitigation -System 2>&1")
    total += 1
    if rc3 == 0 and out3:
        passed += 1
        findings.append({"check": "System-wide Exploit Mitigations", "status": "Pass",
                          "detail": "System exploit mitigations (DEP/ASLR/CFG) are configured."})
    else:
        findings.append({"check": "System-wide Exploit Mitigations", "status": "Warning",
                          "detail": "System exploit mitigations not fully configured."})

    return {"domain": "Software Development Security", "domain_id": 8, "score": _score(passed, total),
            "risk_level": _risk_level(_score(passed, total)), "passed": passed, "total": total, "findings": findings}


def run_cissp_assessment() -> dict:
    """
    Run a full CISSP 8-domain security assessment and return structured results.
    This is the main entry point called by the agent dispatcher.
    """
    timestamp = datetime.datetime.utcnow().isoformat()
    hostname = platform.node()

    print(f"[CISSP] Starting 8-domain assessment on {hostname}...")

    domain_results = []
    domain_runners = [
        _run_cissp_domain1,
        _run_cissp_domain2,
        _run_cissp_domain3,
        _run_cissp_domain4,
        _run_cissp_domain5,
        _run_cissp_domain6,
        _run_cissp_domain7,
        _run_cissp_domain8,
    ]

    for runner in domain_runners:
        try:
            result = runner()
            domain_results.append(result)
            print(f"  [D{result['domain_id']}] {result['domain']}: {result['score']}/100 ({result['risk_level']} Risk)")
        except Exception as e:
            print(f"  [ERROR] Domain runner failed: {e}")

    # Calculate overall score
    if domain_results:
        overall_score = round(sum(d["score"] for d in domain_results) / len(domain_results))
    else:
        overall_score = 0

    overall_risk = _risk_level(overall_score)

    # Identify critical findings
    critical_findings = [
        f for d in domain_results
        for f in d.get("findings", [])
        if f.get("status") == "Fail"
    ]

    report = {
        "type": "cissp_assessment",
        "timestamp": timestamp,
        "hostname": hostname,
        "overall_score": overall_score,
        "overall_risk_level": overall_risk,
        "domains": domain_results,
        "critical_findings_count": len(critical_findings),
        "critical_findings": critical_findings[:10],  # Top 10
        "summary": (
            f"CISSP Assessment for {hostname}: Overall Score {overall_score}/100 ({overall_risk} Risk). "
            f"{len([d for d in domain_results if d['risk_level'] == 'Low'])} of {len(domain_results)} "
            f"domains at Low risk. {len(critical_findings)} critical finding(s) require immediate attention."
        )
    }

    print(f"[CISSP] Assessment complete. Overall: {overall_score}/100 ({overall_risk} Risk)")
    return report


def get_compliance_checks_from_cissp() -> list:
    """
    Convert CISSP assessment results into the standard compliance_checks format
    used by the agent to report evidence back to the backend.
    """
    assessment = run_cissp_assessment()
    checks = []

    for domain in assessment.get("domains", []):
        for finding in domain.get("findings", []):
            status = "Pass" if finding["status"] == "Pass" else (
                "Warning" if finding["status"] == "Warning" else "Fail"
            )
            checks.append({
                "check": finding["check"],
                "status": status,
                "detail": finding["detail"],
                "domain": domain["domain"],
                "cissp_domain_id": domain["domain_id"],
                "evidence_content": (
                    f"CISSP Domain {domain['domain_id']}: {domain['domain']}\n"
                    f"Check: {finding['check']}\n"
                    f"Status: {status}\n"
                    f"Detail: {finding['detail']}\n"
                    f"Domain Score: {domain['score']}/100 ({domain['risk_level']} Risk)"
                )
            })

    return checks
