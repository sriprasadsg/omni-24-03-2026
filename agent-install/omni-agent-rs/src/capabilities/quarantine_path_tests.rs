//! WR-13: a path is judged by where the file really is, not by its text. Real files in temporary
//! directories; the only system files read are hashed against a hash that never matches.

use super::tests::*;
use super::*;

#[cfg(target_os = "linux")]
#[test]
fn another_spelling_of_a_protected_folder_is_still_protected() {
    // The hash never matches, so even the unfixed code moves nothing here.
    let f = fixture();
    for path in ["//etc/passwd", "/./etc/passwd", "/usr//bin/env"] {
        let req = QuarantineRequest { path: path.into(), sha256: "0".repeat(64), allow_protected: false, id: "task-1".into() };
        assert_eq!(outcome(&f.quarantine(&req)), "protected_path", "{path}");
    }
}

#[cfg(unix)]
#[test]
fn a_link_in_a_parent_folder_does_not_get_a_protected_or_own_file_moved() {
    let mut f = fixture();
    let prot = f.root.path().join("prot");
    std::fs::create_dir(&prot).unwrap();
    std::fs::write(prot.join("secret.bin"), b"system").unwrap();
    let sha = hash_file(&prot.join("secret.bin")).unwrap();
    f.paths.protected = vec![format!("{}/", prot.display())];
    let alias = f.root.path().join("data").join("alias");
    std::os::unix::fs::symlink(&prot, &alias).unwrap();
    assert_eq!(outcome(&f.quarantine(&f.request(&alias.join("secret.bin"), &sha, "task-1"))), "protected_path");
    assert!(prot.join("secret.bin").exists());
    // The agent's own executable through a linked folder: refused even when protected paths are allowed.
    let (own, own_sha) = f.file("omni-agent", b"agent");
    f.paths.own_paths = vec![own.clone()];
    let link = f.root.path().join("linked-data");
    std::os::unix::fs::symlink(f.root.path().join("data"), &link).unwrap();
    let mut req = f.request(&link.join("omni-agent"), &own_sha, "task-2");
    req.allow_protected = true;
    assert_eq!(outcome(&f.quarantine(&req)), "protected_path");
    assert!(own.exists());
}

#[cfg(unix)]
#[test]
fn a_protected_folder_that_is_itself_a_link_protects_where_it_points() {
    // `/lib64 -> usr/lib64` on a merged-/usr system: the real folder is protected too.
    let mut f = fixture();
    let real = f.root.path().join("real-lib");
    std::fs::create_dir(&real).unwrap();
    let link = f.root.path().join("lib-link");
    std::os::unix::fs::symlink(&real, &link).unwrap();
    std::fs::write(real.join("libc.so"), b"lib").unwrap();
    let sha = hash_file(&real.join("libc.so")).unwrap();
    f.paths.protected = vec![format!("{}/", link.display())];
    assert_eq!(outcome(&f.quarantine(&f.request(&real.join("libc.so"), &sha, "task-1"))), "protected_path");
    assert!(real.join("libc.so").exists());
}

#[test]
fn windows_forms_the_text_checks_cannot_judge_are_refused() {
    let mut f = fixture();
    f.paths.windows_style = true;
    for bad in [
        "C:\\Windows\\System32.\\x.dll", "C:\\Windows\\System32 \\x.dll", "C:\\Windows\\\\System32\\x.dll",
        "C:\\Windows\\.\\System32\\x.dll", "C:\\Windows\\System32\\x.dll::$DATA", "C:\\Temp\\a.txt:stream",
        "\\\\localhost\\C$\\Windows\\System32\\x.dll", "\\\\.\\C:\\Windows\\x.dll", "\\\\?\\UNC\\srv\\share\\x",
    ] {
        let req = QuarantineRequest { path: bad.into(), sha256: "0".repeat(64), allow_protected: false, id: "task-1".into() };
        let body = f.quarantine(&req);
        assert_eq!(outcome(&body), "refused", "{bad}");
        // `\\?\UNC\..` is not a full path once its prefix is read, so an earlier check refuses it.
        let earlier = bad.starts_with("\\\\?\\UNC");
        assert!(earlier || body["error"].as_str().unwrap().contains("cannot be checked"), "{bad}: {body}");
    }
}

