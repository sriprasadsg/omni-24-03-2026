use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Deserializes a YAML null or missing value as an empty String.
/// Without this, serde_norway converts `null` to the literal string "null".
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
    /// Per-agent enrollment secret issued by /api/agents/register. The backend
    /// requires it to re-enroll this hostname, so the shared registration key
    /// alone cannot take over an enrolled agent.
    #[serde(default, deserialize_with = "deser_nullable_str")]
    pub agent_secret: String,
    #[serde(default = "default_interval")]
    pub interval_seconds: u64,
    #[serde(default = "default_max_cpu")]
    pub max_cpu_percent: f32,
    #[serde(default)]
    pub agentic_mode_enabled: bool,
    /// Legacy: skip certificate checks for the platform. Ignored when
    /// server_ca_cert is set; installers no longer write `true`.
    #[serde(default)]
    pub accept_invalid_certs: bool,
    /// The platform's TLS certificate (PEM), shipped by the installer. When
    /// set, platform connections trust this certificate only (see tls.rs).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub server_ca_cert: Option<String>,
    #[serde(default = "default_fim_paths")]
    pub fim_paths: Vec<String>,
    /// Issued by the platform with heartbeat responses: a salted hash of this
    /// agent's uninstall code (never the code itself). See uninstall.rs.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub uninstall_protection: Option<UninstallProtection>,
    /// The capabilities this agent's tenant lets it use, from the last heartbeat reply.
    /// `None` until the platform says; then collectors outside the list do not run.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub enabled_capabilities: Option<Vec<String>>,
}

#[derive(Debug, Deserialize, Serialize, Clone, PartialEq)]
pub struct UninstallProtection {
    pub version: u64,
    pub salt: String,
    pub iterations: u32,
    pub hash: String,
}

fn default_interval() -> u64 { 30 }
fn default_max_cpu() -> f32 { 20.0 }
fn default_fim_paths() -> Vec<String> {
    #[cfg(windows)]
    return vec![r"C:\Windows\System32\drivers\etc".to_string()];
    #[cfg(not(windows))]
    return vec![
        "/etc".to_string(),
        "/usr/bin".to_string(),
        "/usr/sbin".to_string(),
        format!("{}/.ssh", std::env::var("HOME").unwrap_or_default()),
    ];
}

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
    let cfg: Config = serde_norway::from_str(&text)?;
    Ok(cfg)
}

/// A reinstall writes a fresh config.yaml (no agent id, token or secret); the
/// installer keeps the old one as config.yaml.prev. Carry this machine's
/// enrollment over, or the platform answers 409: re-enrolling a known host
/// needs its per-agent secret. Only from a config for the same platform.
pub fn adopt_previous_identity(cfg: &mut Config) -> bool {
    let prev = config_path().with_extension("yaml.prev");
    let adopted = adopt_from(cfg, &prev);
    let _ = std::fs::remove_file(&prev);
    adopted
}

fn adopt_from(cfg: &mut Config, prev_path: &std::path::Path) -> bool {
    let Some(prev) = std::fs::read_to_string(prev_path)
        .ok()
        .and_then(|t| serde_norway::from_str::<Config>(&t).ok())
    else {
        return false;
    };
    let same_platform = prev.api_base_url.trim_end_matches('/') == cfg.api_base_url.trim_end_matches('/');
    if !same_platform || !cfg.agent_secret.is_empty() || prev.agent_secret.is_empty() {
        return false;
    }
    cfg.agent_id = prev.agent_id;
    cfg.agent_token = prev.agent_token;
    cfg.agent_secret = prev.agent_secret;
    if cfg.uninstall_protection.is_none() {
        cfg.uninstall_protection = prev.uninstall_protection;
    }
    true
}

#[cfg(test)]
mod identity_tests {
    use super::*;

    fn cfg(url: &str, secret: &str) -> Config {
        serde_norway::from_str(&format!(
            "api_base_url: {url}\nagent_id: agent-old\nagent_token: tok-old\nagent_secret: '{secret}'\n"
        ))
        .unwrap()
    }

    fn prev_file(name: &str, c: &Config) -> std::path::PathBuf {
        let p = std::env::temp_dir().join(format!("omni-prev-{name}-{}.yaml", std::process::id()));
        std::fs::write(&p, serde_norway::to_string(c).unwrap()).unwrap();
        p
    }

    #[test]
    fn reinstall_keeps_the_enrollment_of_the_same_platform() {
        let p = prev_file("same", &cfg("https://p.example/", "sec-1"));
        let mut fresh: Config = serde_norway::from_str("api_base_url: https://p.example\n").unwrap();
        assert!(adopt_from(&mut fresh, &p));
        assert_eq!((fresh.agent_id.as_str(), fresh.agent_secret.as_str()), ("agent-old", "sec-1"));
        let _ = std::fs::remove_file(p);
    }

    #[test]
    fn other_platform_or_existing_secret_is_left_alone() {
        let p = prev_file("other", &cfg("https://other.example", "sec-1"));
        let mut fresh: Config = serde_norway::from_str("api_base_url: https://p.example\n").unwrap();
        assert!(!adopt_from(&mut fresh, &p));
        let mut enrolled = cfg("https://other.example", "sec-2");
        assert!(!adopt_from(&mut enrolled, &p));
        assert_eq!(enrolled.agent_secret, "sec-2");
        let _ = std::fs::remove_file(p);
    }
}

pub fn save(cfg: &Config) -> Result<(), Box<dyn std::error::Error>> {
    let path = config_path();
    let text = serde_norway::to_string(cfg)?;
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
        "accept_invalid_certs": cfg.accept_invalid_certs,
        "server_cert_der_b64": crate::tls::pinned_der_base64(),
        // Lets the tray tell the user why it cannot raise tickets or open
        // chats (not enrolled yet / enrollment refused) instead of guessing.
        "enrolled": !cfg.agent_token.is_empty(),
        "enrollment_problem": crate::registration::last_problem(),
    });
    std::fs::write(dir.join("tray-config.json"), serde_json::to_vec_pretty(&tray)?)?;
    Ok(())
}

#[cfg(not(windows))]
pub fn write_tray_config(_cfg: &Config) -> Result<(), Box<dyn std::error::Error>> {
    Ok(())
}
