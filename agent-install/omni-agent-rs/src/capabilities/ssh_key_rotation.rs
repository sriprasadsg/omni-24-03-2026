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

/// Line-injection guard, not cosmetics: an authorized_keys record is
/// newline-delimited, so an unsanitized comment carrying a newline would
/// append an attacker-chosen second key entry. Keeps only ASCII letters,
/// digits, dot, underscore, at-sign and hyphen; truncates to
/// [`MAX_COMMENT_LEN`]; substitutes a fixed fallback token when the
/// filtered result is empty.
pub fn sanitize_comment(raw: &str) -> String {
    let filtered: String = raw
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '@' | '-'))
        .collect();
    let truncated: String = filtered.chars().take(MAX_COMMENT_LEN).collect();
    if truncated.is_empty() {
        "omni-rotated-key".to_string()
    } else {
        truncated
    }
}

/// The D-09 boundary: this type is the entire surface the host reports
/// about a rotation, persisted verbatim by the backend. No field may ever
/// carry key material, a key body, or a filesystem path. Deliberately no
/// `Serialize` derive — the dispatch arm (plan 64-04) constructs its JSON
/// field by field, so there is no derive that could silently widen this
/// payload when a field is added later.
#[derive(Debug, Clone)]
pub struct RotationOutcome {
    pub new_fingerprint: String,
    pub new_comment: String,
}

/// Generates a fresh Ed25519 private key (OpenSSH's own default since
/// 9.5, per RESEARCH.md's State of the Art) seeded from the OS CSPRNG —
/// never a fixed or time-derived seed — and sets the sanitized comment.
fn generate_replacement(comment: &str) -> Result<ssh_key::PrivateKey, RemediationError> {
    let mut key = ssh_key::PrivateKey::random(&mut rand::rngs::OsRng, ssh_key::Algorithm::Ed25519)
        .map_err(|e| RemediationError::OperationFailed(format!("keypair generation failed: {e}")))?;
    key.set_comment(comment);
    Ok(key)
}

/// The only place in the crate where private key bytes exist in memory.
/// Refuses when a prior rotation's key is still pending out-of-band
/// delivery (D-08) rather than overwriting an in-flight credential.
/// Returns the new key's public authorized_keys-format line; nothing else
/// leaves this function.
fn write_new_keypair(authorized_keys_path: &str, key: &ssh_key::PrivateKey) -> Result<String, RemediationError> {
    let priv_path = rotated_key_path_for(authorized_keys_path)?;
    if priv_path.exists() {
        return Err(RemediationError::OperationFailed(format!(
            "A previously rotated private key already exists at {} — deliver or remove it before rotating again.",
            priv_path.display()
        )));
    }
    let pub_path = priv_path.with_extension("pub");

    let openssh = key
        .to_openssh(ssh_key::LineEnding::LF)
        .map_err(|e| RemediationError::OperationFailed(format!("private key serialization failed: {e}")))?;
    std::fs::write(&priv_path, openssh.as_bytes())
        .map_err(|e| RemediationError::OperationFailed(format!("private key write failed: {e}")))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = std::fs::metadata(&priv_path)
            .map_err(|e| RemediationError::OperationFailed(format!("private key stat failed: {e}")))?
            .permissions();
        perms.set_mode(0o600);
        std::fs::set_permissions(&priv_path, perms)
            .map_err(|e| RemediationError::OperationFailed(format!("private key chmod failed: {e}")))?;
    }

    let public_line = key
        .public_key()
        .to_openssh()
        .map_err(|e| RemediationError::OperationFailed(format!("public key serialization failed: {e}")))?;
    std::fs::write(&pub_path, format!("{public_line}\n"))
        .map_err(|e| RemediationError::OperationFailed(format!("public key write failed: {e}")))?;

    Ok(public_line)
}

/// Rebuilds `original` with the line at `line_index` replaced by
/// `replacement_line`, preserving every other line and the presence/
/// absence of a trailing newline exactly.
fn rebuild_file(original: &str, line_index: usize, replacement_line: &str) -> String {
    // Split purely on '\n' (never .lines(), which also strips '\r') so
    // every untouched line survives byte-for-byte (D-04), including any
    // CRLF line endings that happen to be present.
    let had_trailing_newline = original.ends_with('\n');
    let mut segments: Vec<String> = original.split('\n').map(|s| s.to_string()).collect();
    if had_trailing_newline {
        segments.pop();
    }
    if line_index < segments.len() {
        segments[line_index] = replacement_line.to_string();
    }
    let mut result = segments.join("\n");
    if had_trailing_newline {
        result.push('\n');
    }
    result
}

fn read_bounded(path: &str) -> Result<String, RemediationError> {
    let bytes = std::fs::read(path)
        .map_err(|e| RemediationError::OperationFailed(format!("read authorized_keys failed: {e}")))?;
    let capped = if bytes.len() > ssh_key_checks::AUTHORIZED_KEYS_READ_CAP {
        &bytes[..ssh_key_checks::AUTHORIZED_KEYS_READ_CAP]
    } else {
        &bytes[..]
    };
    Ok(String::from_utf8_lossy(capped).into_owned())
}

/// D-07 grounded re-verify, factored out so a test can drive the failure
/// branch directly: re-parses `reread_text` (freshly re-read from disk,
/// never the in-memory pre-write string) and requires both that no entry's
/// fingerprint equals `old_fingerprint` and that the entry whose
/// fingerprint equals `new_fingerprint` has a `weak_reason` of `None`,
/// per `ssh_key_checks::weak_reason_for` — this module never re-implements
/// that judgment.
fn verify_rotation_grounded(reread_text: &str, old_fingerprint: &str, new_fingerprint: &str) -> Result<(), String> {
    let entries = ssh_key_checks::parse_authorized_keys(reread_text);
    if entries.iter().any(|e| e.fingerprint == old_fingerprint) {
        return Err(format!("Old fingerprint {old_fingerprint} still present after rotation."));
    }
    match entries.iter().find(|e| e.fingerprint == new_fingerprint) {
        None => Err(format!("New fingerprint {new_fingerprint} not found after rotation.")),
        Some(e) => match &e.weak_reason {
            Some(reason) => Err(format!("New key failed weak-key re-verify: {reason}")),
            None => Ok(()),
        },
    }
}

/// Composes the full destructive rotation: target selection (D-04/D-05),
/// snapshot (D-06), keypair generation, atomic replacement preserving the
/// matched line's options prefix, and the grounded post-write re-verify
/// (D-07) — rolling back and refusing rather than ever reporting success
/// on an unverified file.
pub fn rotate_in_place(authorized_keys_path: &str, fingerprint: &str) -> Result<RotationOutcome, RemediationError> {
    // a. the single guard between the instruction params and a privileged write.
    validate_target(authorized_keys_path)?;

    // b. bounded read.
    let text = read_bounded(authorized_keys_path)?;

    // c. D-05 lockout / D-04 not-found refusals fire here — before any
    //    keypair exists and before any byte is written.
    let target = select_target(&text, fingerprint)?;

    // d. refuse if a prior rotation's key is still pending out-of-band
    //    delivery (D-08) — overwriting it would destroy a credential in
    //    flight.
    let priv_path = rotated_key_path_for(authorized_keys_path)?;
    if priv_path.exists() {
        return Err(RemediationError::OperationFailed(format!(
            "A previously rotated private key already exists at {} — deliver or remove it before rotating again.",
            priv_path.display()
        )));
    }

    // e. the file is now recoverable, and only now may it be modified (D-06).
    snapshot_backup(authorized_keys_path)?;

    // f. generate the replacement.
    let new_comment = sanitize_comment(&target.comment);
    let new_key = generate_replacement(&new_comment)?;
    let new_fingerprint = new_key.fingerprint(ssh_key::HashAlg::Sha256).to_string();

    // g. write the keypair to disk, build the replacement line (options
    //    prefix preserved verbatim), rebuild and write the file.
    let public_line = write_new_keypair(authorized_keys_path, &new_key)?;
    let replacement_line = if target.options_prefix.is_empty() {
        public_line
    } else {
        format!("{} {}", target.options_prefix, public_line)
    };
    let new_text = rebuild_file(&text, target.line_index, &replacement_line);
    write_atomic(Path::new(authorized_keys_path), &new_text)?;

    // h. grounded re-verify — re-read from disk, never reuse the
    //    in-memory pre-write string.
    let reread = std::fs::read_to_string(authorized_keys_path)
        .map_err(|e| RemediationError::OperationFailed(format!("post-write re-read failed: {e}")))?;

    // i. never report success on an unverified file.
    if let Err(reason) = verify_rotation_grounded(&reread, fingerprint, &new_fingerprint) {
        let _ = rollback_rotation(authorized_keys_path);
        return Err(RemediationError::OperationFailed(reason));
    }

    // j. the D-09 boundary — only a fingerprint and a comment leave this function.
    Ok(RotationOutcome {
        new_fingerprint,
        new_comment,
    })
}


#[cfg(test)]
#[path = "ssh_key_rotation_tests.rs"]
mod tests;
