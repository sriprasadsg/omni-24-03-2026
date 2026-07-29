/*!
 * File logging for Windows Service mode.
 * Primary path:  C:\ProgramData\OmniAgent\logs\omni-agent.log  (always accessible)
 * Fallback path: {exe_dir}\logs\omni-agent.log
 * All messages also go to stderr so they appear in the SCM event log.
 */
use std::{
    fmt::Write as FmtWrite,
    fs::{self, OpenOptions},
    io::Write,
    path::PathBuf,
    sync::{Mutex, OnceLock},
};

static LOG: OnceLock<Mutex<std::fs::File>> = OnceLock::new();
static LOG_PATH: OnceLock<String> = OnceLock::new();

fn try_open(dir: &PathBuf) -> Option<std::fs::File> {
    fs::create_dir_all(dir).ok()?;
    let path = dir.join("omni-agent.log");
    OpenOptions::new().create(true).append(true).open(&path)
        .ok()
        .inspect(|_| { let _ = LOG_PATH.set(path.to_string_lossy().into_owned()); })
}

pub fn init(exe_dir: &PathBuf) {
    // Try C:\ProgramData\OmniAgent\logs\ first (readable by any user / admin tool)
    let programdata = std::env::var("PROGRAMDATA")
        .unwrap_or_else(|_| r"C:\ProgramData".into());
    let primary = PathBuf::from(&programdata).join("OmniAgent").join("logs");

    let file = try_open(&primary)
        .or_else(|| try_open(&exe_dir.join("logs")));

    if let Some(f) = file {
        let _ = LOG.set(Mutex::new(f));
    }

    let log_path = LOG_PATH.get().map(|s| s.as_str()).unwrap_or("(no file — stderr only)");
    write_line(&format!("=== OmniAgent v{} started  pid={}  log={} ===",
        env!("CARGO_PKG_VERSION"),
        std::process::id(),
        log_path,
    ));
    write_line(&format!("exe={}", std::env::current_exe()
        .map(|p| p.display().to_string()).unwrap_or_else(|_| "unknown".into())));
}

pub fn write_line(msg: &str) {
    use chrono::Utc;
    let mut line = String::new();
    let _ = write!(&mut line, "[{}] {}\n", Utc::now().format("%Y-%m-%dT%H:%M:%SZ"), msg);
    eprint!("{}", line);
    if let Some(m) = LOG.get() {
        if let Ok(mut f) = m.lock() {
            let _ = f.write_all(line.as_bytes());
        }
    }
}

#[macro_export]
macro_rules! olog {
    ($($arg:tt)*) => { crate::log::write_line(&format!($($arg)*)) };
}
