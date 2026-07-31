//! Persistence Detection capability — scans common persistence mechanisms.
//! Ports agent/capabilities/persistence_detection.py. Windows: registry Run
//! keys, Startup folders, scheduled tasks. Linux: systemd units, crontab,
//! /etc/cron.*, profile.d, shell rc files, /etc/ld.so.preload. Each finding is
//! risk-scored by suspicious command keywords (LOLBins, temp paths, encoders).

use super::Capability;
use serde_json::{json, Value};

const SUSPICIOUS_KEYWORDS: &[&str] = &[
    "powershell", "cmd.exe", "wscript", "cscript", "mshta", "rundll32",
    "regsvr32", "certutil", "bitsadmin", "curl", "wget", "nc ", "ncat",
    "python", "perl", "ruby", "base64", "encodedcommand", "-enc ",
    "/tmp/", "\\temp\\", "\\appdata\\local\\temp\\",
];

fn risk_score(command: &str) -> &'static str {
    let c = command.to_lowercase();
    let hits = SUSPICIOUS_KEYWORDS.iter().filter(|kw| c.contains(*kw)).count();
    if hits >= 2 {
        "Critical"
    } else if hits == 1 {
        "High"
    } else if c.contains("appdata") || c.contains("temp") {
        "Medium"
    } else {
        "Low"
    }
}

fn finding(kind: &str, location: &str, name: &str, command: &str, severity: &str) -> Value {
    json!({
        "type": kind,
        "location": location,
        "name": name,
        "command": command,
        "severity": severity,
    })
}

pub struct PersistenceDetectionCapability;

impl Capability for PersistenceDetectionCapability {
    fn id(&self) -> &'static str { "persistence_detection" }
    fn name(&self) -> &'static str { "Persistence Detection" }

    fn collect(&self, _sys: &sysinfo::System) -> Value {
        let findings = scan();
        let critical = findings.iter().filter(|f| f["severity"] == "Critical").count();
        let high = findings.iter().filter(|f| f["severity"] == "High").count();
        json!({
            "findings": findings,
            "count": findings.len(),
            "critical_count": critical,
            "high_count": high,
            "platform": if cfg!(windows) { "nt" } else { "posix" },
        })
    }
}

#[cfg(windows)]
fn scan() -> Vec<Value> {
    use winreg::enums::*;
    use winreg::RegKey;

    let mut findings: Vec<Value> = Vec::new();

    let run_keys: &[(&str, isize, &str)] = &[
        ("HKCU", HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ("HKCU", HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
        ("HKCU", HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\RunServices"),
        ("HKLM", HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ("HKLM", HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
        ("HKLM", HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunServices"),
        ("HKLM", HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows NT\CurrentVersion\Winlogon"),
        ("HKCU", HKEY_CURRENT_USER,  r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Run"),
        ("HKLM", HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Run"),
    ];

    for (hive, hk, path) in run_keys {
        let root = RegKey::predef(*hk);
        if let Ok(key) = root.open_subkey(path) {
            for item in key.enum_values() {
                if let Ok((name, val)) = item {
                    let command = format!("{}", val);
                    let sev = risk_score(&command);
                    findings.push(finding(
                        "Registry Run Key",
                        &format!("{}\\{}", hive, path),
                        &name,
                        &command,
                        sev,
                    ));
                }
            }
        }
    }

    // Startup folders
    let mut startup_paths: Vec<String> = Vec::new();
    if let Ok(appdata) = std::env::var("APPDATA") {
        startup_paths.push(format!(r"{}\Microsoft\Windows\Start Menu\Programs\Startup", appdata));
    }
    startup_paths.push(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup".to_string());
    for path in &startup_paths {
        if let Ok(entries) = std::fs::read_dir(path) {
            for entry in entries.flatten() {
                let item = entry.file_name().to_string_lossy().to_string();
                let full = entry.path().to_string_lossy().to_string();
                let sev = risk_score(&item);
                findings.push(finding("Startup Folder", path, &item, &full, sev));
            }
        }
    }

    // Scheduled tasks via schtasks
    findings.extend(scan_schtasks());
    findings
}

#[cfg(windows)]
fn scan_schtasks() -> Vec<Value> {
    let mut findings: Vec<Value> = Vec::new();
    let output = std::process::Command::new("schtasks")
        .args(["/query", "/fo", "CSV", "/v"])
        .output();
    let Ok(out) = output else { return findings };
    let text = String::from_utf8_lossy(&out.stdout);
    for line in text.lines() {
        // Skip the header row and non-data rows (mirrors the Python heuristic).
        if line.contains("TaskName") && line.contains("Task To Run") {
            continue;
        }
        let cols = parse_csv_line(line);
        if cols.len() >= 9 {
            let task_name = cols[0].trim();
            let task_cmd = cols[8].trim();
            if task_name.is_empty() || task_cmd.is_empty() || task_cmd.eq_ignore_ascii_case("Task To Run") {
                continue;
            }
            let sev = risk_score(task_cmd);
            if sev == "Critical" || sev == "High" || sev == "Medium" {
                findings.push(finding("Scheduled Task", "Windows Task Scheduler", task_name, task_cmd, sev));
            }
        }
    }
    findings
}

/// Minimal RFC-4180-ish splitter: handles double-quoted fields containing commas.
#[cfg(windows)]
fn parse_csv_line(line: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut cur = String::new();
    let mut in_quotes = false;
    let mut chars = line.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '"' if in_quotes && chars.peek() == Some(&'"') => { cur.push('"'); chars.next(); }
            '"' => in_quotes = !in_quotes,
            ',' if !in_quotes => { fields.push(std::mem::take(&mut cur)); }
            _ => cur.push(c),
        }
    }
    fields.push(cur);
    fields
}

#[cfg(not(windows))]
fn scan() -> Vec<Value> {
    let mut findings: Vec<Value> = Vec::new();

    // systemd services
    for dir in ["/etc/systemd/system", "/lib/systemd/system", "/usr/lib/systemd/system"] {
        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if name.ends_with(".service") {
                    let full = entry.path().to_string_lossy().to_string();
                    let cmd = read_service_exec(&full);
                    let sev = risk_score(&cmd);
                    findings.push(finding("systemd Service", &full, &name, &cmd, sev));
                }
            }
        }
    }

    // user crontab
    if let Ok(out) = std::process::Command::new("crontab").arg("-l").output() {
        let text = String::from_utf8_lossy(&out.stdout);
        for line in text.lines() {
            let l = line.trim();
            if !l.is_empty() && !l.starts_with('#') {
                let sev = risk_score(l);
                findings.push(finding("Crontab Entry", "User Crontab", "Cron Job", l, sev));
            }
        }
    }

    // /etc/cron.d and /etc/cron.* directories
    for dir in ["/etc/cron.d", "/etc/cron.hourly", "/etc/cron.daily", "/etc/cron.weekly", "/etc/cron.monthly"] {
        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_file() {
                    let item = entry.file_name().to_string_lossy().to_string();
                    if let Ok(content) = std::fs::read_to_string(&path) {
                        for line in content.lines() {
                            let l = line.trim();
                            if !l.is_empty() && !l.starts_with('#') {
                                let sev = risk_score(l);
                                findings.push(finding("Cron File", &path.to_string_lossy(), &item, l, sev));
                            }
                        }
                    }
                }
            }
        }
    }

    // /etc/profile.d scripts
    if let Ok(entries) = std::fs::read_dir("/etc/profile.d") {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                let item = entry.file_name().to_string_lossy().to_string();
                findings.push(finding("Profile Script", &path.to_string_lossy(), &item, "(loaded at login)", "Low"));
            }
        }
    }

    // User + root shell config files — only surface Critical/High lines
    let mut shell_files: Vec<String> = Vec::new();
    if let Ok(home) = std::env::var("HOME") {
        for f in [".bashrc", ".bash_profile", ".profile", ".zshrc"] {
            shell_files.push(format!("{}/{}", home, f));
        }
    }
    shell_files.push("/root/.bashrc".to_string());
    shell_files.push("/root/.bash_profile".to_string());
    for sf in &shell_files {
        if let Ok(content) = std::fs::read_to_string(sf) {
            for line in content.lines() {
                let l = line.trim();
                if !l.is_empty() && !l.starts_with('#') {
                    let sev = risk_score(l);
                    if sev == "Critical" || sev == "High" {
                        let base = std::path::Path::new(sf).file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
                        findings.push(finding("Shell Config", sf, &base, l, sev));
                    }
                }
            }
        }
    }

    // /etc/ld.so.preload — library injection
    if let Ok(content) = std::fs::read_to_string("/etc/ld.so.preload") {
        let c = content.trim();
        if !c.is_empty() {
            findings.push(finding("LD_PRELOAD Hijack", "/etc/ld.so.preload", "ld.so.preload", c, "Critical"));
        }
    }

    findings
}

#[cfg(not(windows))]
fn read_service_exec(path: &str) -> String {
    if let Ok(content) = std::fs::read_to_string(path) {
        for line in content.lines() {
            let l = line.trim();
            if let Some(rest) = l.strip_prefix("ExecStart=") {
                return rest.to_string();
            }
        }
    }
    "N/A".to_string()
}
