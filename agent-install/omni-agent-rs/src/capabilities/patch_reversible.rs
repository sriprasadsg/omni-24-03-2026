//! Reversibility checks for staged patch rollouts (D-05).
//!
//! A patch may install on its own only when it can be put back on this host. Linux: the package
//! source must still offer the version that is installed now (after the upgrade the old version has
//! to be fetched from the source). Windows: Windows Update must mark the offered update as
//! uninstallable. Everything that parses or decides is a pure function here, so tests never run a
//! package manager.

use serde_json::Value;
use std::time::Duration;

pub const NOT_REVERSIBLE: &str = "not_reversible";
pub const REVERTED: &str = "reverted";
pub const NOT_UNINSTALLABLE: &str = "not_uninstallable";
pub const VERSION_NOT_OFFERED: &str = "version_not_offered";
pub const NOT_CHANGED_BY_JOB: &str = "not_changed_by_job";
pub const NOT_APPLICABLE: &str = "not_applicable";

pub const NOT_REVERSIBLE_MESSAGE: &str = "Not installed: this update cannot be reversed on this computer.";
/// The sentences the uninstall script writes; `code_revert_rows` reads the code back from them.
pub const WIN_NOT_UNINSTALLABLE_TEXT: &str = "Windows marks this update as not uninstallable";
pub const WIN_NOT_INSTALLED_TEXT: &str = "Not installed on this host";

/// A result that carries a machine-readable `code` (the agent contract's `patchCodes`).
pub fn coded_result(patch_id: &str, status: &str, code: &str, message: &str, reboot: bool) -> Value {
    let mut r = super::patch_installer::patch_result(patch_id, status, message, reboot);
    r["code"] = Value::from(code);
    r
}

/// Not installed, and not a failure: the patch waits for a person to approve it.
pub fn deferred_result(patch_id: &str, code: &str, message: &str) -> Value {
    coded_result(patch_id, "deferred", code, message, false)
}

/// Versions `apt-cache madison` lists, in listed order. The entry for the local dpkg status file is
/// the installed copy, not something the package source offers, so it is left out.
pub fn parse_madison(stdout: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    for line in stdout.lines() {
        let mut fields = line.split('|').map(str::trim);
        let (Some(_name), Some(version), Some(source)) = (fields.next(), fields.next(), fields.next()) else { continue };
        if version.is_empty() || source.contains("/var/lib/dpkg/status") || out.iter().any(|v| v == version) {
            continue;
        }
        out.push(version.to_string());
    }
    out
}

/// Versions of `pkg` that `dnf|yum --showduplicates list` shows under "Available Packages", as
/// version-release (the epoch is dropped to match what `rpm` reports for the installed copy). The
/// "Installed Packages" rows are the copy on this host, not something the source offers.
pub fn parse_dnf_list(stdout: &str, pkg: &str) -> Vec<String> {
    let (mut available, mut wrapped_name) = (false, None::<&str>);
    let mut out: Vec<String> = Vec::new();
    for line in stdout.lines() {
        let fields: Vec<&str> = line.split_whitespace().collect();
        let (name_arch, version) = match (fields.len(), wrapped_name) {
            (0, _) => continue,
            (1, _) => { wrapped_name = Some(fields[0]); continue; } // long names wrap onto the next line
            (2, None) if !fields[0].contains('.') => { available = line.trim() == "Available Packages"; continue; }
            (2, Some(name)) => (name, fields[0]),
            (n, _) if n >= 3 => (fields[0], fields[1]),
            _ => continue,
        };
        wrapped_name = None;
        let name = name_arch.rsplit_once('.').map_or(name_arch, |(n, _arch)| n);
        let version = version.split_once(':').filter(|(e, _)| e.bytes().all(|b| b.is_ascii_digit())).map_or(version, |(_, v)| v);
        if available && name == pkg && !out.iter().any(|v| v == version) {
            out.push(version.to_string());
        }
    }
    out
}

/// The argv that lists the versions the package source offers; every element is a separate argument.
pub fn offered_versions_command(manager: &str, pkg: &str) -> Vec<String> {
    let argv: &[&str] = if manager == "apt-get" { &["apt-cache", "madison"] } else { &[manager, "-q", "--showduplicates", "list"] };
    argv.iter().map(|s| s.to_string()).chain(std::iter::once(pkg.to_string())).collect()
}

pub fn parse_offered(manager: &str, stdout: &str, pkg: &str) -> Vec<String> {
    if manager == "apt-get" { parse_madison(stdout) } else { parse_dnf_list(stdout, pkg) }
}

/// True when the version installed now is still offered, so it can be put back after an upgrade.
/// An unknown installed version is never reversible.
pub fn reversible_linux(installed: &str, offered: &[String]) -> bool {
    let installed = installed.trim();
    !installed.is_empty() && offered.iter().any(|v| v == installed)
}

/// What the package source offers for `pkg` right now. A source that cannot be read offers nothing,
/// which makes the package not reversible (it is deferred, never installed on a guess).
pub async fn offered_versions(manager: &str, pkg: &str) -> Vec<String> {
    let argv = offered_versions_command(manager, pkg);
    let mut cmd = tokio::process::Command::new(&argv[0]);
    cmd.args(&argv[1..]).env("LC_ALL", "C");
    match super::patch_installer::output(cmd, Duration::from_secs(120)).await {
        Ok(out) if out.status.success() => parse_offered(manager, &String::from_utf8_lossy(&out.stdout), pkg),
        _ => Vec::new(),
    }
}

/// Adds the revert code to the uninstall script's rows (only used for a revert by job).
pub fn code_revert_rows(rows: Vec<Value>) -> Vec<Value> {
    rows.into_iter().map(|mut row| {
        let message = row.get("message").and_then(Value::as_str).unwrap_or("").to_string();
        let code = match row.get("status").and_then(Value::as_str) {
            Some("success") => Some(REVERTED),
            Some("failed") if message.contains(WIN_NOT_UNINSTALLABLE_TEXT) => Some(NOT_UNINSTALLABLE),
            Some("failed") if message.contains(WIN_NOT_INSTALLED_TEXT) => Some(NOT_APPLICABLE),
            _ => None,
        };
        if let (Some(code), Some(obj)) = (code, row.as_object_mut()) {
            obj.insert("code".to_string(), Value::from(code));
        }
        row
    }).collect()
}

#[cfg(test)]
mod tests {
    use super::super::patch_installer::{deferred_result, install_script, parse_job, parse_wua_output, summarize, WUA_INSTALL, WUA_UNINSTALL};
    use super::*;
    use serde_json::json;

    const MADISON: &str = " openssl | 1.1.1f-1ubuntu2.22 | http://security.ubuntu.com/ubuntu focal-security/main amd64 Packages\n \
openssl | 1.1.1f-1ubuntu2.20 | http://archive.ubuntu.com/ubuntu focal-updates/main amd64 Packages\n \
openssl | 1.1.1f-1ubuntu2 | http://archive.ubuntu.com/ubuntu focal/main amd64 Packages\n";

    const DNF: &str = "Last metadata expiration check: 0:12:44 ago on Fri 06 Nov 2026.\n\
Installed Packages\n\
openssl.x86_64        1:1.1.1k-7.el8_6        @baseos\n\
openssl-libs.x86_64   1:1.1.1k-7.el8_6        @baseos\n\
Available Packages\n\
openssl.x86_64        1:1.1.1k-6.el8_5        baseos\n\
openssl.x86_64        1:1.1.1k-7.el8_6        baseos\n\
openssl-libs.x86_64   1:1.1.1k-5.el8_4        baseos\n";

    fn offered(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn patch_reversible_parse_madison_lists_versions_in_order() {
        assert_eq!(parse_madison(MADISON), offered(&["1.1.1f-1ubuntu2.22", "1.1.1f-1ubuntu2.20", "1.1.1f-1ubuntu2"]));
    }

    #[test]
    fn patch_reversible_madison_ignores_the_local_status_file_entry() {
        let out = " curl | 7.68.0-1ubuntu2.25 | /var/lib/dpkg/status\n curl | 7.68.0-1ubuntu2.26 | http://x/ focal-updates/main amd64 Packages\n";
        assert_eq!(parse_madison(out), offered(&["7.68.0-1ubuntu2.26"]));
        assert_eq!(parse_madison(""), Vec::<String>::new());
    }

    #[test]
    fn patch_reversible_parse_dnf_list_keeps_only_available_versions_of_the_named_package() {
        assert_eq!(parse_dnf_list(DNF, "openssl"), offered(&["1.1.1k-6.el8_5", "1.1.1k-7.el8_6"]));
        assert_eq!(parse_dnf_list(DNF, "openssl-libs"), offered(&["1.1.1k-5.el8_4"]));
        assert_eq!(parse_dnf_list(DNF, "curl"), Vec::<String>::new());
    }

    #[test]
    fn patch_reversible_dnf_list_reads_a_wrapped_long_name() {
        let out = "Available Packages\nvery-long-package-name-for-testing.noarch\n    2.0-3.el9   appstream\n";
        assert_eq!(parse_dnf_list(out, "very-long-package-name-for-testing"), offered(&["2.0-3.el9"]));
    }

    #[test]
    fn patch_reversible_dnf_list_with_only_installed_rows_offers_nothing() {
        let out = "Installed Packages\nopenssl.x86_64   1:1.1.1k-7.el8_6   @baseos\n";
        assert_eq!(parse_dnf_list(out, "openssl"), Vec::<String>::new());
    }

    #[test]
    fn patch_reversible_linux_needs_the_installed_version_to_be_offered() {
        let both = offered(&["1.1.1f-1ubuntu2.22", "1.1.1f-1ubuntu2.20"]);
        assert!(reversible_linux("1.1.1f-1ubuntu2.20", &both));
        assert!(!reversible_linux("1.1.1f-1ubuntu2.20", &offered(&["1.1.1f-1ubuntu2.22"])));
        assert!(!reversible_linux("", &both));
        assert!(!reversible_linux("  ", &both));
    }

    #[test]
    fn patch_reversible_commands_are_argv_lists() {
        assert_eq!(offered_versions_command("apt-get", "openssl"), offered(&["apt-cache", "madison", "openssl"]));
        assert_eq!(offered_versions_command("dnf", "openssl"), offered(&["dnf", "-q", "--showduplicates", "list", "openssl"]));
        assert_eq!(offered_versions_command("yum", "openssl")[0], "yum");
    }

    #[test]
    fn patch_reversible_job_reads_require_reversible_from_payload_or_parameters() {
        let flag = |item: Value| parse_job(&item, false).unwrap().require_reversible;
        assert!(flag(json!({"payload": {"patch_ids": ["openssl"], "require_reversible": true}})));
        assert!(flag(json!({"parameters": {"patch_ids": ["openssl"], "require_reversible": true}})));
        assert!(!flag(json!({"payload": {"patch_ids": ["openssl"]}})));
        assert!(!flag(json!({"payload": {"patch_ids": ["openssl"], "require_reversible": "yes"}})));
    }

    #[test]
    fn patch_reversible_deferred_is_neither_a_success_nor_a_failure() {
        let r = deferred_result("openssl", NOT_REVERSIBLE, NOT_REVERSIBLE_MESSAGE);
        assert_eq!((r["status"].as_str(), r["code"].as_str(), r["reboot_required"].as_bool()), (Some("deferred"), Some("not_reversible"), Some(false)));
        let s = summarize(vec![r], Some("job-1"), None);
        assert_eq!((s["status"].as_str(), s["successful"].as_u64(), s["failed"].as_u64(), s["total"].as_u64()), (Some("completed"), Some(0), Some(0), Some(1)));
    }

    #[test]
    fn patch_reversible_windows_install_script_without_the_flag_is_the_2_1_16_script() {
        assert_eq!(install_script(false), WUA_INSTALL);
        assert!(!WUA_INSTALL.contains("deferred"));
    }

    #[test]
    fn patch_reversible_windows_install_script_checks_is_uninstallable_before_adding_an_update() {
        let s = install_script(true);
        assert!(s.contains("IsUninstallable") && s.contains("not_reversible") && s.contains("'deferred'"));
        let (check, add) = (s.find("IsUninstallable").unwrap(), s.find("$coll.Add($u)").unwrap());
        assert!(check < add, "the check has to come before the update is added to the install collection");
        // a deferred id is reported once, as deferred, and never also as "not offered"
        assert!(s.contains("$deferred -notcontains $id"));
    }

    #[test]
    fn patch_reversible_every_script_anchor_exists_in_the_2_1_16_script() {
        for needle in ["$index = @{}; $added = @{}", "$uid = $u.Identity.UpdateID", "    $results = @()\n    foreach ($id in $wanted) {",
                       "        if (-not $index.ContainsKey($id)) {"] {
            assert_eq!(WUA_INSTALL.matches(needle).count(), 1, "{needle}");
        }
    }

    #[test]
    fn patch_reversible_wua_output_maps_a_deferred_row_to_a_coded_result() {
        let line = r#"{"results":[{"patch_id":"KB5034441","status":"deferred","code":"not_reversible","reboot_required":false,"message":"Not installed: this update cannot be reversed on this computer."}]}"#;
        let rows = parse_wua_output(line, "", &["KB5034441".to_string()]);
        assert_eq!((rows[0]["status"].as_str(), rows[0]["code"].as_str()), (Some("deferred"), Some("not_reversible")));
        let plain = parse_wua_output(r#"{"results":[{"patch_id":"KB1","status":"success","message":"Installed"}]}"#, "", &[]);
        assert!(plain[0].get("code").is_none(), "2.1.16 rows carry no code");
    }

    #[test]
    fn patch_reversible_uninstall_script_still_speaks_the_sentences_the_codes_are_read_from() {
        assert!(WUA_UNINSTALL.contains(WIN_NOT_UNINSTALLABLE_TEXT) && WUA_UNINSTALL.contains(WIN_NOT_INSTALLED_TEXT));
    }

    #[test]
    fn patch_reversible_revert_rows_get_their_code_from_the_outcome() {
        let rows = code_revert_rows(vec![
            json!({"patch_id": "KB1", "status": "success", "message": "Uninstalled"}),
            json!({"patch_id": "KB2", "status": "failed", "message": WIN_NOT_UNINSTALLABLE_TEXT}),
            json!({"patch_id": "KB3", "status": "failed", "message": WIN_NOT_INSTALLED_TEXT}),
            json!({"patch_id": "KB4", "status": "failed", "message": "Uninstall failed (result code 4)"}),
        ]);
        let codes: Vec<Option<&str>> = rows.iter().map(|r| r["code"].as_str()).collect();
        assert_eq!(codes, vec![Some("reverted"), Some("not_uninstallable"), Some("not_applicable"), None]);
    }
}
