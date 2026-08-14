// src/capabilities/fim_fanotify_watcher.rs
use fanotify::high_level::{Fanotify, FanotifyMode, FanEvent};
use fanotify::low_level::{FAN_CLOSE_WRITE, FAN_MODIFY, FAN_OPEN_PERM};
use std::io;
use std::os::unix::io::RawFd;
use std::path::PathBuf;

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
        let fanotify = Fanotify::new_nonblocking(FanotifyMode::CONTENT)?;
        let fd = fanotify.as_raw_fd();
        Ok(FanotifyWatcher { fanotify, fd })
    }

    pub fn mark_path(&self, path: &str) -> io::Result<()> {
        let mark_flags = FAN_OPEN_PERM | FAN_MODIFY | FAN_CLOSE_WRITE;
        self.fanotify.add_path(mark_flags, path)?;
        Ok(())
    }

    pub fn read_events(&self) -> io::Result<Vec<FanotifyEvent>> {
        let mut fim_events = Vec::new();
        // fanotify-rs read_event() returns Vec<Event>, not Result<Vec<Event>>
        let events = self.fanotify.read_event();
        for event in events {
            let pid = event.pid as u32;
            let path = PathBuf::from(event.path);
            for fan_event_flag in event.events {
                let event_type = match fan_event_flag {
                    FanEvent::OpenPerm => FanotifyEventType::OpenPerm,
                    FanEvent::Modify => FanotifyEventType::Modify,
                    FanEvent::CloseWrite => FanotifyEventType::CloseWrite,
                    _ => FanotifyEventType::Unknown,
                };
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