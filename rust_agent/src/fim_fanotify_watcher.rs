use fanotify::{Fanotify, EventFlags, InitFlags, MarkFlags};
use std::fs;
use std::io;
use std::os::unix::io::AsRawFd;
use std::path::{Path, PathBuf};
use tokio::io::unix::AsyncFd;

use crate::capabilities_process_mapper::{self, ProcessInfo};

#[derive(Debug, Clone)]
pub struct FanotifyEvent {
    pub pid: u32,
    pub path: PathBuf,
    pub event_type: FanotifyEventType,
    pub process_tree: Vec<ProcessInfo>, // Enriched with process tree
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FanotifyEventType {
    OpenPerm,
    Modify,
    CloseWrite,
    Other,
}

impl From<EventFlags> for FanotifyEventType {
    fn from(flags: EventFlags) -> Self {
        if flags.contains(EventFlags::FAN_OPEN_PERM) {
            FanotifyEventType::OpenPerm
        } else if flags.contains(EventFlags::FAN_MODIFY) {
            FanotifyEventType::Modify
        } else if flags.contains(EventFlags::FAN_CLOSE_WRITE) {
            FanotifyEventType::CloseWrite
        } else {
            FanotifyEventType::Other
        }
    }
}

pub struct FanotifyWatcher {
    fanotify: Fanotify,
    _test_dir: PathBuf,
}

impl FanotifyWatcher {
    pub fn new(test_dir: impl AsRef<Path>) -> io::Result<Self> {
        let test_dir = test_dir.as_ref().to_path_buf();
        fs::create_dir_all(&test_dir)?;

        let init_flags = InitFlags::FAN_CLOEXEC | InitFlags::FAN_CLASS_CONTENT;
        let fanotify = Fanotify::new(init_flags, libc::O_RDONLY | libc::O_NONBLOCK)?;

        let mark_flags = MarkFlags::FAN_MARK_ADD
            | MarkFlags::FAN_MARK_MOUNT
            | MarkFlags::FAN_MARK_IGNORED_MASK;

        fanotify.mark(
            mark_flags,
            EventFlags::FAN_OPEN_PERM | EventFlags::FAN_MODIFY | EventFlags::FAN_CLOSE_WRITE,
            libc::AT_FDCWD,
            &test_dir,
        )?;

        Ok(Self {
            fanotify,
            _test_dir: test_dir,
        })
    }

    pub async fn next_event(&mut self) -> io::Result<Option<FanotifyEvent>> {
        let mut async_fd = AsyncFd::new(self.fanotify.as_raw_fd())?;
        let mut guard = async_fd.readable().await?;

        let mut buffer = vec![0u8; 4096];
        let n = guard.get_inner().try_read(&mut buffer)?;

        if n == 0 {
            return Ok(None);
        }

        let events = fanotify::parse_events(&buffer[..n])?;

        for event in events {
            let path = event.path().map(|p| p.to_path_buf());
            if let Some(path) = path {
                let pid = event.pid();
                let process_tree = capabilities_process_mapper::resolve_process_tree(pid);

                return Ok(Some(FanotifyEvent {
                    pid,
                    path,
                    event_type: event.mask().into(),
                    process_tree,
                }));
            }
        }

        Ok(None)
    }
}