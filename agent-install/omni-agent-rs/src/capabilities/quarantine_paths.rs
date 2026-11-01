//! Where quarantined files live, which paths may never be moved, and how a path read from the
//! process list is compared with the path of a file. Everything here is a plain function on text
//! or a small value, so the Windows rules are tested on Linux too (`windows_style` picks them).
//!
//! The protected lists below equal `protectedPaths` in `shared/agent-response-contract.json`; a
//! test compares them.

use crate::capabilities::response_state::Store;
use std::path::{Path, PathBuf};

/// How many running processes one result may name. Equals `stillRunningCap` in the contract.
pub const STILL_RUNNING_CAP: usize = 128;

/// Windows prefixes, lower case, below the drive letter, with `\` separators.
pub const PROTECTED_WINDOWS: &[&str] = &[
    "windows\\system32",
    "windows\\syswow64",
    "windows\\winsxs",
    "program files\\omniagentrust",
    "programdata\\omniagent",
];

/// Linux prefixes. Each ends in `/`, so `/etc/` matches `/etc/passwd` but not `/etcetera`.
pub const PROTECTED_LINUX: &[&str] = &[
    "/usr/bin/", "/usr/sbin/", "/bin/", "/sbin/", "/boot/", "/lib/", "/lib64/", "/usr/lib/", "/etc/",
    "/var/lib/omni-agent/", "/opt/omni-agent/",
];

/// One process as the quarantine and the kill see it. `start_time` is whole epoch seconds, and
/// `exe` is None when the platform would not say (Windows gives an empty path on a failed read).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunningProcess {
    pub pid: u32,
    pub name: String,
    pub start_time: u64,
    pub exe: Option<String>,
}

/// Where the quarantine keeps its files and what it must never touch.
#[derive(Debug, Clone)]
pub struct QuarantinePaths {
    /// The quarantine directory.
    pub dir: PathBuf,
    /// The agent's own files and folders: refused even with `allow_protected`.
    pub own_paths: Vec<PathBuf>,
    /// Protected operating-system prefixes: refused unless the instruction allows them.
    pub protected: Vec<String>,
    /// Compare paths by the Windows rules (case-insensitive, `\`, drive letter).
    pub windows_style: bool,
    /// The agent's state file; its lock serialises every quarantine and restore.
    pub store: Store,
}

#[cfg(test)]
thread_local! {
    static TEST_PATHS: std::cell::RefCell<Option<QuarantinePaths>> = std::cell::RefCell::new(None);
}

impl QuarantinePaths {
    /// The real locations on this machine. Linux: `/var/lib/omni-agent/quarantine`. Windows:
    /// `quarantine` beside the agent's executable.
    pub fn system() -> QuarantinePaths {
        #[cfg(test)]
        if let Some(paths) = TEST_PATHS.with(|p| p.borrow().clone()) {
            return paths;
        }
        let exe = std::env::current_exe().ok();
        let config_dir = crate::config::config_path().parent().map(Path::to_path_buf);
        let dir = if cfg!(windows) {
            exe.as_deref()
                .and_then(Path::parent)
                .map_or_else(|| PathBuf::from("quarantine"), |d| d.join("quarantine"))
        } else {
            PathBuf::from("/var/lib/omni-agent/quarantine")
        };
        let mut own_paths = vec![dir.clone()];
        own_paths.extend(config_dir);
        own_paths.extend(exe);
        QuarantinePaths::with(dir, own_paths, Store::default())
    }

    /// Paths under `dir` with the platform's protected list; tests give a temporary directory.
    pub fn with(dir: PathBuf, own_paths: Vec<PathBuf>, store: Store) -> QuarantinePaths {
        let windows_style = cfg!(windows);
        let list = if windows_style { PROTECTED_WINDOWS } else { PROTECTED_LINUX };
        QuarantinePaths {
            dir,
            own_paths,
            protected: list.iter().map(|s| s.to_string()).collect(),
            windows_style,
            store,
        }
    }
}

/// Test support: points `QuarantinePaths::system()` of this thread at a fresh temporary
/// directory (the quarantine and the state file both live inside it).
#[cfg(test)]
pub(crate) fn use_temp_paths() -> tempfile::TempDir {
    let dir = tempfile::tempdir().expect("tempdir");
    let paths = QuarantinePaths::with(
        dir.path().join("quarantine"),
        Vec::new(),
        Store::at(dir.path().join("response_state.json")),
    );
    TEST_PATHS.with(|p| *p.borrow_mut() = Some(paths));
    dir
}

/// Where the file quarantined for instruction `id` is kept. This is the only place that name is
/// built: `<dir>/<id>` on Linux, `<dir>\<id>.q` in Windows style.
pub fn stored_path(paths: &QuarantinePaths, id: &str) -> PathBuf {
    if paths.windows_style {
        paths.dir.join(format!("{id}.q"))
    } else {
        paths.dir.join(id)
    }
}

/// The manifest beside the stored file.
pub fn manifest_path(paths: &QuarantinePaths, id: &str) -> PathBuf {
    paths.dir.join(format!("{id}.json"))
}

/// `a` and `b` name the same file. Linux compares exactly. Windows ignores case, reads `/` as
/// `\` and drops a leading `\\?\`. A missing or empty `a` never matches.
pub fn same_exe(a: Option<&str>, b: &str, windows_style: bool) -> bool {
    let Some(a) = a.filter(|a| !a.is_empty()) else { return false };
    if b.is_empty() {
        return false;
    }
    if windows_style {
        normalize(a, true) == normalize(b, true)
    } else {
        a == b
    }
}

/// The text a comparison is made on. Windows: lower case, `\` separators, no `\\?\` prefix, no
/// trailing separator past the root. Linux: the text as given, without a trailing `/`.
pub fn normalize(path: &str, windows_style: bool) -> String {
    if windows_style {
        let slashed = path.to_lowercase().replace('/', "\\");
        let plain = slashed.strip_prefix("\\\\?\\").unwrap_or(&slashed);
        let trimmed = plain.trim_end_matches('\\');
        if trimmed.len() == 2 && trimmed.ends_with(':') {
            format!("{trimmed}\\") // a bare drive root keeps its separator
        } else {
            trimmed.to_string()
        }
    } else if path.len() > 1 {
        path.trim_end_matches('/').to_string()
    } else {
        path.to_string()
    }
}

/// A full path: a drive letter and separator or a UNC name on Windows, a leading `/` on Linux.
pub fn is_absolute(normalized: &str, windows_style: bool) -> bool {
    if windows_style {
        let b = normalized.as_bytes();
        (b.len() >= 3 && b[0].is_ascii_alphabetic() && b[1] == b':' && b[2] == b'\\')
            || normalized.starts_with("\\\\")
    } else {
        normalized.starts_with('/')
    }
}

/// True when any part of the raw path is `..`.
pub fn has_dotdot(raw: &str, windows_style: bool) -> bool {
    raw.split(|c| c == '/' || (windows_style && c == '\\')).any(|part| part == "..")
}

/// `path` is `prefix` or lies below it (both normalised the same way).
pub fn is_under(path: &str, prefix: &str, windows_style: bool) -> bool {
    let sep = if windows_style { '\\' } else { '/' };
    let prefix = prefix.trim_end_matches(sep);
    path == prefix || path.strip_prefix(prefix).is_some_and(|rest| rest.starts_with(sep))
}

/// `normalized` lies under one of the protected prefixes. Windows prefixes are matched below the
/// drive letter, so the system folder counts on any drive.
pub fn under_protected(normalized: &str, protected: &[String], windows_style: bool) -> bool {
    if windows_style {
        let below = match normalized.as_bytes() {
            [d, b':', b'\\', ..] if d.is_ascii_alphabetic() => &normalized[3..],
            _ => return false,
        };
        protected.iter().any(|p| is_under(below, &normalize(p, true), true))
    } else {
        protected.iter().any(|p| is_under(normalized, p, false))
    }
}

#[cfg(unix)]
pub(crate) fn unix_mode(meta: &std::fs::Metadata) -> Option<u32> {
    use std::os::unix::fs::PermissionsExt;
    Some(meta.permissions().mode() & 0o7777)
}
#[cfg(not(unix))]
pub(crate) fn unix_mode(_: &std::fs::Metadata) -> Option<u32> {
    None
}
#[cfg(unix)]
pub(crate) fn unix_owner(meta: &std::fs::Metadata) -> Option<(u32, u32)> {
    use std::os::unix::fs::MetadataExt;
    Some((meta.uid(), meta.gid()))
}
#[cfg(not(unix))]
pub(crate) fn unix_owner(_: &std::fs::Metadata) -> Option<(u32, u32)> {
    None
}

/// The agent's own files and folders contain `normalized`.
pub fn is_own_file(paths: &QuarantinePaths, normalized: &str) -> bool {
    let ws = paths.windows_style;
    paths.own_paths.iter().any(|own| is_under(normalized, &normalize(&own.to_string_lossy(), ws), ws))
}

/// The processes of `list` whose executable is the file at `path`.
pub fn running_from(list: &[RunningProcess], path: &str, windows_style: bool) -> Vec<RunningProcess> {
    list.iter().filter(|p| same_exe(p.exe.as_deref(), path, windows_style)).cloned().collect()
}

/// A fresh read of the process list. A new `System` every call, because a refreshed one keeps
/// the executable path it already read. Threads (Linux lists each as a process) and processes
/// that have ended but not been reaped are left out.
pub fn running_now() -> Vec<RunningProcess> {
    use sysinfo::{ProcessRefreshKind, ProcessStatus, ProcessesToUpdate, System};
    let mut sys = System::new();
    sys.refresh_processes_specifics(ProcessesToUpdate::All, true, ProcessRefreshKind::everything());
    sys.processes()
        .iter()
        .filter(|(_, p)| {
            p.thread_kind().is_none() && !matches!(p.status(), ProcessStatus::Zombie | ProcessStatus::Dead)
        })
        .map(|(pid, p)| RunningProcess {
            pid: pid.as_u32(),
            name: p.name().to_string_lossy().into_owned(),
            start_time: p.start_time(),
            exe: p.exe().map(|e| e.to_string_lossy().into_owned()).filter(|e| !e.is_empty()),
        })
        .collect()
}
