//! Process Monitor capability — enriched process snapshot for the EDR Process
//! Explorer view. Ports agent/capabilities/process_monitor.py: flat process list
//! + parent/child tree, SHA-256 of each executable (cached by path+mtime so we
//! don't rehash unchanged binaries every cycle), and top CPU/memory summaries.

use super::Capability;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::io::Read;
use std::sync::{Mutex, OnceLock};
use sysinfo::{System, Users};

const MAX_HASH_SIZE: u64 = 50 * 1024 * 1024; // skip hashing executables larger than 50 MB

pub struct ProcessMonitorCapability;

/// {path: (mtime_secs, sha256_or_none)} — persists across collect() calls so an
/// unchanged executable is hashed once, not every heartbeat.
fn hash_cache() -> &'static Mutex<HashMap<String, (u64, Option<String>)>> {
    static CACHE: OnceLock<Mutex<HashMap<String, (u64, Option<String>)>>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

fn hash_exe(path: &str) -> Option<String> {
    let meta = std::fs::metadata(path).ok()?;
    let mtime = meta
        .modified()
        .ok()?
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_secs();

    if let Ok(cache) = hash_cache().lock() {
        if let Some((cached_mtime, cached_hash)) = cache.get(path) {
            if *cached_mtime == mtime {
                return cached_hash.clone();
            }
        }
    }

    // Skip very large executables — unlikely tampered payloads and too slow to hash.
    if meta.len() > MAX_HASH_SIZE {
        if let Ok(mut cache) = hash_cache().lock() {
            cache.insert(path.to_string(), (mtime, None));
        }
        return None;
    }

    let mut file = std::fs::File::open(path).ok()?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 65536];
    loop {
        match file.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => hasher.update(&buf[..n]),
            Err(_) => return None,
        }
    }
    let result = format!("{:x}", hasher.finalize());
    if let Ok(mut cache) = hash_cache().lock() {
        cache.insert(path.to_string(), (mtime, Some(result.clone())));
    }
    Some(result)
}

impl Capability for ProcessMonitorCapability {
    fn id(&self) -> &'static str { "process_monitor" }
    fn name(&self) -> &'static str { "Process Monitor" }

    fn collect(&self, sys: &System) -> Value {
        let users = Users::new_with_refreshed_list();

        // First pass: build a flat entry per process.
        let mut entries: Vec<serde_json::Map<String, Value>> = Vec::new();
        let mut children: HashMap<u32, Vec<u32>> = HashMap::new();
        let mut known_pids: HashSet<u32> = HashSet::new();

        for (pid, proc) in sys.processes() {
            let pid_u = pid.as_u32();
            known_pids.insert(pid_u);

            let ppid = proc.parent().map(|p| p.as_u32());
            let name = proc.name().to_string_lossy().to_string();
            let exe = proc
                .exe()
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_default();
            let sha256 = if exe.is_empty() { None } else { hash_exe(&exe) };

            let mut cmdline = proc
                .cmd()
                .iter()
                .map(|c| c.to_string_lossy())
                .collect::<Vec<_>>()
                .join(" ");
            if cmdline.len() > 300 {
                cmdline.truncate(300);
            }

            let username = proc
                .user_id()
                .and_then(|uid| users.get_user_by_id(uid))
                .map(|u| u.name().to_string())
                .unwrap_or_default();

            let mem_mb = (proc.memory() as f64 / (1024.0 * 1024.0) * 10.0).round() / 10.0;
            let cpu = (proc.cpu_usage() * 10.0).round() / 10.0;
            let threads = proc.tasks().map(|t| t.len()).unwrap_or(0);
            let create_time = chrono::DateTime::from_timestamp(proc.start_time() as i64, 0)
                .map(|dt| dt.to_rfc3339())
                .unwrap_or_default();

            if let (Some(parent), true) = (ppid, ppid != Some(pid_u)) {
                children.entry(parent).or_default().push(pid_u);
            }

            let mut entry = serde_json::Map::new();
            entry.insert("pid".into(), json!(pid_u));
            entry.insert("ppid".into(), json!(ppid));
            entry.insert("name".into(), json!(name));
            entry.insert("username".into(), json!(username));
            entry.insert("exe".into(), json!(exe));
            entry.insert("cmdline".into(), json!(cmdline));
            entry.insert("sha256".into(), json!(sha256));
            entry.insert("create_time".into(), json!(create_time));
            entry.insert("status".into(), json!(format!("{:?}", proc.status())));
            entry.insert("cpu_percent".into(), json!(cpu));
            entry.insert("memory_mb".into(), json!(mem_mb));
            entry.insert("threads".into(), json!(threads));
            // Per-process socket counts need a separate netlink/iphlpapi walk; the
            // runtime_security capability already surfaces active connections, so
            // keep this light and report 0 here rather than duplicating that scan.
            entry.insert("connections".into(), json!(0));
            entries.push(entry);
        }

        // Second pass: attach children arrays and collect roots (no known parent).
        let mut roots: Vec<u32> = Vec::new();
        let mut total_cpu = 0.0_f64;
        for entry in entries.iter_mut() {
            let pid_u = entry.get("pid").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
            let ppid = entry.get("ppid").and_then(|v| v.as_u64()).map(|v| v as u32);
            let kids = children.remove(&pid_u).unwrap_or_default();
            entry.insert("children".into(), json!(kids));
            total_cpu += entry.get("cpu_percent").and_then(|v| v.as_f64()).unwrap_or(0.0);
            match ppid {
                Some(p) if known_pids.contains(&p) && p != pid_u => {}
                _ => roots.push(pid_u),
            }
        }

        let processes: Vec<Value> = entries.iter().map(|e| Value::Object(e.clone())).collect();

        let mut by_cpu = entries.clone();
        by_cpu.sort_by(|a, b| {
            let ca = a.get("cpu_percent").and_then(|v| v.as_f64()).unwrap_or(0.0);
            let cb = b.get("cpu_percent").and_then(|v| v.as_f64()).unwrap_or(0.0);
            cb.partial_cmp(&ca).unwrap_or(std::cmp::Ordering::Equal)
        });
        let top_cpu: Vec<Value> = by_cpu.iter().take(5).map(|e| json!({
            "pid": e.get("pid"), "name": e.get("name"), "cpu": e.get("cpu_percent"),
        })).collect();

        let mut by_mem = entries.clone();
        by_mem.sort_by(|a, b| {
            let ma = a.get("memory_mb").and_then(|v| v.as_f64()).unwrap_or(0.0);
            let mb = b.get("memory_mb").and_then(|v| v.as_f64()).unwrap_or(0.0);
            mb.partial_cmp(&ma).unwrap_or(std::cmp::Ordering::Equal)
        });
        let top_mem: Vec<Value> = by_mem.iter().take(5).map(|e| json!({
            "pid": e.get("pid"), "name": e.get("name"), "memory_mb": e.get("memory_mb"),
        })).collect();

        json!({
            "capability": "process_monitor",
            "timestamp": chrono::Utc::now().to_rfc3339(),
            "platform": if cfg!(windows) { "Windows" } else { "Linux" },
            "process_count": processes.len(),
            "processes": processes,
            "root_pids": roots,
            "total_cpu_percent": (total_cpu * 10.0).round() / 10.0,
            "top_cpu_processes": top_cpu,
            "top_memory_processes": top_mem,
        })
    }
}
