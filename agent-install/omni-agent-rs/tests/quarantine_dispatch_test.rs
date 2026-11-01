//! Quarantine and kill against real files and one real child process, all in temporary
//! directories. These tests call `quarantine_at` and `restore_at` with explicit paths: the
//! integration build has no recorder seam and `/var/lib/omni-agent` is not writable here, so
//! nothing here may go through the dispatch arm with the default paths, and nothing here touches
//! a firewall or a service.

use omni_agent::capabilities::quarantine::{
    manifest_path, quarantine_at, restore_at, running_now, same_exe, stored_path, QuarantinePaths,
    QuarantineRequest,
};
use omni_agent::capabilities::response_state::Store;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

const T0: i64 = 1_761_900_000;

fn sha_of(path: &Path) -> String {
    hex::encode(Sha256::digest(std::fs::read(path).unwrap()))
}

fn paths_in(root: &Path) -> QuarantinePaths {
    QuarantinePaths::with(root.join("quarantine"), Vec::new(), Store::at(root.join("response_state.json")))
}

fn request(path: &Path, id: &str) -> QuarantineRequest {
    QuarantineRequest {
        path: path.to_string_lossy().into_owned(),
        sha256: sha_of(path),
        allow_protected: false,
        id: id.to_string(),
    }
}

fn outcome(body: &Value) -> &str {
    body["outcome"].as_str().unwrap_or("")
}

#[test]
fn a_real_file_is_moved_out_and_restored_byte_for_byte() {
    let root = tempfile::tempdir().unwrap();
    let paths = paths_in(root.path());
    let file = root.path().join("payload.bin");
    let bytes: Vec<u8> = (0..200_000u32).map(|i| (i % 251) as u8).collect();
    std::fs::write(&file, &bytes).unwrap();

    let moved = quarantine_at(&paths, &request(&file, "task-1"), T0, &[]);
    assert_eq!(outcome(&moved), "quarantined", "{moved}");
    assert_eq!(moved["verify"]["ok"], true);
    assert!(!file.exists());
    assert!(stored_path(&paths, "task-1").exists());
    assert!(manifest_path(&paths, "task-1").exists());

    let back = restore_at(&paths, "task-1");
    assert_eq!(outcome(&back), "restored", "{back}");
    assert_eq!(std::fs::read(&file).unwrap(), bytes);
    assert!(!manifest_path(&paths, "task-1").exists());
}

#[test]
fn a_file_changed_after_it_was_flagged_is_never_moved() {
    let root = tempfile::tempdir().unwrap();
    let paths = paths_in(root.path());
    let file = root.path().join("payload.bin");
    std::fs::write(&file, b"flagged version").unwrap();
    let req = request(&file, "task-1");
    std::fs::write(&file, b"someone else's version").unwrap();
    let body = quarantine_at(&paths, &req, T0, &[]);
    assert_eq!(outcome(&body), "hash_mismatch");
    assert_eq!(std::fs::read(&file).unwrap(), b"someone else's version");
    assert!(!manifest_path(&paths, "task-1").exists());
}

/// A copy of `sleep` under its own name in `dir`, started for 300 seconds.
#[cfg(target_os = "linux")]
fn spawn_sleeper(dir: &Path) -> (std::process::Child, PathBuf) {
    let source = ["/bin/sleep", "/usr/bin/sleep"].into_iter().map(PathBuf::from).find(|p| p.exists()).unwrap();
    let copy = dir.join("sleep"); // the name stays sleep: some coreutils builds pick the tool from argv[0]
    std::fs::copy(&source, &copy).unwrap();
    let child = std::process::Command::new(&copy).arg("300").spawn().expect("start the copied sleep");
    (child, copy)
}

/// The child's entry once its exec has finished (right after the fork it still shows the test).
#[cfg(target_os = "linux")]
fn wait_for_exe(pid: u32, expected: &str) -> omni_agent::capabilities::quarantine::RunningProcess {
    for _ in 0..50 {
        if let Some(p) = running_now().into_iter().find(|p| p.pid == pid && same_exe(p.exe.as_deref(), expected, false)) {
            return p;
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
    panic!("the child never showed {expected} as its executable");
}

#[cfg(target_os = "linux")]
#[test]
fn a_child_appears_once_in_the_process_list_with_a_start_time_and_its_own_exe() {
    let root = tempfile::tempdir().unwrap();
    let (mut child, copy) = spawn_sleeper(root.path());
    let seen = wait_for_exe(child.id(), &copy.to_string_lossy());
    let count = running_now().iter().filter(|p| p.pid == child.id()).count();
    let _ = child.kill();
    let _ = child.wait();
    assert_eq!(count, 1);
    assert!(seen.start_time > 0);
    assert_eq!(seen.name, "sleep");
}

#[cfg(target_os = "linux")]
#[test]
fn moving_a_running_program_reports_it_and_the_listing_then_shows_the_stored_path() {
    let root = tempfile::tempdir().unwrap();
    let paths = paths_in(root.path());
    let (mut child, copy) = spawn_sleeper(root.path());
    let original = copy.to_string_lossy().into_owned();
    wait_for_exe(child.id(), &original);
    let listing = running_now();

    let body = quarantine_at(&paths, &request(&copy, "task-1"), T0, &listing);
    let after = running_now();
    let stored = stored_path(&paths, "task-1").to_string_lossy().into_owned();
    let seen_after = after.iter().find(|p| p.pid == child.id()).and_then(|p| p.exe.clone());
    let _ = child.kill();
    let _ = child.wait();

    assert_eq!(outcome(&body), "quarantined", "{body}");
    let still = body["still_running"].as_array().expect("the running copy is reported");
    assert_eq!(still.len(), 1);
    assert_eq!(still[0]["pid"], child.id());
    assert!(still[0]["start_time"].as_u64().unwrap() > 0);
    // What this VM reports for a renamed running image: the stored path, not the original.
    let seen_after = seen_after.expect("the child is still running after the move");
    println!("exe reported after the move: {seen_after}");
    assert_eq!(seen_after, stored);
    // A comparison on the original path alone would lose this process, which is why the kill
    // plan also accepts the stored path.
    assert!(!same_exe(Some(&seen_after), &original, false));
}

#[cfg(target_os = "linux")]
fn listed(p: &omni_agent::capabilities::quarantine::RunningProcess) -> omni_agent::capabilities::process_kill::ListedProcess {
    omni_agent::capabilities::process_kill::ListedProcess { pid: p.pid, start_time: p.start_time }
}

#[cfg(target_os = "linux")]
fn is_running(pid: u32) -> bool {
    running_now().iter().any(|p| p.pid == pid)
}

/// The kill after a quarantine, on a real child: the plan finds the child under the stored path,
/// signals only it, and the answer is `killed` with verify ok once it has really left.
#[cfg(target_os = "linux")]
#[tokio::test]
async fn a_kill_after_a_move_ends_the_child_that_runs_the_stored_image() {
    use omni_agent::capabilities::process_kill::{kill_by_exe, KillRequest};
    let root = tempfile::tempdir().unwrap();
    let paths = paths_in(root.path());
    let (mut child, copy) = spawn_sleeper(root.path());
    let original = copy.to_string_lossy().into_owned();
    let seen = wait_for_exe(child.id(), &original);
    let listing = running_now();
    let moved = quarantine_at(&paths, &request(&copy, "task-1"), T0, &listing);
    assert_eq!(outcome(&moved), "quarantined", "{moved}");

    let stored = stored_path(&paths, "task-1").to_string_lossy().into_owned();
    let body = kill_by_exe(KillRequest { expected_exe: original, moved_exe: Some(stored), listed: vec![listed(&seen)] }).await;
    let gone = !is_running(child.id());
    let _ = child.kill(); // a safety net for a failed assertion; the child is already dead
    let _ = child.wait();
    assert_eq!(body["outcome"], "killed", "{body}");
    assert_eq!(body["verify"], serde_json::json!({"ok": true, "check": "process_gone"}));
    assert!(gone, "the pid is gone from the process list");
}

/// With nothing moved, only the approved program ends. A decoy that runs another program, and a
/// pid listed with the wrong start time (a reused pid), are both left alive.
#[cfg(target_os = "linux")]
#[tokio::test]
async fn a_kill_ends_only_the_approved_program_and_leaves_a_reused_pid_alone() {
    use omni_agent::capabilities::process_kill::{kill_by_exe, KillRequest, ListedProcess};
    let target_dir = tempfile::tempdir().unwrap();
    let decoy_dir = tempfile::tempdir().unwrap();
    let (mut target, target_exe) = spawn_sleeper(target_dir.path());
    let (mut decoy, decoy_exe) = spawn_sleeper(decoy_dir.path());
    let seen = wait_for_exe(target.id(), &target_exe.to_string_lossy());
    let decoy_seen = wait_for_exe(decoy.id(), &decoy_exe.to_string_lossy());

    let req = KillRequest {
        expected_exe: target_exe.to_string_lossy().into_owned(),
        moved_exe: None,
        listed: vec![listed(&seen), ListedProcess { pid: decoy.id(), start_time: decoy_seen.start_time + 9_000 }],
    };
    let body = kill_by_exe(req).await;
    let target_gone = !is_running(target.id());
    let decoy_alive = is_running(decoy.id());
    let _ = target.kill();
    let _ = target.wait();
    let _ = decoy.kill();
    let _ = decoy.wait();
    assert_eq!(body["outcome"], "killed", "{body}");
    assert_eq!(body["verify"]["ok"], true);
    assert!(target_gone);
    assert!(decoy_alive, "a process that only shares a listed pid was not signalled");
}
