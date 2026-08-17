//! Weak/compromised SSH `authorized_keys` detection (Phase 64, AUTO-02).
//!
//! This module owns the single shared weak-key predicate (`weak_reason_for`)
//! used by BOTH the vulnerability scanner's `check_authorized_keys` (in
//! `vulnerability_scan.rs`) and the `rotate_key` action's post-write grounded
//! re-verify (in `ssh_key_rotation.rs`). Neither caller re-implements this
//! judgment locally — it must stay the single source of truth.
//!
//! v1 detection scope is weak key **type** only: any RSA key whose modulus is
//! below `MIN_RSA_BITS`, and any DSA key regardless of size (DSA's key size is
//! fixed and inadequate, so it is flagged by type alone, not by a bit-length
//! test). There is no known-compromised-fingerprint blocklist in v1 — the
//! finding schema already carries a fingerprint, so a blocklist feed is purely
//! additive later.
//!
//! A non-default `AuthorizedKeysFile` directive in `sshd_config` is NOT parsed
//! in v1 — `authorized_keys_paths()` only enumerates the conventional
//! `~/.ssh/authorized_keys` locations. Adding an sshd_config directive parser
//! is a separate concern, deliberately out of scope here.

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
            // Bit length derived from the modulus's positive-magnitude bytes
            // (strips the MPInt sign-padding byte, if any): eight times the
            // byte count minus the leading zero bits of the most significant
            // byte. A naive `byte_len * 8` over-counts by 8 whenever the
            // modulus's top bit is set, since MPInt then prepends a 0x00 sign
            // byte to keep the value unambiguously positive.
            let bits = key
                .key_data()
                .rsa()
                .and_then(|rsa| rsa.n.as_positive_bytes())
                .map(|bytes| {
                    let msb = bytes.first().copied().unwrap_or(0);
                    bytes.len() * 8 - msb.leading_zeros() as usize
                })
                .unwrap_or(0);
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

#[cfg(test)]
mod tests {
    use super::*;

    // Real OpenSSH public-key lines generated offline via `ssh-keygen` purely
    // to obtain valid, parseable fixture material — never a private key, and
    // never read from any real host file (per project rule: never commit
    // credentials; these are public keys, not secrets).
    pub(crate) const RSA_1024_LINE: &str = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAAgQDMK2nKu1jTtZkc0iZ9Puo1NCjqiF0xdfgfl77LJCX2Ld6dei2erOMpLOfSXryLa0W+IAbZLwHCgfO5WA8f/P9KAjK7S5Dy5dc0SnvUr5JKBkmdLRJYCe8uSjFm1QhKDZw9/rpiQfK6rvBsM+eVg9E7DvBV9WYbzCphAak04Hjlvw== test-rsa-1024";
    pub(crate) const RSA_2048_LINE: &str = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDYUT58+4+4OUKU4aUHxXbi3dSVwMoxSbdl9vE5XimRRlO0Q+F7Eslk3G65STCpIE8VgXa7cvhOvI76CBECkCi8Ms8ZkxrR3liZKICVOi+VfZS1udKM4bbqlDEuEH7nd+vljnqXwYVBXqt785Cjke/EOEiZrBqsid97wF7AiDLSiqgURrr4muA+PhC9/QdLgA8HF4DR4Ru05C7j+DTqUSP9xlapgrPKPR3Q7q3Hk02ZJ0q5LZ7eLq4i/zfq7y1BMS7TuEAii2A+eMmbrTxf9eg8ef4/HVUwiuaWyK2SudXZNmW9iY82LgJ/ZjOut+2nnAsCQMsqbuji7tYhPwxCpBeF test-rsa-2048";
    pub(crate) const DSA_LINE: &str = "ssh-dss AAAAB3NzaC1kc3MAAACBALtvy5bvmF7iav4Zm86jbukRFiLmaG1ebYDP1wxjfw52f9W/qUDadJwgl+lZHgdqdNAAzuJhl13iOnd6+ccE/FVGYlqs+IRo5RPdxkcK+4yXWB+tCcwy7zcRuU4ckbTaTCGxbsfjU45mdJMLY/lnnIb2SWc116jLgLlzJftsu0u/AAAAFQCn2rd1IWDaPYJKXRWIeDwiOQYsMwAAAIEAsi094ytzq0uOv7Fdp+oNGykE4rQ/RLmXGqYGqVGkp8MSEIlX7Vd8AEL9f/IulX9WJWWRVUDyOCjCyNtIUsTsinuOndAcngtQhCMmVr6rL0HKRwbbw9Y6nhnIKYB8zP2D0Qjj4cnPTDgvVMQWSgCuqm0eEsQ9k1pApMvS/n/yAG0AAACAVKPFoDuhNF9h/qL9EAlevxEx3BfdQR9EEp8MQFy5kNTpJqFnnOhsYKEM3FH1r0qtO70qb+HFIc0c/DJ4b3p6kou8tAPeNwogTzhwimLmw7V6XNE1bvPUc5mih84hKvVwhWfGMVjB7y2fNogxw6pHfWlYoRaCUaqQBLrBXIiKlxQ= test-dsa";
    pub(crate) const ED25519_LINE: &str = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGN3bSdG9aZLl3AdOdzCATNeEDtt3wInkZw5yTvncqAC test-ed25519";

    fn parse_one(line: &str) -> PublicKey {
        PublicKey::from_openssh(line).expect("fixture line must parse")
    }

    // Test 1: RSA 1024 classifies weak (reason names the bit count); RSA 2048
    // classifies not weak.
    #[test]
    fn weak_reason_for_rsa_1024_is_weak_rsa_2048_is_not() {
        let weak = weak_reason_for(&parse_one(RSA_1024_LINE));
        assert!(weak.is_some());
        let reason = weak.unwrap();
        assert!(reason.contains("1024"), "reason should name the bit count: {reason}");

        let strong = weak_reason_for(&parse_one(RSA_2048_LINE));
        assert!(strong.is_none());
    }

    // Test 2: ssh-dss classifies weak by type alone, no bit-length test (D-02).
    #[test]
    fn weak_reason_for_dsa_is_weak_by_type_alone() {
        let reason = weak_reason_for(&parse_one(DSA_LINE));
        assert!(reason.is_some());
        assert!(reason.unwrap().to_uppercase().contains("DSA"));
    }

    // Test 3: ssh-ed25519 classifies not weak.
    #[test]
    fn weak_reason_for_ed25519_is_not_weak() {
        assert!(weak_reason_for(&parse_one(ED25519_LINE)).is_none());
    }

    // Test 4: a blank line, a `#` comment line, a truncated base64 line, and
    // one valid Ed25519 line yields exactly one entry — malformed input is
    // skipped, never panics, never produces an entry.
    #[test]
    fn parse_authorized_keys_skips_malformed_lines() {
        let text = format!(
            "\n# a comment\nssh-rsa truncated-not-a-real-key\n{ED25519_LINE}\n"
        );
        let entries = parse_authorized_keys(&text);
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].algorithm, format!("{:?}", Algorithm::Ed25519));
    }

    // Test 5: a line carrying an options prefix (command="...",no-pty style)
    // before the key type token preserves that prefix verbatim, and
    // algorithm/fingerprint are still correctly parsed.
    #[test]
    fn parse_authorized_keys_preserves_options_prefix() {
        let prefix = r#"command="/usr/bin/true",no-pty"#;
        let line = format!("{prefix} {ED25519_LINE}");
        let entries = parse_authorized_keys(&line);
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].options_prefix, prefix);
        assert_eq!(entries[0].algorithm, format!("{:?}", Algorithm::Ed25519));
        let expected_fp = parse_one(ED25519_LINE).fingerprint(HashAlg::Sha256).to_string();
        assert_eq!(entries[0].fingerprint, expected_fp);
    }

    // Test 6: entries expose a SHA256-form fingerprint, stable across calls.
    #[test]
    fn fingerprint_is_sha256_and_stable() {
        let entries_a = parse_authorized_keys(ED25519_LINE);
        let entries_b = parse_authorized_keys(ED25519_LINE);
        assert_eq!(entries_a.len(), 1);
        assert_eq!(entries_b.len(), 1);
        assert!(entries_a[0].fingerprint.starts_with("SHA256:"));
        assert_eq!(entries_a[0].fingerprint, entries_b[0].fingerprint);
    }

    // Test 7: is_authorized_keys_path accepts authorized_keys and
    // administrators_authorized_keys file names; rejects /etc/shadow,
    // /etc/environment, a relative path, and parent-directory traversal.
    #[test]
    fn is_authorized_keys_path_accepts_and_rejects() {
        assert!(is_authorized_keys_path("/root/.ssh/authorized_keys"));
        assert!(is_authorized_keys_path(
            "/etc/ssh/administrators_authorized_keys"
        ));
        assert!(!is_authorized_keys_path("/etc/shadow"));
        assert!(!is_authorized_keys_path("/etc/environment"));
        assert!(!is_authorized_keys_path(".ssh/authorized_keys"));
        assert!(!is_authorized_keys_path("/root/.ssh/../../etc/authorized_keys"));
    }

    // Test 8: empty string returns an empty vector.
    #[test]
    fn parse_authorized_keys_empty_input_returns_empty_vec() {
        assert!(parse_authorized_keys("").is_empty());
    }
}

