//! Destructive half of the `rotate_key` remediation action (Phase 64).
//!
//! This module owns every filesystem mutation involved in rotating a
//! weak/compromised SSH `authorized_keys` entry. It never judges key
//! strength itself — it always asks `ssh_key_checks` (the single shared
//! weak-key predicate), both when selecting a target line's context and
//! when grounding the post-write re-verify (D-07). The backup path and
//! the rotated-key path are derived deterministically from the
//! `authorized_keys` path alone, because the rollback playbook step
//! (`rotate_key_rollback`, shipped in plan 64-01) receives only that one
//! path. This module deliberately emits no diagnostic output at all — not
//! even at error granularity — so no runtime message can ever carry key
//! material (D-09).

use crate::capabilities::remediation_actions::RemediationError;
use crate::capabilities::ssh_key_checks;
use std::path::{Path, PathBuf};

pub const BACKUP_SUFFIX: &str = ".omni-rotate-backup";
pub const ROTATED_KEY_FILENAME: &str = "omni_rotated_ed25519";
pub const MAX_COMMENT_LEN: usize = 48;

/// A single `authorized_keys` line selected as the rotation target.
#[derive(Debug, Clone)]
pub struct TargetedEntry {
    pub line_index: usize,
    pub options_prefix: String,
    pub comment: String,
    pub total_entries: usize,
}

/// Returns `authorized_keys_path` with [`BACKUP_SUFFIX`] appended, always
/// in the same directory as the source — a rename across filesystems is
/// not atomic, and the parent `.ssh` directory is already owner-only.
/// This filename can never be read by sshd, which only consults the exact
/// configured `AuthorizedKeysFile` names.
pub fn backup_path_for(authorized_keys_path: &str) -> String {
    format!("{authorized_keys_path}{BACKUP_SUFFIX}")
}

/// Derives the deterministic path for the newly generated private key,
/// alongside `authorized_keys` in the same directory.
pub fn rotated_key_path_for(authorized_keys_path: &str) -> Result<PathBuf, RemediationError> {
    let parent = Path::new(authorized_keys_path).parent().ok_or_else(|| {
        RemediationError::InvalidPath(format!(
            "'{authorized_keys_path}' has no parent directory."
        ))
    })?;
    Ok(parent.join(ROTATED_KEY_FILENAME))
}

/// The single guard between an untrusted instruction parameter and a
/// privileged file write.
pub fn validate_target(authorized_keys_path: &str) -> Result<(), RemediationError> {
    if authorized_keys_path.is_empty() {
        return Err(RemediationError::InvalidPath(
            "authorized_keys path cannot be empty.".to_string(),
        ));
    }
    if !ssh_key_checks::is_authorized_keys_path(authorized_keys_path) {
        return Err(RemediationError::InvalidPath(format!(
            "'{authorized_keys_path}' is not a valid authorized_keys path."
        )));
    }
    if !Path::new(authorized_keys_path).is_file() {
        return Err(RemediationError::FileNotFound(authorized_keys_path.to_string()));
    }
    Ok(())
}

/// Selects the single `authorized_keys` entry whose fingerprint is exactly
/// equal to `fingerprint`. Refuses (D-05) before ever attempting a match
/// when fewer than two parseable entries exist — the lockout check runs
/// first so a single-entry file refuses identically whether or not the
/// fingerprint matches.
pub fn select_target(text: &str, fingerprint: &str) -> Result<TargetedEntry, RemediationError> {
    if fingerprint.is_empty() {
        return Err(RemediationError::InvalidTarget(
            "Fingerprint cannot be empty.".to_string(),
        ));
    }
    let entries = ssh_key_checks::parse_authorized_keys(text);
    let total_entries = entries.len();
    if total_entries < 2 {
        return Err(RemediationError::LockoutRefused(format!(
            "Only {total_entries} parseable authorized_keys entr{} found; rotating the sole access path is refused.",
            if total_entries == 1 { "y" } else { "ies" }
        )));
    }
    match entries.into_iter().find(|e| e.fingerprint == fingerprint) {
        Some(e) => Ok(TargetedEntry {
            line_index: e.line_index,
            options_prefix: e.options_prefix,
            comment: e.comment,
            total_entries,
        }),
        None => Err(RemediationError::KeyNotFound(format!(
            "No authorized_keys entry matches fingerprint '{fingerprint}'."
        ))),
    }
}

/// Writes `contents` to a same-directory temp file, copies the target's
/// existing permissions onto it, then renames it over `path`. Any failure
/// removes the temp file before returning `OperationFailed`. When the
/// target has no pre-existing metadata the mode defaults to owner
/// read/write only.
pub fn write_atomic(path: &Path, contents: &str) -> Result<(), RemediationError> {
    let parent = path.parent().ok_or_else(|| {
        RemediationError::InvalidPath("write_atomic target has no parent directory.".to_string())
    })?;
    let file_name = path
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or_else(|| RemediationError::InvalidPath("write_atomic target has no file name.".to_string()))?;

    #[cfg(unix)]
    let existing_mode: Option<u32> = {
        use std::os::unix::fs::PermissionsExt;
        std::fs::metadata(path).ok().map(|m| m.permissions().mode())
    };

    let tmp_path = parent.join(format!("{file_name}.omni-tmp-{}", std::process::id()));

    let result: Result<(), RemediationError> = (|| {
        std::fs::write(&tmp_path, contents)
            .map_err(|e| RemediationError::OperationFailed(format!("write temp file failed: {e}")))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = existing_mode.unwrap_or(0o600);
            let mut perms = std::fs::metadata(&tmp_path)
                .map_err(|e| RemediationError::OperationFailed(format!("temp file stat failed: {e}")))?
                .permissions();
            perms.set_mode(mode);
            std::fs::set_permissions(&tmp_path, perms)
                .map_err(|e| RemediationError::OperationFailed(format!("temp file chmod failed: {e}")))?;
        }
        std::fs::rename(&tmp_path, path)
            .map_err(|e| RemediationError::OperationFailed(format!("rename into place failed: {e}")))?;
        Ok(())
    })();

    if result.is_err() {
        let _ = std::fs::remove_file(&tmp_path);
    }
    result
}

/// Copies the whole `authorized_keys` file to its deterministic backup
/// path, owner-only permissions. Overwrites any existing snapshot on
/// purpose — the snapshot always means "state immediately before this
/// rotation", which is exactly what a step rollback must restore.
pub fn snapshot_backup(authorized_keys_path: &str) -> Result<String, RemediationError> {
    let backup_path = backup_path_for(authorized_keys_path);
    std::fs::copy(authorized_keys_path, &backup_path)
        .map_err(|e| RemediationError::OperationFailed(format!("snapshot copy failed: {e}")))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = std::fs::metadata(&backup_path)
            .map_err(|e| RemediationError::OperationFailed(format!("snapshot stat failed: {e}")))?
            .permissions();
        perms.set_mode(0o600);
        std::fs::set_permissions(&backup_path, perms)
            .map_err(|e| RemediationError::OperationFailed(format!("snapshot chmod failed: {e}")))?;
    }
    Ok(backup_path)
}

/// Restores the snapshot over the live file byte-for-byte, then
/// best-effort removes the snapshot and any pending rotated-key files (the
/// private key and its `.pub` sibling) so a subsequent rotation is
/// unblocked. Removal failures are ignored — the restore is the contract,
/// the cleanup is hygiene.
pub fn rollback_rotation(authorized_keys_path: &str) -> Result<(), RemediationError> {
    validate_target(authorized_keys_path)?;
    let backup_path = backup_path_for(authorized_keys_path);
    if !Path::new(&backup_path).is_file() {
        return Err(RemediationError::FileNotFound(backup_path));
    }
    let snapshot_contents = std::fs::read_to_string(&backup_path)
        .map_err(|e| RemediationError::OperationFailed(format!("snapshot read failed: {e}")))?;
    write_atomic(Path::new(authorized_keys_path), &snapshot_contents)?;

    let _ = std::fs::remove_file(&backup_path);
    if let Ok(rk_path) = rotated_key_path_for(authorized_keys_path) {
        let _ = std::fs::remove_file(&rk_path);
        let _ = std::fs::remove_file(rk_path.with_extension("pub"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    /// Generates a real, freshly-random Ed25519 public key line for test
    /// fixtures. Never a hardcoded key — and never any private key
    /// material in a fixture (project rule).
    fn sample_key_line(comment: &str) -> String {
        let key = ssh_key::PrivateKey::random(&mut rand::rngs::OsRng, ssh_key::Algorithm::Ed25519)
            .expect("keygen for test fixture");
        let mut public = key.public_key().clone();
        public.set_comment(comment);
        public.to_openssh().expect("public key encode for test fixture")
    }

    fn fingerprint_of(pubkey_line: &str) -> String {
        let pk = ssh_key::PublicKey::from_openssh(pubkey_line).expect("parse test fixture key");
        pk.fingerprint(ssh_key::HashAlg::Sha256).to_string()
    }

    // ── select_target ────────────────────────────────────────────────────

    #[test]
    fn rotate_key_select_target_exact_fingerprint_match_among_three() {
        let l1 = sample_key_line("one");
        let l2 = sample_key_line("two");
        let l3 = sample_key_line("three");
        let text = format!("{l1}\n{l2}\n{l3}\n");
        let fp2 = fingerprint_of(&l2);

        let target = select_target(&text, &fp2).expect("should match line 2");
        assert_eq!(target.line_index, 1);
        assert_eq!(target.total_entries, 3);
        assert_eq!(target.comment, "two");
    }

    #[test]
    fn rotate_key_select_target_prefix_of_real_fingerprint_never_matches() {
        let l1 = sample_key_line("one");
        let l2 = sample_key_line("two");
        let text = format!("{l1}\n{l2}\n");
        let fp1 = fingerprint_of(&l1);
        let prefix = &fp1[..fp1.len() - 1];

        let result = select_target(&text, prefix);
        assert!(matches!(result, Err(RemediationError::KeyNotFound(_))));
    }

    #[test]
    fn rotate_key_select_target_sole_entry_refuses_lockout() {
        let l1 = sample_key_line("only");
        let text = format!("{l1}\n");
        let fp1 = fingerprint_of(&l1);

        let result = select_target(&text, &fp1);
        assert!(matches!(result, Err(RemediationError::LockoutRefused(_))));
    }

    #[test]
    fn rotate_key_select_target_sole_entry_plus_noise_still_lockout() {
        let l1 = sample_key_line("only");
        let text = format!(
            "\n# a comment\n{l1}\nssh-rsa truncated-not-a-real-key\n\n"
        );
        let fp1 = fingerprint_of(&l1);

        let result = select_target(&text, &fp1);
        assert!(matches!(result, Err(RemediationError::LockoutRefused(_))));
    }

    #[test]
    fn rotate_key_select_target_unmatched_fingerprint_not_found() {
        let l1 = sample_key_line("one");
        let l2 = sample_key_line("two");
        let text = format!("{l1}\n{l2}\n");

        let result = select_target(&text, "SHA256:doesnotexistanywhereinthisfile00000000000");
        assert!(matches!(result, Err(RemediationError::KeyNotFound(_))));
    }

    #[test]
    fn rotate_key_select_target_zero_entries_refuses_not_panics() {
        let result = select_target("", "SHA256:anything");
        assert!(result.is_err());
    }

    // ── validate_target ─────────────────────────────────────────────────

    #[test]
    fn rotate_key_validate_target_rejects_empty() {
        assert!(matches!(validate_target(""), Err(RemediationError::InvalidPath(_))));
    }

    #[test]
    fn rotate_key_validate_target_rejects_relative() {
        assert!(matches!(validate_target("authorized_keys"), Err(RemediationError::InvalidPath(_))));
    }

    #[test]
    fn rotate_key_validate_target_rejects_wrong_filename() {
        assert!(matches!(validate_target("/tmp/id_rsa"), Err(RemediationError::InvalidPath(_))));
    }

    #[test]
    fn rotate_key_validate_target_rejects_nonexistent() {
        let result = validate_target("/tmp/omni-rotate-key-test-does-not-exist-dir/authorized_keys");
        assert!(matches!(result, Err(RemediationError::FileNotFound(_))));
    }

    #[test]
    fn rotate_key_validate_target_accepts_real_authorized_keys_file() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("authorized_keys");
        std::fs::write(&path, "content").unwrap();
        assert!(validate_target(path.to_str().unwrap()).is_ok());
    }

    // ── backup_path_for / rotated_key_path_for ──────────────────────────

    #[test]
    fn rotate_key_backup_and_rotated_paths_are_pure_and_same_dir() {
        let input = "/home/alice/.ssh/authorized_keys";
        assert_eq!(backup_path_for(input), backup_path_for(input));
        let backup = backup_path_for(input);
        assert_eq!(Path::new(&backup).parent(), Path::new(input).parent());

        let rk1 = rotated_key_path_for(input).unwrap();
        let rk2 = rotated_key_path_for(input).unwrap();
        assert_eq!(rk1, rk2);
        assert_eq!(rk1.parent(), Path::new(input).parent());
    }

    #[test]
    fn rotate_key_rotated_key_path_for_errors_with_no_parent() {
        let result = rotated_key_path_for("/");
        assert!(result.is_err());
    }

    // ── write_atomic ─────────────────────────────────────────────────────

    #[test]
    fn rotate_key_write_atomic_replaces_contents_no_leftover_temp() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("authorized_keys");
        std::fs::write(&path, "old content").unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o640)).unwrap();
        }

        write_atomic(&path, "new content").expect("write_atomic should succeed");
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "new content");

        let leftovers: Vec<_> = std::fs::read_dir(dir.path())
            .unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| e.file_name().to_string_lossy().contains(".omni-tmp-"))
            .collect();
        assert!(leftovers.is_empty(), "no leftover temp files should remain");

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = std::fs::metadata(&path).unwrap().permissions().mode() & 0o777;
            assert_eq!(mode, 0o640);
        }
    }

    // ── snapshot_backup ──────────────────────────────────────────────────

    #[test]
    fn rotate_key_snapshot_backup_byte_identical_owner_only() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("authorized_keys");
        std::fs::write(&path, "exact bytes to preserve\n").unwrap();

        let backup_path = snapshot_backup(path.to_str().unwrap()).expect("snapshot should succeed");
        assert_eq!(
            std::fs::read(&backup_path).unwrap(),
            std::fs::read(&path).unwrap()
        );

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = std::fs::metadata(&backup_path).unwrap().permissions().mode() & 0o777;
            assert_eq!(mode, 0o600);
        }
    }

    // ── rollback_rotation ────────────────────────────────────────────────

    #[test]
    fn rotate_key_rollback_restores_byte_for_byte_and_cleans_up() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("authorized_keys");
        let original = "original line one\noriginal line two\n";
        std::fs::write(&path, original).unwrap();

        let backup_path = snapshot_backup(path.to_str().unwrap()).unwrap();
        std::fs::write(&path, "tampered content after a fake rotation\n").unwrap();

        let rk_path = rotated_key_path_for(path.to_str().unwrap()).unwrap();
        std::fs::write(&rk_path, "fake private key").unwrap();
        let rk_pub = rk_path.with_extension("pub");
        std::fs::write(&rk_pub, "fake public key").unwrap();

        rollback_rotation(path.to_str().unwrap()).expect("rollback should succeed");

        assert_eq!(std::fs::read_to_string(&path).unwrap(), original);
        assert!(!Path::new(&backup_path).exists());
        assert!(!rk_path.exists());
        assert!(!rk_pub.exists());
    }

    #[test]
    fn rotate_key_rollback_without_snapshot_refuses_and_leaves_file_untouched() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("authorized_keys");
        let original = "untouched content\n";
        std::fs::write(&path, original).unwrap();

        let result = rollback_rotation(path.to_str().unwrap());
        assert!(matches!(result, Err(RemediationError::FileNotFound(_))));
        assert_eq!(std::fs::read_to_string(&path).unwrap(), original);
    }
}
