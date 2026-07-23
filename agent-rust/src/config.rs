use std::{fs, path::PathBuf};
use serde::{Deserialize, Serialize};
use crate::crypto;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    #[serde(default = "default_url")]
    pub api_base_url: String,
    pub registration_key: Option<String>,
    pub agent_id:         Option<String>,
    pub agent_token:      Option<String>,
    pub interval_seconds: Option<u64>,
    /// Optional VirusTotal API key. When set, the agent enriches malware-scan hits
    /// with VirusTotal verdicts locally (Option B) instead of relying on the backend.
    #[serde(default)]
    pub virustotal_api_key: Option<String>,
    /// TLS certificate verification. Defaults to `true` (secure). Only set to `false`
    /// for local dev against a self-signed backend — never in production, as it exposes
    /// every heartbeat, token, and command to a man-in-the-middle. Prefer `ca_cert_path`
    /// to trust a private CA instead of disabling verification wholesale.
    #[serde(default = "default_true")]
    pub verify_tls: bool,
    /// Optional path to a PEM CA certificate to trust in addition to the system roots.
    /// Lets the agent validate a backend that uses a private/internal CA while keeping
    /// full certificate verification enabled.
    #[serde(default)]
    pub ca_cert_path: Option<String>,
}

fn default_url() -> String { "http://localhost:5000".into() }
fn default_true() -> bool { true }

pub fn config_path() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.join("config.yaml")))
        .unwrap_or_else(|| PathBuf::from("config.yaml"))
}

pub fn load_config(path: &PathBuf) -> Config {
    let mut cfg = fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_yaml::from_str(&s).ok())
        .unwrap_or_else(|| Config {
            api_base_url: default_url(),
            registration_key: None,
            agent_id: None,
            agent_token: None,
            interval_seconds: None,
            virustotal_api_key: None,
            verify_tls: true,
            ca_cert_path: None,
        });
    // Decrypt any DPAPI-protected secrets into plaintext for in-memory use. Legacy
    // plaintext values pass through unchanged.
    decrypt_secrets(&mut cfg);
    cfg
}

pub fn save_config(path: &PathBuf, cfg: &Config) {
    // Persist secrets DPAPI-encrypted (machine scope) so a stolen config.yaml is useless
    // off-box; the in-memory `cfg` keeps its plaintext values untouched.
    let mut to_write = cfg.clone();
    to_write.agent_token = cfg.agent_token.as_deref().map(crypto::protect);
    to_write.registration_key = cfg.registration_key.as_deref().map(crypto::protect);
    if let Ok(yaml) = serde_yaml::to_string(&to_write) {
        let _ = fs::write(path, yaml);
    }
}

fn decrypt_secrets(cfg: &mut Config) {
    cfg.agent_token = cfg.agent_token.as_deref().map(crypto::unprotect);
    cfg.registration_key = cfg.registration_key.as_deref().map(crypto::unprotect);
}
