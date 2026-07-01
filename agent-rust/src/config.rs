use std::{fs, path::PathBuf};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    #[serde(default = "default_url")]
    pub api_base_url: String,
    pub registration_key: Option<String>,
    pub agent_id:         Option<String>,
    pub agent_token:      Option<String>,
    pub interval_seconds: Option<u64>,
}

fn default_url() -> String { "http://localhost:5000".into() }

pub fn config_path() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.join("config.yaml")))
        .unwrap_or_else(|| PathBuf::from("config.yaml"))
}

pub fn load_config(path: &PathBuf) -> Config {
    fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_yaml::from_str(&s).ok())
        .unwrap_or_else(|| Config {
            api_base_url: default_url(),
            registration_key: None,
            agent_id: None,
            agent_token: None,
            interval_seconds: None,
        })
}

pub fn save_config(path: &PathBuf, cfg: &Config) {
    if let Ok(yaml) = serde_yaml::to_string(cfg) {
        let _ = fs::write(path, yaml);
    }
}
