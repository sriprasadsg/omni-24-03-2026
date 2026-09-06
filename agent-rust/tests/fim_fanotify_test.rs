
use omni_agent::fim_fanotify_watcher::FanotifyWatcher;
use omni_agent::fim_process_mapper::get_process_name;
use std::fs::{self, File};
use std::io::Write;
use std::path::PathBuf;
use std::process::Command;
use std::{thread, time};
use tempfile::tempdir;

#[test]
fn test_fanotify_event_capture() {
    let dir = tempdir().unwrap();
    let dir_path = dir.path().to_path_buf();
    let file_path = dir_path.join("test_file.txt");

    let mut watcher = FanotifyWatcher::new().expect("Failed to initialize fanotify watcher");
    watcher.add_path_to_watch(&dir_path).expect("Failed to add path to watch");

    // Spawn a child process to modify a file
    let child = Command::new("sh")
        .arg("-c")
        .arg(format!("echo 'hello' > {:?}", file_path))
        .spawn()
        .expect("Failed to spawn child process");

    let pid = child.id();

    // Give some time for the event to be captured
    thread::sleep(time::Duration::from_millis(500));

    let events = watcher.read_events().expect("Failed to read events");

    let mut found = false;
    for (event_pid, event_path) in events {
        if event_path == file_path {
            found = true;
            assert_eq!(event_pid, pid);
            let process_name = get_process_name(event_pid).expect("Failed to get process name");
            assert!(!process_name.is_empty());
            println!("Captured event: PID={}, Process={}, Path={:?}", event_pid, process_name, event_path);
        }
    }

    assert!(found, "Target event was not captured");
}
