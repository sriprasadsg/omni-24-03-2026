use super::Capability;
use serde_json::{json, Value};
use sysinfo::System;

const CURRENT_VERSION: &str = "2.0.3";

pub struct AgentUpdateCapability;

impl Capability for AgentUpdateCapability {
    fn id(&self) -> &'static str { "agent_update" }
    fn name(&self) -> &'static str { "Agent Update" }

    fn collect(&self, _sys: &System) -> Value {
        // Passive: just report current version. Version check/update is triggered via instruction.
        json!({
            "current_version": CURRENT_VERSION,
            "status": "ready",
            "timestamp": chrono::Utc::now().to_rfc3339(),
        })
    }
}

struct UpdateInfo {
    version: String,
    url: Option<String>,
    filename: Option<String>,
}

fn fetch_update_info(cfg: &crate::config::Config) -> Option<UpdateInfo> {
    let url = format!(
        "{}/api/agent-updates/latest?platform=windows",
        cfg.api_base_url.trim_end_matches('/')
    );
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .ok()?;
    let resp: serde_json::Value = client
        .get(&url)
        .bearer_auth(&cfg.agent_token)
        .send()
        .ok()?
        .json()
        .ok()?;
    Some(UpdateInfo {
        version: resp.get("version")?.as_str()?.to_string(),
        url: resp.get("url").and_then(|v| v.as_str()).map(|s| s.to_string()),
        filename: resp.get("filename").and_then(|v| v.as_str()).map(|s| s.to_string()),
    })
}

/// Check for an update and perform self-replacement if a newer version exists.
/// Creates a bat script that stops the service, replaces the binary, and restarts.
/// Designed to be called via `tokio::task::spawn_blocking` from an async instruction handler.
pub fn apply_update(cfg: &crate::config::Config) -> Result<String, String> {
    let info = fetch_update_info(cfg).ok_or("Could not reach update server")?;

    if info.version == CURRENT_VERSION {
        return Ok(format!("Agent is already up to date ({})", CURRENT_VERSION));
    }
    let download_url = info.url.ok_or("No download URL in update response")?;
    let _filename = info.filename.unwrap_or_else(|| "omni-agent.exe".to_string());

    log::info!("Update available: {} -> {}", CURRENT_VERSION, info.version);

    // Download new binary
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(300))
        .build()
        .map_err(|e| e.to_string())?;

    let bytes = client
        .get(&download_url)
        .bearer_auth(&cfg.agent_token)
        .send()
        .and_then(|r| r.bytes())
        .map_err(|e| format!("Download failed: {}", e))?;

    let exe_path = std::env::current_exe().map_err(|e| e.to_string())?;
    let new_exe = exe_path.with_extension("new.exe");
    std::fs::write(&new_exe, &bytes).map_err(|e| format!("Write failed: {}", e))?;

    // Update script: wait → find OUR service by binary path → stop → replace →
    // start → self-delete. Resolving via Win32_Service.PathName (rather than a
    // hardcoded/guessed name) is correct under either install path — the
    // download installer registers "OmniAgentRust" while service.rs uses
    // "OmniAgent". The whole sequence runs in one PowerShell process so the
    // resolved name persists across stop/start.
    let script_dir = exe_path.parent().unwrap_or(std::path::Path::new("."));
    let script_path = script_dir.join("_omni_agent_update.ps1");
    let exe_str = exe_path.to_string_lossy();
    let new_exe_str = new_exe.to_string_lossy();
    // Single-quoted PS literals avoid backslash escaping; install paths contain
    // no single quotes. A doubled '' escapes a literal quote defensively.
    let exe_lit = exe_str.replace('\'', "''");
    let new_exe_lit = new_exe_str.replace('\'', "''");
    let ps = format!(
        "Start-Sleep -Seconds 5\r\n\
         $exe = '{exe_lit}'\r\n\
         $svc = Get-CimInstance Win32_Service | Where-Object {{ $_.PathName -like ('*' + $exe + '*') }} | Select-Object -First 1 -ExpandProperty Name\r\n\
         if ($svc) {{ Stop-Service -Name $svc -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2 }}\r\n\
         Move-Item -Path '{new_exe_lit}' -Destination '{exe_lit}' -Force\r\n\
         if ($svc) {{ Start-Service -Name $svc -ErrorAction SilentlyContinue }}\r\n\
         Remove-Item -Path $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue\r\n"
    );
    std::fs::write(&script_path, ps).map_err(|e| e.to_string())?;

    // Detach via `start` so stopping the service does not kill the updater
    // mid-swap (the updater must outlive the process it is replacing).
    std::process::Command::new("cmd")
        .args([
            "/c", "start", "", "/b",
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden", "-File", script_path.to_str().unwrap_or(""),
        ])
        .spawn()
        .map_err(|e| e.to_string())?;

    Ok(format!(
        "Update to {} initiated — service will restart in ~5 seconds.",
        info.version
    ))
}
