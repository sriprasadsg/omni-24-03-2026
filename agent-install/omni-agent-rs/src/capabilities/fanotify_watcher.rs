use fanotify::{high::{Fanotify, FanotifyResponse, EventType}, low::{fanotify_event_metadata, FAN_ALLOW, FAN_CLASS_NOTIF, FAN_CLOSE_WRITE, FAN_EVENT_ON_CHILD, FAN_MODIFY, FAN_OPEN_PERM, FAN_ACCESS_PERM}, EventFd};
use std::os::fd::{AsFd, BorrowedFd};
use std::path::{Path, PathBuf};
use std::time::Duration;
use tokio::sync::{watch, mpsc};
use libc::{pid_t, read, size_t, EINVAL, EBADF, ENOENT};

// Structure to hold event data to be sent through the channel
#[derive(Debug, Clone)]
pub struct FanotifyEventData {
    pub pid: pid_t,
    pub path: String,
    pub event_mask: u32,
}

pub async fn start_fanotify_watcher(
    paths: Vec<String>,
    mut stop_rx: watch::Receiver<bool>,
    event_tx: mpsc::Sender<FanotifyEventData>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    log::info!("Starting fanotify watcher");

    let fanotify = Fanotify::new(FAN_CLASS_NOTIF, FAN_NONBLOCK |
        FAN_CLOEXEC | FAN_REPORT_FID)?; // Use FAN_REPORT_FID for file handles

    let mut fd_map = std::collections::HashMap::new();

    for p in &paths {
        let path = Path::new(p);
        if !path.exists() {
            log::warn!("Fanotify path does not exist: {}", p);
            continue;
        }
        let metadata = fs::metadata(path)?;

        // Recursive monitoring only for directories
        // FAN_EVENT_ON_CHILD: for directory events, report events on files within that directory
        // FAN_MARK_MOUNT: for mount points (directories that are mount points)
        let mut mark_flags = FAN_MARK_ADD;
        if metadata.is_dir() {
             // To monitor recursively, we should ideally mark the mount point or the directory itself and enable FAN_EVENT_ON_CHILD
             // For simplicity in this tracer, we might mark directories directly. A full implementation would need careful handling of mount points.
            mark_flags |= FAN_MARK_MOUNT; // This flag is usually for mount points, but let's try it on directories for recursive behavior.
                                          // A more robust approach would be to detect mount points and mark them.
        }

        let flags = FAN_OPEN_PERM | FAN_ACCESS_PERM | FAN_MODIFY | FAN_CLOSE_WRITE | FAN_EVENT_ON_CHILD;
        fanotify.mark(mark_flags, flags, -1, path)?;
        log::info!("Fanotify watching: {}", p);
    }

    let mut buffer = vec![0; 4096]; // Buffer for fanotify events
    let fd = fanotify.as_fd();

    loop {
        tokio::select! {
            _ = stop_rx.changed() => {
                if *stop_rx.borrow() {
                    log::info!("Fanotify watcher stop signal received");
                    break;
                }
            }
            _ = tokio::time::sleep(Duration::from_millis(100)) => {
                // Allow other tasks to run and check for stop signal more frequently
            }
        }

        match read_fanotify_events(fd, &mut buffer) {
            Ok(0) => continue, // No events, or would block
            Ok(len) => {
                let mut offset = 0;
                while offset < len {
                    let metadata = unsafe { &*(buffer.as_ptr().add(offset) as *const fanotify_event_metadata) };

                    if metadata.event_len == 0 {
                        log::warn!("Fanotify event_len is 0, stopping buffer processing");
                        break;
                    }

                    let pid = metadata.pid;
                    // Note: FAN_REPORT_NAME would be needed here to get the path string directly from the event.
                    // Without it, we only get the file descriptor, which we'd have to resolve to a path.
                    // For this tracer, we focus on PID and mask extraction.
                    let path_indicator = if metadata.fd > 0 {
                        format!("fd:{}", metadata.fd)
                    } else {
                        "unknown_path_no_fd".to_string()
                    };

                    log::info!("Fanotify event: pid={}, mask={}, path_indicator={}", pid, metadata.mask, path_indicator);

                    // If we have an event_fd, we can potentially resolve the path more reliably.
                    // However, for this tracer, we're prioritizing PID and mask extraction.
                    if metadata.fd > 0 {
                         // Respond to permission events (FAN_OPEN_PERM, FAN_ACCESS_PERM)
                         // For other events, we might still need to respond if the kernel requires it.
                        if (metadata.mask & (FAN_OPEN_PERM | FAN_ACCESS_PERM)) != 0 {
                            fanotify.response(FanotifyResponse::Allow(metadata.fd as i32, metadata.pid as i32))?;
                        } else {
                            // For non-permission events, we might need to explicitly allow or deny if the kernel expects a response.
                            // For now, assume non-permission events don't strictly require a response for basic monitoring.
                        }
                    }

                    // Send event data through the channel to FIM
                    // We need to get the path associated with metadata.fd. This is complex and usually involves
                    // reading /proc/self/fd/<fd> or similar. For this tracer, we'll use a placeholder path
                    // and focus on sending PID and mask.
                    // A more complete solution would involve a map from fd to PathBuf.
                    let event_data = FanotifyEventData {
                        pid: pid as pid_t,
                        path: path_indicator, // Placeholder for path
                        event_mask: metadata.mask,
                    };
                    if let Err(e) = event_tx.send(event_data).await {
                        log::error!("Failed to send fanotify event data: {}", e);
                    }

                    offset += metadata.event_len as usize;
                }
            }
            Err(e) => {
                if e.kind() == std::io::ErrorKind::WouldBlock {
                    tokio::time::sleep(Duration::from_millis(50)).await;
                    continue;
                }
                log::error!("Error reading fanotify events: {}", e);
                return Err(e.into());
            }
        }
    }

    Ok(())
}

// Helper to read fanotify events from the file descriptor
fn read_fanotify_events(fd: BorrowedFd, buffer: &mut Vec<u8>) -> std::io::Result<usize> {
    let bytes_read = unsafe { read(fd.as_raw_fd(), buffer.as_mut_ptr() as *mut libc::c_void, buffer.len() as size_t) };
    if bytes_read < 0 {
        let err = std::io::Error::last_os_error();
        if err.kind() == std::io::ErrorKind::Interrupted { // EINTR
            return Ok(0);
        }
        if err.kind() == std::io::ErrorKind::WouldBlock { // EAGAIN
            return Err(err);
        }
        return Err(err);
    }
    Ok(bytes_read as usize)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;
    use std::fs::{self, File};
    use std::io::Write;
    use tokio::runtime::Runtime;
    use std::process::Command;
    use std::thread;
    use std::time::Duration;
    use std::sync::{Arc, Mutex};

    // Test for basic fanotify watcher functionality and PID extraction
    // This test requires root privileges and a Linux environment to run successfully.
    // Skipping for automated runs as it requires specific environment setup.
    #[test]
    #[ignore = "Requires root and a specific Linux environment, manual verification expected for now"]
    fn fanotify_basic_pid_extraction() {
        let rt = Runtime::new().unwrap();
        rt.block_on(async {
            let dir = tempdir().expect("Failed to create temp directory");
            let test_path = dir.path().join("fim_test");
            fs::create_dir(&test_path).expect("Failed to create test_path");

            let (stop_tx, stop_rx) = watch::channel(false);
            let watched_paths = vec![test_path.to_string_lossy().to_string()];

            let (event_tx, mut event_rx) = mpsc::channel(100);

            // Mock logging to capture output for assertions
            let log_output = Arc::new(Mutex::new(String::new()));
            let log_output_clone = log_output.clone();

            // Redirect logs to capture for assertion
            // Using a simple WriteLogger to a file and then reading it is a common strategy
            let log_file_path = "/tmp/fanotify_test.log";
            simplelog::CombinedLogger::init(
                vec![
                    simplelog::WriteLogger::new(simplelog::LevelFilter::Info,
                                              simplelog::Config::default(),
                                              std::fs::File::create(log_file_path).unwrap()),
                ]
            ).unwrap();

            let watcher_handle = tokio::spawn(async move {
                start_fanotify_watcher(watched_paths, stop_rx, event_tx).await
            });

            tokio::time::sleep(Duration::from_secs(1)).await; // Give watcher time to initialize
            log::info!("Attempting to touch file in watched directory");

            // Perform a file operation that fanotify should catch
            let file_path = test_path.join("test_file.txt");
            // Ensure the file is created by a process that fanotify can see, e.g., the test runner itself.
            // This might require running the test with elevated privileges.
            let mut file = File::create(&file_path).expect("Failed to create test_file");
            file.write_all(b"hello").expect("Failed to write to file");
            drop(file);
            log::info!("Touched file: {}", file_path.to_string_lossy());

            // Wait for an event to be received through the channel
            tokio::time::timeout(Duration::from_secs(5), event_rx.recv()).await;
            match received_event {
                Ok(Some(event_data)) => {
                    log::info!("Received fanotify event data: {:?}", event_data);
                    assert!(event_data.pid > 0, "PID should be extracted");
                    assert!(event_data.path.starts_with("fd:"), "Path indicator should be present");
                }
                Ok(None) => {
                    panic!("Did not receive fanotify event data through the channel");
                }
                Err(_) => {
                    panic!("Timed out waiting for fanotify event data");
                }
            }

            stop_tx.send(true).expect("Failed to send stop signal");
            let _ = watcher_handle.await;

            // Clean up log file
            // fs::remove_file(log_file_path).ok();
        });
    }
}
