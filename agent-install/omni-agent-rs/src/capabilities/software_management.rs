use super::Capability;
use serde_json::{json, Value};
use sysinfo::System;

pub struct SoftwareManagementCapability;

impl Capability for SoftwareManagementCapability {
    fn id(&self) -> &'static str { "software_management" }
    fn name(&self) -> &'static str { "Software Management" }

    fn collect(&self, _sys: &System) -> Value {
        let installed = enumerate_installed_software();
        json!({
            "status": "idle",
            "last_operation": null,
            "winget_available": winget_available(),
            "installed_software": installed,
            "timestamp": chrono::Utc::now().to_rfc3339(),
        })
    }
}

fn winget_available() -> bool {
    std::process::Command::new("winget")
        .args(["--version"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

#[cfg(windows)]
fn enumerate_installed_software() -> Vec<Value> {
    use winreg::enums::{HKEY_LOCAL_MACHINE, KEY_READ};
    use winreg::RegKey;

    let hklm = RegKey::predef(HKEY_LOCAL_MACHINE);
    let paths = [
        "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
        "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
    ];

    let mut seen = std::collections::HashSet::new();
    let mut software: Vec<Value> = Vec::new();

    for path in &paths {
        let uninstall_key = match hklm.open_subkey_with_flags(path, KEY_READ) {
            Ok(k) => k,
            Err(_) => continue,
        };
        for name in uninstall_key.enum_keys().filter_map(|r| r.ok()) {
            let subkey = match uninstall_key.open_subkey_with_flags(&name, KEY_READ) {
                Ok(k) => k,
                Err(_) => continue,
            };
            let display_name: String = subkey.get_value("DisplayName").unwrap_or_default();
            if display_name.is_empty() || !seen.insert(display_name.clone()) {
                continue;
            }
            let version: String = subkey.get_value("DisplayVersion").unwrap_or_default();
            let publisher: String = subkey.get_value("Publisher").unwrap_or_default();
            let install_date: String = subkey.get_value("InstallDate").unwrap_or_default();

            // Format install_date from "YYYYMMDD" to "YYYY-MM-DD" when present
            let formatted_date = if install_date.len() == 8 {
                format!("{}-{}-{}", &install_date[..4], &install_date[4..6], &install_date[6..])
            } else {
                install_date
            };

            software.push(json!({
                "name": display_name,
                "version": version,
                "publisher": publisher,
                "install_date": formatted_date,
                "update_available": false,
            }));
        }
    }

    software.sort_by(|a, b| {
        a["name"].as_str().unwrap_or("").cmp(b["name"].as_str().unwrap_or(""))
    });
    software
}

#[cfg(not(windows))]
fn enumerate_installed_software() -> Vec<Value> {
    vec![]
}

/// Install or upgrade a package using winget.
/// Called from instructions.rs.
pub fn install_package(package_id: &str, upgrade: bool) -> Result<String, String> {
    let action = if upgrade { "upgrade" } else { "install" };
    let output = std::process::Command::new("winget")
        .args([action, "--id", package_id, "--silent", "--accept-package-agreements"])
        .output()
        .map_err(|e| e.to_string())?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    if output.status.success() {
        Ok(stdout)
    } else {
        Err(format!("{}\n{}", stdout, stderr))
    }
}
