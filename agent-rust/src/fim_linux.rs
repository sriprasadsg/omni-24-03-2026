/*!
 * Linux File Integrity Monitoring via fanotify, with real process attribution
 * (Phase 63/999.3 — completes FIM-02's "process tree" clause for Linux).
 *
 * CAVEAT (read before trusting this in production): this module was written
 * without access to a Rust toolchain (no cargo/rustc in the authoring
 * environment) and has never been compiled. Build it with `cargo check`
 * on a real Linux host before relying on it. It replaces no existing
 * behavior — `agentic::realtime_fim_poller` (Windows path-hash polling)
 * is untouched, and this module is only ever compiled/spawned on Linux
 * (see `#[cfg(target_os = "linux")]` at every call site).
 *
 * Why fanotify and not the polling approach the Windows side uses: a
 * poll-and-diff loop can only ever notice a file changed sometime in the
 * last N seconds — by the time the diff runs, the responsible process is
 * long gone. Real "process attribution" requires an event-driven mechanism
 * that captures the PID at the moment of the write, which is exactly what
 * fanotify's classic event metadata provides (a `pid` field on every
 * event) and inotify does not.
 *
 * Design notes:
 *   - Uses the CLASSIC fanotify event format (no FAN_REPORT_FID), whose
 *     fixed-size `fanotify_event_metadata` struct has existed since
 *     fanotify's introduction (Linux 2.6.37) — deliberately avoiding the
 *     newer FID-based variable-length record format to keep parsing simple
 *     and compatible with older kernels.
 *   - `fanotify_init`/`fanotify_mark` have no safe wrapper in the `libc`
 *     crate versions this project might resolve to, so they're invoked via
 *     raw `libc::syscall()` with locally-defined syscall numbers (x86_64
 *     and aarch64 only — see `SYS_FANOTIFY_INIT`/`SYS_FANOTIFY_MARK`
 *     below). On any other architecture the watcher logs a message and
 *     exits gracefully rather than guessing a wrong syscall number.
 *   - The classic fanotify event carries an `fd` for the affected file, not
 *     a path — the path is recovered via `readlink("/proc/self/fd/{fd}")`,
 *     the standard technique for this API.
 *   - The blocking `read()` on the fanotify fd runs on a dedicated OS
 *     thread via `tokio::task::spawn_blocking` (integrating a raw blocking
 *     fd into tokio's async reactor via `AsyncFd` would be more idiomatic
 *     but is meaningfully more code to get right without a compiler to
 *     check it against). Detected events are handed to the async world
 *     over an mpsc channel, which does the hashing and HTTP POST.
 *   - No graceful-shutdown wiring for the blocking read loop: unlike the
 *     other pollers, there is no natural point in a blocking `read()` to
 *     check `running`. The thread lives for the process's lifetime; the OS
 *     reclaims it (and the fanotify fd) on exit. This is a deliberate scope
 *     cut, not an oversight.
 */
use std::collections::HashMap;
use std::ffi::CString;
use std::fs;
use std::os::unix::io::RawFd;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;

use reqwest::Client;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tokio::sync::{mpsc, RwLock};

use crate::config::Config;

/// Critical Linux files worth watching by default — auth, privilege
/// escalation, and shell-of-last-resort binaries. Mirrors the intent of
/// `agentic::FIM_WATCH_FILES` (the Windows equivalent list) rather than its
/// literal contents, since the two platforms' critical-file sets differ.
const FIM_WATCH_FILES: &[&str] = &[
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/ssh/sshd_config",
    "/etc/crontab",
    "/bin/bash",
    "/usr/bin/sudo",
    "/usr/bin/su",
];

#[cfg(target_arch = "x86_64")]
const SYS_FANOTIFY_INIT: libc::c_long = 300;
#[cfg(target_arch = "x86_64")]
const SYS_FANOTIFY_MARK: libc::c_long = 301;
#[cfg(target_arch = "aarch64")]
const SYS_FANOTIFY_INIT: libc::c_long = 262;
#[cfg(target_arch = "aarch64")]
const SYS_FANOTIFY_MARK: libc::c_long = 263;

const FAN_CLASS_NOTIF: u32 = 0x0000_0000;
const FAN_MODIFY: u64 = 0x0000_0002;
const FAN_CLOSE_WRITE: u64 = 0x0000_0008;
const FAN_MARK_ADD: u32 = 0x0000_0001;
const FAN_EVENT_METADATA_LEN: u32 = 24; // size_of::<FanotifyEventMetadata>()

#[repr(C)]
struct FanotifyEventMetadata {
    event_len: u32,
    vers: u8,
    reserved: u8,
    metadata_len: u16,
    mask: u64,
    fd: i32,
    pid: i32,
}

struct DetectedChange {
    path: String,
    pid: i32,
    mask: u64,
}

/// One frame of the triggering process's ancestry, from itself up toward init.
#[derive(serde::Serialize)]
struct ProcessFrame {
    pid: i32,
    name: String,
}

/// Reads /proc to build the triggering process's ancestry chain. Best-effort:
/// a process that has already exited by the time we look (a fast-running
/// tool) yields a short or empty chain rather than an error — this is
/// inherent to any /proc-based attribution, not specific to this
/// implementation.
fn resolve_process_ancestry(start_pid: i32) -> Vec<ProcessFrame> {
    let mut frames = Vec::new();
    let mut pid = start_pid;
    for _ in 0..25 {
        if pid <= 1 {
            break;
        }
        let name = fs::read_to_string(format!("/proc/{}/comm", pid))
            .map(|s| s.trim().to_string())
            .unwrap_or_else(|_| "unknown".to_string());
        if name == "unknown" {
            // Process no longer exists — stop rather than guess further.
            break;
        }
        frames.push(ProcessFrame { pid, name });

        let ppid = fs::read_to_string(format!("/proc/{}/stat", pid))
            .ok()
            .and_then(|stat| parse_ppid(&stat));
        match ppid {
            Some(p) => pid = p,
            None => break,
        }
    }
    frames
}

/// Parses the ppid (4th field) out of /proc/{pid}/stat. The 2nd field (comm)
/// is parenthesized and may itself contain spaces or parens, so field
/// splitting starts after the LAST ')' rather than naively splitting on
/// whitespace from the start of the line — the standard technique for this
/// file.
fn parse_ppid(stat_line: &str) -> Option<i32> {
    let after_comm = stat_line.rsplit_once(')')?.1;
    after_comm.split_whitespace().nth(1)?.parse().ok()
}

fn sha256_hex(path: &str) -> Option<String> {
    let data = fs::read(path).ok()?;
    let mut hasher = Sha256::new();
    hasher.update(&data);
    Some(hex::encode(hasher.finalize()))
}

/// Blocking body: init fanotify, mark every watched file, then loop reading
/// events forever. Runs on a dedicated OS thread (see the caller). Returns
/// only on a setup failure (unsupported arch, fanotify_init/mark error) —
/// a running watcher never returns.
fn run_fanotify_blocking(tx: mpsc::UnboundedSender<DetectedChange>) {
    #[cfg(not(any(target_arch = "x86_64", target_arch = "aarch64")))]
    {
        eprintln!("[OmniAgent] Linux FIM: unsupported CPU architecture — fanotify watcher not started");
        return;
    }

    #[cfg(any(target_arch = "x86_64", target_arch = "aarch64"))]
    {
        // SAFETY: fanotify_init/fanotify_mark/read/close are standard Linux
        // syscalls; arguments are constructed per their documented ABI
        // (man 2 fanotify_init, man 2 fanotify_mark). Return values are
        // checked before use.
        let fan_fd: RawFd = unsafe {
            libc::syscall(SYS_FANOTIFY_INIT, FAN_CLASS_NOTIF, libc::O_RDONLY) as RawFd
        };
        if fan_fd < 0 {
            eprintln!(
                "[OmniAgent] Linux FIM: fanotify_init failed (errno {}) — likely missing CAP_SYS_ADMIN; watcher not started",
                std::io::Error::last_os_error()
            );
            return;
        }

        let mut marked = 0usize;
        for &path in FIM_WATCH_FILES {
            let c_path = match CString::new(path) {
                Ok(c) => c,
                Err(_) => continue,
            };
            let rc = unsafe {
                libc::syscall(
                    SYS_FANOTIFY_MARK,
                    fan_fd,
                    FAN_MARK_ADD,
                    FAN_MODIFY | FAN_CLOSE_WRITE,
                    libc::AT_FDCWD,
                    c_path.as_ptr(),
                )
            };
            if rc == 0 {
                marked += 1;
            } else {
                eprintln!(
                    "[OmniAgent] Linux FIM: fanotify_mark failed for {} (errno {})",
                    path,
                    std::io::Error::last_os_error()
                );
            }
        }
        if marked == 0 {
            eprintln!("[OmniAgent] Linux FIM: no watch paths could be marked — watcher not started");
            unsafe { libc::close(fan_fd) };
            return;
        }
        eprintln!("[OmniAgent] Linux FIM: fanotify watcher active on {} path(s)", marked);

        let mut buf = [0u8; 4096];
        loop {
            let n = unsafe { libc::read(fan_fd, buf.as_mut_ptr() as *mut libc::c_void, buf.len()) };
            if n <= 0 {
                eprintln!(
                    "[OmniAgent] Linux FIM: fanotify read failed (errno {}) — stopping this watcher instance",
                    std::io::Error::last_os_error()
                );
                break;
            }

            let mut offset: usize = 0;
            while (offset as isize) + (FAN_EVENT_METADATA_LEN as isize) <= n as isize {
                let meta = unsafe {
                    &*(buf.as_ptr().add(offset) as *const FanotifyEventMetadata)
                };
                if meta.event_len < FAN_EVENT_METADATA_LEN || meta.metadata_len != FAN_EVENT_METADATA_LEN as u16 {
                    // Unrecognized/extended record we don't parse — stop
                    // walking this buffer rather than risk misreading it.
                    break;
                }

                // Recover the path via the event's fd (classic fanotify gives
                // an fd, not a path) before closing it — required per the
                // fanotify API to avoid leaking one fd per event.
                let path = fs::read_link(format!("/proc/self/fd/{}", meta.fd))
                    .ok()
                    .and_then(|p| p.to_str().map(str::to_string));
                unsafe { libc::close(meta.fd) };

                if let Some(path) = path {
                    let _ = tx.send(DetectedChange { path, pid: meta.pid, mask: meta.mask });
                }

                offset += meta.event_len as usize;
            }
        }
        unsafe { libc::close(fan_fd) };
    }
}

/// Async side: owns the HTTP client and baseline hashes, receives detected
/// changes from the blocking fanotify thread, and reports each one to the
/// existing `/api/agents/{agent_id}/fim-events` ingest endpoint (the same
/// one `agentic::realtime_fim_poller` already posts to) with a populated
/// `process` field — the actual point of this phase.
pub async fn linux_fim_watcher(cfg: Arc<RwLock<Config>>, client: Arc<Client>, _running: Arc<AtomicBool>) {
    let mut baseline: HashMap<String, String> = HashMap::new();
    for &path in FIM_WATCH_FILES {
        if let Some(hash) = sha256_hex(path) {
            baseline.insert(path.to_string(), hash);
        }
    }

    let (tx, mut rx) = mpsc::unbounded_channel::<DetectedChange>();
    // The fanotify read loop blocks indefinitely; it must not run on a
    // tokio worker thread (it would starve the runtime), hence spawn_blocking.
    tokio::task::spawn_blocking(move || run_fanotify_blocking(tx));

    while let Some(change) = rx.recv().await {
        let hash_before = baseline.get(&change.path).cloned();
        let hash_after = sha256_hex(&change.path);
        if hash_before == hash_after {
            continue; // metadata-only event (e.g. permission change) — no content diff to report
        }
        if let Some(h) = &hash_after {
            baseline.insert(change.path.clone(), h.clone());
        }

        let change_type = if change.mask & FAN_CLOSE_WRITE != 0 { "modified" } else { "metadata_modified" };
        let ancestry = resolve_process_ancestry(change.pid);
        let process = json!({
            "pid": change.pid,
            "name": ancestry.first().map(|f| f.name.clone()).unwrap_or_else(|| "unknown".to_string()),
            "ancestry": ancestry,
        });

        let (agent_id, token, base) = {
            let c = cfg.read().await;
            match (&c.agent_id, &c.agent_token) {
                (Some(id), Some(tok)) => (id.clone(), tok.clone(), c.api_base_url.trim_end_matches('/').to_string()),
                _ => continue,
            }
        };

        let event: Value = json!({
            "event": change_type,
            "change_type": change_type,
            "path": change.path,
            "hash_before": hash_before,
            "hash_after": hash_after,
            "process": process,
            "ts": chrono::Utc::now().to_rfc3339(),
        });

        eprintln!("[OmniAgent] Linux FIM: {} changed (pid {})", change.path, change.pid);
        let url = format!("{}/api/agents/{}/fim-events", base, agent_id);
        let _ = client.post(&url).bearer_auth(&token)
            .json(&json!({"changes": [event], "detected_at": chrono::Utc::now().to_rfc3339()}))
            .send().await;
    }
}
