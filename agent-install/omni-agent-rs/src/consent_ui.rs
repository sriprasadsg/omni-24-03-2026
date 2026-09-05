//! Session-0 consent dialog and persistent stop-control bar for remote control.
//!
//! The agent runs as a Session-0 service and cannot draw an interactive window
//! itself. This module spawns a PowerShell WinForms consent dialog *into the
//! active console session* using `CreateProcessAsUserW` with a token obtained
//! from `WTSQueryUserToken(WTSGetActiveConsoleSessionId())`. The endpoint user
//! must click Accept before the agent replays any input (D-01), and sees a
//! persistent one-click stop-control bar for as long as control lasts (D-09).
//!
//! The requester identity (name/email/tenant) is untrusted input that reaches
//! this process through a backend payload, so it travels to the PowerShell
//! script ONLY through a per-session JSON config file read with
//! `ConvertFrom-Json` (T-74-08) — never interpolated into the script text or
//! the command line.
//!
//! `winapi` (frozen 0.3 API) is used rather than the `windows` crate to keep
//! the FFI surface stable, mirroring `chat_ui.rs`. The two embedded PowerShell
//! constants live in `consent_scripts.rs` (500-line source-cap split).

use std::collections::HashSet;
use std::sync::{Mutex, OnceLock};

#[cfg(windows)]
use crate::consent_scripts::{CONSENT_UI_PS, STOP_BAR_PS};

/// Session IDs that currently have a consent dialog or stop bar process running.
fn active() -> &'static Mutex<HashSet<String>> {
    static ACTIVE: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();
    ACTIVE.get_or_init(|| Mutex::new(HashSet::new()))
}

fn mark_active(session_id: &str) {
    if let Ok(mut s) = active().lock() {
        s.insert(session_id.to_string());
    }
}

fn mark_closed(session_id: &str) {
    if let Ok(mut s) = active().lock() {
        s.remove(session_id);
    }
}

/// The endpoint user's decision about a control request.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConsentDecision {
    Accept,
    Decline,
    Timeout,
}

/// Why the consent dialog could not be shown (or the request otherwise failed).
#[derive(Debug)]
pub enum ConsentError {
    /// No interactive console session exists (WTSGetActiveConsoleSessionId
    /// returned 0xFFFF_FFFF) — D-02's refusal condition.
    NoInteractiveSession,
    /// The dialog/bar process could not be spawned.
    SpawnFailed(String),
}

/// Directory that holds the per-session config, decision file, and sentinels.
#[cfg(windows)]
pub fn data_dir() -> std::path::PathBuf {
    let base = std::env::var("ProgramData").unwrap_or_else(|_| r"C:\ProgramData".to_string());
    std::path::Path::new(&base).join("OmniAgent")
}

/// Path where the consent dialog script is materialized.
#[cfg(windows)]
fn script_path() -> std::path::PathBuf {
    data_dir().join("consent_ui.ps1")
}

/// Write the embedded consent-dialog script to ProgramData. Idempotent.
#[cfg(windows)]
fn ensure_script_installed() -> Result<std::path::PathBuf, ConsentError> {
    let dir = data_dir();
    std::fs::create_dir_all(&dir)
        .map_err(|e| ConsentError::SpawnFailed(format!("create {}: {e}", dir.display())))?;
    let p = script_path();
    std::fs::write(&p, CONSENT_UI_PS)
        .map_err(|e| ConsentError::SpawnFailed(format!("write consent script: {e}")))?;
    Ok(p)
}

/// Path where the stop-control bar script is materialized.
#[cfg(windows)]
fn stop_bar_script_path() -> std::path::PathBuf {
    data_dir().join("consent_stop_bar.ps1")
}

/// Write the embedded stop-bar script to ProgramData. Idempotent.
#[cfg(windows)]
fn ensure_stop_bar_installed() -> Result<std::path::PathBuf, ConsentError> {
    let dir = data_dir();
    std::fs::create_dir_all(&dir)
        .map_err(|e| ConsentError::SpawnFailed(format!("create {}: {e}", dir.display())))?;
    let p = stop_bar_script_path();
    std::fs::write(&p, STOP_BAR_PS)
        .map_err(|e| ConsentError::SpawnFailed(format!("write stop bar script: {e}")))?;
    Ok(p)
}

/// Parse the decision file body into a `ConsentDecision`. Only the exact three
/// literal words the script writes parse; anything else (a stale, partial, or
/// tampered file) returns `None` and can never be read as Accept (T-74-17).
pub fn parse_decision(body: &str) -> Option<ConsentDecision> {
    match body.trim() {
        "accept" => Some(ConsentDecision::Accept),
        "decline" => Some(ConsentDecision::Decline),
        "timeout" => Some(ConsentDecision::Timeout),
        _ => None,
    }
}

/// Build the decision-file body for a decision (kept for tests/consistency with
/// the three literal words the script writes).
pub fn decision_payload(decision: &ConsentDecision) -> &'static str {
    match decision {
        ConsentDecision::Accept => "accept",
        ConsentDecision::Decline => "decline",
        ConsentDecision::Timeout => "timeout",
    }
}

/// Serialize the requester identity config JSON for the consent dialog.
#[cfg(windows)]
fn build_consent_config(
    session_id: &str,
    requester_name: &str,
    requester_email: &str,
    tenant_name: &str,
    timeout_secs: u64,
) -> Vec<u8> {
    serde_json::json!({
        "session_id": session_id,
        "requester_name": requester_name,
        "requester_email": requester_email,
        "tenant_name": tenant_name,
        "timeout_secs": timeout_secs,
    })
    .to_string()
    .into_bytes()
}

/// Ask the interactive endpoint user for consent to control their desktop.
///
/// Blocks (synchronously) until the user chooses or the timeout elapses. On the
/// no-interactive-session sentinel it returns `ConsentError::NoInteractiveSession`
/// immediately, before attempting any spawn (D-02). Consumes both the config and
/// the decision file before returning so no residue can be replayed (T-74-17,
/// D-04).
#[cfg(windows)]
pub fn request_consent(
    session_id: &str,
    requester_name: &str,
    requester_email: &str,
    tenant_name: &str,
    timeout_secs: u64,
) -> Result<ConsentDecision, ConsentError> {
    unsafe {
        if win::WTSGetActiveConsoleSessionId() == 0xFFFF_FFFF {
            return Err(ConsentError::NoInteractiveSession);
        }
    }

    let dir = data_dir();
    let script_path = ensure_script_installed()?;

    let cfg = build_consent_config(session_id, requester_name, requester_email, tenant_name, timeout_secs);
    let cfg_path = dir.join(format!("consent_{session_id}.json"));
    std::fs::write(&cfg_path, cfg)
        .map_err(|e| ConsentError::SpawnFailed(format!("write consent config: {e}")))?;

    let cmdline = format!(
        "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"{}\" \"{}\"",
        script_path.display(),
        cfg_path.display()
    );

    if let Err(e) = win::spawn_in_active_session(&cmdline) {
        let _ = std::fs::remove_file(&cfg_path);
        return Err(e);
    }
    mark_active(session_id);

    // Poll the decision file until it appears or the timeout elapses. The script
    // writes one of the three literal words on every exit path.
    let decision_file = dir.join(format!("consent_{session_id}.decision"));
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(timeout_secs);
    let mut decision = ConsentDecision::Timeout;
    while std::time::Instant::now() < deadline {
        if let Ok(body) = std::fs::read_to_string(&decision_file) {
            if let Some(d) = parse_decision(&body) {
                decision = d;
                break;
            }
            // Unrecognised body — keep polling until the deadline; never Accept.
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }

    // Cleanup on every path (T-74-17 / D-04): no residue to replay next session.
    let _ = std::fs::remove_file(&decision_file);
    let _ = std::fs::remove_file(&cfg_path);
    mark_closed(session_id);
    Ok(decision)
}

/// Show the persistent stop-control bar naming the controlling admin.
#[cfg(windows)]
pub fn show_stop_bar(session_id: &str, requester_name: &str) -> Result<(), ConsentError> {
    let dir = data_dir();
    let script_path = ensure_stop_bar_installed()?;

    let cfg = serde_json::json!({
        "session_id": session_id,
        "requester_name": requester_name,
    })
    .to_string()
    .into_bytes();
    let cfg_path = dir.join(format!("consent_{session_id}_bar.json"));
    std::fs::write(&cfg_path, cfg)
        .map_err(|e| ConsentError::SpawnFailed(format!("write stop bar config: {e}")))?;

    let cmdline = format!(
        "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"{}\" \"{}\"",
        script_path.display(),
        cfg_path.display()
    );

    if let Err(e) = win::spawn_in_active_session(&cmdline) {
        let _ = std::fs::remove_file(&cfg_path);
        return Err(e);
    }
    mark_active(session_id);
    Ok(())
}

/// Whether the endpoint user has clicked Stop Control (`stop_{sid}.stop` exists).
pub fn stop_requested(session_id: &str) -> bool {
    #[cfg(windows)]
    {
        data_dir().join(format!("stop_{session_id}.stop")).exists()
    }
    #[cfg(not(windows))]
    {
        let _ = session_id;
        false
    }
}

/// Hide the stop-control bar and clear the session's sentinels/bookkeeping.
#[cfg(windows)]
pub fn hide_stop_bar(session_id: &str) -> Result<(), ConsentError> {
    let dir = data_dir();
    let _ = std::fs::create_dir_all(&dir);
    let close = dir.join(format!("stop_{session_id}.close"));
    std::fs::write(&close, b"close")
        .map_err(|e| ConsentError::SpawnFailed(format!("write stop close sentinel: {e}")))?;
    let _ = std::fs::remove_file(dir.join(format!("stop_{session_id}.stop")));
    let _ = std::fs::remove_file(dir.join(format!("consent_{session_id}_bar.json")));
    mark_closed(session_id);
    Ok(())
}

#[cfg(not(windows))]
pub fn request_consent(
    _session_id: &str,
    _requester_name: &str,
    _requester_email: &str,
    _tenant_name: &str,
    _timeout_secs: u64,
) -> Result<ConsentDecision, ConsentError> {
    Err(ConsentError::NoInteractiveSession)
}

#[cfg(not(windows))]
pub fn show_stop_bar(_session_id: &str, _requester_name: &str) -> Result<(), ConsentError> {
    Err(ConsentError::NoInteractiveSession)
}

#[cfg(not(windows))]
pub fn hide_stop_bar(_session_id: &str) -> Result<(), ConsentError> {
    Ok(())
}

/// Construct the stop sentinel filename for a session (test helper, platform
/// independent — the Windows path uses the same name).
pub fn stop_sentinel_name(session_id: &str) -> String {
    format!("stop_{session_id}.stop")
}

#[cfg(windows)]
mod win {
    use std::os::windows::ffi::OsStrExt;
    use winapi::shared::minwindef::{DWORD, FALSE, LPVOID};
    use winapi::um::errhandlingapi::GetLastError;
    use winapi::um::handleapi::CloseHandle;
    use winapi::um::processthreadsapi::{CreateProcessAsUserW, PROCESS_INFORMATION, STARTUPINFOW};
    use winapi::um::securitybaseapi::DuplicateTokenEx;
    use winapi::um::userenv::{CreateEnvironmentBlock, DestroyEnvironmentBlock};
    use winapi::um::winbase::{WTSGetActiveConsoleSessionId, CREATE_NO_WINDOW, CREATE_UNICODE_ENVIRONMENT};
    use winapi::um::winnt::{
        SecurityImpersonation, TokenPrimary, HANDLE, MAXIMUM_ALLOWED,
    };
    use winapi::um::wtsapi32::WTSQueryUserToken;

    fn wide(s: &str) -> Vec<u16> {
        std::ffi::OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
    }

    /// Launch `cmdline` as the interactive console user on winsta0\default.
    pub fn spawn_in_active_session(cmdline: &str) -> Result<(), crate::consent_ui::ConsentError> {
        use crate::consent_ui::ConsentError;
        unsafe {
            let session = WTSGetActiveConsoleSessionId();
            if session == 0xFFFF_FFFF {
                return Err(ConsentError::NoInteractiveSession);
            }

            let mut user_token: HANDLE = std::ptr::null_mut();
            if WTSQueryUserToken(session, &mut user_token) == 0 {
                return Err(ConsentError::SpawnFailed(format!(
                    "WTSQueryUserToken failed ({})", GetLastError()
                )));
            }

            let mut primary: HANDLE = std::ptr::null_mut();
            let dup = DuplicateTokenEx(
                user_token,
                MAXIMUM_ALLOWED,
                std::ptr::null_mut(),
                SecurityImpersonation,
                TokenPrimary,
                &mut primary,
            );
            CloseHandle(user_token);
            if dup == 0 {
                return Err(ConsentError::SpawnFailed(format!(
                    "DuplicateTokenEx failed ({})", GetLastError()
                )));
            }

            let mut env: LPVOID = std::ptr::null_mut();
            let have_env = CreateEnvironmentBlock(&mut env, primary, FALSE) != 0;

            let mut si: STARTUPINFOW = std::mem::zeroed();
            si.cb = std::mem::size_of::<STARTUPINFOW>() as DWORD;
            let mut desktop = wide(r"winsta0\default");
            si.lpDesktop = desktop.as_mut_ptr();

            let mut pi: PROCESS_INFORMATION = std::mem::zeroed();
            let mut cmd = wide(cmdline);
            let flags = CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW;

            let ok = CreateProcessAsUserW(
                primary,
                std::ptr::null(),
                cmd.as_mut_ptr(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                FALSE,
                flags,
                if have_env { env } else { std::ptr::null_mut() },
                std::ptr::null(),
                &mut si,
                &mut pi,
            );
            let err = GetLastError();

            if have_env {
                DestroyEnvironmentBlock(env);
            }
            CloseHandle(primary);

            if ok == 0 {
                return Err(ConsentError::SpawnFailed(format!(
                    "CreateProcessAsUserW failed ({err})"
                )));
            }
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn config_serializes_five_expected_keys() {
        // D-03: the identity config carries all five keys the script reads.
        #[cfg(windows)]
        {
            let cfg = String::from_utf8(build_consent_config("s1", "Ada", "ada@c", "Acme", 60))
                .unwrap();
            let v: serde_json::Value = serde_json::from_str(&cfg).unwrap();
            assert_eq!(v["session_id"], "s1");
            assert_eq!(v["requester_name"], "Ada");
            assert_eq!(v["requester_email"], "ada@c");
            assert_eq!(v["tenant_name"], "Acme");
            assert_eq!(v["timeout_secs"], 60);
        }
        #[cfg(not(windows))]
        {
            assert!(true, "config serialization is Windows-only");
        }
    }

    #[test]
    fn accept_body_parses_to_accept() {
        assert_eq!(parse_decision("accept"), Some(ConsentDecision::Accept));
    }

    #[test]
    fn decline_body_parses_to_decline() {
        assert_eq!(parse_decision("decline"), Some(ConsentDecision::Decline));
    }

    #[test]
    fn timeout_body_parses_to_timeout() {
        assert_eq!(parse_decision("timeout"), Some(ConsentDecision::Timeout));
    }

    #[test]
    fn unknown_decision_body_does_not_parse_to_accept() {
        // T-74-17 / D-04: a stale, partial, or tampered file never reads as Accept.
        for bad in ["", "accept\nignore", "ACCEPT", "maybe", " decline", "{\"accept\":true}", "1"] {
            assert_ne!(parse_decision(bad), Some(ConsentDecision::Accept), "body: {bad:?}");
        }
        // The three valid bodies still round-trip exactly.
        assert_eq!(parse_decision("accept"), Some(ConsentDecision::Accept));
        assert_eq!(parse_decision("decline"), Some(ConsentDecision::Decline));
        assert_eq!(parse_decision("timeout"), Some(ConsentDecision::Timeout));
    }

    #[test]
    fn stop_sentinel_name_construction() {
        // D-09: the stop sentinel the bar writes matches what stop_requested reads.
        assert_eq!(stop_sentinel_name("abc-123"), "stop_abc-123.stop");
        assert_eq!(stop_sentinel_name(""), "stop_.stop");
    }
}
