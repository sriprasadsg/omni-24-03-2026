//! Test module for `ssh_key_rotation.rs`, split into a sibling file
//! purely to keep the production module under the project's 500-line
//! cap (CLAUDE.md) without trimming test behavior. Included via
//! `#[path = "ssh_key_rotation_tests.rs"] mod tests;` in the parent
//! module, so `use super::*;` below reaches everything in
//! `ssh_key_rotation.rs`.

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

// ── sanitize_comment ────────────────────────────────────────────────

#[test]
fn rotate_key_sanitize_comment_strips_and_bounds() {
    let raw = "bad comment; rm -rf /\nwith spaces\tand a tab $(evil) ".repeat(3);
    let sanitized = sanitize_comment(&raw);
    assert!(sanitized
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '@' | '-')));
    assert!(sanitized.len() <= MAX_COMMENT_LEN);
    assert!(!sanitized.is_empty());

    let empty = sanitize_comment("");
    assert!(!empty.is_empty());
}

// ── rotate_in_place ──────────────────────────────────────────────────

fn write_fixture(dir: &Path, lines: &[String]) -> PathBuf {
    let path = dir.join("authorized_keys");
    let content = lines.join("\n") + "\n";
    std::fs::write(&path, content).unwrap();
    path
}

#[test]
fn rotate_key_rotate_in_place_three_entry_success() {
    let dir = tempdir().unwrap();
    let l1 = sample_key_line("one");
    let l2 = sample_key_line("two");
    let l3 = sample_key_line("three");
    let path = write_fixture(dir.path(), &[l1, l2.clone(), l3]);
    let fp2 = fingerprint_of(&l2);

    let outcome = rotate_in_place(path.to_str().unwrap(), &fp2).expect("rotation should succeed");

    let after = std::fs::read_to_string(&path).unwrap();
    let entries = ssh_key_checks::parse_authorized_keys(&after);
    assert_eq!(entries.len(), 3);
    assert!(entries.iter().all(|e| e.fingerprint != fp2));
    assert!(entries.iter().any(|e| e.fingerprint == outcome.new_fingerprint));
}

#[test]
fn rotate_key_rotate_in_place_untouched_lines_byte_identical_and_ordered() {
    let dir = tempdir().unwrap();
    let l1 = sample_key_line("one");
    let l2 = sample_key_line("two");
    let l3 = sample_key_line("three");
    let path = write_fixture(dir.path(), &[l1.clone(), l2.clone(), l3.clone()]);
    let fp2 = fingerprint_of(&l2);

    rotate_in_place(path.to_str().unwrap(), &fp2).expect("rotation should succeed");

    let after = std::fs::read_to_string(&path).unwrap();
    let after_lines: Vec<&str> = after.split('\n').collect();
    assert_eq!(after_lines[0], l1);
    assert_eq!(after_lines[2], l3);
}

#[test]
fn rotate_key_rotate_in_place_preserves_options_prefix() {
    let dir = tempdir().unwrap();
    let l1 = sample_key_line("one");
    let bare = sample_key_line("two");
    let l2 = format!("command=\"/usr/bin/true\",no-pty {bare}");
    let l3 = sample_key_line("three");
    let path = write_fixture(dir.path(), &[l1, l2, l3]);
    let fp2 = fingerprint_of(&bare);

    rotate_in_place(path.to_str().unwrap(), &fp2).expect("rotation should succeed");

    let after = std::fs::read_to_string(&path).unwrap();
    let after_lines: Vec<&str> = after.split('\n').collect();
    assert!(after_lines[1].starts_with("command=\"/usr/bin/true\",no-pty "));
}

#[test]
fn rotate_key_rotate_in_place_outcome_never_leaks_private_key() {
    let dir = tempdir().unwrap();
    let l1 = sample_key_line("one");
    let l2 = sample_key_line("two");
    let l3 = sample_key_line("three");
    let path = write_fixture(dir.path(), &[l1, l2.clone(), l3]);
    let fp2 = fingerprint_of(&l2);

    let outcome = rotate_in_place(path.to_str().unwrap(), &fp2).expect("rotation should succeed");
    let debug_repr = format!("{outcome:?}");
    assert!(!debug_repr.contains("-----BEGIN"));

    let rk_path = rotated_key_path_for(path.to_str().unwrap()).unwrap();
    let private_key_contents = std::fs::read_to_string(&rk_path).unwrap();
    assert!(!debug_repr.contains(&private_key_contents));
}

#[test]
fn rotate_key_rotate_in_place_writes_private_key_owner_only_and_pub_sibling() {
    let dir = tempdir().unwrap();
    let l1 = sample_key_line("one");
    let l2 = sample_key_line("two");
    let l3 = sample_key_line("three");
    let path = write_fixture(dir.path(), &[l1, l2.clone(), l3]);
    let fp2 = fingerprint_of(&l2);

    rotate_in_place(path.to_str().unwrap(), &fp2).expect("rotation should succeed");

    let rk_path = rotated_key_path_for(path.to_str().unwrap()).unwrap();
    assert!(rk_path.exists());
    assert!(rk_path.with_extension("pub").exists());

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = std::fs::metadata(&rk_path).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o600);
    }
}

#[test]
fn rotate_key_rotate_in_place_refuses_when_pending_rotated_key_exists() {
    let dir = tempdir().unwrap();
    let l1 = sample_key_line("one");
    let l2 = sample_key_line("two");
    let l3 = sample_key_line("three");
    let path = write_fixture(dir.path(), &[l1, l2.clone(), l3]);
    let fp2 = fingerprint_of(&l2);

    let rk_path = rotated_key_path_for(path.to_str().unwrap()).unwrap();
    std::fs::write(&rk_path, "a private key pending out-of-band delivery").unwrap();

    let before = std::fs::read_to_string(&path).unwrap();
    let result = rotate_in_place(path.to_str().unwrap(), &fp2);
    assert!(result.is_err());
    assert_eq!(std::fs::read_to_string(&path).unwrap(), before);
}

#[test]
fn rotate_key_rotate_in_place_sole_entry_refuses_lockout_untouched() {
    let dir = tempdir().unwrap();
    let l1 = sample_key_line("only");
    let path = write_fixture(dir.path(), &[l1.clone()]);
    let fp1 = fingerprint_of(&l1);
    let before = std::fs::read_to_string(&path).unwrap();

    let result = rotate_in_place(path.to_str().unwrap(), &fp1);
    assert!(matches!(result, Err(RemediationError::LockoutRefused(_))));
    assert_eq!(std::fs::read_to_string(&path).unwrap(), before);

    let backup_path = backup_path_for(path.to_str().unwrap());
    assert!(!Path::new(&backup_path).exists());
    let rk_path = rotated_key_path_for(path.to_str().unwrap()).unwrap();
    assert!(!rk_path.exists());
}

// ── D-07 grounded re-verify ─────────────────────────────────────────

#[test]
fn rotate_key_verify_rotation_grounded_fails_when_old_fingerprint_still_present() {
    let l1 = sample_key_line("one");
    let l2 = sample_key_line("two");
    let text = format!("{l1}\n{l2}\n");
    let fp1 = fingerprint_of(&l1);
    let fp2 = fingerprint_of(&l2);

    // A "rotation" that didn't actually remove the old fingerprint.
    let result = verify_rotation_grounded(&text, &fp1, &fp2);
    assert!(result.is_err());
}

#[test]
fn rotate_key_verify_rotation_grounded_fails_when_new_entry_is_weak() {
    // DSA is unconditionally weak per ssh_key_checks::weak_reason_for,
    // regardless of bit length — deterministic without depending on
    // ssh-key's default RSA key-size choice.
    let weak = ssh_key::PrivateKey::random(&mut rand::rngs::OsRng, ssh_key::Algorithm::Dsa)
        .expect("dsa keygen for test fixture");
    let weak_line = weak.public_key().to_openssh().expect("encode weak key");
    let text = format!("{weak_line}\n");
    let new_fp = fingerprint_of(&weak_line);

    let result = verify_rotation_grounded(&text, "SHA256:old-not-present-anywhere", &new_fp);
    assert!(result.is_err());
}

#[test]
fn rotate_key_rotate_in_place_duplicate_fingerprint_fails_reverify_and_rolls_back() {
    let dir = tempdir().unwrap();
    let dup = sample_key_line("duplicate");
    let other = sample_key_line("other");
    // The same underlying key appears twice (line 0 and line 2) plus
    // one distinct entry — 3 total parseable entries, so D-05 doesn't
    // fire, but rotating only the first occurrence leaves the second
    // with the stale fingerprint, so the real grounded re-verify
    // genuinely fails without any test-only mocking.
    let path = write_fixture(dir.path(), &[dup.clone(), other, dup.clone()]);
    let fp = fingerprint_of(&dup);
    let before = std::fs::read_to_string(&path).unwrap();

    let result = rotate_in_place(path.to_str().unwrap(), &fp);
    assert!(result.is_err());
    assert_eq!(
        std::fs::read_to_string(&path).unwrap(),
        before,
        "file must be restored byte-for-byte after a failed re-verify"
    );
}

#[test]
fn rotate_key_rotate_in_place_uses_real_csprng_not_fixed_seed() {
    let dir1 = tempdir().unwrap();
    let l1a = sample_key_line("one");
    let l1b = sample_key_line("two");
    let l1c = sample_key_line("three");
    let path1 = write_fixture(dir1.path(), &[l1a, l1b.clone(), l1c]);
    let fp1b = fingerprint_of(&l1b);
    let outcome1 = rotate_in_place(path1.to_str().unwrap(), &fp1b).expect("rotation 1 should succeed");

    let dir2 = tempdir().unwrap();
    let l2a = sample_key_line("one");
    let l2b = sample_key_line("two");
    let l2c = sample_key_line("three");
    let path2 = write_fixture(dir2.path(), &[l2a, l2b.clone(), l2c]);
    let fp2b = fingerprint_of(&l2b);
    let outcome2 = rotate_in_place(path2.to_str().unwrap(), &fp2b).expect("rotation 2 should succeed");

    assert_ne!(outcome1.new_fingerprint, outcome2.new_fingerprint);
}
