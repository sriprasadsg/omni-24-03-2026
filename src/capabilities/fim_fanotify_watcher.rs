// src/capabilities/fim_fanotify_watcher.rs
use fanotify::high_level::{Fanotify, FanotifyMode};
use fanotify::low_level::{FAN_CLOSE_WRITE, FAN_MODIFY};
use std::io;
use std::os::unix::io::RawFd;
use std::path::PathBuf;
use std::time::Duration;

#[derive(Debug, Clone)]
pub struct FanotifyEvent {
    pub pid: u32,
    pub path: PathBuf,
    pub event_type: FanotifyEventType,
}

#[derive(Debug, Clone, PartialEq)]
pub enum FanotifyEventType {
    OpenPerm,
    Modify,
    CloseWrite,
    Unknown,
}

pub struct FanotifyWatcher {
    fanotify: Fanotify,
    fd: RawFd,
}

impl FanotifyWatcher {
    pub fn new() -> io::Result<Self> {
        let fanotify = Fanotify::new_nonblocking(FanotifyMode::NOTIF)?;
        let fd = fanotify.as_raw_fd();
        Ok(FanotifyWatcher { fanotify, fd })
    }

    pub fn mark_path(&self, path: &str) -> io::Result<()> {
        let mark_flags = FAN_MODIFY | FAN_CLOSE_WRITE;
        let result = self.fanotify.add_path(mark_flags, path);
        eprintln!("Mark path result for {}: {:?}", path, result);
        result
    }

    pub fn read_events(&self) -> io::Result<Vec<FanotifyEvent>> {
        self.read_events_timeout(Duration::from_millis(100))
    }

    pub fn read_events_timeout(&self, timeout: Duration) -> io::Result<Vec<FanotifyEvent>> {
        let mut fim_events = Vec::new();

        let mut pollfds = [nix::poll::PollFd::new(
            self.fd,
            nix::poll::PollFlags::POLLIN,
        )];

        let poll_result = nix::poll::poll(&mut pollfds, timeout.as_millis() as i32)?;

        if poll_result == 0 {
            // Timeout, no events
            return Ok(Vec::new());
        }

        if poll_result < 0 {
            return Err(io::Error::last_os_error());
        }

        for event in self.fanotify.read_event() {
            let pid = event.pid as u32;
            let path = PathBuf::from(event.path);
            let mut event_types = Vec::new();

            // event.events is a slice of FanEvent enum variants
            let mask = event.events;
            if mask.contains(&fanotify::high_level::FanEvent::OpenPerm) {
                event_types.push(FanotifyEventType::OpenPerm);
            }
            if mask.contains(&fanotify::high_level::FanEvent::Modify) {
                event_types.push(FanotifyEventType::Modify);
            }
            if mask.contains(&fanotify::high_level::FanEvent::CloseWrite) {
                event_types.push(FanotifyEventType::CloseWrite);
            }

            if event_types.is_empty() {
                event_types.push(FanotifyEventType::Unknown);
            }

            for event_type in event_types {
                fim_events.push(FanotifyEvent {
                    pid,
                    path: path.clone(),
                    event_type,
                });
            }
        }
        Ok(fim_events)
    }

    pub fn as_raw_fd(&self) -> RawFd {
        self.fd
    }
}