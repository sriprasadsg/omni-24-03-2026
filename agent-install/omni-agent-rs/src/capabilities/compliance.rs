use super::Capability;
use serde_json::{json, Value};
#[cfg(windows)]
use std::process::Command;
use sysinfo::System;

pub struct ComplianceCapability;

impl Capability for ComplianceCapability {
    fn id(&self) -> &'static str { "compliance_enforcement" }
    fn name(&self) -> &'static str { "Compliance Enforcement" }

    fn collect(&self, _sys: &System) -> Value {
        let checks = platform_checks();
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

/// The checks of this computer's own operating system. Another system sends none: the Windows checks run on
/// Linux used to report Fail for settings Linux does not have.
#[cfg(windows)]
fn platform_checks() -> Vec<Value> { windows_compliance_checks() }
#[cfg(target_os = "linux")]
fn platform_checks() -> Vec<Value> { linux::checks() }
#[cfg(target_os = "macos")]
fn platform_checks() -> Vec<Value> { macos::checks() }
#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
fn platform_checks() -> Vec<Value> { Vec::new() }

#[cfg(any(target_os = "macos", test))]
#[path = "compliance_macos.rs"]
mod macos;

#[cfg(windows)]
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

#[cfg(windows)]
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

/// Linux checks. Each name is mapped to controls by the backend (COMPLIANCE_CHECK_MAPPINGS); what a command or
/// file says is read by a pure function the tests below cover. Read-only: nothing is changed on the machine.
/// The macOS checks reuse its sshd_config reading.
#[cfg(any(target_os = "linux", target_os = "macos", test))]
#[cfg_attr(target_os = "macos", allow(dead_code))]
mod linux {
    use serde_json::{json, Value};

    fn run(cmd: &str, args: &[&str]) -> Option<String> {
        std::process::Command::new(cmd).args(args).output().ok()
            .filter(|o| o.status.success())
            .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
    }

    fn read(path: &str) -> String { std::fs::read_to_string(path).unwrap_or_default() }

    fn verdict(pass: bool) -> &'static str { if pass { "Pass" } else { "Fail" } }

    pub(super) fn checks() -> Vec<Value> {
        let fw = firewall_in_use(run("ufw", &["status"]).as_deref(), run("systemctl", &["is-active", "firewalld"]).as_deref(),
                                 run("nft", &["list", "ruleset"]).as_deref(), run("iptables", &["-S", "INPUT"]).as_deref());
        let sshd = run("sshd", &["-T"]).unwrap_or_else(|| read("/etc/ssh/sshd_config"));
        let (ssh_status, ssh_details) = if sshd.is_empty() { ("Pass", "No SSH server is installed".to_string()) }
                                        else { root_login(&permit_root_login(&sshd)) };
        let updates = apt_unattended(&read("/etc/apt/apt.conf.d/20auto-upgrades"))
            || ["dnf-automatic-install.timer", "dnf-automatic.timer"].iter()
                .any(|t| run("systemctl", &["is-enabled", t]).map_or(false, |s| s.trim() == "enabled"));
        let root = run("findmnt", &["-no", "SOURCE", "/"]).unwrap_or_default().trim().to_string();
        let encrypted = !root.is_empty() && run("lsblk", &["-s", "-no", "TYPE", &root]).map_or(false, |t| has_crypt(&t));
        let pam = format!("{}\n{}", read("/etc/pam.d/common-password"), read("/etc/pam.d/system-auth"));
        let min_len = min_password_length(&pam, &read("/etc/security/pwquality.conf"));
        let auditd = run("systemctl", &["is-active", "auditd"]).map_or(false, |s| s.trim() == "active");
        let risky = risky_listeners(&run("ss", &["-ltnH"]).unwrap_or_default());
        let efi = std::path::Path::new("/sys/firmware/efi").exists();
        let sb = std::fs::read("/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c").unwrap_or_default();
        vec![
            json!({"check": "Firewall Status", "status": verdict(fw.is_some()),
                   "details": fw.map_or("No active host firewall (ufw, firewalld, nftables or an iptables INPUT drop policy)".to_string(),
                                        |f| format!("Host firewall active: {}", f))}),
            json!({"check": "SSH Root Login Disabled", "status": ssh_status, "details": ssh_details}),
            json!({"check": "Automatic Security Updates", "status": verdict(updates),
                   "details": if updates { "Unattended security updates are enabled" } else { "Neither unattended-upgrades nor dnf-automatic is enabled" }}),
            json!({"check": "Disk Encryption (LUKS)", "status": verdict(encrypted),
                   "details": if encrypted { format!("The root filesystem ({}) is on a LUKS volume", root) }
                              else { format!("The root filesystem ({}) is not on a LUKS volume. Encryption done by a cloud provider is not visible from inside the machine", root) }}),
            json!({"check": "Password Policy (Min Length)", "status": verdict(min_len.map_or(false, |n| n >= 8)),
                   "details": min_len.map_or("Password quality is not enforced (pam_pwquality is not in the PAM password stack)".to_string(),
                                             |n| format!("Minimum length: {} (required: 8)", n))}),
            json!({"check": "Audit Logging Policy", "status": verdict(auditd),
                   "details": if auditd { "auditd is running" } else { "auditd is not running" }}),
            json!({"check": "Risky Network Ports", "status": verdict(risky.is_empty()),
                   "details": if risky.is_empty() { "No risky ports open".to_string() } else { format!("Open risky ports: {}", risky.join(", ")) }}),
            json!({"check": "Secure Boot", "status": verdict(secure_boot_on(&sb)),
                   "details": if secure_boot_on(&sb) { "Secure Boot is enabled" } else if efi { "Secure Boot is not enabled" } else { "Not booted with UEFI, so Secure Boot is off" }}),
        ]
    }

    /// The first firewall found active, in this order.
    pub(super) fn firewall_in_use(ufw: Option<&str>, firewalld: Option<&str>, nft: Option<&str>, iptables: Option<&str>) -> Option<&'static str> {
        if ufw.map_or(false, |s| s.lines().any(|l| l.trim() == "Status: active")) { return Some("ufw"); }
        if firewalld.map_or(false, |s| s.trim() == "active") { return Some("firewalld"); }
        if nft.map_or(false, |s| s.lines().any(|l| l.contains("hook input") && l.contains("policy drop"))) { return Some("nftables"); }
        if iptables.map_or(false, |s| s.lines().any(|l| l.trim() == "-P INPUT DROP")) { return Some("iptables"); }
        None
    }

    /// PermitRootLogin as sshd applies it: the first uncommented setting, else the OpenSSH default.
    pub(super) fn permit_root_login(config: &str) -> String {
        config.lines().map(str::trim).filter(|l| !l.starts_with('#'))
            .find_map(|l| { let mut p = l.split_whitespace();
                            (p.next()?.eq_ignore_ascii_case("permitrootlogin")).then(|| p.next().unwrap_or("").to_lowercase()) })
            .unwrap_or_else(|| "prohibit-password".to_string())
    }

    pub(super) fn root_login(value: &str) -> (&'static str, String) {
        match value {
            "no" => ("Pass", "Root cannot log in over SSH".to_string()),
            "yes" => ("Fail", "Root can log in over SSH with a password".to_string()),
            other => ("Warning", format!("Root can log in over SSH with a key (PermitRootLogin {})", other)),
        }
    }

    pub(super) fn apt_unattended(conf: &str) -> bool {
        conf.lines().map(str::trim).filter(|l| !l.starts_with("//"))
            .any(|l| l.starts_with("APT::Periodic::Unattended-Upgrade") && !l.contains("\"0\""))
    }

    pub(super) fn has_crypt(lsblk_types: &str) -> bool { lsblk_types.lines().any(|t| t.trim() == "crypt") }

    /// The enforced minimum length: pam_pwquality's own minlen= argument, else pwquality.conf, else its default 8.
    /// None when pam_pwquality is not in the PAM password stack.
    pub(super) fn min_password_length(pam: &str, pwquality_conf: &str) -> Option<u32> {
        let line = pam.lines().map(str::trim).find(|l| !l.starts_with('#') && l.contains("pam_pwquality.so"))?;
        let arg = |text: &str, sep: char| text.split_whitespace().find_map(|w| w.strip_prefix("minlen")
            .and_then(|r| r.trim_start().strip_prefix(sep)).and_then(|v| v.trim().parse::<u32>().ok()));
        arg(line, '=').or_else(|| pwquality_conf.lines().map(str::trim).filter(|l| !l.starts_with('#'))
            .find_map(|l| l.strip_prefix("minlen").and_then(|r| r.trim().strip_prefix('=')).and_then(|v| v.trim().parse().ok())))
            .or(Some(8))
    }

    /// Listening TCP ports 21 (FTP) and 23 (Telnet) in `ss -ltnH` output (the fourth column is local address:port).
    pub(super) fn risky_listeners(ss: &str) -> Vec<&'static str> {
        let ports: Vec<&str> = ss.lines().filter_map(|l| l.split_whitespace().nth(3)?.rsplit(':').next()).collect();
        [("21", "FTP (21)"), ("23", "Telnet (23)")].iter().filter(|(p, _)| ports.contains(p)).map(|(_, n)| *n).collect()
    }

    /// The SecureBoot EFI variable: four attribute bytes, then 1 when Secure Boot is on.
    pub(super) fn secure_boot_on(efivar: &[u8]) -> bool { efivar.len() >= 5 && efivar[4] == 1 }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[test]
        fn a_firewall_counts_only_when_it_filters_inbound() {
            assert_eq!(firewall_in_use(Some("Status: active\n"), None, None, None), Some("ufw"));
            assert_eq!(firewall_in_use(Some("Status: inactive\n"), Some("inactive\n"), None, None), None);
            assert_eq!(firewall_in_use(None, None, Some("chain input { type filter hook input priority 0; policy drop;"), None), Some("nftables"));
            assert_eq!(firewall_in_use(None, None, Some("chain input { type filter hook input priority 0; policy accept;"), None), None);
            assert_eq!(firewall_in_use(None, None, None, Some("-P INPUT DROP\n")), Some("iptables"));
            assert_eq!(firewall_in_use(None, None, None, Some("-P INPUT ACCEPT\n")), None);
        }

        #[test]
        fn root_login_follows_the_first_setting_and_the_openssh_default() {
            assert_eq!(permit_root_login("# PermitRootLogin yes\nPermitRootLogin no\nPermitRootLogin yes\n"), "no");
            assert_eq!(permit_root_login("permitrootlogin without-password\n"), "without-password");
            assert_eq!(permit_root_login("Port 22\n"), "prohibit-password");
            assert_eq!(root_login("no").0, "Pass");
            assert_eq!(root_login("yes").0, "Fail");
            assert_eq!(root_login("prohibit-password").0, "Warning");
        }

        #[test]
        fn unattended_upgrades_is_on_only_when_set_to_a_non_zero_value() {
            assert!(apt_unattended("APT::Periodic::Update-Package-Lists \"1\";\nAPT::Periodic::Unattended-Upgrade \"1\";\n"));
            assert!(!apt_unattended("APT::Periodic::Unattended-Upgrade \"0\";\n"));
            assert!(!apt_unattended("// APT::Periodic::Unattended-Upgrade \"1\";\n"));
            assert!(!apt_unattended(""));
        }

        #[test]
        fn the_root_filesystem_is_encrypted_when_a_crypt_device_is_below_it() {
            assert!(has_crypt("lvm\ncrypt\npart\ndisk\n"));
            assert!(!has_crypt("part\ndisk\n"));
        }

        #[test]
        fn the_password_length_comes_from_pam_then_pwquality_conf_then_the_default() {
            let pam = "password requisite pam_pwquality.so retry=3 minlen=12\n";
            assert_eq!(min_password_length(pam, "minlen = 10\n"), Some(12));
            assert_eq!(min_password_length("password requisite pam_pwquality.so retry=3\n", "# minlen = 4\nminlen = 10\n"), Some(10));
            assert_eq!(min_password_length("password requisite pam_pwquality.so\n", ""), Some(8));
            assert_eq!(min_password_length("# password requisite pam_pwquality.so\npassword pam_unix.so\n", "minlen = 14\n"), None);
        }

        #[test]
        fn only_listening_ftp_and_telnet_ports_are_risky() {
            let ss = "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\nLISTEN 0 32 [::]:21 [::]:*\nLISTEN 0 5 127.0.0.1:2323 0.0.0.0:*\n";
            assert_eq!(risky_listeners(ss), vec!["FTP (21)"]);
            assert!(risky_listeners("LISTEN 0 128 0.0.0.0:443 0.0.0.0:*\n").is_empty());
        }

        #[test]
        fn secure_boot_reads_the_value_byte_after_the_attributes() {
            assert!(secure_boot_on(&[6, 0, 0, 0, 1]));
            assert!(!secure_boot_on(&[6, 0, 0, 0, 0]));
            assert!(!secure_boot_on(&[]));
        }

        #[cfg(target_os = "linux")]
        #[test]
        fn a_linux_computer_sends_the_linux_checks_and_no_windows_check() {
            let names: Vec<String> = super::super::platform_checks().iter().map(|c| c["check"].as_str().unwrap().to_string()).collect();
            assert_eq!(names.len(), 8, "{:?}", names);
            assert!(names.iter().all(|n| !n.contains("Windows") && !n.contains("BitLocker")), "{:?}", names);
        }
    }
}
