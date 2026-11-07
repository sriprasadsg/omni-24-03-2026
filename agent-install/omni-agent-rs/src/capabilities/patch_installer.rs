//! OS patch installation and rollback (`install_patches` / `rollback_patches`).
//!
//! Windows: the Windows Update Agent COM API through PowerShell, matching offered
//! updates by KB number. Linux: apt-get / dnf / yum, upgrading only packages that are
//! already installed. Rollback never removes a package: Windows uninstalls the KB
//! through WUA, Linux downgrades to the version this agent recorded before it upgraded.
//!
//! Patch ids come from the platform, so they are validated here (KB numbers and plain
//! package names only) and never spliced into a shell or PowerShell command line.

pub use super::patch_reversible::{coded_result, deferred_result};
use super::patch_reversible::{self, NOT_REVERSIBLE, NOT_REVERSIBLE_MESSAGE};
use super::patch_state;
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
    /// Install only what can be put back on this host; the rest is deferred (D-05).
    pub require_reversible: bool,
    /// Rollback only: revert what this install job changed, not the oldest recorded version.
    pub revert_of: Option<String>,
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
    let field = |key: &str| args.and_then(|a| a.get(key)).or_else(|| item.get(key)).filter(|v| !v.is_null());
    let job_id = field("job_id").and_then(safe_id);
    // A revert_of that is present but malformed must never fall back to the oldest-version rollback.
    let revert_of = match field("revert_of") {
        None => None,
        Some(v) if rollback => Some(safe_id(v).ok_or("The patch instruction carried an invalid revert_of")?),
        Some(_) => return Err("revert_of applies to rollback_patches only".to_string()),
    };
    let require_reversible = field("require_reversible").and_then(Value::as_bool).unwrap_or(false);
    Ok(PatchJob { patch_ids: ids, job_id, rollback, require_reversible, revert_of })
}

/// The platform's own id shape (letters, digits, `-`, `_`; up to 80 characters), or None.
fn safe_id(v: &Value) -> Option<String> {
    v.as_str().filter(|s| !s.is_empty() && s.len() <= 80 && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_'))
        .map(str::to_string)
}

/// The apt argv that puts `pkg` back to `previous`. Never a shell string; the `--` keeps the target from
/// being read as an option.
#[cfg_attr(not(target_os = "linux"), allow(dead_code))]
pub(crate) fn apt_downgrade_args(pkg: &str, previous: &str) -> Vec<String> {
    ["apt-get", "install", "-y", "-q", "--allow-downgrades", "-o", "Dpkg::Options::=--force-confdef",
     "-o", "Dpkg::Options::=--force-confold", "--"].iter().map(|s| s.to_string())
        .chain(std::iter::once(format!("{pkg}={previous}"))).collect()
}

/// The answer a revert can give without touching the package manager, or None when the downgrade should run.
#[cfg_attr(not(target_os = "linux"), allow(dead_code))]
pub(crate) fn revert_precheck(_pkg: &str, _installed: Option<&str>, _recorded: &str) -> Option<Value> {
    None
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
        results.extend(run_os(&valid, job).await);
    }
    summarize(results, job.job_id.as_deref(), None)
}

pub(super) async fn output(mut cmd: tokio::process::Command, timeout: Duration) -> Result<std::process::Output, String> {
    cmd.kill_on_drop(true);
    match tokio::time::timeout(timeout, cmd.output()).await {
        Ok(Ok(out)) => Ok(out),
        Ok(Err(e)) => Err(format!("could not start: {e}")),
        Err(_) => Err(format!("did not finish within {} minutes", timeout.as_secs() / 60)),
    }
}

// ── Windows ────────────────────────────────────────────────────────────────

#[cfg_attr(not(windows), allow(dead_code))]
pub(crate) const WUA_INSTALL: &str = r#"
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

#[cfg_attr(not(windows), allow(dead_code))]
pub(crate) const WUA_UNINSTALL: &str = r#"
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

/// The install script. With `require_reversible`, an offered update Windows does not mark as
/// uninstallable is left out of the install collection and reported as deferred (D-05); without
/// it this is the 2.1.16 script, byte for byte.
#[cfg_attr(not(windows), allow(dead_code))]
pub(crate) fn install_script(require_reversible: bool) -> String {
    if !require_reversible {
        return WUA_INSTALL.to_string();
    }
    let deferred = format!("@{{ patch_id = $id; status = 'deferred'; code = '{NOT_REVERSIBLE}'; reboot_required = $false; message = '{NOT_REVERSIBLE_MESSAGE}' }}");
    WUA_INSTALL
        .replacen("$index = @{}; $added = @{}", "$index = @{}; $added = @{}; $deferred = @()", 1)
        .replacen("$uid = $u.Identity.UpdateID",
                  "if (-not $u.IsUninstallable) { if ($deferred -notcontains $id) { $deferred += $id }; continue }\n                $uid = $u.Identity.UpdateID", 1)
        .replacen("    $results = @()\n    foreach ($id in $wanted) {",
                  &format!("    $results = @()\n    foreach ($id in $deferred) {{ $results += {deferred} }}\n    foreach ($id in $wanted) {{"), 1)
        .replacen("        if (-not $index.ContainsKey($id)) {", "        if (-not $index.ContainsKey($id) -and $deferred -notcontains $id) {", 1)
}

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
    rows.iter().filter(|r| r.is_object()).map(|r| {
        let mut result = patch_result(
            r.get("patch_id").and_then(Value::as_str).unwrap_or("?"),
            r.get("status").and_then(Value::as_str).unwrap_or("failed"),
            r.get("message").and_then(Value::as_str).unwrap_or(""),
            r.get("reboot_required").and_then(Value::as_bool).unwrap_or(false),
        );
        if let Some(code) = r.get("code").and_then(Value::as_str) {
            result["code"] = json!(code);
        }
        result
    }).collect()
}

#[cfg(windows)]
async fn run_os(kbs: &[String], job: &PatchJob) -> Vec<Value> {
    if !job.rollback {
        let results = run_wua(kbs, &install_script(job.require_reversible)).await;
        if let Some(id) = &job.job_id {
            let mut state = patch_state::load();
            state.record_kb_successes(id, chrono::Utc::now().timestamp(), &results);
            patch_state::save(&mut state);
        }
        return results;
    }
    let Some(revert_of) = &job.revert_of else { return run_wua(kbs, WUA_UNINSTALL).await };
    // Revert by job: only the KBs that job installed are uninstalled; the rest are answered without touching Windows.
    let plan = patch_state::load().plan_revert(revert_of, kbs);
    let todo: Vec<String> = plan.todo.into_iter().map(|(id, _)| id).collect();
    let mut results = plan.immediate;
    if !todo.is_empty() {
        results.extend(patch_reversible::code_revert_rows(run_wua(&todo, WUA_UNINSTALL).await));
    }
    results
}

#[cfg(windows)]
async fn run_wua(kbs: &[String], script: &str) -> Vec<Value> {
    let mut cmd = tokio::process::Command::new("powershell");
    cmd.args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script])
        .env("OMNI_KBS", kbs.join(","));
    match output(cmd, WINDOWS_TIMEOUT).await {
        Ok(out) => parse_wua_output(&String::from_utf8_lossy(&out.stdout), &String::from_utf8_lossy(&out.stderr), kbs),
        Err(e) => kbs.iter().map(|kb| patch_result(kb, "failed", &format!("Windows Update {e}"), false)).collect(),
    }
}

// ── Linux ──────────────────────────────────────────────────────────────────

#[cfg(target_os = "linux")]
mod linux {
    use super::patch_reversible::{REVERTED, VERSION_NOT_OFFERED};
    use super::*;

    fn tail(bytes: &[u8], n: usize) -> String {
        let s = String::from_utf8_lossy(bytes).trim().to_string();
        let chars: Vec<char> = s.chars().collect();
        chars[chars.len().saturating_sub(n)..].iter().collect()
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

    pub async fn install(packages: &[String], job: &PatchJob) -> Vec<Value> {
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
        let mut state = patch_state::load();
        let mut results = Vec::new();
        for pkg in packages {
            let Some(before) = installed_version(mgr, pkg).await else {
                results.push(patch_result(pkg, "failed", "Package is not installed; patching only upgrades installed packages", false));
                continue;
            };
            // D-05: checked just before this package's upgrade, against what the source offers now.
            if job.require_reversible && !patch_reversible::reversible_linux(&before, &patch_reversible::offered_versions(mgr, pkg).await) {
                results.push(deferred_result(pkg, NOT_REVERSIBLE, NOT_REVERSIBLE_MESSAGE));
                continue;
            }
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
                        state.legacy.entry(pkg.clone()).or_insert(before.clone()); // keep the oldest pre-patch version
                        if let Some(id) = &job.job_id {
                            state.record_install(id, "linux", chrono::Utc::now().timestamp(), pkg, &before);
                        }
                        results.push(patch_result(pkg, "success", &format!("Upgraded {before} -> {after}"), reboot_required().await));
                    }
                    _ => results.push(patch_result(pkg, "skipped", &format!("Already at the newest available version ({before})"), false)),
                },
            }
        }
        patch_state::save(&mut state);
        results
    }

    /// Downgrades `pkg` to `previous`; Ok only when the package manager confirms that version is installed.
    async fn downgrade(mgr: &str, pkg: &str, previous: &str) -> Result<(), String> {
        let cmd = if mgr == "apt-get" {
            let args = apt_downgrade_args(pkg, previous);
            privileged(&args.iter().map(String::as_str).collect::<Vec<_>>())
        } else {
            privileged(&[mgr, "downgrade", "-y", "-q", &format!("{pkg}-{previous}")])
        };
        match output(cmd, LINUX_TIMEOUT).await {
            Ok(out) if out.status.success() && installed_version(mgr, pkg).await.as_deref() == Some(previous) => Ok(()),
            Ok(out) => Err(format!("Downgrade to {previous} failed: {}", tail(if out.stderr.is_empty() { &out.stdout } else { &out.stderr }, 400))),
            Err(e) => Err(format!("{mgr} {e}")),
        }
    }

    /// Revert by job: put back the version that job replaced, and only when the source still offers it.
    async fn rollback_job(mgr: &str, packages: &[String], job_id: &str) -> Vec<Value> {
        let plan = patch_state::load().plan_revert(job_id, packages);
        let mut results = plan.immediate;
        for (pkg, version) in plan.todo {
            if installed_version(mgr, &pkg).await.as_deref() == Some(version.as_str()) {
                results.push(coded_result(&pkg, "success", REVERTED, &format!("Already at the earlier version {version}"), false));
            } else if !patch_reversible::reversible_linux(&version, &patch_reversible::offered_versions(mgr, &pkg).await) {
                results.push(coded_result(&pkg, "failed", VERSION_NOT_OFFERED, &format!("The package source no longer offers {version}"), false));
            } else {
                results.push(match downgrade(mgr, &pkg, &version).await {
                    Ok(()) => coded_result(&pkg, "success", REVERTED, &format!("Put back the earlier version of {pkg} ({version})"), reboot_required().await),
                    Err(message) => patch_result(&pkg, "failed", &message, false),
                });
            }
        }
        results
    }

    pub async fn rollback(packages: &[String], job: &PatchJob) -> Vec<Value> {
        let Some(mgr) = manager() else {
            return packages.iter().map(|p| patch_result(p, "failed", "No supported package manager (apt-get, dnf, yum)", false)).collect();
        };
        if !can_escalate().await {
            return packages.iter().map(|p| patch_result(p, "failed", "The agent needs root or passwordless sudo to roll back updates", false)).collect();
        }
        if let Some(revert_of) = &job.revert_of {
            return rollback_job(mgr, packages, revert_of).await;
        }
        let mut state = patch_state::load();
        let mut results = Vec::new();
        for pkg in packages {
            let Some(previous) = state.legacy.get(pkg).cloned() else {
                results.push(patch_result(pkg, "failed", "No pre-patch version recorded by this agent; refusing to remove the package", false));
                continue;
            };
            match downgrade(mgr, pkg, &previous).await {
                Ok(()) => {
                    state.legacy.remove(pkg);
                    results.push(patch_result(pkg, "success", &format!("Downgraded to {previous}"), reboot_required().await));
                }
                Err(message) => results.push(patch_result(pkg, "failed", &message, false)),
            }
        }
        patch_state::save(&mut state);
        results
    }
}

#[cfg(target_os = "linux")]
async fn run_os(packages: &[String], job: &PatchJob) -> Vec<Value> {
    if job.rollback { linux::rollback(packages, job).await } else { linux::install(packages, job).await }
}

#[cfg(not(any(windows, target_os = "linux")))]
async fn run_os(ids: &[String], _job: &PatchJob) -> Vec<Value> {
    ids.iter().map(|id| patch_result(id, "failed", "Patching is not supported on this OS", false)).collect()
}
