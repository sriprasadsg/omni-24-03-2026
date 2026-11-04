//! Quarantine and restore against real files in temporary directories. No test here touches the
//! real quarantine folder or signals a process.

use super::*;
use crate::capabilities::quarantine_paths::{
    has_dotdot, is_own_file, under_protected, use_temp_paths,
};
use crate::capabilities::response_state::Store;
use std::path::PathBuf;

pub(super) const T0: i64 = 1_761_900_000;

fn contract() -> Option<Value> {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../shared/agent-response-contract.json");
    let text = std::fs::read_to_string(path).ok()?;
    Some(serde_json::from_str(&text).expect("the contract file is valid JSON"))
}

pub(super) struct Fixture {
    pub(super) root: tempfile::TempDir,
    pub(super) paths: QuarantinePaths,
}

pub(super) fn fixture() -> Fixture {
    let root = tempfile::tempdir().unwrap();
    std::fs::create_dir(root.path().join("data")).unwrap();
    let paths = QuarantinePaths::with(
        root.path().join("quarantine"),
        Vec::new(),
        Store::at(root.path().join("response_state.json")),
    );
    Fixture { root, paths }
}

impl Fixture {
    pub(super) fn file(&self, name: &str, body: &[u8]) -> (PathBuf, String) {
        let path = self.root.path().join("data").join(name);
        std::fs::write(&path, body).unwrap();
        let sha = hash_file(&path).unwrap();
        (path, sha)
    }
    pub(super) fn request(&self, path: &Path, sha: &str, id: &str) -> QuarantineRequest {
        QuarantineRequest {
            path: path.to_string_lossy().into_owned(),
            sha256: sha.to_string(),
            allow_protected: false,
            id: id.to_string(),
        }
    }
    pub(super) fn quarantine(&self, req: &QuarantineRequest) -> Value {
        quarantine_at(&self.paths, req, T0, &[])
    }
}

pub(super) fn outcome(body: &Value) -> &str {
    body["outcome"].as_str().unwrap_or("")
}

#[test]
fn a_matching_file_is_moved_with_a_manifest_and_nothing_is_deleted() {
    let f = fixture();
    let (path, sha) = f.file("evil.bin", b"malicious bytes");
    let body = f.quarantine(&f.request(&path, &sha, "task-1"));
    if let Some(c) = contract() {
        assert_eq!(body, c["examples"]["quarantine_moved"]);
    }
    assert_eq!(outcome(&body), "quarantined");
    assert!(!path.exists(), "the original is gone");
    let stored = stored_path(&f.paths, "task-1");
    assert!(stored.exists());
    let manifest: Value =
        serde_json::from_str(&std::fs::read_to_string(manifest_path(&f.paths, "task-1")).unwrap()).unwrap();
    assert_eq!(manifest["originalPath"], path.to_string_lossy().as_ref());
    assert_eq!(manifest["sha256"], sha.as_str());
    assert_eq!(manifest["size"], 15);
    assert_eq!(manifest["quarantinedAt"], T0);
    assert_eq!(manifest["id"], "task-1");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(std::fs::metadata(&stored).unwrap().permissions().mode() & 0o777, 0);
        assert_eq!(std::fs::metadata(&f.paths.dir).unwrap().permissions().mode() & 0o777, 0o700);
    }
    let index = f.paths.store.load().unwrap().quarantine_index;
    assert_eq!(index.len(), 1);
    assert_eq!(index[0]["id"], "task-1");
}

#[test]
fn a_changed_file_is_left_alone_and_answers_hash_mismatch() {
    let f = fixture();
    let (path, sha) = f.file("evil.bin", b"before");
    std::fs::write(&path, b"after").unwrap();
    let body = f.quarantine(&f.request(&path, &sha, "task-1"));
    if let Some(c) = contract() {
        assert_eq!(body, c["examples"]["quarantine_hash_mismatch"]);
    }
    assert_eq!(outcome(&body), "hash_mismatch");
    assert_eq!(std::fs::read(&path).unwrap(), b"after");
    assert!(!stored_path(&f.paths, "task-1").exists());
}

#[test]
fn a_folder_and_a_link_are_refused_and_nothing_moves() {
    let f = fixture();
    let dir = f.root.path().join("data").join("folder");
    std::fs::create_dir(&dir).unwrap();
    let body = f.quarantine(&f.request(&dir, &"0".repeat(64), "task-1"));
    assert_eq!(outcome(&body), "refused");
    assert!(dir.is_dir());
    #[cfg(unix)]
    {
        let (target, sha) = f.file("real.bin", b"x");
        let link = f.root.path().join("data").join("link.bin");
        std::os::unix::fs::symlink(&target, &link).unwrap();
        let body = f.quarantine(&f.request(&link, &sha, "task-2"));
        assert_eq!(outcome(&body), "refused");
        assert!(link.symlink_metadata().is_ok() && target.exists());
    }
}

#[test]
fn an_empty_relative_or_dotdot_path_is_refused() {
    let f = fixture();
    let sha = "0".repeat(64);
    for bad in ["", "evil.bin", "data/evil.bin", "/tmp/../etc/passwd", "/tmp/a/../b"] {
        let req = QuarantineRequest { path: bad.into(), sha256: sha.clone(), allow_protected: true, id: "task-1".into() };
        assert_eq!(outcome(&f.quarantine(&req)), "refused", "{bad:?}");
    }
    let (path, sha) = f.file("evil.bin", b"x");
    let long = "x".repeat(65);
    for bad_id in ["", "has space", "a/b", long.as_str()] {
        let mut req = f.request(&path, &sha, bad_id);
        req.id = bad_id.to_string();
        assert_eq!(outcome(&f.quarantine(&req)), "refused", "{bad_id:?}");
    }
    let mut req = f.request(&path, "not-a-hash", "task-1");
    assert_eq!(outcome(&f.quarantine(&req)), "refused");
    req.sha256 = sha.to_uppercase();
    assert_eq!(outcome(&f.quarantine(&req)), "quarantined", "the hash compares without regard to case");
}

#[test]
fn protected_prefixes_and_the_agents_own_files_answer_protected_path() {
    let mut f = fixture();
    let (path, sha) = f.file("evil.bin", b"x");
    // The agent's own quarantine folder and its own executable are refused, allowed or not.
    let own_exe = f.root.path().join("data").join("omni-agent");
    std::fs::write(&own_exe, b"agent").unwrap();
    f.paths.own_paths = vec![f.paths.dir.clone(), own_exe.clone()];
    let inside = f.paths.dir.join("anything");
    for target in [inside, own_exe.clone()] {
        for allow in [false, true] {
            let mut req = f.request(&target, &sha, "task-1");
            req.allow_protected = allow;
            let body = f.quarantine(&req);
            assert_eq!(outcome(&body), "protected_path", "{target:?} allow={allow}");
            assert_eq!(body["status"], "error");
        }
    }
    assert!(own_exe.exists());
    // A protected prefix is refused unless the instruction allows it.
    f.paths.protected = vec![format!("{}/", f.root.path().join("data").display())];
    let body = f.quarantine(&f.request(&path, &sha, "task-1"));
    assert_eq!(outcome(&body), "protected_path");
    assert!(path.exists());
    let mut req = f.request(&path, &sha, "task-1");
    req.allow_protected = true;
    assert_eq!(outcome(&f.quarantine(&req)), "quarantined");
}

#[test]
fn a_repeat_with_the_same_id_moves_nothing() {
    let f = fixture();
    let (path, sha) = f.file("evil.bin", b"x");
    let req = f.request(&path, &sha, "task-1");
    assert_eq!(outcome(&f.quarantine(&req)), "quarantined");
    let (other, other_sha) = f.file("other.bin", b"y");
    let again = f.quarantine(&req);
    assert_eq!(outcome(&again), "already_applied");
    assert_eq!(again["verify"]["ok"], true);
    // The same id for another file is refused, and that file stays where it is.
    let clash = f.quarantine(&f.request(&other, &other_sha, "task-1"));
    assert_eq!(outcome(&clash), "refused");
    assert!(other.exists());
}

#[test]
fn a_restore_puts_the_file_back_with_its_bytes_and_mode_and_removes_the_manifest() {
    let f = fixture();
    let (path, sha) = f.file("evil.bin", b"restore me");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o640)).unwrap();
    }
    assert_eq!(outcome(&f.quarantine(&f.request(&path, &sha, "task-1"))), "quarantined");
    let body = restore_at(&f.paths, "task-1");
    assert_eq!(body, json!({"status": "success", "outcome": "restored", "verify": {"ok": true, "check": "restored_to_path"}}));
    assert_eq!(std::fs::read(&path).unwrap(), b"restore me");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(std::fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o640);
    }
    assert!(!manifest_path(&f.paths, "task-1").exists());
    assert!(!stored_path(&f.paths, "task-1").exists());
    assert!(f.paths.store.load().unwrap().quarantine_index.is_empty());
    // A second restore of the same id, and a restore of an id never seen, are not_found.
    assert_eq!(outcome(&restore_at(&f.paths, "task-1")), "not_found");
    assert_eq!(outcome(&restore_at(&f.paths, "never-seen")), "not_found");
    assert_eq!(outcome(&restore_at(&f.paths, "bad id")), "refused");
}

#[test]
fn a_restore_refuses_an_existing_destination_and_a_changed_stored_file() {
    let f = fixture();
    let (path, sha) = f.file("evil.bin", b"original");
    f.quarantine(&f.request(&path, &sha, "task-1"));
    std::fs::write(&path, b"a new file stands here").unwrap();
    let body = restore_at(&f.paths, "task-1");
    assert_eq!(outcome(&body), "refused");
    assert_eq!(body["status"], "error");
    assert_eq!(std::fs::read(&path).unwrap(), b"a new file stands here");
    assert!(stored_path(&f.paths, "task-1").exists(), "the stored file stays");
    std::fs::remove_file(&path).unwrap();
    // Change the stored file: restore must not put a different file back.
    let stored = stored_path(&f.paths, "task-1");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&stored, std::fs::Permissions::from_mode(0o600)).unwrap();
    }
    std::fs::write(&stored, b"tampered").unwrap();
    let body = restore_at(&f.paths, "task-1");
    assert_eq!(outcome(&body), "refused");
    assert!(!path.exists());
    assert!(stored.exists());
}

#[cfg(unix)]
#[test]
fn a_restore_refuses_a_destination_folder_that_is_a_link() {
    let f = fixture();
    let (path, sha) = f.file("evil.bin", b"x");
    f.quarantine(&f.request(&path, &sha, "task-1"));
    let data = f.root.path().join("data");
    let elsewhere = f.root.path().join("elsewhere");
    std::fs::create_dir(&elsewhere).unwrap();
    std::fs::remove_dir(&data).unwrap();
    std::os::unix::fs::symlink(&elsewhere, &data).unwrap();
    assert_eq!(outcome(&restore_at(&f.paths, "task-1")), "refused");
    assert!(!elsewhere.join("evil.bin").exists());
    assert!(stored_path(&f.paths, "task-1").exists());
}

fn crossing(_: &Path, _: &Path) -> io::Result<()> {
    Err(io::Error::from(io::ErrorKind::CrossesDevices))
}
fn cannot_remove(_: &Path) -> io::Result<()> {
    Err(io::Error::from(io::ErrorKind::PermissionDenied))
}

#[test]
fn a_copy_across_volumes_that_cannot_remove_the_original_removes_only_its_copy() {
    let f = fixture();
    let (path, sha) = f.file("evil.bin", b"keep me");
    let ops = FileOps { rename: crossing, remove_original: cannot_remove };
    let running = RunningProcess { pid: 4242, name: "evil.exe".into(), start_time: 1_761_900_000, exe: Some(path.to_string_lossy().into_owned()) };
    let body = quarantine_with(&f.paths, &f.request(&path, &sha, "task-1"), T0, &[running.clone()], &Vec::new, &ops);
    assert_eq!(outcome(&body), "locked");
    assert_eq!(body["still_running"], json!([{"pid": 4242, "name": "evil.exe", "start_time": 1_761_900_000u64}]));
    assert_eq!(std::fs::read(&path).unwrap(), b"keep me", "the person's file is untouched");
    assert!(!stored_path(&f.paths, "task-1").exists(), "our copy is removed");
    assert!(!manifest_path(&f.paths, "task-1").exists());
    // Without a running process the body equals the contract's locked example.
    let body = quarantine_with(&f.paths, &f.request(&path, &sha, "task-1"), T0, &[], &Vec::new, &ops);
    if let Some(c) = contract() {
        assert_eq!(body, c["examples"]["quarantine_locked"]);
    }
}

#[test]
fn a_copy_across_volumes_removes_the_original_only_after_it_hashed_the_copy() {
    let f = fixture();
    let (path, sha) = f.file("evil.bin", b"moved by copy");
    let ops = FileOps { rename: crossing, remove_original: FileOps::REAL.remove_original };
    let body = quarantine_with(&f.paths, &f.request(&path, &sha, "task-1"), T0, &[], &Vec::new, &ops);
    assert_eq!(outcome(&body), "quarantined");
    assert_eq!(body["verify"]["ok"], true);
    assert!(!path.exists());
    assert_eq!(hash_stored(&stored_path(&f.paths, "task-1")).unwrap(), sha);
}

#[test]
fn a_moved_file_whose_process_still_runs_is_reported_with_pid_name_and_start_time() {
    let f = fixture();
    let (path, sha) = f.file("evil.bin", b"x");
    let exe = Some(path.to_string_lossy().into_owned());
    let running = RunningProcess { pid: 4242, name: "evil.exe".into(), start_time: 1_761_900_000, exe: exe.clone() };
    let unrelated = RunningProcess { pid: 7, name: "other".into(), start_time: 1, exe: Some("/usr/bin/other".into()) };
    let still = vec![running.clone()];
    let body = quarantine_with(
        &f.paths,
        &f.request(&path, &sha, "task-1"),
        T0,
        &[running, unrelated],
        &|| still.clone(),
        &FileOps::REAL,
    );
    if let Some(c) = contract() {
        assert_eq!(body, c["examples"]["quarantine_moved_still_running"]);
    }
    assert_eq!(outcome(&body), "quarantined");
    assert_eq!(body["still_running"].as_array().unwrap().len(), 1);
}

#[test]
fn a_listed_process_that_left_is_not_reported() {
    let f = fixture();
    let (path, sha) = f.file("evil.bin", b"x");
    let running = RunningProcess { pid: 4242, name: "evil.exe".into(), start_time: 100, exe: Some(path.to_string_lossy().into_owned()) };
    // The pid is back after the move with another start time: a different process.
    let reused = RunningProcess { start_time: 9_000, ..running.clone() };
    let body = quarantine_with(&f.paths, &f.request(&path, &sha, "task-1"), T0, &[running], &|| vec![reused.clone()], &FileOps::REAL);
    assert!(body.get("still_running").is_none());
}

#[test]
fn the_protected_lists_equal_the_contracts() {
    let Some(c) = contract() else { return };
    let strings = |v: &Value| -> Vec<String> { v.as_array().unwrap().iter().map(|s| s.as_str().unwrap().to_string()).collect() };
    assert_eq!(strings(&c["protectedPaths"]["windows"]), PROTECTED_WINDOWS);
    assert_eq!(strings(&c["protectedPaths"]["linux"]), PROTECTED_LINUX);
    assert_eq!(c["stillRunningCap"], STILL_RUNNING_CAP);
}

#[test]
fn same_exe_follows_each_platforms_rules() {
    assert!(same_exe(Some("/usr/bin/evil"), "/usr/bin/evil", false));
    assert!(!same_exe(Some("/usr/bin/Evil"), "/usr/bin/evil", false), "Linux is case-sensitive");
    assert!(same_exe(Some("C:\\Temp\\Evil.EXE"), "c:/temp/evil.exe", true));
    assert!(same_exe(Some("\\\\?\\C:\\Temp\\evil.exe"), "C:\\Temp\\evil.exe", true));
    assert!(!same_exe(Some("C:\\Temp\\evil.exe"), "C:\\Temp\\other.exe", true));
    for windows in [false, true] {
        assert!(!same_exe(None, "/x", windows));
        assert!(!same_exe(Some(""), "", windows));
        assert!(!same_exe(Some(""), "/x", windows));
        assert!(!same_exe(Some("/x"), "", windows));
    }
}

#[test]
fn the_stored_name_is_built_in_one_place_in_each_style() {
    let mut f = fixture();
    assert_eq!(stored_path(&f.paths, "task-1"), f.paths.dir.join("task-1"));
    f.paths.windows_style = true;
    assert_eq!(stored_path(&f.paths, "task-1"), f.paths.dir.join("task-1.q"));
    assert_eq!(manifest_path(&f.paths, "task-1"), f.paths.dir.join("task-1.json"));
}

#[test]
fn windows_style_paths_are_checked_as_text() {
    let protected: Vec<String> = PROTECTED_WINDOWS.iter().map(|s| s.to_string()).collect();
    let norm = |p: &str| normalize(p, true);
    for hit in [
        "C:\\Windows\\System32\\cmd.exe",
        "d:/WINDOWS/system32/x.dll",
        "\\\\?\\C:\\Windows\\SysWOW64\\a.exe",
        "C:\\Windows\\WinSxS\\x\\y",
        "c:\\program files\\omniagentrust\\omni-agent.exe",
        "C:\\ProgramData\\OmniAgent\\quarantine\\a",
        "C:\\Windows\\System32",
    ] {
        assert!(under_protected(&norm(hit), &protected, true), "{hit}");
    }
    for miss in ["C:\\Windows\\System32Evil\\a.exe", "C:\\Users\\a\\System32\\x.exe", "C:\\Temp\\evil.exe", "\\\\server\\share\\a"] {
        assert!(!under_protected(&norm(miss), &protected, true), "{miss}");
    }
    assert!(is_absolute(&norm("C:\\a\\b"), true) && is_absolute(&norm("\\\\srv\\share\\a"), true));
    assert!(!is_absolute(&norm("a\\b.exe"), true) && !is_absolute(&norm("\\a"), true));
    assert!(has_dotdot("C:\\a\\..\\b", true) && has_dotdot("C:/a/../b", true) && !has_dotdot("C:\\a..b\\c", true));
    assert!(!has_dotdot("/a\\..\\b", false), "a backslash is an ordinary character on Linux");
}

#[test]
fn linux_prefixes_match_whole_folders_only() {
    let protected: Vec<String> = PROTECTED_LINUX.iter().map(|s| s.to_string()).collect();
    for hit in ["/usr/bin/ls", "/bin/sh", "/etc/passwd", "/etc", "/var/lib/omni-agent/quarantine/x", "/boot/vmlinuz"] {
        assert!(under_protected(hit, &protected, false), "{hit}");
    }
    for miss in ["/etcetera/x", "/usr/binary/x", "/tmp/a", "/home/u/bin/x", "/var/lib/omni-agent2/x"] {
        assert!(!under_protected(miss, &protected, false), "{miss}");
    }
}

#[test]
fn own_files_are_matched_by_folder_and_by_exact_file() {
    let mut f = fixture();
    f.paths.own_paths = vec![PathBuf::from("/opt/agent/quarantine"), PathBuf::from("/opt/agent/omni-agent")];
    assert!(is_own_file(&f.paths, "/opt/agent/quarantine/x"));
    assert!(is_own_file(&f.paths, "/opt/agent/omni-agent"));
    assert!(!is_own_file(&f.paths, "/opt/agent/omni-agent2"));
    assert!(!is_own_file(&f.paths, "/opt/agent/quarantine2/x"));
}

#[tokio::test]
async fn the_dispatch_arms_move_and_restore_with_the_overridden_paths() {
    let _dir = use_temp_paths();
    let work = tempfile::tempdir().unwrap();
    let path = work.path().join("evil.bin");
    std::fs::write(&path, b"dispatch").unwrap();
    let sha = hash_file(&path).unwrap();
    let cfg = crate::capabilities::response_contract_tests::test_cfg();
    let client = reqwest::Client::new();
    let item = json!({"task_id": "task-9", "parameters": {"path": path.to_string_lossy(), "sha256": sha}});
    // The work runs off the poll loop (WR-22): `accepted` now, the final body once that was posted.
    let body = crate::capabilities::response_actions::handle("quarantine_file", &item, &cfg, &client).await;
    assert_eq!(body, json!({"status": "accepted"}));
    let body = crate::instructions::final_body("task-9").await.expect("a final body");
    assert_eq!(outcome(&body), "quarantined", "{body}");
    assert!(!path.exists());
    let undo = json!({"task_id": "task-9u", "parameters": {"quarantine_id": "task-9"}});
    let body = crate::capabilities::response_actions::handle("unquarantine_file", &undo, &cfg, &client).await;
    assert_eq!(body, json!({"status": "accepted"}));
    let body = crate::instructions::final_body("task-9u").await.expect("a final body");
    assert_eq!(outcome(&body), "restored", "{body}");
    assert_eq!(std::fs::read(&path).unwrap(), b"dispatch");
    // A missing parameter is a refusal, not a panic.
    let body = crate::capabilities::response_actions::handle("quarantine_file", &json!({"task_id": "t"}), &cfg, &client).await;
    assert_eq!(outcome(&body), "refused");
    let body = crate::capabilities::response_actions::handle("unquarantine_file", &json!({}), &cfg, &client).await;
    assert_eq!(outcome(&body), "refused");
}

#[test]
fn running_now_lists_this_process_once_with_its_start_time_and_exe() {
    let list = running_now();
    let own: Vec<_> = list.iter().filter(|p| p.pid == std::process::id()).collect();
    assert_eq!(own.len(), 1);
    assert!(own[0].start_time > 0);
    assert!(own[0].exe.is_some());
    assert!(list.iter().all(|p| p.pid > 0));
}

#[test]
fn a_quarantine_does_not_hold_the_state_lock_while_it_moves_the_file() {
    // WR-22: block expiry and the isolation revert must never wait behind a large file.
    let f = fixture();
    let (path, sha) = f.file("evil.bin", b"x");
    let other = Store::at(f.root.path().join("other.json"));
    let free = std::cell::Cell::new(false);
    let later = || {
        let other = other.clone();
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let _ = other.update(|s| s.add_claim("45.33.32.156", "a", 2, 1));
            let _ = tx.send(());
        });
        free.set(rx.recv_timeout(std::time::Duration::from_secs(2)).is_ok());
        Vec::new()
    };
    let body = quarantine_with(&f.paths, &f.request(&path, &sha, "task-1"), T0, &[], &later, &FileOps::REAL);
    assert_eq!(outcome(&body), "quarantined");
    assert!(free.get(), "the state lock was held while the file was moved");
}
