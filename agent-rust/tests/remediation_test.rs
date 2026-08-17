use omni_agent::scanner::ssh_key_rotation::{backup_key, generate_new_key, verify_rotation};
use std::fs;
use tempfile::tempdir;

#[test]
fn test_remediation_rotation_flow() {
    let dir = tempdir().unwrap();
    let weak_key_path = dir.path().join("id_rsa_weak");
    fs::write(&weak_key_path, "weak key content").unwrap();

    // Simulate remediation flow:
    // 1. Backup
    let backup_path = backup_key(&weak_key_path).unwrap();
    assert!(backup_path.exists());

    // 2. Generate new key
    generate_new_key(&weak_key_path).unwrap();

    // 3. Verify
    assert!(verify_rotation(&weak_key_path).is_ok());
}
