//! Endpoint tray helper materialization.
//!
//! The tray UI runs in the interactive user session (a logon scheduled task
//! launches it) because the service in session 0 cannot show a tray icon. The
//! agent — running as SYSTEM — writes the tray script to ProgramData at startup
//! so the logon task always has a current copy, and publishes a user-readable
//! `tray-config.json` (the locked `config.yaml` is SYSTEM/Admin-only).

#[cfg(windows)]
const TRAY_PS: &str = include_str!("../scripts/tray_icon.ps1");

/// The windowless launcher the logon task runs (wscript → hidden powershell).
#[cfg(windows)]
const TRAY_VBS: &str = include_str!("../scripts/tray_launch.vbs");

/// Path where the tray script is materialized.
#[cfg(windows)]
pub fn script_path() -> std::path::PathBuf {
    crate::chat_ui::data_dir().join("tray_icon.ps1")
}

/// Path where the windowless VBScript launcher is materialized.
#[cfg(windows)]
pub fn launcher_path() -> std::path::PathBuf {
    crate::chat_ui::data_dir().join("tray_launch.vbs")
}

/// Write the embedded tray script + windowless launcher to ProgramData. Idempotent.
#[cfg(windows)]
pub fn ensure_script_installed() -> Result<std::path::PathBuf, String> {
    let dir = crate::chat_ui::data_dir();
    std::fs::create_dir_all(&dir).map_err(|e| format!("create {}: {e}", dir.display()))?;
    let p = script_path();
    std::fs::write(&p, TRAY_PS).map_err(|e| format!("write tray script: {e}"))?;
    std::fs::write(launcher_path(), TRAY_VBS).map_err(|e| format!("write tray launcher: {e}"))?;
    Ok(p)
}

#[cfg(not(windows))]
pub fn ensure_script_installed() -> Result<std::path::PathBuf, String> {
    Err("tray is Windows-only".to_string())
}
