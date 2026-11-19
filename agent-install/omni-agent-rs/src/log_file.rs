//! The agent's log file, rotated by size: once it would pass `MAX_BYTES` it becomes
//! `<name>.1` (older copies shift up to `<name>.KEEP`, the oldest is dropped) and a new
//! file starts, so the log never takes more than about `MAX_BYTES * (KEEP + 1)` of disk.

use std::fs::{File, OpenOptions};
use std::io::{self, Write};
use std::path::PathBuf;

pub const MAX_BYTES: u64 = 10 * 1024 * 1024;
pub const KEEP: u32 = 3;

pub struct RotatingFile {
    path: PathBuf,
    file: Option<File>,
    size: u64,
    max_bytes: u64,
    keep: u32,
}

impl RotatingFile {
    pub fn open(path: PathBuf) -> io::Result<Self> {
        Self::with_limits(path, MAX_BYTES, KEEP)
    }

    pub fn with_limits(path: PathBuf, max_bytes: u64, keep: u32) -> io::Result<Self> {
        let file = OpenOptions::new().create(true).append(true).open(&path)?;
        let size = file.metadata().map(|m| m.len()).unwrap_or(0);
        let mut log = RotatingFile { path, file: Some(file), size, max_bytes, keep };
        if log.size >= max_bytes {
            log.rotate()?; // a log left over from a build that never rotated
        }
        Ok(log)
    }

    fn numbered(&self, n: u32) -> PathBuf {
        PathBuf::from(format!("{}.{n}", self.path.display()))
    }

    fn rotate(&mut self) -> io::Result<()> {
        self.file = None; // close first: Windows cannot rename an open file
        let _ = std::fs::remove_file(self.numbered(self.keep));
        for n in (1..self.keep).rev() {
            let _ = std::fs::rename(self.numbered(n), self.numbered(n + 1));
        }
        // If another process holds the file, renaming fails and the file keeps growing; counting
        // from zero again retries only after another `max_bytes`, not on every line.
        let _ = std::fs::rename(&self.path, self.numbered(1));
        self.file = Some(OpenOptions::new().create(true).append(true).open(&self.path)?);
        self.size = 0;
        Ok(())
    }
}

impl Write for RotatingFile {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        if self.size > 0 && self.size + buf.len() as u64 > self.max_bytes {
            self.rotate()?;
        }
        let file = self.file.as_mut().ok_or_else(|| io::Error::other("log file is closed"))?;
        let written = file.write(buf)?;
        self.size += written as u64;
        Ok(written)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.file.as_mut().map_or(Ok(()), |f| f.flush())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_log(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("omni-log-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir.join("omni-agent.log")
    }

    fn len(path: PathBuf) -> u64 {
        std::fs::metadata(path).map(|m| m.len()).unwrap_or(0)
    }

    #[test]
    fn rotates_by_size_and_keeps_only_the_newest_copies() {
        let path = temp_log("rotate");
        let mut log = RotatingFile::with_limits(path.clone(), 100, 2).unwrap();
        for _ in 0..10 {
            log.write_all(&[b'x'; 60]).unwrap();
        }
        log.flush().unwrap();
        assert!(len(path.clone()) <= 100);
        assert_eq!(len(PathBuf::from(format!("{}.1", path.display()))), 60);
        assert_eq!(len(PathBuf::from(format!("{}.2", path.display()))), 60);
        assert!(!PathBuf::from(format!("{}.3", path.display())).exists());
    }

    #[test]
    fn an_oversized_log_from_an_older_build_is_rotated_on_open() {
        let path = temp_log("oversized");
        std::fs::write(&path, vec![b'x'; 500]).unwrap();
        let mut log = RotatingFile::with_limits(path.clone(), 100, 3).unwrap();
        log.write_all(b"fresh\n").unwrap();
        log.flush().unwrap();
        assert_eq!(std::fs::read(&path).unwrap(), b"fresh\n");
        assert_eq!(len(PathBuf::from(format!("{}.1", path.display()))), 500);
    }
}
