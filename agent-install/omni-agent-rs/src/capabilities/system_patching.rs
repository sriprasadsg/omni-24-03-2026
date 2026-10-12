use super::Capability;
use serde_json::{json, Value};
use std::process::Command;
use std::sync::Mutex;
use std::fs;
use sysinfo::System;

pub struct SystemPatchingCapability;

impl Capability for SystemPatchingCapability {
    fn id(&self) -> &'static str { "system_patching" }
    fn name(&self) -> &'static str { "System Patching" }

    fn collect(&self, _sys: &System) -> Value {
        let uptime_secs = uptime_seconds();
        let bios_version = bios_version_str();
        let last_boot = last_boot_time();
        let (updates, scan_error) = cached_pending_updates();
        let update_count = updates.len();

        let mut out = json!({
            "uptime_seconds": uptime_secs,
            "last_boot": last_boot,
            "bios_version": bios_version,
            "bios_manufacturer": bios_field("BIOSVendor", "bios_vendor"),
            "bios_release_date": bios_field("BIOSReleaseDate", "bios_date"),
            "pending_updates": updates,
            "pending_update_count": update_count,
            "timestamp": chrono::Utc::now().to_rfc3339(),
        });
        // Lets the dashboard tell "0 pending" apart from "the scan failed".
        if let Some(e) = scan_error {
            out["scan_error"] = json!(e);
        }
        out
    }
}

type ScanResult = (Vec<Value>, Option<String>);
static UPDATE_CACHE: Mutex<Option<(std::time::Instant, ScanResult)>> = Mutex::new(None);

fn cached_pending_updates() -> ScanResult {
    const TTL: std::time::Duration = std::time::Duration::from_secs(300);
    let mut guard = UPDATE_CACHE.lock().unwrap_or_else(|p| p.into_inner());
    if let Some((ts, ref cached)) = *guard {
        if ts.elapsed() < TTL {
            return cached.clone();
        }
    }
    let scan = match pending_updates_list() {
        Ok(list) => (list, None),
        Err(e) => (Vec::new(), Some(e)),
    };
    *guard = Some((std::time::Instant::now(), scan.clone()));
    scan
}

fn uptime_seconds() -> u64 {
    let boot = sysinfo::System::boot_time();
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    now.saturating_sub(boot)
}

fn last_boot_time() -> String {
    // Convert boot_time (Unix seconds) to an ISO-8601 string. No wmic needed.
    let boot_secs = sysinfo::System::boot_time();
    chrono::DateTime::from_timestamp(boot_secs as i64, 0)
        .map(|dt| dt.format("%Y-%m-%dT%H:%M:%SZ").to_string())
        .unwrap_or_default()
}

/// One BIOS field from the registry (Windows) or sysfs (Linux); both are readable
/// without admin rights. Empty when unavailable.
#[allow(unreachable_code, unused_variables)]
fn bios_field(reg_value: &str, sysfs_file: &str) -> String {
    #[cfg(windows)]
    {
        use winreg::enums::HKEY_LOCAL_MACHINE;
        use winreg::RegKey;
        return RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey(r"HARDWARE\DESCRIPTION\System\BIOS")
            .and_then(|key| key.get_value::<String, _>(reg_value))
            .unwrap_or_default();
    }
    #[cfg(target_os = "linux")]
    {
        return fs::read_to_string(format!("/sys/class/dmi/id/{sysfs_file}"))
            .map(|s| s.trim().to_string())
            .ok()
            .filter(|s| s != "Not Specified")
            .unwrap_or_default();
    }
    String::new()
}

fn bios_version_str() -> String {
    // Read BIOS version from registry — no wmic needed.
    #[cfg(windows)]
    {
        use winreg::enums::HKEY_LOCAL_MACHINE;
        use winreg::RegKey;
        if let Ok(key) = RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey(r"HARDWARE\DESCRIPTION\System\BIOS")
        {
            let ver: String = key.get_value("BIOSVersion").unwrap_or_default();
            if !ver.is_empty() {
                return ver;
            }
            // Fallback: BIOSReleaseDate
            return key.get_value("BIOSReleaseDate").unwrap_or_default();
        }
    }

    // Linux: try sysfs (no sudo needed), then dmidecode (needs sudo)
    #[cfg(target_os = "linux")]
    {
        // Try sysfs first - no root required
        let bios_version = fs::read_to_string("/sys/class/dmi/id/bios_version")
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty() && s != "Not Specified");
        if let Some(v) = bios_version {
            return v;
        }

        // Fallback to dmidecode if available
        if let Ok(out) = Command::new("dmidecode")
            .args(["-t", "bios"])
            .output()
        {
            let text = String::from_utf8_lossy(&out.stdout);
            for line in text.lines() {
                let line = line.trim();
                if line.to_lowercase().starts_with("version:") && line.to_lowercase().contains("bios") {
                    if let Some(val) = line.split(':').nth(1) {
                        let val = val.trim();
                        if !val.is_empty() && val != "Not Specified" {
                            return val.to_string();
                        }
                    }
                }
            }
        }
    }
    String::new()
}

/// Pending OS updates, each with an installable `id` (a KB number on Windows, the
/// package name on Linux) that the install_patches instruction accepts.
#[allow(unreachable_code)] // the Windows arm returns before the Linux/other fallback
fn pending_updates_list() -> Result<Vec<Value>, String> {
    #[cfg(windows)]
    {
        // Returns each update as {title, severity, mandatory, kb, size_mb}
        let ps = r#"
$ErrorActionPreference = 'Stop'
$Session = New-Object -ComObject Microsoft.Update.Session
$Searcher = $Session.CreateUpdateSearcher()
$Results = $Searcher.Search("IsInstalled=0 and Type='Software' and IsHidden=0")
$updates = @()
foreach ($u in $Results.Updates) {
    $updates += [PSCustomObject]@{
        title     = $u.Title
        severity  = if ($u.MsrcSeverity) { $u.MsrcSeverity } else { 'Unknown' }
        mandatory = [bool]$u.AutoSelectOnWebSites
        kb        = ($u.KBArticleIDs | Select-Object -First 1)
        size_mb   = [math]::Round($u.MaxDownloadSize / 1MB, 1)
    }
}
if ($updates.Count -eq 0) { '[]' } else { $updates | ConvertTo-Json -Compress }
"#;
        let out = Command::new("powershell")
            .args(["-NoProfile", "-NonInteractive", "-Command", ps])
            .output()
            .map_err(|e| format!("Windows Update search could not start: {e}"))?;
        return parse_windows_updates(&String::from_utf8_lossy(&out.stdout), &String::from_utf8_lossy(&out.stderr));
    }

    #[cfg(target_os = "linux")]
    {
        // Try apt (Debian/Ubuntu)
        if let Ok(out) = Command::new("apt")
            .args(["list", "--upgradable"])
            .output()
        {
            if out.status.success() {
                let text = String::from_utf8_lossy(&out.stdout);
                let mut updates = Vec::new();
                for line in text.lines().skip(1) { // Skip header
                    if let Some(u) = parse_apt_line(line) {
                        updates.push(u);
                    }
                }
                return Ok(updates.into_iter().take(50).collect());
            }
        }

        // Try dnf (Fedora/RHEL 8+)
        if let Ok(out) = Command::new("dnf")
            .args(["check-update", "-q"])
            .output()
        {
            if out.status.code() == Some(100) { // 100 = updates available
                let text = String::from_utf8_lossy(&out.stdout);
                let mut updates = Vec::new();
                for line in text.lines() {
                    if let Some(u) = parse_rpm_line(line) {
                        updates.push(u);
                    }
                }
                return Ok(updates.into_iter().take(50).collect());
            }
        }

        // Try yum (RHEL/CentOS 7)
        if let Ok(out) = Command::new("yum")
            .args(["check-update", "-q"])
            .output()
        {
            if out.status.code() == Some(100) {
                let text = String::from_utf8_lossy(&out.stdout);
                let mut updates = Vec::new();
                for line in text.lines() {
                    if let Some(u) = parse_rpm_line(line) {
                        updates.push(u);
                    }
                }
                return Ok(updates.into_iter().take(50).collect());
            }
        }
    }
    Ok(vec![])
}

/// Parses the Windows Update search output (a JSON array, or a bare object for one update).
pub fn parse_windows_updates(stdout: &str, stderr: &str) -> Result<Vec<Value>, String> {
    let text = stdout.trim();
    let rows: Vec<Value> = if text.starts_with('[') {
        serde_json::from_str(text).map_err(|e| format!("Windows Update search returned unreadable output: {e}"))?
    } else if text.starts_with('{') {
        vec![serde_json::from_str(text).map_err(|e| format!("Windows Update search returned unreadable output: {e}"))?]
    } else {
        let why: String = format!("{} {}", stderr.trim(), text).trim().chars().take(300).collect();
        return Err(format!("Windows Update search failed: {}", if why.is_empty() { "no output" } else { &why }));
    };
    Ok(rows.into_iter().filter(|r| r.is_object()).map(|mut r| {
        let kb = r.get("kb").map(|k| k.as_str().map(str::to_string).unwrap_or_else(|| k.to_string())).unwrap_or_default();
        if !kb.is_empty() && kb.chars().all(|c| c.is_ascii_digit()) {
            r["id"] = json!(format!("KB{kb}"));
        }
        r
    }).collect())
}

/// "pkg/suite 1.2-3 amd64 [upgradable from: 1.2-2]" -> {id, package, title}.
pub fn parse_apt_line(line: &str) -> Option<Value> {
    let (pkg, rest) = line.split_once('/')?;
    let pkg = pkg.trim();
    if pkg.is_empty() || pkg.contains(' ') {
        return None;
    }
    let version = rest.split_whitespace().nth(1).unwrap_or("");
    Some(json!({"id": pkg, "package": pkg, "title": format!("{pkg} ({version})"),
                "severity": "Medium", "mandatory": false}))
}

/// "name.arch  version  repo" from dnf/yum check-update; headers and blank lines are skipped.
pub fn parse_rpm_line(line: &str) -> Option<Value> {
    let parts: Vec<&str> = line.split_whitespace().collect();
    if parts.len() < 3 {
        return None;
    }
    Some(json!({"id": parts[0], "package": parts[0], "title": format!("{} ({})", parts[0], parts[1]),
                "severity": "Medium", "mandatory": false}))
}

#[cfg(all(test, target_os = "linux"))]
mod tests {
    use super::*;

    #[test]
    fn bios_field_reads_sysfs_without_root() {
        let Ok(raw) = fs::read_to_string("/sys/class/dmi/id/bios_vendor") else { return };
        assert_eq!(bios_field("BIOSVendor", "bios_vendor"), raw.trim());
        assert_eq!(bios_field("BIOSVendor", "no_such_dmi_file"), "");
    }
}
