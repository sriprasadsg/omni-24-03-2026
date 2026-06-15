use super::Capability;
use serde_json::{json, Value};
use std::process::Command;
use std::sync::Mutex;
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
    vec![]
}
