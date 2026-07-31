use std::{net::UdpSocket, time::Duration};
use reqwest::Client;
use crate::{config::Config, olog};

/// Build the shared HTTP client with TLS verification driven by config.
///
/// Secure by default: certificates are fully validated against the system trust
/// store. A private/internal CA can be trusted via `ca_cert_path` without weakening
/// verification. `verify_tls: false` disables validation entirely — dev-only, and the
/// agent logs a loud warning so an insecure production deployment is never silent.
pub fn build_client(cfg: &Config) -> Client {
    let mut builder = Client::builder()
        .timeout(Duration::from_secs(10))
        .connect_timeout(Duration::from_secs(5));

    if let Some(path) = cfg.ca_cert_path.as_deref().filter(|p| !p.is_empty()) {
        match std::fs::read(path).ok().and_then(|pem| reqwest::Certificate::from_pem(&pem).ok()) {
            Some(cert) => {
                builder = builder.add_root_certificate(cert);
                olog!("[tls] trusting extra CA certificate: {}", path);
            }
            None => olog!("[tls] WARNING: could not load ca_cert_path '{}' — falling back to system roots", path),
        }
    }

    if !cfg.verify_tls {
        olog!("[tls] WARNING: certificate verification DISABLED (verify_tls=false). \
               Connections are exposed to man-in-the-middle. Use only for local dev.");
        builder = builder.danger_accept_invalid_certs(true);
    }

    builder.build().expect("HTTP client")
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
/// Outcome of a PowerShell invocation, distinguishing "the process never ran"
/// from "it ran and exited". Lets callers that must report an action's success
/// (EDR/SOAR handlers) tell a genuine failure from empty-but-successful output.
enum PsOutcome {
    /// Process spawned and exited. `status_ok` reflects the exit code.
    Ran { status_ok: bool, output: String },
    /// Spawn failed (e.g. PowerShell absent / non-Windows) or timed out.
    Failed(String),
}

async fn run_ps_raw(cmd: &str) -> PsOutcome {
    let fut = tokio::process::Command::new(PS_EXE)
        .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cmd])
        .output();
    match tokio::time::timeout(Duration::from_secs(30), fut).await {
        Ok(Ok(o)) => {
            let stdout = String::from_utf8_lossy(&o.stdout).trim().to_string();
            let stderr = String::from_utf8_lossy(&o.stderr).trim().to_string();
            let output = if stdout.is_empty() && !stderr.is_empty() { stderr } else { stdout };
            PsOutcome::Ran { status_ok: o.status.success(), output }
        }
        Ok(Err(e)) => PsOutcome::Failed(format!("PowerShell spawn failed: {}", e)),
        Err(_)     => PsOutcome::Failed("PowerShell command timed out after 30s".to_string()),
    }
}

pub async fn run_ps(cmd: &str) -> String {
    // Preserves historical behavior: return output whenever the process ran
    // (regardless of exit code); empty string only when it never ran.
    match run_ps_raw(cmd).await {
        PsOutcome::Ran { output, .. } => output,
        PsOutcome::Failed(_) => String::new(),
    }
}

/// Like [`run_ps`] but surfaces whether the command actually executed and succeeded.
/// `Ok(output)` — PowerShell spawned and exited 0. `Err(reason)` — spawn failed
/// (PowerShell missing / non-Windows), timed out, or exited non-zero. Use this for
/// response actions whose reported `success` must reflect reality.
pub async fn run_ps_checked(cmd: &str) -> Result<String, String> {
    match run_ps_raw(cmd).await {
        PsOutcome::Ran { status_ok: true, output } => Ok(output),
        PsOutcome::Ran { status_ok: false, output } => {
            Err(if output.is_empty() { "PowerShell command exited non-zero".to_string() } else { output })
        }
        PsOutcome::Failed(reason) => Err(reason),
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
