use tokio::process::Command;
use tokio::fs;
use tempfile::tempdir;
use std::time::Duration;
use std::env;

use rust_agent::fim_fanotify_watcher::FanotifyWatcher;
use rust_agent::capabilities_process_mapper::{get_process_name, resolve_process_tree, ProcessInfo};

#[tokio::test]
async fn test_fanotify_event_capture_and_process_attribution() {
    // 1. Create a temporary test directory
    let dir = tempdir().expect("Failed to create temporary directory");
    let test_dir_path = dir.path().to_path_buf();
    let test_file_path = test_dir_path.join("test_file.txt");

    // 2. Initialize the fanotify watcher and mark the directory
    let mut watcher = FanotifyWatcher::new(&test_dir_path)
        .expect("Failed to create FanotifyWatcher");

    // 3. Spawns a child process that opens and writes to a file in the marked directory
    let mut child = Command::new("sh")
        .arg("-c")
        .arg(format!("echo 'hello' > {}; sleep 0.1", test_file_path.display()))
        .spawn()
        .expect("Failed to spawn child process");

    // Give some time for the event to propagate
    tokio::time::sleep(Duration::from_millis(50)).await;

    // 4. Reads the fanotify event, extracts the PID, and verifies get_process_name returns a non-empty string.
    let mut found_event = false;
    let mut event_pid = 0;
    let mut captured_process_tree: Vec<ProcessInfo> = Vec::new();

    for _ in 0..10 { // Try reading multiple times in case of multiple events or timing issues
        if let Ok(Some(event)) = watcher.next_event().await {
            println!("Captured event: {:?}", event);
            if event.path == test_file_path {
                event_pid = event.pid;
                captured_process_tree = event.process_tree; // Get the enriched process tree
                found_event = true;
                break;
            }
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }

    assert!(found_event, "No fanotify event captured for the test file.");
    assert_ne!(event_pid, 0, "PID extracted from event was 0.");

    // Verify process name (from the enriched tree)
    let process_name_from_tree = captured_process_tree.last().map(|p| p.name.clone());
    println!("Process name from enriched tree for PID {}: {:?}", event_pid, process_name_from_tree);
    assert!(process_name_from_tree.is_some(), "Process name not found in enriched tree for PID {}", event_pid);
    assert!(!process_name_from_tree.unwrap().is_empty(), "Process name is empty in enriched tree for PID {}", event_pid);

    // Verify the process tree
    println!("Enriched Process tree for PID {}: {:?}", event_pid, captured_process_tree);
    assert!(!captured_process_tree.is_empty(), "Enriched process tree is empty for PID {}", event_pid);
    assert!(captured_process_tree.iter().any(|info| info.pid == event_pid), "PID not found in its own enriched process tree.");
    // Optionally, compare with directly resolved tree to ensure consistency
    let direct_process_tree = resolve_process_tree(event_pid);
    assert_eq!(captured_process_tree.len(), direct_process_tree.len(), "Enriched tree length mismatch with direct resolution");
    assert!(captured_process_tree.iter().zip(direct_process_tree.iter()).all(|(a, b)| a.pid == b.pid && a.name == b.name), "Enriched tree content mismatch with direct resolution");

    child.wait().await.expect("Child process did not exit correctly");

    // Clean up
    fs::remove_file(&test_file_path).await.ok();
    dir.close().expect("Failed to close temporary directory");
}