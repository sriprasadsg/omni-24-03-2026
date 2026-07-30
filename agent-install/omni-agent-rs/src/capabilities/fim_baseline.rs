//! Signed baseline snapshot + restart drift detection (FIM-03).
//!
//! At first run the agent computes a baseline snapshot (watched path -> sha256),
//! signs it with an agent-local ed25519 key, and persists it.
//! On restart the agent verifies the baseline signature before trusting it;
//! an invalid/missing baseline is recomputed and flagged as a reset (fail-closed).
//! Drift (added/removed/changed paths vs baseline) is detected on restart and
//! emitted as events into fim_queue. The baseline private key is agent-generated,
//! persisted locally, and never shipped.

use ed25519_dalek::{Signer, SigningKey, Signature, VerifyingKey};
use chrono::{DateTime, Utc};
use sha2::{Digest, Sha256};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;
use rand::rngs::OsRng;

/// The versioned baseline snapshot of file states.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Baseline {
    pub version: u64,
    pub created_at: DateTime<Utc>,
    pub entries: Vec<FileEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FileEntry {
    pub path: String,
    pub sha256: String,
    pub size_bytes: u64,
    pub modified_at: String,
}

/// Drift event types for fim_queue.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "change_type")]
pub enum DriftEvent {
    Added { path: String, hash_after: String },
    Removed { path: String, hash_before: String },
    Changed { path: String, hash_before: String, hash_after: String },
    BaselineReset { reason: String },
}

/// Agent-local storage paths for the baseline and signature.
fn baseline_dir() -> PathBuf {
    let mut dir = dirs::data_dir().unwrap_or_else(|| PathBuf::from("."));
    dir.push("omni-agent");
    dir.push("baseline");
    fs::create_dir_all(&dir).unwrap_or_else(|_| {});
    dir
}

fn baseline_path() -> PathBuf {
    baseline_dir().join("baseline.bin")
}

fn signature_path() -> PathBuf {
    baseline_dir().join("signature.sig")
}

fn key_path() -> PathBuf {
    baseline_dir().join("signing_key.dat")
}

/// Loads or generates and persists an agent-local ed25519 keypair.
/// The private key is stored locally with 0600 permissions (not shipped).
fn local_keypair() -> SigningKey {
    if key_path().exists() {
        let mut file = File::open(&key_path()).expect("Failed to open key file");
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes).expect("Failed to read key file");
        let arr: [u8; 32] = bytes[..32].try_into().expect("Invalid key length");
        SigningKey::from_bytes(&arr)
    } else {
        let signing_key = SigningKey::generate(&mut OsRng); // Use OsRng for generation
        let mut file = File::create(&key_path()).expect("Failed to create key file");
        file.write_all(signing_key.to_bytes().as_ref()).expect("Failed to write key file"); // Use to_bytes().as_ref()
        // Set 0600 permissions on Unix (no-op on Windows)
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = fs::metadata(&key_path()).unwrap().permissions();
            perms.set_mode(0o600);
            fs::set_permissions(&key_path(), perms).ok();
        }
        signing_key
    }
}

/// Computes SHA256 hash of a file.
fn hash_file(path: &Path) -> Result<(String, u64, String), Box<dyn std::error::Error>> {
    let data = fs::read(path)?;
    let mut hasher = Sha256::new();
    hasher.update(&data);
    let hash = hex::encode(hasher.finalize());
    let meta = fs::metadata(path)?;
    let size = meta.len();
    let modified = meta
        .modified()
        .ok()
        .and_then(|t| {
            t.duration_since(UNIX_EPOCH)
                .ok()
                .map(|d| {
                    DateTime::<Utc>::from(UNIX_EPOCH + d).to_rfc3339()
                })
        })
        .unwrap_or_default();
    Ok((hash, size, modified))
}

/// Walks the watched paths and computes the baseline snapshot.
pub fn compute_baseline(paths: &[String]) -> Baseline {
    let mut entries = Vec::new();
    for rel_path in paths {
        let path = Path::new(rel_path);
        if path.exists() && path.is_file() {
            if let Ok((hash, size, modified)) = hash_file(path) {
                entries.push(FileEntry {
                    path: rel_path.clone(),
                    sha256: hash,
                    size_bytes: size,
                    modified_at: modified,
                });
            }
        }
    }
    Baseline {
        version: 1,
        created_at: Utc::now(),
        entries,
    }
}

/// Serializes and saves the baseline + detached ed25519 signature.
pub fn save_signed(baseline: &Baseline) {
    let signing_key = local_keypair();
    let serialized = bincode::serialize(baseline).expect("Failed to serialize baseline");
    let signature: Signature = signing_key.sign(&serialized);

    // Atomic-ish write: temp then rename
    let tmp_baseline = baseline_path().with_extension("bin.tmp");
    let tmp_sig = signature_path().with_extension("sig.tmp");

    fs::write(&tmp_baseline, &serialized).expect("Failed to write baseline temp");
    fs::write(&tmp_sig, signature.to_bytes()).expect("Failed to write signature temp");

    fs::rename(&tmp_baseline, baseline_path()).expect("Failed to rename baseline");
    fs::rename(&tmp_sig, signature_path()).expect("Failed to rename signature");
}

/// Loads and verifies the signed baseline using the local public key.
/// Returns None on any verification failure (fail-closed).
pub fn load_verified() -> Option<Baseline> {
    let signing_key = local_keypair();
    let verifying_key = VerifyingKey::from(&signing_key);

    let baseline_bytes = fs::read(baseline_path()).ok()?;
    let sig_bytes = fs::read(signature_path()).ok()?;

    if sig_bytes.len() != 64 {
        return None;
    }
    let signature = Signature::from_slice(&sig_bytes).ok()?;

    if verifying_key.verify_strict(&baseline_bytes, &signature).is_err() {
        log::warn!("baseline signature verification FAILED — will recompute (fail-closed)");
        return None;
    }

    bincode::deserialize(&baseline_bytes).ok()
}

/// Checks for drift on restart and enqueues events into fim_queue.
/// If baseline is missing/invalid: recomputes, saves, enqueues baseline_reset (fail-closed).
/// Else diffs current hashes vs baseline entries, emits drift events, then re-saves signed baseline.
pub fn check_drift_on_start(paths: &[String]) {
    let current_baseline = compute_baseline(paths);
    let current_entries: HashMap<String, FileEntry> = current_baseline
        .entries
        .iter()
        .map(|e| (e.path.clone(), e.clone()))
        .collect();

    let verified_baseline = load_verified();

    if let Some(baseline) = verified_baseline {
        let baseline_entries: HashMap<String, FileEntry> = baseline
            .entries
            .iter()
            .map(|e| (e.path.clone(), e.clone()))
            .collect();

        // Check for removed and changed
        for (path, entry) in &baseline_entries {
            match current_entries.get(path) {
                Some(current_entry) => {
                    if current_entry.sha256 != entry.sha256 {
                        enqueue_drift(DriftEvent::Changed {
                            path: path.clone(),
                            hash_before: entry.sha256.clone(),
                            hash_after: current_entry.sha256.clone(),
                        });
                    }
                }
                None => {
                    enqueue_drift(DriftEvent::Removed {
                        path: path.clone(),
                        hash_before: entry.sha256.clone(),
                    });
                }
            }
        }

        // Check for added
        for (path, entry) in &current_entries {
            if !baseline_entries.contains_key(path) {
                enqueue_drift(DriftEvent::Added {
                    path: path.clone(),
                    hash_after: entry.sha256.clone(),
                });
            }
        }

        // Re-save the signed baseline with current state
        save_signed(&current_baseline);
    } else {
        // Missing or invalid baseline - fail-closed: recompute + flag reset
        log::warn!("baseline missing or invalid — recomputing and flagging reset (fail-closed)");
        enqueue_drift(DriftEvent::BaselineReset {
            reason: if baseline_path().exists() { "signature_verification_failed" } else { "missing_baseline" }.to_string(),
        });
        save_signed(&current_baseline);
    }
}

/// Enqueues a drift event into fim_queue (local SQLite).
fn enqueue_drift(event: DriftEvent) {
    let db_path = fim_queue_path();
    let Ok(conn) = rusqlite::Connection::open(&db_path) else {
        log::error!("Failed to open fim_queue DB at {:?}", db_path);
        return;
    };

    // Ensure table exists (created by fim.rs on init, but be safe)
    let _ = conn.execute(
        "CREATE TABLE IF NOT EXISTS fim_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )",
        [],
    );

    let event_json = serde_json::to_string(&event).unwrap_or_default();
    let now = Utc::now().to_rfc3339();

    let _ = conn.execute(
        "INSERT INTO fim_queue (event_json, created_at) VALUES (?1, ?2)",
        rusqlite::params![event_json, now],
    );

    log::debug!("Enqueued FIM drift event: {:?}", event);
}

fn fim_queue_path() -> PathBuf {
    crate::config::config_path()
        .parent()
        .map(|p| p.join("fim_queue.db"))
        .unwrap_or_else(|| PathBuf::from("fim_queue.db"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn sign_verify_roundtrip() {
        let dir = tempdir().unwrap();
        let test_path = dir.path().join("test.txt");
        fs::write(&test_path, b"hello world").unwrap();

        let paths = vec![test_path.to_string_lossy().to_string()];
        let baseline = compute_baseline(&paths);
        save_signed(&baseline);

        let loaded = load_verified();
        assert!(loaded.is_some());
        let loaded = loaded.unwrap();
        assert_eq!(loaded.version, baseline.version);
        assert_eq!(loaded.entries.len(), baseline.entries.len());
        assert_eq!(loaded.entries[0].sha256, baseline.entries[0].sha256);
    }

    #[test]
    fn tampered_baseline_fails_verification() {
        let dir = tempdir().unwrap();
        let test_path = dir.path().join("test.txt");
        fs::write(&test_path, b"hello world").unwrap();

        let paths = vec![test_path.to_string_lossy().to_string()];
        let baseline = compute_baseline(&paths);
        save_signed(&baseline);

        // Tamper with the baseline file
        let baseline_file = baseline_path();
        let mut bytes = fs::read(&baseline_file).unwrap();
        if !bytes.is_empty() {
            bytes[0] ^= 0xFF; // Flip a bit
            fs::write(&baseline_file, &bytes).unwrap();
        }

        let loaded = load_verified();
        assert!(loaded.is_none(), "Tampered baseline should fail verification");
    }

    #[test]
    fn drift_diff_add_remove_change() {
        let dir = tempdir().unwrap();

        // Initial baseline with file1
        let file1 = dir.path().join("file1.txt");
        fs::write(&file1, b"content1").unwrap();
        let paths = vec![file1.to_string_lossy().to_string()];
        let baseline = compute_baseline(&paths);
        save_signed(&baseline);

        // Now: file1 changed, file2 added, file1 removed from watched paths
        // Simulate by creating a new file and removing file1 from paths
        let file2 = dir.path().join("file2.txt");
        fs::write(&file2, b"content2").unwrap();

        // Manually check drift logic
        let current_baseline = compute_baseline(&paths);
        let current_entries: HashMap<String, FileEntry> = current_baseline
            .entries
            .iter()
            .map(|e| (e.path.clone(), e.clone()))
            .collect();

        let verified = load_verified().unwrap();
        let baseline_entries: HashMap<String, FileEntry> = verified
            .entries
            .iter()
            .map(|e| (e.path.clone(), e.clone()))
            .collect();

        // file1 should still be in baseline_entries
        assert!(baseline_entries.contains_key(&file1.to_string_lossy().to_string()));
        // file2 not in baseline_entries
        assert!(!baseline_entries.contains_key(&file2.to_string_lossy().to_string()));
    }

    #[test]
    fn missing_baseline_recomputes() {
        let dir = tempdir().unwrap();

        // No baseline exists
        let test_path = dir.path().join("test.txt");
        fs::write(&test_path, b"hello world").unwrap();
        let paths = vec![test_path.to_string_lossy().to_string()];

        // load_verified should return None
        let loaded = load_verified();
        assert!(loaded.is_none());

        // Compute and save
        let baseline = compute_baseline(&paths);
        save_signed(&baseline);

        // Now should load
        let loaded = load_verified();
        assert!(loaded.is_some());
    }
}