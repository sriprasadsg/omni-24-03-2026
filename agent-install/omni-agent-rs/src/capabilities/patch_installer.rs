//! OS patch installation and rollback (`install_patches` / `rollback_patches`).
//!
//! Windows: the Windows Update Agent COM API through PowerShell, matching offered
//! updates by KB number. Linux: apt-get / dnf / yum, upgrading only packages that are
//! already installed. Rollback never removes a package: Windows uninstalls the KB
//! through WUA, Linux downgrades to the version this agent recorded before it upgraded.
//!
//! Patch ids come from the platform, so they are validated here (KB numbers and plain
//! package names only) and never spliced into a shell or PowerShell command line.

use serde_json::{json, Value};
use std::sync::LazyLock;
use std::time::Duration;

static KB_RE: LazyLock<regex::Regex> = LazyLock::new(|| regex::Regex::new(r"(?i)^KB\d{4,8}$").unwrap());
// Advisory ids (CVE-…) and KB-shaped ids of the wrong length are never treated as package names.
static NOT_PKG_RE: LazyLock<regex::Regex> = LazyLock::new(|| regex::Regex::new(r"(?i)^(CVE-\d{4}-\d+|KB\d+)$").unwrap());
// Same rule as the backend (patch_core_endpoints.installable_patch_id).
static PKG_RE: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"^[A-Za-z0-9][A-Za-z0-9.+_:-]{0,127}$").unwrap());

#[cfg(windows)]
const WINDOWS_TIMEOUT: Duration = Duration::from_secs(3600);
#[cfg(target_os = "linux")]
const LINUX_TIMEOUT: Duration = Duration::from_secs(1800);

/// One patch job as delivered by the platform's instruction poll.
#[derive(Debug, Clone, PartialEq)]
pub struct PatchJob {
    pub patch_ids: Vec<String>,
    pub job_id: Option<String>,
    pub rollback: bool,
}

/// A KB number (as "KB1234567") or a package name; None for anything else, CVE ids included.
pub fn normalize_patch_id(raw: &str) -> Option<String> {
    let v = raw.trim();
    if KB_RE.is_match(v) {
        return Some(v.to_uppercase());
    }
    if NOT_PKG_RE.is_match(v) || !PKG_RE.is_match(v) {
        return None;
    }
    Some(v.to_string())
}

/// Reads the job from an instruction item: `payload.patch_ids` / `payload.job_id`
/// (also accepted under `parameters`, or as top-level `patches` / `job_id`).
pub fn parse_job(item: &Value, rollback: bool) -> Result<PatchJob, String> {
    let args = item.get("payload").filter(|v| v.is_object())
        .or_else(|| item.get("parameters").filter(|v| v.is_object()));
    let ids = args.and_then(|a| a.get("patch_ids")).or_else(|| item.get("patches"))
        .and_then(|v| v.as_array())
        .map(|a| a.iter().filter_map(|v| v.as_str().map(str::to_string)).collect::<Vec<_>>())
        .unwrap_or_default();
    if ids.is_empty() {
        return Err("The patch instruction carried no patch ids".to_string());
    }
    // The job id becomes a URL path segment, so only the platform's own id shape is kept.
    let job_id = args.and_then(|a| a.get("job_id")).or_else(|| item.get("job_id"))
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty() && s.len() <= 80 && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_'))
        .map(str::to_string);
    Ok(PatchJob { patch_ids: ids, job_id, rollback })
}

pub fn patch_result(patch_id: &str, status: &str, message: &str, reboot: bool) -> Value {
    json!({"patch_id": patch_id, "status": status, "message": message,
           "reboot_required": reboot, "timestamp": chrono::Utc::now().to_rfc3339()})
}

/// The job summary posted to /api/deployments/{job_id}/result.
pub fn summarize(results: Vec<Value>, job_id: Option<&str>, error: Option<&str>) -> Value {
    let count = |s: &str| results.iter().filter(|r| r.get("status").and_then(Value::as_str) == Some(s)).count();
    let (ok, failed) = (count("success"), count("failed"));
    let status = if error.is_some() || (failed > 0 && ok == 0) { "failed" } else if failed > 0 { "partial" } else { "completed" };
    let mut out = json!({"status": status, "job_id": job_id, "total": results.len(), "successful": ok,
                         "failed": failed, "results": results, "timestamp": chrono::Utc::now().to_rfc3339()});
    if let Some(e) = error {
        out["error"] = json!(e);
    }
    out
}

/// Splits ids into the ones this OS can act on and immediate failures for the rest.
pub fn triage(raw_ids: &[String], windows: bool) -> (Vec<String>, Vec<Value>) {
    let (mut valid, mut rejected) = (Vec::new(), Vec::new());
    for raw in raw_ids {
        match normalize_patch_id(raw) {
            None => rejected.push(patch_result(&raw.chars().take(80).collect::<String>(), "failed",
                                               "Not an installable KB number or package name", false)),
            Some(id) if windows && !id.starts_with("KB") =>
                rejected.push(patch_result(&id, "failed", "Only Windows KB updates can be installed on Windows", false)),
            Some(id) if !windows && KB_RE.is_match(&id) =>
                rejected.push(patch_result(&id, "failed", "Windows KB updates do not apply to Linux", false)),
            Some(id) => if !valid.contains(&id) { valid.push(id) },
        }
    }
    (valid, rejected)
}

/// Runs the job to completion and returns its summary.
pub async fn run(job: &PatchJob) -> Value {
    let (valid, mut results) = triage(&job.patch_ids, cfg!(windows));
    log::info!("Patch job {:?}: {} {} patch(es)", job.job_id, if job.rollback { "rolling back" } else { "installing" }, valid.len());
    if !valid.is_empty() {
        results.extend(run_os(&valid, job.rollback).await);
    }
    summarize(results, job.job_id.as_deref(), None)
}

async fn output(mut cmd: tokio::process::Command, timeout: Duration) -> Result<std::process::Output, String> {
    cmd.kill_on_drop(true);
    match tokio::time::timeout(timeout, cmd.output()).await {
        Ok(Ok(out)) => Ok(out),
        Ok(Err(e)) => Err(format!("could not start: {e}")),
        Err(_) => Err(format!("did not finish within {} minutes", timeout.as_secs() / 60)),
    }
}

// ── Windows ────────────────────────────────────────────────────────────────

#[cfg(windows)]
const WUA_INSTALL: &str = r#"
$ErrorActionPreference = 'Stop'
try {
    $wanted = @($env:OMNI_KBS -split ',' | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ })
    $session = New-Object -ComObject Microsoft.Update.Session
    $session.ClientApplicationID = 'Omni-Agent'
    $offered = $session.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Software' and IsHidden=0").Updates
    $coll = New-Object -ComObject Microsoft.Update.UpdateColl
    $index = @{}; $added = @{}
    foreach ($u in $offered) {
        foreach ($kb in $u.KBArticleIDs) {
            $id = "KB$kb"
            if ($wanted -contains $id -and -not $index.ContainsKey($id)) {
                $uid = $u.Identity.UpdateID
                if (-not $added.ContainsKey($uid)) {
                    if (-not $u.EulaAccepted) { $u.AcceptEula() }
                    $added[$uid] = $coll.Add($u)
                }
                $index[$id] = $added[$uid]
            }
        }
    }
    $results = @()
    foreach ($id in $wanted) {
        if (-not $index.ContainsKey($id)) {
            $results += @{ patch_id = $id; status = 'skipped'; reboot_required = $false;
                           message = 'Not offered by Windows Update (already installed or not applicable)' }
        }
    }
    if ($coll.Count -gt 0) {
        $dl = $session.CreateUpdateDownloader(); $dl.Updates = $coll; [void]$dl.Download()
        $inst = $session.CreateUpdateInstaller(); $inst.Updates = $coll
        $res = $inst.Install()
        foreach ($id in $index.Keys) {
            $ur = $res.GetUpdateResult($index[$id])
            $ok = ($ur.ResultCode -eq 2) -or ($ur.ResultCode -eq 3)
            $status = 'failed'; $msg = 'Install failed (result code ' + $ur.ResultCode + ', HRESULT 0x' + ('{0:X8}' -f $ur.HResult) + ')'
            if ($ok) { $status = 'success'; $msg = 'Installed' }
            $results += @{ patch_id = $id; status = $status; message = $msg; reboot_required = [bool]$ur.RebootRequired }
        }
    }
    @{ results = $results } | ConvertTo-Json -Depth 4 -Compress
} catch {
    @{ error = $_.Exception.Message } | ConvertTo-Json -Compress
    exit 1
}
"#;

#[cfg(windows)]
const WUA_UNINSTALL: &str = r#"
$ErrorActionPreference = 'Stop'
try {
    $wanted = @($env:OMNI_KBS -split ',' | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ })
    $session = New-Object -ComObject Microsoft.Update.Session
    $session.ClientApplicationID = 'Omni-Agent'
    $installed = $session.CreateUpdateSearcher().Search("IsInstalled=1 and Type='Software'").Updates
    $results = @()
    foreach ($id in $wanted) {
        $match = $null
        foreach ($u in $installed) { if ($u.KBArticleIDs | Where-Object { "KB$_" -eq $id }) { $match = $u; break } }
        if (-not $match) {
            $results += @{ patch_id = $id; status = 'failed'; reboot_required = $false; message = 'Not installed on this host' }
        } elseif (-not $match.IsUninstallable) {
            $results += @{ patch_id = $id; status = 'failed'; reboot_required = $false;
                           message = 'Windows marks this update as not uninstallable' }
        } else {
            $coll = New-Object -ComObject Microsoft.Update.UpdateColl; [void]$coll.Add($match)
            $inst = $session.CreateUpdateInstaller(); $inst.Updates = $coll
            $ur = $inst.Uninstall().GetUpdateResult(0)
            $ok = ($ur.ResultCode -eq 2) -or ($ur.ResultCode -eq 3)
            $status = 'failed'; $msg = 'Uninstall failed (result code ' + $ur.ResultCode + ')'
            if ($ok) { $status = 'success'; $msg = 'Uninstalled' }
            $results += @{ patch_id = $id; status = $status; message = $msg; reboot_required = [bool]$ur.RebootRequired }
        }
    }
    @{ results = $results } | ConvertTo-Json -Depth 4 -Compress
} catch {
    @{ error = $_.Exception.Message } | ConvertTo-Json -Compress
    exit 1
}
"#;

/// Turns the PowerShell script's JSON line into per-KB results.
pub fn parse_wua_output(stdout: &str, stderr: &str, kbs: &[String]) -> Vec<Value> {
    let last = stdout.lines().rev().find(|l| !l.trim().is_empty()).unwrap_or("");
    let data: Value = serde_json::from_str(last.trim()).unwrap_or(Value::Null);
    let rows = match data.get("results") {
        Some(Value::Array(a)) => a.clone(),
        Some(v @ Value::Object(_)) => vec![v.clone()],
        _ => {
            let reason = data.get("error").and_then(Value::as_str).map(str::to_string)
                .unwrap_or_else(|| { let t = format!("{stderr}{stdout}"); t.trim().chars().take(300).collect() });
            let reason = if reason.is_empty() { "no output".to_string() } else { reason };
            return kbs.iter().map(|kb| patch_result(kb, "failed", &format!("Windows Update error: {reason}"), false)).collect();
        }
    };
    rows.iter().filter(|r| r.is_object()).map(|r| patch_result(
        r.get("patch_id").and_then(Value::as_str).unwrap_or("?"),
        r.get("status").and_then(Value::as_str).unwrap_or("failed"),
        r.get("message").and_then(Value::as_str).unwrap_or(""),
        r.get("reboot_required").and_then(Value::as_bool).unwrap_or(false),
    )).collect()
}

#[cfg(windows)]
async fn run_os(kbs: &[String], rollback: bool) -> Vec<Value> {
    let mut cmd = tokio::process::Command::new("powershell");
    cmd.args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
              if rollback { WUA_UNINSTALL } else { WUA_INSTALL }])
        .env("OMNI_KBS", kbs.join(","));
    match output(cmd, WINDOWS_TIMEOUT).await {
        Ok(out) => parse_wua_output(&String::from_utf8_lossy(&out.stdout), &String::from_utf8_lossy(&out.stderr), kbs),
        Err(e) => kbs.iter().map(|kb| patch_result(kb, "failed", &format!("Windows Update {e}"), false)).collect(),
    }
}

// ── Linux ──────────────────────────────────────────────────────────────────

#[cfg(target_os = "linux")]
mod linux {
    use super::*;
    use std::collections::BTreeMap;

    fn tail(bytes: &[u8], n: usize) -> String {
        let s = String::from_utf8_lossy(bytes).trim().to_string();
        let chars: Vec<char> = s.chars().collect();
        chars[chars.len().saturating_sub(n)..].iter().collect()
    }

    pub fn state_path() -> std::path::PathBuf {
        crate::config::config_path().with_file_name("patch_state.json")
    }

    pub fn load_state() -> BTreeMap<String, String> {
        std::fs::read(state_path()).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default()
    }

    pub fn save_state(state: &BTreeMap<String, String>) {
        let path = state_path();
        let tmp = path.with_extension("json.tmp");
        let ok = serde_json::to_vec_pretty(state).ok()
            .map(|b| std::fs::write(&tmp, b).and_then(|_| std::fs::rename(&tmp, &path)).is_ok());
        if ok != Some(true) {
            log::warn!("Could not record pre-patch package versions in {}", path.display());
        }
    }

    fn is_root() -> bool {
        // SAFETY: geteuid has no preconditions and cannot fail.
        unsafe { libc::geteuid() == 0 }
    }

    fn which(bin: &str) -> bool {
        std::env::var_os("PATH").map(|p| std::env::split_paths(&p).any(|d| d.join(bin).is_file())).unwrap_or(false)
    }

    pub fn manager() -> Option<&'static str> {
        ["apt-get", "dnf", "yum"].into_iter().find(|m| which(m))
    }

    /// The command as root: directly when the agent is root, else through passwordless sudo.
    fn privileged(args: &[&str]) -> tokio::process::Command {
        let mut cmd = if is_root() {
            tokio::process::Command::new(args[0])
        } else {
            let mut c = tokio::process::Command::new("sudo");
            c.arg("-n").arg(args[0]);
            c
        };
        cmd.args(&args[1..]).env("DEBIAN_FRONTEND", "noninteractive").env("NEEDRESTART_MODE", "a");
        cmd
    }

    pub async fn can_escalate() -> bool {
        is_root() || (which("sudo") && output({ let mut c = tokio::process::Command::new("sudo"); c.args(["-n", "true"]); c },
                                              Duration::from_secs(15)).await.map(|o| o.status.success()).unwrap_or(false))
    }

    pub async fn installed_version(manager: &str, pkg: &str) -> Option<String> {
        let mut cmd = if manager == "apt-get" {
            let mut c = tokio::process::Command::new("dpkg-query");
            c.args(["-W", "-f=${Version}", pkg]);
            c
        } else {
            let mut c = tokio::process::Command::new("rpm");
            c.args(["-q", "--qf", "%{VERSION}-%{RELEASE}", pkg]);
            c
        };
        cmd.env("LC_ALL", "C");
        let out = output(cmd, Duration::from_secs(30)).await.ok()?;
        let v = String::from_utf8_lossy(&out.stdout).trim().to_string();
        (out.status.success() && !v.is_empty() && !v.contains("not installed")).then_some(v)
    }

    async fn reboot_required() -> bool {
        if std::path::Path::new("/var/run/reboot-required").exists() {
            return true;
        }
        if which("needs-restarting") {
            let mut c = tokio::process::Command::new("needs-restarting");
            c.arg("-r");
            return output(c, Duration::from_secs(60)).await.map(|o| o.status.code() == Some(1)).unwrap_or(false);
        }
        false
    }

    pub async fn install(packages: &[String]) -> Vec<Value> {
        let Some(mgr) = manager() else {
            return packages.iter().map(|p| patch_result(p, "failed", "No supported package manager (apt-get, dnf, yum)", false)).collect();
        };
        if !can_escalate().await {
            return packages.iter().map(|p| patch_result(p, "failed", "The agent needs root or passwordless sudo to install updates", false)).collect();
        }
        if mgr == "apt-get" {
            if let Err(e) = output(privileged(&["apt-get", "update", "-q"]), LINUX_TIMEOUT).await {
                log::warn!("apt-get update {e}");
            }
        }
        let mut state = load_state();
        let mut results = Vec::new();
        for pkg in packages {
            let Some(before) = installed_version(mgr, pkg).await else {
                results.push(patch_result(pkg, "failed", "Package is not installed; patching only upgrades installed packages", false));
                continue;
            };
            let cmd = if mgr == "apt-get" {
                privileged(&["apt-get", "install", "-y", "-q", "--only-upgrade", "-o", "Dpkg::Options::=--force-confdef",
                             "-o", "Dpkg::Options::=--force-confold", "--", pkg])
            } else {
                privileged(&[mgr, "upgrade", "-y", "-q", pkg])
            };
            match output(cmd, LINUX_TIMEOUT).await {
                Err(e) => results.push(patch_result(pkg, "failed", &format!("{mgr} {e}"), false)),
                Ok(out) if !out.status.success() => results.push(patch_result(pkg, "failed",
                    &format!("{mgr} failed: {}", tail(if out.stderr.is_empty() { &out.stdout } else { &out.stderr }, 400)), false)),
                Ok(_) => match installed_version(mgr, pkg).await {
                    Some(after) if after != before => {
                        state.entry(pkg.clone()).or_insert(before.clone()); // keep the oldest pre-patch version
                        results.push(patch_result(pkg, "success", &format!("Upgraded {before} -> {after}"), reboot_required().await));
                    }
                    _ => results.push(patch_result(pkg, "skipped", &format!("Already at the newest available version ({before})"), false)),
                },
            }
        }
        save_state(&state);
        results
    }

    pub async fn rollback(packages: &[String]) -> Vec<Value> {
        let Some(mgr) = manager() else {
            return packages.iter().map(|p| patch_result(p, "failed", "No supported package manager (apt-get, dnf, yum)", false)).collect();
        };
        if !can_escalate().await {
            return packages.iter().map(|p| patch_result(p, "failed", "The agent needs root or passwordless sudo to roll back updates", false)).collect();
        }
        let mut state = load_state();
        let mut results = Vec::new();
        for pkg in packages {
            let Some(previous) = state.get(pkg).cloned() else {
                results.push(patch_result(pkg, "failed", "No pre-patch version recorded by this agent; refusing to remove the package", false));
                continue;
            };
            let target = if mgr == "apt-get" { format!("{pkg}={previous}") } else { format!("{pkg}-{previous}") };
            let cmd = if mgr == "apt-get" {
                privileged(&["apt-get", "install", "-y", "-q", "--allow-downgrades", "-o", "Dpkg::Options::=--force-confdef",
                             "-o", "Dpkg::Options::=--force-confold", "--", &target])
            } else {
                privileged(&[mgr, "downgrade", "-y", "-q", &target])
            };
            match output(cmd, LINUX_TIMEOUT).await {
                Ok(out) if out.status.success() && installed_version(mgr, pkg).await.as_deref() == Some(previous.as_str()) => {
                    state.remove(pkg);
                    results.push(patch_result(pkg, "success", &format!("Downgraded to {previous}"), reboot_required().await));
                }
                Ok(out) => results.push(patch_result(pkg, "failed", &format!("Downgrade to {previous} failed: {}",
                    tail(if out.stderr.is_empty() { &out.stdout } else { &out.stderr }, 400)), false)),
                Err(e) => results.push(patch_result(pkg, "failed", &format!("{mgr} {e}"), false)),
            }
        }
        save_state(&state);
        results
    }
}

#[cfg(target_os = "linux")]
async fn run_os(packages: &[String], rollback: bool) -> Vec<Value> {
    if rollback { linux::rollback(packages).await } else { linux::install(packages).await }
}

#[cfg(not(any(windows, target_os = "linux")))]
async fn run_os(ids: &[String], _rollback: bool) -> Vec<Value> {
    ids.iter().map(|id| patch_result(id, "failed", "Patching is not supported on this OS", false)).collect()
}
