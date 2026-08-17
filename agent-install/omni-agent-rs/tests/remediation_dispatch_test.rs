/// Integration tests for the `rotate_key` / `rotate_key_rollback` dispatch
/// arms added to `instructions.rs` in plan 64-04. These drive the real
/// `compute_instruction_result` dispatcher (the same match statement the
/// live agent runs) with a constructed instruction `item` JSON value
/// against a real fixture `authorized_keys` file — not the underlying
/// `remediation_actions`/`ssh_key_rotation` functions directly.
use omni_agent::config::Config;
use omni_agent::instructions::compute_instruction_result;
use serde_json::json;
use std::path::PathBuf;

fn test_config() -> Config {
    serde_norway::from_str(
        "api_base_url: http://127.0.0.1:1\n\
         tenant_id: tenant_test\n\
         agent_id: agent_test\n\
         agent_token: tok_test\n\
         registration_key: reg_test\n",
    )
    .expect("parse test config")
}

fn test_client() -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(2))
        .build()
        .expect("build test http client")
}

/// Generates a real, freshly-random Ed25519 public key line for test
/// fixtures — never a hardcoded key, never any private key material.
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

/// Builds a fresh `<tempdir>/authorized_keys` fixture with 3 entries and
/// returns (dir, path, fingerprints-by-comment). `is_authorized_keys_path`
/// requires the file be literally named `authorized_keys`.
fn multi_entry_fixture() -> (tempfile::TempDir, PathBuf, String, String, String) {
    let dir = tempfile::tempdir().expect("tempdir");
    let path = dir.path().join("authorized_keys");
    let l1 = sample_key_line("one");
    let l2 = sample_key_line("two");
    let l3 = sample_key_line("three");
    let fp1 = fingerprint_of(&l1);
    let fp2 = fingerprint_of(&l2);
    let fp3 = fingerprint_of(&l3);
    std::fs::write(&path, format!("{l1}\n{l2}\n{l3}\n")).expect("write fixture");
    (dir, path, fp1, fp2, fp3)
}

// ── Test 1: successful rotation via the real dispatcher ────────────────────

#[tokio::test]
async fn dispatch_rotate_key_success_returns_no_path_or_key_material() {
    let (_dir, path, _fp1, fp2, _fp3) = multi_entry_fixture();
    let cfg = test_config();
    let client = test_client();
    let item = json!({
        "action": "rotate_key",
        "parameters": {
            "fingerprint": fp2,
            "authorized_keys_path": path.to_str().unwrap(),
        }
    });

    let result = compute_instruction_result("rotate_key", "rotate_key", &item, &cfg, &client)
        .await
        .expect("rotate_key must return Some");

    assert_eq!(result["status"], "success");
    assert!(result["new_fingerprint"].as_str().is_some_and(|s| !s.is_empty()));
    assert!(result["new_comment"].as_str().is_some_and(|s| !s.is_empty()));
    // D-09: no filesystem path, no private key material anywhere in the response.
    let serialized = result.to_string();
    assert!(!serialized.contains(path.to_str().unwrap()));
    assert!(!serialized.contains("PRIVATE KEY"));
    assert!(result.get("authorized_keys_path").is_none());
}

// ── Test 2: unknown fingerprint — structured error, fixture untouched ──────

#[tokio::test]
async fn dispatch_rotate_key_unknown_fingerprint_errors_and_leaves_file_untouched() {
    let (_dir, path, _fp1, _fp2, _fp3) = multi_entry_fixture();
    let before = std::fs::read(&path).expect("read fixture before");
    let cfg = test_config();
    let client = test_client();
    let item = json!({
        "action": "rotate_key",
        "parameters": {
            "fingerprint": "SHA256:doesnotexistanywhereinthisfile00000000000",
            "authorized_keys_path": path.to_str().unwrap(),
        }
    });

    let result = compute_instruction_result("rotate_key", "rotate_key", &item, &cfg, &client)
        .await
        .expect("rotate_key must return Some");

    assert_eq!(result["status"], "error");
    let err = result["error"].as_str().expect("error string present");
    assert!(!err.is_empty());
    assert!(err.to_lowercase().contains("not found") || err.to_lowercase().contains("no authorized_keys entry"));

    let after = std::fs::read(&path).expect("read fixture after");
    assert_eq!(before, after, "fixture must be byte-for-byte unchanged on error");
}

// ── Test 3: missing parameters — structured error, never a panic ───────────

#[tokio::test]
async fn dispatch_rotate_key_missing_parameters_errors_not_panics() {
    let cfg = test_config();
    let client = test_client();
    let item = json!({"action": "rotate_key", "parameters": {}});

    let result = compute_instruction_result("rotate_key", "rotate_key", &item, &cfg, &client)
        .await
        .expect("rotate_key must return Some");

    assert_eq!(result["status"], "error");
    assert!(result["error"].as_str().is_some_and(|s| !s.is_empty()));
}

// ── Test 4: rollback restores a prior rotation byte-for-byte ───────────────

#[tokio::test]
async fn dispatch_rotate_key_rollback_restores_byte_for_byte() {
    let (_dir, path, _fp1, fp2, _fp3) = multi_entry_fixture();
    let before_rotation = std::fs::read(&path).expect("read fixture before rotation");
    let cfg = test_config();
    let client = test_client();

    // First, rotate for real through the dispatcher.
    let rotate_item = json!({
        "action": "rotate_key",
        "parameters": {"fingerprint": fp2, "authorized_keys_path": path.to_str().unwrap()},
    });
    let rotate_result =
        compute_instruction_result("rotate_key", "rotate_key", &rotate_item, &cfg, &client)
            .await
            .expect("rotate_key must return Some");
    assert_eq!(rotate_result["status"], "success");
    let after_rotation = std::fs::read(&path).expect("read fixture after rotation");
    assert_ne!(before_rotation, after_rotation, "rotation must have changed the file");

    // Then roll it back through the dispatcher.
    let rollback_item = json!({
        "action": "rotate_key_rollback",
        "parameters": {"authorized_keys_path": path.to_str().unwrap()},
    });
    let rollback_result = compute_instruction_result(
        "rotate_key_rollback",
        "rotate_key_rollback",
        &rollback_item,
        &cfg,
        &client,
    )
    .await
    .expect("rotate_key_rollback must return Some");

    assert_eq!(rollback_result["status"], "success");
    let after_rollback = std::fs::read(&path).expect("read fixture after rollback");
    assert_eq!(before_rotation, after_rollback, "rollback must restore the file byte-for-byte");
}

// ── Test 5: rollback with no prior rotation/snapshot — error, untouched ────

#[tokio::test]
async fn dispatch_rotate_key_rollback_without_prior_rotation_errors_and_leaves_file_untouched() {
    let (_dir, path, _fp1, _fp2, _fp3) = multi_entry_fixture();
    let before = std::fs::read(&path).expect("read fixture before");
    let cfg = test_config();
    let client = test_client();
    let item = json!({
        "action": "rotate_key_rollback",
        "parameters": {"authorized_keys_path": path.to_str().unwrap()},
    });

    let result = compute_instruction_result(
        "rotate_key_rollback",
        "rotate_key_rollback",
        &item,
        &cfg,
        &client,
    )
    .await
    .expect("rotate_key_rollback must return Some");

    assert_eq!(result["status"], "error");
    assert!(result["error"].as_str().is_some_and(|s| !s.is_empty()));

    let after = std::fs::read(&path).expect("read fixture after");
    assert_eq!(before, after, "fixture must be byte-for-byte unchanged when there is nothing to roll back");
}
