use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Deserializes a YAML null or missing value as an empty String.
/// Without this, serde_yaml converts `null` to the literal string "null".
fn deser_nullable_str<'de, D: serde::Deserializer<'de>>(d: D) -> Result<String, D::Error> {
    let opt = Option::<String>::deserialize(d)?;
    Ok(opt.unwrap_or_default())
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct Config {
    pub api_base_url: String,
    #[serde(default, deserialize_with = "deser_nullable_str")]
    pub tenant_id: String,
    #[serde(default, deserialize_with = "deser_nullable_str")]
    pub agent_id: String,
    #[serde(default, deserialize_with = "deser_nullable_str")]
    pub agent_token: String,
    #[serde(default, deserialize_with = "deser_nullable_str")]
    pub registration_key: String,
    #[serde(default = "default_interval")]
    pub interval_seconds: u64,
    #[serde(default = "default_max_cpu")]
    pub max_cpu_percent: f32,
    #[serde(default)]
    pub agentic_mode_enabled: bool,
}

fn default_interval() -> u64 { 30 }
fn default_max_cpu() -> f32 { 20.0 }

pub fn config_path() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.join("config.yaml")))
        .unwrap_or_else(|| PathBuf::from("config.yaml"))
}

pub fn load() -> Result<Config, Box<dyn std::error::Error>> {
    let path = config_path();
    let text = std::fs::read_to_string(&path)
        .map_err(|e| format!("Cannot read {}: {}", path.display(), e))?;
    let cfg: Config = serde_yaml::from_str(&text)?;
    Ok(cfg)
}

pub fn save(cfg: &Config) -> Result<(), Box<dyn std::error::Error>> {
    let path = config_path();
    let text = serde_yaml::to_string(cfg)?;
    std::fs::write(&path, text)?;
    Ok(())
}

/// Publish a user-readable tray-config.json for the interactive-session tray
/// helper. The service's own `config.yaml` is locked to SYSTEM/Administrators
/// (installer WR-04), so the tray — running as the logged-on user — reads this
/// instead. ProgramData's default ACL grants Users read, which is what the tray
/// needs; the agent token is intentionally exposed to the local user here, the
/// same trust boundary already used for the chat-window session files.
#[cfg(windows)]
pub fn write_tray_config(cfg: &Config) -> Result<(), Box<dyn std::error::Error>> {
    let base = std::env::var("ProgramData").unwrap_or_else(|_| r"C:\ProgramData".to_string());
    let dir = std::path::Path::new(&base).join("OmniAgent");
    std::fs::create_dir_all(&dir)?;
    let chat_ui = dir.join("chat_ui.ps1");
    let tray = serde_json::json!({
        "api_base_url": cfg.api_base_url.trim_end_matches('/'),
        "agent_id": cfg.agent_id,
        "agent_token": cfg.agent_token,
        "chat_ui": chat_ui.to_string_lossy(),
    });
    std::fs::write(dir.join("tray-config.json"), serde_json::to_vec_pretty(&tray)?)?;
    Ok(())
}

#[cfg(not(windows))]
pub fn write_tray_config(_cfg: &Config) -> Result<(), Box<dyn std::error::Error>> {
    Ok(())
}
