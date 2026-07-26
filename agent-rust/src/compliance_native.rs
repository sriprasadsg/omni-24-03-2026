/*!
 * Native Windows Registry compliance checks — no PowerShell required.
 * Reads HKLM directly via winreg; works even when PowerShell is unavailable
 * or blocked in the Windows Service session.
 * Check names match COMPLIANCE_CHECK_MAPPINGS keys in compliance_evidence_processor.py.
 */
#[cfg(windows)]
use winreg::{RegKey, enums::*};
use serde_json::{json, Value};

// ── Registry helpers ──────────────────────────────────────────────────────────

fn rdw(path: &str, name: &str) -> Option<u32> {
    #[cfg(windows)]
    {
        RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey_with_flags(path, KEY_READ).ok()?
            .get_value(name).ok()
    }
    #[cfg(not(windows))]
    { let _ = (path, name); None }
}

fn rstr(path: &str, name: &str) -> Option<String> {
    #[cfg(windows)]
    {
        RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey_with_flags(path, KEY_READ).ok()?
            .get_value(name).ok()
    }
    #[cfg(not(windows))]
    { let _ = (path, name); None }
}

fn key_exists(path: &str) -> bool {
    #[cfg(windows)]
    {
        RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey_with_flags(path, KEY_READ).is_ok()
    }
    #[cfg(not(windows))]
    { let _ = path; false }
}

#[cfg(windows)]
fn subkey_count(path: &str) -> usize {
    RegKey::predef(HKEY_LOCAL_MACHINE)
        .open_subkey_with_flags(path, KEY_READ)
        .map(|k| k.enum_values().count())
        .unwrap_or(0)
}
#[cfg(not(windows))]
fn subkey_count(_path: &str) -> usize { 0 }

fn add(c: &mut Vec<Value>, n: &str, s: &str, d: &str) {
    c.push(json!({"check": n, "status": s, "details": d}));
}
fn pass(c: &mut Vec<Value>, n: &str, d: &str) { add(c, n, "Pass", d); }
fn warn(c: &mut Vec<Value>, n: &str, d: &str) { add(c, n, "Warning", d); }
fn fail(c: &mut Vec<Value>, n: &str, d: &str) { add(c, n, "Fail", d); }

// ── Native compliance checks ──────────────────────────────────────────────────

pub fn run_native_compliance() -> Value {
    let mut c: Vec<Value> = Vec::new();

    // 1. BitLocker Encryption
    // BootStatus=1: pre-boot auth recorded. BootStatus=0: successful boot (TPM+PIN, TPM-only,
    // or Intune-managed devices use 0 for a clean/successful boot — it is NOT "off").
    // Corroborate BootStatus=0 with the fvevol driver key which is only present when
    // BitLocker is actively loaded. The PS check (Get-BitLockerVolume) is authoritative
    // and runs alongside this; native result is overridden when PS succeeds.
    match rdw("SYSTEM\\CurrentControlSet\\Control\\BitLockerStatus", "BootStatus") {
        Some(1) => pass(&mut c, "BitLocker Encryption", "BitLocker active (BootStatus=1)"),
        Some(0) => {
            // BootStatus=0 on a protected drive means clean/successful boot, not "off".
            // Confirm by checking the fvevol BitLocker filter driver is registered.
            if key_exists("SYSTEM\\CurrentControlSet\\Services\\fvevol") {
                pass(&mut c, "BitLocker Encryption", "BitLocker active (BootStatus=0, fvevol loaded)")
            } else {
                warn(&mut c, "BitLocker Encryption", "BitLocker status unclear (BootStatus=0, fvevol absent)")
            }
        }
        Some(v) => warn(&mut c, "BitLocker Encryption", &format!("BitLocker inactive (BootStatus={v})")),
        None => warn(&mut c, "BitLocker Encryption", "BitLocker registry key absent — check via PS"),
    }

    // 2. User Access Control
    match rdw("SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System", "EnableLUA") {
        Some(1) => pass(&mut c, "User Access Control", "UAC enabled (EnableLUA=1)"),
        Some(0) => fail(&mut c, "User Access Control", "UAC disabled — privilege escalation risk"),
        _ => warn(&mut c, "User Access Control", "UAC state undetermined"),
    }

    // 3. Secure Boot
    match rdw("SYSTEM\\CurrentControlSet\\Control\\SecureBoot\\State", "UEFISecureBootEnabled") {
        Some(1) => pass(&mut c, "Secure Boot", "Secure Boot enabled via UEFI"),
        Some(0) => warn(&mut c, "Secure Boot", "Secure Boot disabled"),
        None => warn(&mut c, "Secure Boot", "Secure Boot key absent (legacy BIOS or VM)"),
        _ => warn(&mut c, "Secure Boot", "Secure Boot state undetermined"),
    }

    // 4. Remote Desktop Service
    match rdw("SYSTEM\\CurrentControlSet\\Control\\Terminal Server", "fDenyTSConnections") {
        Some(1) => pass(&mut c, "Remote Desktop Service", "RDP disabled"),
        Some(0) => warn(&mut c, "Remote Desktop Service", "RDP enabled — verify NLA and firewall scope"),
        _ => warn(&mut c, "Remote Desktop Service", "RDP state undetermined"),
    }

    // 5. RDP NLA Required
    match rdw("SYSTEM\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp", "UserAuthentication") {
        Some(1) => pass(&mut c, "RDP NLA Required", "Network Level Authentication required"),
        Some(0) => warn(&mut c, "RDP NLA Required", "NLA not enforced — credential exposure risk"),
        _ => warn(&mut c, "RDP NLA Required", "RDP NLA state undetermined"),
    }

    // 6. SMBv1 Protocol Disabled
    match rdw("SYSTEM\\CurrentControlSet\\Services\\LanmanServer\\Parameters", "SMB1") {
        Some(0) => pass(&mut c, "SMBv1 Protocol Disabled", "SMBv1 disabled (registry SMB1=0)"),
        Some(1) => fail(&mut c, "SMBv1 Protocol Disabled", "SMBv1 ENABLED — EternalBlue attack surface"),
        None => {
            // Win10 v1709+ disables SMBv1 by default; mrxsmb10 Start=4 confirms driver disabled.
            let drv = rdw("SYSTEM\\CurrentControlSet\\Services\\mrxsmb10", "Start");
            let msg = match drv {
                Some(4) => "SMBv1 key absent + mrxsmb10 driver disabled (Start=4) — disabled by OS default",
                _ => "SMBv1 key absent — disabled by OS default on Win10+ v1709+",
            };
            pass(&mut c, "SMBv1 Protocol Disabled", msg);
        }
        _ => warn(&mut c, "SMBv1 Protocol Disabled", "SMBv1 state undetermined"),
    }

    // 7. PowerShell Script Block Logging
    match rdw("SOFTWARE\\Policies\\Microsoft\\Windows\\PowerShell\\ScriptBlockLogging", "EnableScriptBlockLogging") {
        Some(1) => pass(&mut c, "PowerShell Script Block Logging", "Script block logging enabled via GPO"),
        _ => warn(&mut c, "PowerShell Script Block Logging", "Script block logging not configured"),
    }

    // 8. WinRM Status
    match rdw("SYSTEM\\CurrentControlSet\\Services\\WinRM", "Start") {
        Some(4) => pass(&mut c, "WinRM Status", "WinRM service disabled (Start=4)"),
        Some(v) => warn(&mut c, "WinRM Status", &format!("WinRM Start={v} — verify firewall scope")),
        None => pass(&mut c, "WinRM Status", "WinRM key absent (not installed)"),
    }

    // 9. Windows Update Service
    match rdw("SYSTEM\\CurrentControlSet\\Services\\wuauserv", "Start") {
        Some(4) => fail(&mut c, "Windows Update Service", "Windows Update DISABLED (Start=4)"),
        Some(v) => pass(&mut c, "Windows Update Service", &format!("Windows Update enabled (Start={v})")),
        None => warn(&mut c, "Windows Update Service", "wuauserv service key not found"),
    }

    // 10. Windows Firewall Profiles (registry — no PS module needed)
    let fw_dom  = rdw("SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters\\FirewallPolicy\\DomainProfile", "EnableFirewall");
    let fw_priv = rdw("SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters\\FirewallPolicy\\StandardProfile", "EnableFirewall");
    let fw_pub  = rdw("SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters\\FirewallPolicy\\PublicProfile", "EnableFirewall");
    let all_on  = fw_dom == Some(1) && fw_priv == Some(1) && fw_pub == Some(1);
    let any_on  = fw_dom == Some(1) || fw_priv == Some(1) || fw_pub == Some(1);
    let fw_det  = format!("Domain:{} Private:{} Public:{}", fw_dom.unwrap_or(0), fw_priv.unwrap_or(0), fw_pub.unwrap_or(0));
    if all_on   { pass(&mut c, "Windows Firewall Profiles", &fw_det); }
    else if any_on { warn(&mut c, "Windows Firewall Profiles", &format!("Some profiles disabled — {fw_det}")); }
    else        { fail(&mut c, "Windows Firewall Profiles", &format!("Firewall appears disabled — {fw_det}")); }

    // 11. Windows Defender Antivirus (registry)
    match rdw("SOFTWARE\\Microsoft\\Windows Defender\\Real-Time Protection", "DisableRealtimeMonitoring") {
        Some(0) | None => pass(&mut c, "Windows Defender Antivirus", "Real-time protection enabled"),
        Some(1) => fail(&mut c, "Windows Defender Antivirus", "Real-time protection DISABLED via registry"),
        _ => warn(&mut c, "Windows Defender Antivirus", "Defender RTP state undetermined"),
    }

    // 12. Credential Guard
    let cg_lsa = rdw("SYSTEM\\CurrentControlSet\\Control\\LSA", "LsaCfgFlags");
    let cg_vbs = rdw("SYSTEM\\CurrentControlSet\\Control\\DeviceGuard", "EnableVirtualizationBasedSecurity");
    let cg_on  = cg_lsa.map_or(false, |v| v >= 1) || cg_vbs == Some(1);
    if cg_on { pass(&mut c, "Credential Guard", &format!("Enabled (LsaCfgFlags={:?} VBS={:?})", cg_lsa, cg_vbs)); }
    else     { warn(&mut c, "Credential Guard", "Credential Guard not configured"); }

    // 13. Device Guard/WDAC
    let vbs  = rdw("SYSTEM\\CurrentControlSet\\Control\\DeviceGuard", "EnableVirtualizationBasedSecurity");
    let hvci = rdw("SYSTEM\\CurrentControlSet\\Control\\DeviceGuard", "HypervisorEnforcedCodeIntegrity");
    if vbs == Some(1) || hvci == Some(1) {
        pass(&mut c, "Device Guard/WDAC", &format!("VBS={:?} HVCI={:?}", vbs, hvci));
    } else {
        warn(&mut c, "Device Guard/WDAC", "Device Guard/WDAC not enabled");
    }

    // 14. Exploit Protection (DEP/ASLR)
    let ep_set = rdw("SYSTEM\\CurrentControlSet\\Control\\Session Manager\\kernel", "MitigationOptions").is_some()
        || rdw("SYSTEM\\CurrentControlSet\\Control\\Session Manager\\kernel", "MitigationAuditOptions").is_some();
    if ep_set { pass(&mut c, "Exploit Protection (DEP/ASLR)", "Kernel mitigation options configured"); }
    else      { warn(&mut c, "Exploit Protection (DEP/ASLR)", "Kernel mitigation options not explicitly set"); }

    // 15. Attack Surface Reduction
    let asr_rules = "SOFTWARE\\Microsoft\\Windows Defender\\Windows Defender Exploit Guard\\ASR\\Rules";
    let asr_count = subkey_count(asr_rules);
    if asr_count >= 3 { pass(&mut c, "Attack Surface Reduction", &format!("{asr_count} ASR rule(s) active")); }
    else              { warn(&mut c, "Attack Surface Reduction", &format!("{asr_count} ASR rule(s) — recommend >= 3")); }

    // 16. Controlled Folder Access
    match rdw("SOFTWARE\\Microsoft\\Windows Defender\\Exploit Guard\\Controlled Folder Access", "EnableControlledFolderAccess") {
        Some(v) if v >= 1 => pass(&mut c, "Controlled Folder Access", &format!("CFA enabled (mode={v})")),
        _ => warn(&mut c, "Controlled Folder Access", "Controlled Folder Access not enabled"),
    }

    // 17. TLS Security Configuration
    let ssl2  = rdw("SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\SCHANNEL\\Protocols\\SSL 2.0\\Server", "Enabled");
    let ssl3  = rdw("SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\SCHANNEL\\Protocols\\SSL 3.0\\Server", "Enabled");
    let tls10 = rdw("SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\SCHANNEL\\Protocols\\TLS 1.0\\Server", "Enabled");
    let weak_on = ssl2 == Some(1) || ssl3 == Some(1) || tls10 == Some(1);
    let tls_det = format!("SSL2:{:?} SSL3:{:?} TLS1.0:{:?}", ssl2, ssl3, tls10);
    if !weak_on { pass(&mut c, "TLS Security Configuration", &format!("No weak protocols enabled — {tls_det}")); }
    else        { warn(&mut c, "TLS Security Configuration", &format!("Weak protocol(s) explicitly enabled — {tls_det}")); }

    // 18. LLMNR/NetBIOS Protection
    let llmnr    = rdw("SOFTWARE\\Policies\\Microsoft\\Windows NT\\DNSClient", "EnableMulticast");
    let nb_type  = rdw("SYSTEM\\CurrentControlSet\\Services\\NetBT\\Parameters", "NodeType");
    let llmnr_ok = llmnr == Some(0);
    let nb_ok    = nb_type == Some(2);
    let lnb_det  = format!("LLMNR_disabled:{llmnr_ok} NetBIOS_P-node:{nb_ok}");
    if llmnr_ok && nb_ok { pass(&mut c, "LLMNR/NetBIOS Protection", &lnb_det); }
    else                 { warn(&mut c, "LLMNR/NetBIOS Protection", &lnb_det); }

    // 19. USB Mass Storage Access
    match rdw("SYSTEM\\CurrentControlSet\\Services\\USBSTOR", "Start") {
        Some(4) => pass(&mut c, "USB Mass Storage Access", "USB storage disabled (Start=4)"),
        Some(v) => warn(&mut c, "USB Mass Storage Access", &format!("USB storage enabled (Start={v})")),
        None    => warn(&mut c, "USB Mass Storage Access", "USBSTOR key absent"),
    }

    // 20. Idle Timeout (Screensaver)
    let ss_active  = rstr("SOFTWARE\\Policies\\Microsoft\\Windows\\Control Panel\\Desktop", "ScreenSaveActive");
    let ss_secure  = rstr("SOFTWARE\\Policies\\Microsoft\\Windows\\Control Panel\\Desktop", "ScreenSaverIsSecure");
    let ss_timeout = rstr("SOFTWARE\\Policies\\Microsoft\\Windows\\Control Panel\\Desktop", "ScreenSaveTimeOut");
    let t_min      = ss_timeout.as_deref().and_then(|s| s.parse::<u32>().ok()).map(|s| s / 60).unwrap_or(0);
    let ss_ok      = ss_active.as_deref() == Some("1") && ss_secure.as_deref() == Some("1") && t_min > 0 && t_min <= 15;
    if ss_ok { pass(&mut c, "Idle Timeout (Screensaver)", &format!("Lock-on-resume, timeout={t_min}min")); }
    else     { warn(&mut c, "Idle Timeout (Screensaver)", &format!("Active:{:?} Secure:{:?} Timeout:{t_min}min", ss_active, ss_secure)); }

    // 21. NTLM Authentication Level
    match rdw("SYSTEM\\CurrentControlSet\\Control\\Lsa", "LmCompatibilityLevel") {
        Some(v) if v >= 3 => pass(&mut c, "NTLM Authentication Level", &format!("LmCompatibilityLevel={v} (NTLMv2)")),
        Some(v) => warn(&mut c, "NTLM Authentication Level", &format!("LmCompatibilityLevel={v} — recommend >= 3")),
        None    => warn(&mut c, "NTLM Authentication Level", "Not configured (OS default applies)"),
    }

    // 22. LSA Protection
    match rdw("SYSTEM\\CurrentControlSet\\Control\\Lsa", "RunAsPPL") {
        Some(v) if v >= 1 => pass(&mut c, "LSA Protection", &format!("LSA PPL enabled (RunAsPPL={v})")),
        Some(0) => warn(&mut c, "LSA Protection", "LSA PPL disabled — credential theft risk"),
        None    => warn(&mut c, "LSA Protection", "RunAsPPL not set — lsass unprotected"),
        _ => warn(&mut c, "LSA Protection", "LSA protection state undetermined"),
    }

    // 23. WDigest Authentication
    match rdw("SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\WDigest", "UseLogonCredential") {
        Some(0) => pass(&mut c, "WDigest Authentication", "WDigest disabled — cleartext creds not cached"),
        Some(1) => fail(&mut c, "WDigest Authentication", "WDigest ENABLED — plaintext passwords in memory"),
        None    => pass(&mut c, "WDigest Authentication", "WDigest key absent (disabled by OS default)"),
        _ => warn(&mut c, "WDigest Authentication", "WDigest state undetermined"),
    }

    // 24. Always Install Elevated
    let aie = rdw("SOFTWARE\\Policies\\Microsoft\\Windows\\Installer", "AlwaysInstallElevated");
    if aie == Some(1) { fail(&mut c, "Always Install Elevated", "AlwaysInstallElevated=1 — privilege escalation risk"); }
    else              { pass(&mut c, "Always Install Elevated", "AlwaysInstallElevated not set (safe)"); }

    // 25. Remote Registry Service
    match rdw("SYSTEM\\CurrentControlSet\\Services\\RemoteRegistry", "Start") {
        Some(4) => pass(&mut c, "Remote Registry Service", "RemoteRegistry disabled (Start=4)"),
        Some(3) => warn(&mut c, "Remote Registry Service", "RemoteRegistry on-demand (Start=3)"),
        Some(2) => warn(&mut c, "Remote Registry Service", "RemoteRegistry auto-start (Start=2) — remote access enabled"),
        _       => pass(&mut c, "Remote Registry Service", "RemoteRegistry service absent"),
    }

    // 26. Registry Baseline
    let anon     = rdw("SYSTEM\\CurrentControlSet\\Control\\Lsa", "RestrictAnonymous").map_or(false, |v| v >= 1);
    let null_sam = rdw("SYSTEM\\CurrentControlSet\\Control\\Lsa", "RestrictAnonymousSAM") == Some(1);
    let auto_log = rstr("SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon", "AutoAdminLogon")
        .map_or(false, |v| v == "1");
    if anon && null_sam && !auto_log {
        pass(&mut c, "Registry Baseline", "Anonymous restricted, SAM protected, AutoLogon off");
    } else {
        warn(&mut c, "Registry Baseline", &format!("AnonRestricted:{anon} NullSAM:{null_sam} AutoLogon:{auto_log}"));
    }

    // 27. AutoRun Disabled
    match rdw("SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "NoDriveTypeAutoRun") {
        Some(0xFF) | Some(0x91) => pass(&mut c, "AutoRun Disabled", "AutoRun disabled for all drive types"),
        Some(v) => warn(&mut c, "AutoRun Disabled", &format!("AutoRun partial (NoDriveTypeAutoRun=0x{v:X})")),
        None => {
            if key_exists("SOFTWARE\\Policies\\Microsoft\\Windows\\Explorer") {
                warn(&mut c, "AutoRun Disabled", "AutoRun policy not set — USB autoruns may execute");
            } else {
                warn(&mut c, "AutoRun Disabled", "AutoRun not restricted via policy");
            }
        }
    }

    // 28. Windows Script Host
    match rdw("SOFTWARE\\Microsoft\\Windows Script Host\\Settings", "Enabled") {
        Some(0) => pass(&mut c, "Windows Script Host", "WSH disabled — scripting attack surface reduced"),
        Some(1) | None => warn(&mut c, "Windows Script Host", "WSH enabled — consider disabling if unused"),
        _ => warn(&mut c, "Windows Script Host", "WSH state undetermined"),
    }

    json!({"compliance_checks": c})
}
