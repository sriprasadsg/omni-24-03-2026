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
        let updates = cached_pending_updates();
        let update_count = updates.len();

        json!({
            "uptime_seconds": uptime_secs,
            "last_boot": last_boot,
            "bios_version": bios_version,
            "pending_updates": updates,
            "pending_update_count": update_count,
            "timestamp": chrono::Utc::now().to_rfc3339(),
        })
    }
}

static UPDATE_CACHE: Mutex<Option<(std::time::Instant, Vec<Value>)>> = Mutex::new(None);

fn cached_pending_updates() -> Vec<Value> {
    const TTL: std::time::Duration = std::time::Duration::from_secs(300);
    let mut guard = UPDATE_CACHE.lock().unwrap_or_else(|p| p.into_inner());
    if let Some((ts, ref list)) = *guard {
        if ts.elapsed() < TTL {
            return list.clone();
        }
    }
    let updates = pending_updates_list();
    *guard = Some((std::time::Instant::now(), updates.clone()));
    updates
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

fn pending_updates_list() -> Vec<Value> {
    #[cfg(windows)]
    {
        // Returns each update as {title, severity, mandatory, kb, size_mb}
        let ps = r#"
$Session = New-Object -ComObject Microsoft.Update.Session
$Searcher = $Session.CreateUpdateSearcher()
$Results = $Searcher.Search("IsInstalled=0 and Type='Software'")
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
        if let Ok(out) = Command::new("powershell")
            .args(["-NoProfile", "-NonInteractive", "-Command", ps])
            .output()
        {
            let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
            if text.starts_with('[') {
                return serde_json::from_str::<Vec<Value>>(&text).unwrap_or_default();
            } else if text.starts_with('{') {
                // PS returns a bare object when there's exactly one update
                return serde_json::from_str::<Value>(&text)
                    .map(|v| vec![v])
                    .unwrap_or_default();
            }
        }
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
                    if line.contains('/') {
                        let parts: Vec<&str> = line.split('/').collect();
                        if let Some(pkg_name) = parts.first() {
                            let version_part = parts.get(1).unwrap_or(&"").split(' ').next().unwrap_or("");
                            updates.push(json!({
                                "title": format!("{} ({})", pkg_name.trim(), version_part.trim()),
                                "severity": "Medium",
                                "mandatory": false
                            }));
                        }
                    }
                }
                return updates.into_iter().take(50).collect();
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
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if let Some(pkg) = parts.first() {
                        updates.push(json!({
                            "title": pkg.trim(),
                            "severity": "Medium",
                            "mandatory": false
                        }));
                    }
                }
                return updates.into_iter().take(50).collect();
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
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if let Some(pkg) = parts.first() {
                        updates.push(json!({
                            "title": pkg.trim(),
                            "severity": "Medium",
                            "mandatory": false
                        }));
                    }
                }
                return updates.into_iter().take(50).collect();
            }
        }
    }
    vec![]
}
