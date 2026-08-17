use tokio::sync::{watch, mpsc};
use libc::pid_t;
use naughtyfy::api::{init, mark, read, close};
use naughtyfy::flags::{FAN_CLOEXEC, FAN_CLASS_CONTENT, FAN_MARK_ADD, FAN_MARK_MOUNT, FAN_ACCESS, AT_FDCWD, O_RDONLY, O_LARGEFILE, FAN_MODIFY, FAN_CLOSE_WRITE, FAN_CREATE, FAN_DELETE, FAN_MOVE, FAN_ATTRIB};
use std::os::fd::AsRawFd;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

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
    log::info!("Starting fanotify watcher for paths: {:?}", paths);

    let fanotify_fd = Arc::new(Mutex::new(init(FAN_CLOEXEC | FAN_CLASS_CONTENT, O_RDONLY | O_LARGEFILE)?));
    let fanotify_fd_raw_for_close = fanotify_fd.lock().unwrap().as_raw_fd();

    let all_mask = FAN_ACCESS | FAN_MODIFY | FAN_CLOSE_WRITE | FAN_CREATE | FAN_DELETE | FAN_MOVE | FAN_ATTRIB;

    for path_str in &paths {
        let path = Path::new(path_str);
        if path.is_dir() {
            mark(&fanotify_fd.lock().unwrap(), FAN_MARK_ADD | FAN_MARK_MOUNT, all_mask, AT_FDCWD, path_str)?;
            log::info!("Marked directory: {} with mask {:?}", path_str, all_mask);
        } else if path.is_file() {
            mark(&fanotify_fd.lock().unwrap(), FAN_MARK_ADD, all_mask, AT_FDCWD, path_str)?;
            log::info!("Marked file: {} with mask {:?}", path_str, all_mask);
        } else {
            log::warn!("Path does not exist or is not a file/directory: {}", path_str);
        }
    }

    loop {
        let fanotify_fd_clone = Arc::clone(&fanotify_fd);
        tokio::select! {
            _ = stop_rx.changed() => {
                if *stop_rx.borrow() {
                    log::info!("Fanotify watcher stop signal received");
                    let _ = close(fanotify_fd_raw_for_close);
                    break;
                }
            }
            event_result = tokio::task::spawn_blocking(move || read(&fanotify_fd_clone.lock().unwrap())) => {
                match event_result {
                    Ok(Ok(events)) => {
                        for event_metadata in events {
                            let event_path = match get_path_from_fd(event_metadata.fd) {
                                Ok(p) => Some(p),
                                Err(_) => None,
                            };

                            if let Some(path) = event_path {
                                let event_data = FanotifyEventData {
                                    pid: event_metadata.pid,
                                    path: path.to_string_lossy().into_owned(),
                                    event_mask: event_metadata.mask as u32,
                                };
                                if let Err(e) = event_tx.send(event_data).await {
                                    log::error!("Failed to send fanotify event: {}", e);
                                }
                            }
                            let _ = close(event_metadata.fd);
                        }
                    },
                    Ok(Err(e)) => log::error!("Error reading fanotify events: {}", e),
                    Err(e) => log::error!("Join error from spawn_blocking: {}", e),
                }
            }
        }
    }

    Ok(())
}

fn get_path_from_fd(fd: i32) -> Result<PathBuf, std::io::Error> {
    use std::fs;
    let proc_fd_path = format!("/proc/self/fd/{}", fd);
    fs::read_link(proc_fd_path)
}