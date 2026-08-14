use omni_agent::scanner::ssh_key_rotation::{backup_key, generate_new_key, update_authorized_keys, verify_rotation};
use std::path::{Path, PathBuf};
use std::fs;
use tempfile::tempdir;

#[test]
fn test_backup_key() {
    let dir = tempdir().unwrap();
    let original_key_path = dir.path().join("id_rsa");
    fs::write(&original_key_path, "original key content").unwrap();

    let backup_path = backup_key(&original_key_path).unwrap();
    assert!(backup_path.exists());
    assert_eq!(fs::read_to_string(&backup_path).unwrap(), "original key content");
    assert_eq!(backup_path, original_key_path.with_extension("bak"));
}

#[test]
fn test_generate_new_key() {
    let dir = tempdir().unwrap();
    let new_key_path = dir.path().join("id_ed25519");

    generate_new_key(&new_key_path).unwrap();
    assert!(new_key_path.exists());
    assert!(new_key_path.with_extension("pub").exists());
    assert!(!fs::read_to_string(&new_key_path).unwrap().is_empty());
    assert!(!fs::read_to_string(&new_key_path.with_extension("pub")).unwrap().is_empty());
}

#[test]
fn test_update_authorized_keys() {
    // This test is harder to implement without actual file operations and content
    // For now, testing the placeholder function returns Ok(())
    assert!(update_authorized_keys("old_pub", "new_pub").is_ok());
}

#[test]
fn test_verify_rotation() {
    let dir = tempdir().unwrap();
    let key_path = dir.path().join("id_ed25519");
    fs::write(&key_path, "new key content").unwrap();

    assert!(verify_rotation(&key_path).is_ok());

    let non_existent_key_path = dir.path().join("non_existent_key");
    assert!(verify_rotation(&non_existent_key_path).is_err());
}
