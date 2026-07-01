use super::Capability;
use serde_json::{json, Value};
use sysinfo::System;

const CURRENT_VERSION: &str = "2.0.0";

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

    // Bat script: wait → stop service → replace binary → start service → self-delete
    let script_dir = exe_path.parent().unwrap_or(std::path::Path::new("."));
    let script_path = script_dir.join("_omni_agent_update.bat");
    let exe_str = exe_path.to_string_lossy();
    let new_exe_str = new_exe.to_string_lossy();
    let bat = format!(
        "@echo off\r\ntimeout /t 5 /nobreak >nul\r\nnet stop OmniAgent >nul 2>&1\r\nmove /y \"{new_exe_str}\" \"{exe_str}\"\r\nnet start OmniAgent >nul 2>&1\r\ndel \"%~f0\"\r\n"
    );
    std::fs::write(&script_path, bat).map_err(|e| e.to_string())?;

    std::process::Command::new("cmd")
        .args(["/c", "start", "/b", "", script_path.to_str().unwrap_or("")])
        .spawn()
        .map_err(|e| e.to_string())?;

    Ok(format!(
        "Update to {} initiated — service will restart in ~5 seconds.",
        info.version
    ))
}
