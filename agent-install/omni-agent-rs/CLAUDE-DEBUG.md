# CLAUDE-DEBUG.md

## Current State: Debugging 64-02-PLAN.md (Weak-key scanner module)

**Context is Critical.** Cannot effectively debug complex Rust compilation issues with current context limits.

**Problem:** `ssh_key_checks.rs` is not compiling, specifically the `parse_authorized_keys` function and related tests. Errors (`E0277`, `E0308`, `E0533`, `E0599`) indicate issues with `ssh-key` crate API usage, type mismatches, and trait bounds. The compiler output is too verbose to debug line-by-line.

**Specific Issues:**
- `PublicKey::from_openssh` likely not receiving expected format in `key_portion`.
- `weak_reason_for` was using `format!("{:?}", pk.algorithm())` which was fixed to `match key.algorithm()`.
- Test helpers `rsa_key_str`, `dsa_key_str`, `ed25519_key_str` in `ssh_key_checks.rs` were modified to correctly generate keys with the `ssh-key` crate.
- `Cargo.toml` was corrected from `rand-core` to `rand_core` and `ssh-dss` to `dsa`.

**Current `ssh_key_checks.rs` content (after latest attempt to fix):**
```rust
use ssh_key::{Algorithm, AuthorizedKeys, Fingerprint, HashAlg, PrivateKey, PublicKey, SshSig};

pub const MIN_RSA_BITS: u32 = 2048;
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
        Algorithm::Rsa => {
            let bits = key.bits();
            if bits < MIN_RSA_BITS {
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
            (trimmed[..start_idx].trim_end().to_string(), trimmed[start_idx..])
        } else {
            // No recognized key type found, skip this line.
            continue;
        };

        match PublicKey::from_openssh(key_portion) {
            Ok(pk) => {
                let algo = format!("{:?}", pk.algorithm());
                let fp = pk.fingerprint(HashAlg::Sha256).to_string();
                let comment = pk.comment().unwrap_or("").to_string();
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


#[cfg(test)]
mod tests {
    use super::*;
    use ssh_key::{LineEnding, PrivateKey};

    // Helper to generate an RSA public key string
    fn rsa_key_str(bits: u32) -> String {
        let key = PrivateKey::from_rsa(bits).unwrap();
        key.public_key().to_openssh().unwrap()
    }

    // Helper to generate a DSA public key string
    fn dsa_key_str() -> String {
        let key = PrivateKey::from_dsa().unwrap();
        key.public_key().to_openssh().unwrap()
    }

    // Helper to generate an Ed25519 public key string
    fn ed25519_key_str() -> String {
        let key = PrivateKey::generate(Algorithm::Ed25519, &mut ssh_key::rand_core::OsRng).unwrap();
        key.public_key().to_openssh().unwrap()
    }

    #[test]
    fn rsa_1024_is_weak() {
        let key_str = rsa_key_str(1024);
        let pk = PublicKey::from_openssh(&key_str).unwrap();
        let reason = weak_reason_for(&pk);
        assert!(reason.is_some());
        assert!(reason.unwrap().contains("1024"));
    }

    #[test]
    fn rsa_2048_is_strong() {
        let key_str = rsa_key_str(2048);
        let pk = PublicKey::from_openssh(&key_str).unwrap();
        assert!(weak_reason_for(&pk).is_none());
    }

    #[test]
    fn dsa_is_weak() {
        let key_str = dsa_key_str();
        let pk = PublicKey::from_openssh(&key_str).unwrap();
        let reason = weak_reason_for(&pk);
        assert!(reason.is_some());
        assert!(reason.unwrap().contains("DSA"));
    }

    #[test]
    fn ed25519_is_strong() {
        let key_str = ed25519_key_str();
        let pk = PublicKey::from_openssh(&key_str).unwrap();
        assert!(weak_reason_for(&pk).is_none());
    }

    #[test]
    fn parses_malformed_input_safely() {
        let text = "\n# a comment\nmalformed_key_xyz\nssh-ed25519 ".to_string() + &ed25519_key_str();
        let entries = parse_authorized_keys(&text);
        assert_eq!(entries.len(), 1); // Only the valid key should be parsed
    }

    #[test]
    fn parses_options_prefix() {
        let key_str = ed25519_key_str();
        let line = format!("command=\"/bin/sh\",no-pty {} {}", key_str, "user@host");
        let entries = parse_authorized_keys(&line);
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].options_prefix, "command=\"/bin/sh\",no-pty");
        assert_eq!(entries[0].algorithm, "Ed25519"); // Check algo is correct
        assert!(!entries[0].fingerprint.is_empty());
    }

    #[test]
    fn fingerprint_is_sha256_and_stable() {
        let key_str = ed25519_key_str();
        let entries1 = parse_authorized_keys(&key_str);
        let entries2 = parse_authorized_keys(&key_str);
        assert_eq!(entries1.len(), 1);
        assert_eq!(entries1[0].fingerprint, entries2[0].fingerprint);
        assert!(entries1[0].fingerprint.starts_with("SHA256:"));
    }

    #[test]
    fn path_guard_works() {
        assert!(is_authorized_keys_path("/home/user/.ssh/authorized_keys"));
        assert!(is_authorized_keys_path("/home/user/.ssh/administrators_authorized_keys"));
        assert!(!is_authorized_keys_path("/etc/shadow"));
        assert!(!is_authorized_keys_path("/etc/environment"));
        assert!(!is_authorized_keys_path("relative/path"));
        assert!(!is_authorized_keys_path("/home/../etc/passwd"));
    }

    #[test]
    fn empty_string_returns_empty() {
        let entries = parse_authorized_keys("");
        assert!(entries.is_empty());
    }
}
```