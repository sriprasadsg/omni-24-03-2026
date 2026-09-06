use std::path::Path;
use anyhow::{Result, anyhow};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum KeyStrength {
    Strong,
    Weak(String),
}

#[derive(Debug, Clone)]
pub struct SshKeyInfo {
    pub path: std::path::PathBuf,
    pub key_type: String,
    pub strength: KeyStrength,
    pub bit_length: Option<u32>,
}

pub fn find_ssh_keys() -> Result<Vec<std::path::PathBuf>> {
    let mut keys = Vec::new();
    let home = dirs::home_dir().ok_or_else(|| anyhow!("Could not find home directory"))?;
    let ssh_dir = home.join(".ssh");

    if ssh_dir.exists() {
        let common_keys = ["id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"];
        for key_name in &common_keys {
            let path = ssh_dir.join(key_name);
            if path.exists() {
                keys.push(path);
            }
        }
    }
    Ok(keys)
}

pub fn check_key_strength(key_path: &Path) -> Result<SshKeyInfo> {
    // Simplified check - in real implementation, would parse the key file
    // For now, we'll use a placeholder based on filename
    let key_type = key_path.file_name()
        .and_then(|n| n.to_str())
        .map(|n| {
            if n.contains("rsa") { "RSA" }
            else if n.contains("dsa") { "DSA" }
            else if n.contains("ecdsa") { "ECDSA" }
            else if n.contains("ed25519") { "Ed25519" }
            else { "Unknown" }
        })
        .unwrap_or("Unknown")
        .to_string();

    let strength = match key_type.as_str() {
        "RSA" => KeyStrength::Weak("RSA key < 2048 bits".to_string()),
        "DSA" => KeyStrength::Weak("DSA key < 1024 bits".to_string()),
        "ECDSA" => KeyStrength::Strong,
        "Ed25519" => KeyStrength::Strong,
        _ => KeyStrength::Weak("Unknown key type".to_string()),
    };

    Ok(SshKeyInfo {
        path: key_path.to_path_buf(),
        key_type,
        strength,
        bit_length: None,
    })
}

pub fn perform_ssh_key_scan() -> Result<Vec<SshKeyInfo>> {
    let keys = find_ssh_keys()?;
    let mut results = Vec::new();
    for key_path in keys {
        if let Ok(info) = check_key_strength(&key_path) {
            results.push(info);
        }
    }
    Ok(results)
}