use std::{net::UdpSocket, time::Duration};
use reqwest::Client;

pub fn build_client() -> Client {
    Client::builder()
        .timeout(Duration::from_secs(10))
        .connect_timeout(Duration::from_secs(5))
        .danger_accept_invalid_certs(true)
        .build()
        .expect("HTTP client")
}

pub fn local_ip() -> String {
    UdpSocket::bind("0.0.0.0:0")
        .and_then(|s| { s.connect("8.8.8.8:80")?; s.local_addr() })
        .map(|a| a.ip().to_string())
        .unwrap_or_else(|_| "unknown".into())
}

/// Full PowerShell executable path — avoids failures in a stripped Windows service PATH.
#[cfg(windows)]
pub const PS_EXE: &str = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe";
#[cfg(not(windows))]
pub const PS_EXE: &str = "powershell";

/// Run a PowerShell command.
/// Returns combined output: stdout when non-empty, stderr as fallback so callers
/// can surface errors that admin-required commands write to stderr.
/// Timeout raised to 30 s to accommodate privileged evidence commands.
pub async fn run_ps(cmd: &str) -> String {
    let fut = tokio::process::Command::new(PS_EXE)
        .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cmd])
        .output();
    match tokio::time::timeout(Duration::from_secs(30), fut).await {
        Ok(Ok(o)) => {
            let stdout = String::from_utf8_lossy(&o.stdout).trim().to_string();
            let stderr = String::from_utf8_lossy(&o.stderr).trim().to_string();
            if stdout.is_empty() && !stderr.is_empty() { stderr } else { stdout }
        }
        _ => String::new(),
    }
}

/// Return true when the current process holds Windows Administrator privileges.
/// Windows services running as SYSTEM or a local Administrator always return true.
pub async fn is_admin() -> bool {
    let out = run_ps(
        "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent())\
         .IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"
    ).await;
    out.trim().eq_ignore_ascii_case("true")
}

/// Run a PowerShell command that requires administrator privileges.
///
/// **Already elevated (Windows Service / SYSTEM):** executes inline — no elevation hop,
/// no UAC prompt, no temp files.  This is the normal path for deployed agents.
///
/// **Not elevated (interactive dev/test):** writes the command to a temp `.ps1` file,
/// re-launches it via `Start-Process -Verb RunAs` (triggers UAC), waits up to 45 s,
/// then reads output from a second temp file.  Returns an "[elevation required]" marker
/// if the user cancels UAC or the process times out.
pub async fn run_ps_admin(cmd: &str) -> String {
    if is_admin().await {
        // Most common path for production services — no overhead.
        return run_ps(cmd).await;
    }

    // Non-admin path: temp-file handoff so Start-Process can redirect output.
    let tmp      = std::env::temp_dir();
    let script   = tmp.join("omni_adm_script.ps1");
    let out_file = tmp.join("omni_adm_out.txt");

    // Wrap the command so the elevated process redirects its own output.
    let out_escaped = out_file.to_string_lossy().replace('\'', "''");
    let wrapped = format!(
        "try {{\n{}\n}} catch {{ $_.Exception.Message }} 2>&1 | Out-File -FilePath '{}' -Encoding UTF8 -Force",
        cmd, out_escaped
    );
    if std::fs::write(&script, wrapped.as_bytes()).is_err() {
        return "[run_ps_admin: failed to write temp script]".to_string();
    }

    let script_quoted = script.to_string_lossy().replace('"', "\\\"");
    let launcher = format!(
        "Start-Process '{}' '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"{}\"' \
         -Verb RunAs -Wait -WindowStyle Hidden 2>$null",
        PS_EXE, script_quoted
    );
    let _ = tokio::time::timeout(Duration::from_secs(45), tokio::process::Command::new(PS_EXE)
        .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", &launcher])
        .output())
        .await;

    let result = std::fs::read_to_string(&out_file)
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|_| "[elevation required — run agent as Administrator or SYSTEM service]".to_string());

    let _ = std::fs::remove_file(&script);
    let _ = std::fs::remove_file(&out_file);
    result
}
