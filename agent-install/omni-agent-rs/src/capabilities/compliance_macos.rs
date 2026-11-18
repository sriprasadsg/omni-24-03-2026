//! macOS checks. Each name is mapped to controls by the backend (COMPLIANCE_CHECK_MAPPINGS); what a command
//! says is read by a pure function the tests below cover. Read-only: nothing is changed on the machine.

use serde_json::{json, Value};

#[cfg(target_os = "macos")]
fn run(cmd: &str, args: &[&str]) -> Option<String> {
    let out = std::process::Command::new(cmd).args(args).output().ok()?;
    // csrutil and spctl print their state on stderr on some releases.
    Some(format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr)))
}

fn verdict(pass: bool) -> &'static str { if pass { "Pass" } else { "Fail" } }

#[cfg(target_os = "macos")]
pub(super) fn checks() -> Vec<Value> {
    let defaults = |domain: &str, key: &str| run("defaults", &["read", domain, key]).map(|s| s.trim().to_string())
        .filter(|s| !s.contains("does not exist"));
    let sshd_loaded = std::process::Command::new("launchctl").args(["print", "system/com.openssh.sshd"]).output()
        .map_or(false, |o| o.status.success());
    let mut sshd = std::fs::read_to_string("/etc/ssh/sshd_config").unwrap_or_default();
    if let Ok(dir) = std::fs::read_dir("/etc/ssh/sshd_config.d") {
        let mut parts: Vec<_> = dir.flatten().map(|e| e.path()).collect();
        parts.sort();
        // sshd reads the Include at the top of sshd_config first, and the first setting wins.
        sshd = parts.iter().filter_map(|p| std::fs::read_to_string(p).ok()).collect::<String>() + &sshd;
    }
    let lsof = run("lsof", &["-nP", "-iTCP", "-sTCP:LISTEN"]).unwrap_or_default();
    vec![
        firewall(&run("/usr/libexec/ApplicationFirewall/socketfilterfw", &["--getglobalstate"]).unwrap_or_default()),
        filevault(&run("fdesetup", &["status"]).unwrap_or_default()),
        gatekeeper(&run("spctl", &["--status"]).unwrap_or_default()),
        sip(&run("csrutil", &["status"]).unwrap_or_default()),
        automatic_updates(defaults("/Library/Preferences/com.apple.SoftwareUpdate", "AutomaticCheckEnabled").as_deref(),
                          defaults("/Library/Preferences/com.apple.SoftwareUpdate", "CriticalUpdateInstall").as_deref()),
        guest(defaults("/Library/Preferences/com.apple.loginwindow", "GuestEnabled").as_deref()),
        ssh_root(sshd_loaded, &sshd),
        risky_ports(&lsof),
    ]
}

pub(super) fn firewall(state: &str) -> Value {
    // "Firewall is enabled. (State = 1)", "(State = 2)" is block-all; State = 0 is off.
    let on = state.contains("enabled") || state.contains("State = 1") || state.contains("State = 2");
    json!({"check": "Firewall Status", "status": verdict(on),
           "details": if on { "The macOS application firewall is on" } else { "The macOS application firewall is off" }})
}

pub(super) fn filevault(status: &str) -> Value {
    let (s, d) = if status.contains("FileVault is On") { ("Pass", "FileVault encrypts the startup disk") }
                 else if status.contains("in progress") { ("Warning", "FileVault encryption is in progress") }
                 else { ("Fail", "FileVault is off: the startup disk is not encrypted") };
    json!({"check": "Disk Encryption (FileVault)", "status": s, "details": d})
}

pub(super) fn gatekeeper(status: &str) -> Value {
    let on = status.contains("assessments enabled");
    json!({"check": "Gatekeeper", "status": verdict(on),
           "details": if on { "Gatekeeper checks downloaded apps" } else { "Gatekeeper is off: unsigned apps can run" }})
}

pub(super) fn sip(status: &str) -> Value {
    let on = status.contains("status: enabled");
    json!({"check": "System Integrity Protection", "status": verdict(on),
           "details": if on { "System Integrity Protection is on" } else { "System Integrity Protection is off or partly off" }})
}

/// AutomaticCheckEnabled and CriticalUpdateInstall are on unless set to 0 (the macOS default is on).
pub(super) fn automatic_updates(check: Option<&str>, critical: Option<&str>) -> Value {
    let off: Vec<&str> = [(check, "checking for updates"), (critical, "security responses and system files")]
        .iter().filter(|(v, _)| *v == Some("0")).map(|(_, what)| *what).collect();
    json!({"check": "Automatic Security Updates", "status": verdict(off.is_empty()),
           "details": if off.is_empty() { "Automatic update checks and security responses are on".to_string() }
                      else { format!("Turned off: {}", off.join(", ")) }})
}

pub(super) fn guest(enabled: Option<&str>) -> Value {
    let on = enabled == Some("1");
    json!({"check": "Guest Account Disabled", "status": verdict(!on),
           "details": if on { "The guest account can log in" } else { "The guest account is off" }})
}

pub(super) fn ssh_root(remote_login: bool, sshd_config: &str) -> Value {
    let (status, details) = if !remote_login { ("Pass", "Remote Login (SSH) is off".to_string()) }
                            else { super::linux::root_login(&super::linux::permit_root_login(sshd_config)) };
    json!({"check": "SSH Root Login Disabled", "status": status, "details": details})
}

/// Listening TCP ports 21 (FTP) and 23 (Telnet) in `lsof -nP -iTCP -sTCP:LISTEN` output (NAME is "addr:port (LISTEN)").
pub(super) fn risky_ports(lsof: &str) -> Value {
    let ports: Vec<&str> = lsof.lines().skip(1)
        .filter_map(|l| l.split_whitespace().rev().nth(1)?.rsplit(':').next()).collect();
    let risky: Vec<&str> = [("21", "FTP (21)"), ("23", "Telnet (23)")].iter()
        .filter(|(p, _)| ports.contains(p)).map(|(_, n)| *n).collect();
    json!({"check": "Risky Network Ports", "status": verdict(risky.is_empty()),
           "details": if risky.is_empty() { "No risky ports open".to_string() } else { format!("Open risky ports: {}", risky.join(", ")) }})
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_setting_is_read_from_what_its_tool_prints() {
        assert_eq!(firewall("Firewall is enabled. (State = 1)\n")["status"], "Pass");
        assert_eq!(firewall("Firewall is disabled. (State = 0)\n")["status"], "Fail");
        assert_eq!(filevault("FileVault is On.\n")["status"], "Pass");
        assert_eq!(filevault("FileVault is Off.\n")["status"], "Fail");
        assert_eq!(filevault("Encryption in progress: Percent completed = 12.3\n")["status"], "Warning");
        assert_eq!(gatekeeper("assessments enabled\n")["status"], "Pass");
        assert_eq!(gatekeeper("assessments disabled\n")["status"], "Fail");
        assert_eq!(sip("System Integrity Protection status: enabled.\n")["status"], "Pass");
        assert_eq!(sip("System Integrity Protection status: disabled.\n")["status"], "Fail");
        assert_eq!(sip("System Integrity Protection status: unknown (Custom Configuration).\n")["status"], "Fail");
    }

    #[test]
    fn updates_and_the_guest_account_follow_the_macos_defaults_when_unset() {
        assert_eq!(automatic_updates(None, None)["status"], "Pass");
        assert_eq!(automatic_updates(Some("1"), Some("0"))["details"], "Turned off: security responses and system files");
        assert_eq!(guest(None)["status"], "Pass");
        assert_eq!(guest(Some("1"))["status"], "Fail");
    }

    #[test]
    fn root_ssh_login_matters_only_when_remote_login_is_on() {
        assert_eq!(ssh_root(false, "PermitRootLogin yes\n")["status"], "Pass");
        assert_eq!(ssh_root(true, "PermitRootLogin yes\n")["status"], "Fail");
        assert_eq!(ssh_root(true, "#PermitRootLogin prohibit-password\n")["status"], "Warning");
    }

    #[test]
    fn only_listening_ftp_and_telnet_ports_are_risky() {
        let lsof = "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n\
                    sshd 1 root 4u IPv6 0x1 0t0 TCP *:22 (LISTEN)\n\
                    ftpd 9 root 5u IPv4 0x2 0t0 TCP 127.0.0.1:21 (LISTEN)\n\
                    app 7 me 6u IPv4 0x3 0t0 TCP *:2323 (LISTEN)\n";
        assert_eq!(risky_ports(lsof)["details"], "Open risky ports: FTP (21)");
        assert_eq!(risky_ports("COMMAND PID\n")["status"], "Pass");
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn a_mac_sends_the_macos_checks_and_no_windows_or_linux_check() {
        let names: Vec<String> = super::super::platform_checks().iter().map(|c| c["check"].as_str().unwrap().to_string()).collect();
        assert_eq!(names.len(), 8, "{:?}", names);
        assert!(names.iter().all(|n| !n.contains("Windows") && !n.contains("BitLocker") && !n.contains("LUKS")), "{:?}", names);
    }
}
