#[cfg(target_os = "linux")]
use std::{io, path::PathBuf};

#[cfg(target_os = "linux")]
use fanotify::high_level::{Fanotify, FanEvent, FanotifyMode};
#[cfg(target_os = "linux")]
use crate::olog;

#[cfg(target_os = "linux")]
pub struct FanotifyWatcher {
    fanotify: Fanotify,
}

#[cfg(target_os = "linux")]
impl FanotifyWatcher {
    pub fn new() -> io::Result<Self> {
        // Initialize fanotify in non-blocking content mode
        let fanotify = Fanotify::new_nonblocking(FanotifyMode::CONTENT)?;
        Ok(FanotifyWatcher { fanotify })
    }

    pub fn add_path_to_watch(&mut self, path: &PathBuf) -> io::Result<()> {
        olog!("Adding path to watch: {:?}", path);
        // Use add_mountpoint for FAN_MARK_MOUNT behavior (matches original MarkFlags::MOUNT)
        // Mode: OPEN_PERM | MODIFY | CLOSE_WRITE
        let mode = FanEvent::OpenPerm as u64 | FanEvent::Modify as u64 | FanEvent::CloseWrite as u64;
        self.fanotify.add_mountpoint(mode, path)?;
        olog!("Path {:?} successfully marked.", path);
        Ok(())
    }

    pub fn read_events(&mut self) -> io::Result<Vec<(u32, PathBuf)>> {
        let mut events = Vec::new();
        for event in self.fanotify.read_event() {
            let path = PathBuf::from(&event.path);
            olog!("Event: Type: {:?}, PID: {:?}, Path: {:?}", event.events, event.pid, path);
            events.push((event.pid as u32, path));

            // Check for OPEN_PERM and respond with ALLOW
            if event.events.iter().any(|e| *e == FanEvent::OpenPerm) {
                self.fanotify.send_response(event.fd, fanotify::high_level::FanotifyResponse::Allow);
            }
        }
        Ok(events)
    }
}