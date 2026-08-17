// tests/fim_fanotify_test.rs
use fim_process_attribution::capabilities::fim_fanotify_watcher::{FanotifyEventType, FanotifyWatcher};
use fim_process_attribution::capabilities::fim_process_mapper::{get_process_name, get_process_tree};
use std::io;
use std::time::Duration;
use tempfile::tempdir;

// Helper to make sure we're running as root
fn require_root_skip_test() {
    if !nix::unistd::Uid::effective().is_root() {
        eprintln!("Tests require root privileges to run fanotify. Skipping.");
        panic!("Not running as root.");
    }
}

#[cfg(test)]
mod integration_tests {
    use super::*;

    #[test]
    fn test_fanotify_event_capture() -> io::Result<()> {
        require_root_skip_test();

        let tmp_dir = tempdir()?;
        let test_dir = tmp_dir.path();
        let test_file_path = test_dir.join("test_file.txt");

        std::fs::write(&test_file_path, "initial content")?; // Create file before marking

        let watcher = FanotifyWatcher::new()?;
        watcher.mark_path(test_file_path.to_str().unwrap())?;

        // Give fanotify a moment to set up
        std::thread::sleep(Duration::from_millis(500));

        // Write directly to trigger events - this ensures events are generated with our PID
        std::fs::write(&test_file_path, "hello")?;
        std::thread::sleep(Duration::from_millis(100));
        std::fs::write(&test_file_path, "world")?;
        std::thread::sleep(Duration::from_millis(100));

        // Debug: check fanotify fd
        eprintln!("Fanotify FD: {}", watcher.as_raw_fd());

        // Read events with a timeout to allow the kernel to deliver them
        let events = watcher.read_events_timeout(Duration::from_secs(5))?;
        eprintln!("Events captured: {:?}", events);
        assert!(!events.is_empty(), "No fanotify events captured");

        let mut found_modify = false;
        let mut found_close_write = false;

        for event in &events {
            println!(
                "Event: PID={}, Path={:?}, Type={:?}",
                event.pid, event.path, event.event_type
            );
            assert!(event.path.ends_with(test_file_path.file_name().unwrap()));
            match event.event_type {
                FanotifyEventType::Modify => found_modify = true,
                FanotifyEventType::CloseWrite => found_close_write = true,
                _ => {}
            }
        }

        assert!(found_modify, "Did not find FAN_MODIFY event");
        assert!(found_close_write, "Did not find FAN_CLOSE_WRITE event");

        Ok(())
    }

    #[test]
    fn test_process_name_resolution() -> io::Result<()> {
        require_root_skip_test();

        let self_pid = nix::unistd::getpid().as_raw();
        let process_name = get_process_name(self_pid as u32);
        println!("Self PID: {}, Name: {:?}", self_pid, process_name);

        assert!(process_name.is_some());
        assert!(!process_name.unwrap().is_empty());
        Ok(())
    }

    #[test]
    fn test_process_tree_resolution() -> io::Result<()> {
        require_root_skip_test();

        let self_pid = nix::unistd::getpid().as_raw();
        let tree = get_process_tree(self_pid as u32);

        println!("Process Tree for PID {}: {:?}", self_pid, tree);

        assert!(!tree.is_empty());
        // Verify that our own process is in the tree
        assert!(tree.iter().any(|p| p.pid == self_pid as u32));

        // Verify that the tree starts from init (PID 1) or a very early process
        // This might vary based on test runner or environment
        if let Some(root_process) = tree.first() {
            // Usually init (1) or a systemd process
            assert!(root_process.pid == 1 || root_process.pid < 100);
            assert!(!root_process.name.is_empty());
        } else {
            panic!("Process tree is empty!");
        }

        // Test with a non-existent PID (should return empty tree)
        let non_existent_pid = 999999;
        let empty_tree = get_process_tree(non_existent_pid);
        assert!(empty_tree.is_empty(), "Tree for non-existent PID should be empty");

        Ok(())
    }
}