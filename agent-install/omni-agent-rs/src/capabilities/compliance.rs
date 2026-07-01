use super::Capability;
use serde_json::{json, Value};
use std::process::Command;
use sysinfo::System;

pub struct ComplianceCapability;

impl Capability for ComplianceCapability {
    fn id(&self) -> &'static str { "compliance_enforcement" }
    fn name(&self) -> &'static str { "Compliance Enforcement" }

    fn collect(&self, _sys: &System) -> Value {
        let checks = windows_compliance_checks();
        let total = checks.len();
        let passed = checks.iter().filter(|c| c["status"] == "Pass").count();
        let failed = total - passed;
        let score = if total == 0 {
            0.0
        } else {
            passed as f64 / total as f64 * 100.0
        };

        json!({
            "compliance_checks": checks,
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "compliance_score": (score * 10.0).round() / 10.0,
        })
    }
}

fn ps_json(cmd: &str) -> Option<serde_json::Value> {
    let out = Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", cmd])
        .output()
        .ok()?;
    let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if text.is_empty() {
        return None;
    }
    serde_json::from_str(&text).ok()
}

fn windows_compliance_checks() -> Vec<Value> {
    let mut checks: Vec<Value> = vec![];

    // Firewall profiles
    let fw_status = ps_json(
        "Get-NetFirewallProfile | Select-Object Name,Enabled | ConvertTo-Json -Compress",
    );
    let fw_ok = fw_status
        .as_ref()
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().all(|p| p["Enabled"] == true || p["Enabled"] == 1))
        .unwrap_or(false);
    checks.push(json!({
        "check": "Windows Firewall Profiles",
        "status": if fw_ok { "Pass" } else { "Fail" },
        "details": if fw_ok { "Firewall enabled on all profiles" } else { "Firewall disabled on one or more profiles" },
    }));

    // Windows Defender
    let av_status = ps_json(
        "Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled | ConvertTo-Json -Compress",
    );
    let av_ok = av_status
        .as_ref()
        .and_then(|v| v.get("AntivirusEnabled"))
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let rtp_ok = av_status
        .as_ref()
        .and_then(|v| v.get("RealTimeProtectionEnabled"))
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    checks.push(json!({
        "check": "Windows Defender Antivirus",
        "status": if av_ok { "Pass" } else { "Fail" },
        "details": if av_ok && rtp_ok { "Antivirus and real-time protection enabled" }
                   else if av_ok { "Antivirus enabled, real-time protection disabled" }
                   else { "Antivirus disabled" },
    }));

    // UAC via registry
    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;
        let uac_enabled = RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey(r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System")
            .and_then(|k| k.get_value::<u32, _>("EnableLUA"))
            .map(|v| v == 1)
            .unwrap_or(false);
        checks.push(json!({
            "check": "User Account Control (UAC)",
            "status": if uac_enabled { "Pass" } else { "Fail" },
            "details": if uac_enabled { "UAC is enabled" } else { "UAC is disabled" },
        }));
    }

    // BitLocker (system drive)
    let bl_status = ps_json(
        "Get-BitLockerVolume -MountPoint $env:SystemDrive -ErrorAction SilentlyContinue | Select-Object ProtectionStatus | ConvertTo-Json -Compress",
    );
    let bl_ok = bl_status
        .as_ref()
        .and_then(|v| v.get("ProtectionStatus"))
        .and_then(|v| v.as_i64())
        .map(|v| v == 1)
        .unwrap_or(false);
    checks.push(json!({
        "check": "BitLocker Drive Encryption",
        "status": if bl_ok { "Pass" } else { "Fail" },
        "details": if bl_ok { "System drive is BitLocker protected" } else { "System drive is not encrypted" },
    }));

    // Auto-update
    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;
        let au_val = RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey(r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update")
            .and_then(|k| k.get_value::<u32, _>("AUOptions"))
            .unwrap_or(0);
        // 4 = auto download and install
        let au_ok = au_val == 4;
        checks.push(json!({
            "check": "Windows Automatic Updates",
            "status": if au_ok { "Pass" } else { "Fail" },
            "details": format!("AUOptions registry value: {}", au_val),
        }));
    }


    // --- Password Policy (Min Length) ---
    let net_out = Command::new("net").args(["accounts"]).output()
        .ok().map(|o| String::from_utf8_lossy(&o.stdout).to_string()).unwrap_or_default();
    let min_len: u32 = net_out.lines()
        .find(|l| l.contains("Minimum password length"))
        .and_then(|l| l.split(':').nth(1))
        .and_then(|v| v.trim().parse().ok())
        .unwrap_or(0);
    checks.push(json!({
        "check": "Password Policy (Min Length)",
        "status": if min_len >= 8 { "Pass" } else { "Fail" },
        "details": format!("Minimum length: {} (required: 8)", min_len),
    }));

    // --- Guest Account Disabled ---
    let guest_status = ps_json(
        "try { Get-LocalUser -Name 'Guest' | Select-Object Enabled | ConvertTo-Json -Compress } catch { '{}' }"
    );
    let guest_enabled = guest_status.as_ref()
        .and_then(|v| v.get("Enabled")).and_then(|v| v.as_bool()).unwrap_or(true);
    checks.push(json!({
        "check": "Guest Account Disabled",
        "status": if !guest_enabled { "Pass" } else { "Fail" },
        "details": if !guest_enabled { "Guest account is disabled" } else { "Guest account is enabled (security risk)" },
    }));

    // --- RDP Network Level Authentication ---
    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;
        let nla_val = RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey(r"SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp")
            .and_then(|k| k.get_value::<u32, _>("UserAuthentication"))
            .unwrap_or(0);
        checks.push(json!({
            "check": "RDP Network Level Authentication",
            "status": if nla_val == 1 { "Pass" } else { "Fail" },
            "details": if nla_val == 1 { "NLA is required" } else { "NLA is not required" },
        }));
    }

    // --- Secure Boot ---
    let sb_out = Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", "Confirm-SecureBootUEFI"])
        .output().ok()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string()).unwrap_or_default();
    let sb_ok = sb_out.to_lowercase().contains("true");
    checks.push(json!({
        "check": "Secure Boot",
        "status": if sb_ok { "Pass" } else { "Fail" },
        "details": if sb_ok { "Secure Boot is enabled" } else { "Secure Boot not enabled or not UEFI" },
    }));

    // --- Windows Update Service ---
    let svc_out = Command::new("sc").args(["query", "wuauserv"]).output()
        .ok().map(|o| String::from_utf8_lossy(&o.stdout).to_string()).unwrap_or_default();
    let svc_ok = svc_out.contains("RUNNING");
    checks.push(json!({
        "check": "Windows Update Service",
        "status": if svc_ok { "Pass" } else { "Fail" },
        "details": if svc_ok { "Windows Update service is running" } else { "Windows Update service is not running" },
    }));

    // --- Audit Logging Policy ---
    let audit_out = Command::new("auditpol").args(["/get", "/category:Logon/Logoff"]).output()
        .ok().map(|o| String::from_utf8_lossy(&o.stdout).to_string()).unwrap_or_default();
    let audit_ok = audit_out.contains("Success and Failure");
    checks.push(json!({
        "check": "Audit Logging Policy",
        "status": if audit_ok { "Pass" } else { "Fail" },
        "details": "Logon/Logoff audit policy verification",
    }));

    // --- Risky Network Ports ---
    let netstat_out = Command::new("netstat").args(["-an"]).output()
        .ok().map(|o| String::from_utf8_lossy(&o.stdout).to_string()).unwrap_or_default();
    let has_telnet = netstat_out.contains(":23 ");
    let has_ftp = netstat_out.contains(":21 ");
    let mut risky_ports: Vec<&str> = vec![];
    if has_telnet { risky_ports.push("Telnet (23)"); }
    if has_ftp { risky_ports.push("FTP (21)"); }
    let ports_ok = risky_ports.is_empty();
    checks.push(json!({
        "check": "Risky Network Ports",
        "status": if ports_ok { "Pass" } else { "Fail" },
        "details": if ports_ok { "No risky ports open".to_string() } else { format!("Open risky ports: {}", risky_ports.join(", ")) },
    }));

    // --- TLS 1.0 Disabled ---
    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;
        let tls10_enabled = RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey(r"SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\TLS 1.0\Server")
            .and_then(|k| k.get_value::<u32, _>("Enabled"))
            .map(|v: u32| v == 1)
            .unwrap_or(false);
        checks.push(json!({
            "check": "TLS 1.0 Disabled",
            "status": if !tls10_enabled { "Pass" } else { "Fail" },
            "details": if !tls10_enabled { "TLS 1.0 is disabled" } else { "TLS 1.0 is enabled (security risk)" },
        }));
    }

    // --- Prohibited Software ---
    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;
        let blacklist = ["bittorrent", "utorrent", "cheat engine"];
        let mut found: Vec<String> = vec![];
        for path in [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ] {
            if let Ok(key) = RegKey::predef(HKEY_LOCAL_MACHINE).open_subkey(path) {
                for sk in key.enum_keys().flatten() {
                    if let Ok(sub) = key.open_subkey(&sk) {
                        let name: String = sub.get_value("DisplayName").unwrap_or_default();
                        let lower = name.to_lowercase();
                        if blacklist.iter().any(|b| lower.contains(b)) {
                            found.push(name);
                        }
                    }
                }
            }
        }
        checks.push(json!({
            "check": "Prohibited Software",
            "status": if found.is_empty() { "Pass" } else { "Fail" },
            "details": if found.is_empty() { "No prohibited software found".to_string() } else { format!("Found: {}", found.join(", ")) },
        }));
    }

    checks
}
