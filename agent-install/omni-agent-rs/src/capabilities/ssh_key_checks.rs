use ssh_key::{Algorithm, HashAlg, PublicKey};

pub const MIN_RSA_BITS: usize = 2048;
pub const MAX_AUTHORIZED_KEYS_FILES: usize = 64;
pub const AUTHORIZED_KEYS_READ_CAP: usize = 256 * 1024;

#[derive(Debug, Clone)]
pub struct AuthorizedKeyEntry {
    pub line_index: usize,
    pub options_prefix: String,
    pub algorithm: String,
    pub fingerprint: String,
    pub comment: String,
    pub weak_reason: Option<String>,
}

pub fn weak_reason_for(key: &PublicKey) -> Option<String> {
    match key.algorithm() {
        Algorithm::Dsa => Some("DSA key (fixed inadequate key size)".to_string()),
        Algorithm::Rsa { hash: _ } => {
            let bits = key.key_data().rsa().map(|rsa| rsa.n.as_ref().len() * 8).unwrap_or(0);
            if (bits as usize) < MIN_RSA_BITS {
                Some(format!("RSA key is {} bits (minimum {})", bits, MIN_RSA_BITS))
            } else {
                None
            }
        }
        _ => None, // Ed25519, Ecdsa, etc. are considered strong
    }
}

pub fn parse_authorized_keys(text: &str) -> Vec<AuthorizedKeyEntry> {
    let mut entries = Vec::new();
    for (idx, line) in text.lines().enumerate() {
        let trimmed = line.trim_start();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }

        // Find the start of the key material (ssh-, ecdsa-, sk-).
        let key_start_idx = trimmed.find("ssh-")
            .or_else(|| trimmed.find("ecdsa-"))
            .or_else(|| trimmed.find("sk-"));

        let (options_prefix, key_portion) = if let Some(start_idx) = key_start_idx {
            (trimmed[..start_idx].trim_end().to_string(), trimmed[start_idx..].to_string())
        } else {
            // No recognized key type found, skip this line.
            continue;
        };

        match PublicKey::from_openssh(&key_portion) {
            Ok(pk) => {
                let algo = format!("{:?}", pk.algorithm());
                let fp = pk.fingerprint(HashAlg::Sha256).to_string();
                let comment = pk.comment().to_string();
                let weak_reason = weak_reason_for(&pk);
                entries.push(AuthorizedKeyEntry {
                    line_index: idx,
                    options_prefix,
                    algorithm: algo,
                    fingerprint: fp,
                    comment,
                    weak_reason,
                });
            }
            Err(_) => continue, // Silently skip unparseable keys
        }
    }
    entries
}

pub fn is_authorized_keys_path(path: &str) -> bool {
    if path.is_empty() || !path.starts_with('/') {
        return false;
    }
    if path.contains("..") { // Prevent directory traversal
        return false;
    }
    let last_component = std::path::Path::new(path).file_name().and_then(|n| n.to_str()).unwrap_or("");
    last_component == "authorized_keys" || last_component == "administrators_authorized_keys"
}

#[cfg(unix)]
pub fn authorized_keys_paths() -> Vec<String> {
    let mut paths = Vec::new();
    let mut add_if_exists = |p: &str| {
        let path = std::path::Path::new(p);
        if path.is_file() {
            paths.push(p.to_string());
        }
    };

    // Add root's authorized_keys
    add_if_exists("/root/.ssh/authorized_keys");

    // Add home directories' authorized_keys
    if let Ok(entries) = std::fs::read_dir("/home") {
        for entry in entries.flatten() {
            if let Ok(file_type) = entry.file_type() {
                if file_type.is_dir() {
                    let path_str = format!("{}/.ssh/authorized_keys", entry.path().display());
                    add_if_exists(&path_str);
                }
            }
        }
    }

    #[cfg(target_os = "macos")]
    if let Ok(entries) = std::fs::read_dir("/Users") {
        for entry in entries.flatten() {
            if let Ok(file_type) = entry.file_type() {
                if file_type.is_dir() {
                    let path_str = format!("{}/.ssh/authorized_keys", entry.path().display());
                    add_if_exists(&path_str);
                }
            }
        }
    }

    paths.sort();
    paths.truncate(MAX_AUTHORIZED_KEYS_FILES);
    paths
}

#[cfg(not(unix))]
pub fn authorized_keys_paths() -> Vec<String> {
    // Return empty for non-Unix systems (e.g., Windows) as per scope boundary
    Vec::new()
}


