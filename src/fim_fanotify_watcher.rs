// src/fim_fanotify_watcher.rs
use std::{
    io::{self, Read},
    os::unix::io::RawFd,
    path::PathBuf,
};

// Use the fanotify crate for fanotify operations
use fanotify::high_level::{Fanotify, FanotifyMode};
use fanotify::low_level::{
    FAN_OPEN_PERM, FAN_MODIFY, FAN_CLOSE_WRITE,
};

#[derive(Debug)]
pub enum FimEvent {
    OpenPerm(FimEventData),
    Modify(FimEventData),
    CloseWrite(FimEventData),
    Unknown(FimEventData),
}

#[derive(Debug, Clone)]
pub struct FimEventData {
    pub pid: u32,
    pub path: PathBuf,
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

    pub fn read_events(&self) -> io::Result<Vec<FimEvent>> {
        let events = self.fanotify.read_event();
        let mut fim_events = Vec::new();

        for event in events {
            let pid = event.pid as u32;
            let path = PathBuf::from(event.path);
            let event_data = FimEventData { pid, path };

            for fan_event in event.events {
                match fan_event {
                    fanotify::high_level::FanEvent::OpenPerm => {
                        fim_events.push(FimEvent::OpenPerm(event_data.clone()))
                    }
                    fanotify::high_level::FanEvent::Modify => {
                        fim_events.push(FimEvent::Modify(event_data.clone()))
                    }
                    fanotify::high_level::FanEvent::CloseWrite => {
                        fim_events.push(FimEvent::CloseWrite(event_data.clone()))
                    }
                    _ => fim_events.push(FimEvent::Unknown(event_data.clone())),
                }
            }
        }
        Ok(fim_events)
    }
}
