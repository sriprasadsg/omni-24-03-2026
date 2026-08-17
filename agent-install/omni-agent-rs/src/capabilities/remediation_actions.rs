//! Bounded, param-validated remediation actions dispatched by the backend
//! autonomous remediation engine (Phase 53). Every action returns a
//! structured `Result` and never panics — failures surface as
//! `RemediationError` so the caller (instructions.rs) reports a clean
//! `{status: "error", error: ...}` back to the backend, which verifies
//! before ever marking a finding resolved.
//!
//! Real OS calls (kill signal, firewall rule, service start/stop) are
//! gated behind `run_privileged_command` / the sysinfo kill call, which
//! are stubbed out under `#[cfg(test)]` so the unit test suite exercises
//! only param validation + branching — it never actually kills a process,
//! touches the host firewall, or starts/stops a real service.

use crate::capabilities::ssh_key_rotation;
use std::net::IpAddr;
use std::path::Path;

// Small, deliberately conservative denylists: even though the backend's
// approval gate (53-04) is the primary control, the agent itself refuses
// to touch a short list of single-instance, OS-critical targets so a
// malformed or overly broad playbook can never brick or lock out the host.
const CRITICAL_PROCESS_NAMES: &[&str] = &[
    "init", "systemd", "launchd", "kernel_task",
    "wininit.exe", "winlogon.exe", "csrss.exe", "smss.exe", "services.exe", "lsass.exe",
];
const CRITICAL_SERVICE_NAMES: &[&str] = &[
    "sshd", "ssh", "systemd", "dbus", "networkmanager", "init",
];

#[derive(Debug, thiserror::Error)]
pub enum RemediationError {
    #[error("Invalid target: {0}")]
    InvalidTarget(String),
    #[error("Process not found: {0}")]
    ProcessNotFound(String),
    #[error("Service not found: {0}")]
    ServiceNotFound(String),
    #[error("IP address not found: {0}")]
    IpNotFound(String),
    #[error("File not found: {0}")]
    FileNotFound(String),
    #[error("Operation failed: {0}")]
    OperationFailed(String),
    #[error("Invalid IP address format: {0}")]
    InvalidIpAddress(String),
    #[error("Invalid port: {0}")]
    InvalidPort(String),
    #[error("Failed to parse path: {0}")]
    InvalidPath(String),
    #[error("Refusing to rotate: {0}")]
    LockoutRefused(String),
    #[error("Key not found: {0}")]
    KeyNotFound(String),
}

/// Runs a privileged OS command (firewall rule, service control) and maps
/// a non-zero exit to `OperationFailed`. Stubbed to a no-op success under
/// `#[cfg(test)]` so unit tests never touch the real firewall/service
/// manager (per the plan's hermetic-test requirement).
#[cfg(not(test))]
fn run_privileged_command(program: &str, args: &[&str]) -> Result<(), RemediationError> {
    let output = std::process::Command::new(program)
        .args(args)
        .output()
        .map_err(|e| RemediationError::OperationFailed(format!("{program} failed to spawn: {e}")))?;
    if output.status.success() {
        Ok(())
    } else {
        Err(RemediationError::OperationFailed(format!(
            "{program} exited with {:?}: {}",
            output.status.code(),
            String::from_utf8_lossy(&output.stderr).trim()
        )))
    }
}

#[cfg(test)]
fn run_privileged_command(_program: &str, _args: &[&str]) -> Result<(), RemediationError> {
    Ok(())
}

fn is_valid_service_name(name: &str) -> bool {
    !name.is_empty()
        && !name.starts_with('-')
        && name.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'))
}

/// Kills a process by PID (all digits) or exact name. Refuses PID 0/1, the
/// agent's own PID, and a short list of OS-critical process names.
pub async fn kill_process(target: &str) -> Result<(), RemediationError> {
    if target.is_empty() {
        return Err(RemediationError::InvalidTarget("Process target cannot be empty.".to_string()));
    }

    let self_pid = std::process::id();

    if target.chars().all(|c| c.is_ascii_digit()) {
        let pid_num: u32 = target
            .parse()
            .map_err(|_| RemediationError::InvalidTarget("Failed to parse PID.".to_string()))?;
        if pid_num == 0 || pid_num == 1 {
            return Err(RemediationError::InvalidTarget("Refusing to kill PID 0/1 (init).".to_string()));
        }
        if pid_num == self_pid {
            return Err(RemediationError::InvalidTarget("Refusing to kill the agent's own process.".to_string()));
        }

        let sys = sysinfo::System::new_all();
        let pid = sysinfo::Pid::from(pid_num as usize);
        return match sys.process(pid) {
            Some(proc) => {
                if proc.kill() {
                    Ok(())
                } else {
                    Err(RemediationError::OperationFailed(format!("Failed to signal PID {pid_num}.")))
                }
            }
            None => Err(RemediationError::ProcessNotFound(target.to_string())),
        };
    }

    let lower = target.to_ascii_lowercase();
    if CRITICAL_PROCESS_NAMES.iter().any(|n| *n == lower) {
        return Err(RemediationError::InvalidTarget(format!("Refusing to kill OS-critical process '{target}'.")));
    }

    let self_name = std::env::current_exe()
        .ok()
        .and_then(|p| p.file_name().map(|n| n.to_string_lossy().to_ascii_lowercase()));
    if self_name.as_deref() == Some(lower.as_str()) {
        return Err(RemediationError::InvalidTarget("Refusing to kill the agent's own process.".to_string()));
    }

    let sys = sysinfo::System::new_all();
    let matches: Vec<_> = sys
        .processes()
        .iter()
        .filter(|(pid, proc)| pid.as_u32() != self_pid && proc.name().to_string_lossy() == target)
        .collect();

    if matches.is_empty() {
        return Err(RemediationError::ProcessNotFound(target.to_string()));
    }

    let mut any_success = false;
    for (_, proc) in matches {
        if proc.kill() {
            any_success = true;
        }
    }
    if any_success {
        Ok(())
    } else {
        Err(RemediationError::OperationFailed(format!("Failed to signal any process named '{target}'.")))
    }
}

/// Restores `file_path` from an explicit `backup_path`. There is no
/// implicit "known-good" source to fall back to — the FIM baseline only
/// stores hashes, not file content — so a missing backup_path is a refusal,
/// never a guess.
pub async fn restore_file(file_path: &str, backup_path: Option<&str>) -> Result<(), RemediationError> {
    if file_path.is_empty() {
        return Err(RemediationError::InvalidPath("File path cannot be empty.".to_string()));
    }

    match backup_path {
        Some(bp) if bp.is_empty() => Err(RemediationError::InvalidPath("Backup path cannot be empty.".to_string())),
        Some(bp) => {
            let backup = Path::new(bp);
            if !backup.exists() {
                return Err(RemediationError::FileNotFound(bp.to_string()));
            }
            std::fs::copy(backup, file_path)
                .map(|_| ())
                .map_err(|e| RemediationError::OperationFailed(format!("Restore copy failed: {e}")))
        }
        None => Err(RemediationError::OperationFailed(
            "No known-good backup source available for restore.".to_string(),
        )),
    }
}

/// Adds a host firewall DROP rule for `ip_address` (iptables on Linux,
/// Windows Advanced Firewall on Windows).
pub async fn block_ip(ip_address: &str) -> Result<(), RemediationError> {
    let ip = validate_ip(ip_address)?;

    #[cfg(target_os = "linux")]
    {
        run_privileged_command("iptables", &["-I", "INPUT", "-s", &ip.to_string(), "-j", "DROP"])
    }
    #[cfg(target_os = "windows")]
    {
        let rule_name = format!("OmniAgent_Block_{ip}");
        run_privileged_command(
            "netsh",
            &[
                "advfirewall", "firewall", "add", "rule",
                &format!("name={rule_name}"), "dir=in", "action=block",
                &format!("remoteip={ip}"),
            ],
        )
    }
    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    {
        Err(RemediationError::OperationFailed("block_ip is unsupported on this platform.".to_string()))
    }
}

/// Removes the firewall rule added by `block_ip`.
pub async fn unblock_ip(ip_address: &str) -> Result<(), RemediationError> {
    let ip = validate_ip(ip_address)?;

    #[cfg(target_os = "linux")]
    {
        run_privileged_command("iptables", &["-D", "INPUT", "-s", &ip.to_string(), "-j", "DROP"])
    }
    #[cfg(target_os = "windows")]
    {
        let rule_name = format!("OmniAgent_Block_{ip}");
        run_privileged_command(
            "netsh",
            &["advfirewall", "firewall", "delete", "rule", &format!("name={rule_name}")],
        )
    }
    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    {
        Err(RemediationError::OperationFailed("unblock_ip is unsupported on this platform.".to_string()))
    }
}

fn validate_ip(ip_address: &str) -> Result<IpAddr, RemediationError> {
    if ip_address.is_empty() {
        return Err(RemediationError::InvalidIpAddress("IP address cannot be empty.".to_string()));
    }
    ip_address
        .parse::<IpAddr>()
        .map_err(|_| RemediationError::InvalidIpAddress(ip_address.to_string()))
}

/// Stops and disables a named service (systemctl on Linux, sc.exe on
/// Windows). Refuses a short list of OS-critical services.
pub async fn disable_service(service_name: &str) -> Result<(), RemediationError> {
    validate_service_name(service_name)?;

    #[cfg(target_os = "linux")]
    {
        let _ = run_privileged_command("systemctl", &["stop", service_name]);
        run_privileged_command("systemctl", &["disable", service_name])
    }
    #[cfg(target_os = "windows")]
    {
        let _ = run_privileged_command("sc", &["stop", service_name]);
        run_privileged_command("sc", &["config", service_name, "start=", "disabled"])
    }
    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    {
        Err(RemediationError::OperationFailed("disable_service is unsupported on this platform.".to_string()))
    }
}

/// Enables and starts a named service — the rollback counterpart of
/// `disable_service`.
pub async fn enable_service(service_name: &str) -> Result<(), RemediationError> {
    validate_service_name(service_name)?;

    #[cfg(target_os = "linux")]
    {
        run_privileged_command("systemctl", &["enable", service_name])?;
        run_privileged_command("systemctl", &["start", service_name])
    }
    #[cfg(target_os = "windows")]
    {
        run_privileged_command("sc", &["config", service_name, "start=", "auto"])?;
        run_privileged_command("sc", &["start", service_name])
    }
    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    {
        Err(RemediationError::OperationFailed("enable_service is unsupported on this platform.".to_string()))
    }
}

fn validate_service_name(service_name: &str) -> Result<(), RemediationError> {
    if service_name.is_empty() {
        return Err(RemediationError::InvalidTarget("Service name cannot be empty.".to_string()));
    }
    if !is_valid_service_name(service_name) {
        return Err(RemediationError::InvalidTarget(format!("Service name '{service_name}' contains invalid characters.")));
    }
    if CRITICAL_SERVICE_NAMES.iter().any(|n| *n == service_name.to_ascii_lowercase()) {
        return Err(RemediationError::ServiceNotFound(format!("Refusing to touch OS-critical service '{service_name}'.")));
    }
    Ok(())
}

/// Thin wrapper dispatching to `ssh_key_rotation::rotate_in_place` — the
/// synchronous rotation logic does small, bounded file I/O, so no
/// `spawn_blocking` is used, matching `restore_file`'s pattern. No
/// additional validation here — `rotate_in_place`/`validate_target`
/// already refuse every invalid case.
pub async fn rotate_key(
    authorized_keys_path: &str,
    fingerprint: &str,
) -> Result<ssh_key_rotation::RotationOutcome, RemediationError> {
    ssh_key_rotation::rotate_in_place(authorized_keys_path, fingerprint)
}

/// Thin wrapper dispatching to `ssh_key_rotation::rollback_rotation` — the
/// rollback counterpart of `rotate_key`.
pub async fn rotate_key_rollback(authorized_keys_path: &str) -> Result<(), RemediationError> {
    ssh_key_rotation::rollback_rotation(authorized_keys_path)
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── kill_process ──────────────────────────────────────────────────────
    #[tokio::test]
    async fn kill_process_empty_target() {
        let result = kill_process("").await;
        assert!(matches!(result, Err(RemediationError::InvalidTarget(_))));
    }

    #[tokio::test]
    async fn kill_process_refuses_pid_zero_and_one() {
        assert!(matches!(kill_process("0").await, Err(RemediationError::InvalidTarget(_))));
        assert!(matches!(kill_process("1").await, Err(RemediationError::InvalidTarget(_))));
    }

    #[tokio::test]
    async fn kill_process_refuses_own_pid() {
        let own = std::process::id().to_string();
        assert!(matches!(kill_process(&own).await, Err(RemediationError::InvalidTarget(_))));
    }

    #[tokio::test]
    async fn kill_process_refuses_critical_name() {
        let result = kill_process("systemd").await;
        assert!(matches!(result, Err(RemediationError::InvalidTarget(_))));
    }

    #[tokio::test]
    async fn kill_process_nonexistent_name() {
        let result = kill_process("definitely_not_a_real_process_xyz123").await;
        assert!(matches!(result, Err(RemediationError::ProcessNotFound(_))));
    }

    #[tokio::test]
    async fn kill_process_nonexistent_pid() {
        // A PID astronomically unlikely to exist on any real system.
        let result = kill_process("4000000000").await;
        assert!(matches!(result, Err(RemediationError::ProcessNotFound(_))));
    }

    // ── restore_file ──────────────────────────────────────────────────────
    #[tokio::test]
    async fn restore_file_empty_path() {
        let result = restore_file("", None).await;
        assert!(matches!(result, Err(RemediationError::InvalidPath(_))));
    }

    #[tokio::test]
    async fn restore_file_refuses_without_backup() {
        let result = restore_file("/tmp/some_target.txt", None).await;
        assert!(matches!(result, Err(RemediationError::OperationFailed(_))));
    }

    #[tokio::test]
    async fn restore_file_missing_backup_source() {
        let result = restore_file("/tmp/some_target.txt", Some("/path/to/nonexistent/backup")).await;
        assert!(matches!(result, Err(RemediationError::FileNotFound(_))));
    }

    #[tokio::test]
    async fn restore_file_copies_from_real_backup() {
        let dir = std::env::temp_dir();
        let target = dir.join(format!("omni_restore_target_{}.txt", std::process::id()));
        let backup = dir.join(format!("omni_restore_backup_{}.txt", std::process::id()));
        std::fs::write(&backup, b"known-good content").unwrap();

        let result = restore_file(target.to_str().unwrap(), Some(backup.to_str().unwrap())).await;
        assert!(result.is_ok());
        assert_eq!(std::fs::read_to_string(&target).unwrap(), "known-good content");

        let _ = std::fs::remove_file(&target);
        let _ = std::fs::remove_file(&backup);
    }

    // ── block_ip / unblock_ip ────────────────────────────────────────────
    #[tokio::test]
    async fn block_ip_empty() {
        assert!(matches!(block_ip("").await, Err(RemediationError::InvalidIpAddress(_))));
    }

    #[tokio::test]
    async fn block_ip_invalid_format() {
        assert!(matches!(block_ip("not-an-ip").await, Err(RemediationError::InvalidIpAddress(_))));
    }

    #[tokio::test]
    async fn block_ip_valid_format_stubbed_success() {
        // Real Command execution is stubbed out under #[cfg(test)] — this
        // only proves validation passes through to the (stubbed) dispatch.
        assert!(block_ip("192.0.2.10").await.is_ok());
    }

    #[tokio::test]
    async fn unblock_ip_invalid_format() {
        assert!(matches!(unblock_ip("not-an-ip").await, Err(RemediationError::InvalidIpAddress(_))));
    }

    // ── disable_service / enable_service ────────────────────────────────
    #[tokio::test]
    async fn disable_service_empty_name() {
        assert!(matches!(disable_service("").await, Err(RemediationError::InvalidTarget(_))));
    }

    #[tokio::test]
    async fn disable_service_refuses_critical() {
        assert!(matches!(disable_service("sshd").await, Err(RemediationError::ServiceNotFound(_))));
    }

    #[tokio::test]
    async fn disable_service_refuses_invalid_chars() {
        assert!(matches!(disable_service("evil; rm -rf /").await, Err(RemediationError::InvalidTarget(_))));
    }

    #[tokio::test]
    async fn disable_service_valid_name_stubbed_success() {
        assert!(disable_service("some-app.service").await.is_ok());
    }

    #[tokio::test]
    async fn enable_service_empty_name() {
        assert!(matches!(enable_service("").await, Err(RemediationError::InvalidTarget(_))));
    }

    #[tokio::test]
    async fn enable_service_valid_name_stubbed_success() {
        assert!(enable_service("some-app.service").await.is_ok());
    }
}
