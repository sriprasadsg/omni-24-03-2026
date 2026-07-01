use super::Capability;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use sysinfo::System;

// Always suspicious — these tools have no legitimate system path.
static SUSPICIOUS_ALWAYS: &[&str] = &[
    "mimikatz", "nc.exe", "netcat", "psexec",
];

// LOLBins — legitimate Windows system binaries that are abused by attackers.
// Only flag them when running outside of the Windows system directories.
static SUSPICIOUS_LOLBINS: &[&str] = &[
    "mshta", "wscript", "cscript", "regsvr32", "rundll32", "certutil", "bitsadmin",
];

fn is_system_path(path: &str) -> bool {
    let p = path.to_lowercase();
    p.contains(r"windows\system32") || p.contains(r"windows\syswow64") || p.contains(r"windows\sysnative")
}

pub struct RuntimeSecurityCapability {
    baseline: Mutex<HashSet<String>>,
}

impl RuntimeSecurityCapability {
    pub fn new() -> Self {
        RuntimeSecurityCapability {
            baseline: Mutex::new(HashSet::new()),
        }
    }
}

impl Capability for RuntimeSecurityCapability {
    fn id(&self) -> &'static str { "runtime_security" }
    fn name(&self) -> &'static str { "Runtime Security" }

    fn collect(&self, sys: &System) -> Value {
        let total_mem = sys.total_memory();
        let scan_time = chrono::Utc::now().to_rfc3339();

        let mut current_names: HashSet<String> = HashSet::new();
        let mut all_processes: Vec<Value> = Vec::new();
        let mut suspicious: Vec<Value> = Vec::new();

        for (pid, proc) in sys.processes() {
            let name_lower = proc.name().to_string_lossy().to_lowercase();
            let name_orig = proc.name().to_string_lossy().to_string();
            current_names.insert(name_lower.clone());

            let cpu = proc.cpu_usage();
            let mem_pct = if total_mem > 0 {
                (proc.memory() as f64 / total_mem as f64 * 100.0 * 10.0).round() / 10.0
            } else {
                0.0
            };
            let user: String = String::new(); // sysinfo Uid lacks Display on Windows

            all_processes.push(json!({
                "pid": pid.as_u32(),
                "name": name_orig,
                "user": user,
                "cpu_percent": (cpu * 10.0).round() / 10.0,
                "memory_percent": mem_pct,
            }));

            let exe_path = proc.exe()
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_default();

            let always_hit = SUSPICIOUS_ALWAYS.iter().find(|&&kw| name_lower.contains(kw));
            // Only flag a LOLBin when we have a confirmed non-system path.
            // Empty path means we couldn't read it (permissions) — don't alert.
            let lolbin_hit = if !exe_path.is_empty() && !is_system_path(&exe_path) {
                SUSPICIOUS_LOLBINS.iter().find(|&&kw| name_lower.contains(kw))
            } else {
                None
            };

            if let Some(kw) = always_hit.or(lolbin_hit) {
                let (severity, detail) = if always_hit.is_some() {
                    ("high", String::new())
                } else {
                    ("medium", format!(" (outside system directory: {})", exe_path))
                };
                suspicious.push(json!({
                    "type": "Suspicious Process",
                    "description": format!("Process '{}' (PID {}) matches suspicious pattern '{}'{}",
                        name_orig, pid.as_u32(), kw, detail),
                    "severity": severity,
                    "timestamp": scan_time,
                }));
            }
        }

        // Sort by CPU descending, expose top 20
        all_processes.sort_by(|a, b| {
            let ca = a["cpu_percent"].as_f64().unwrap_or(0.0);
            let cb = b["cpu_percent"].as_f64().unwrap_or(0.0);
            cb.partial_cmp(&ca).unwrap_or(std::cmp::Ordering::Equal)
        });
        all_processes.truncate(20);
        suspicious.truncate(10);

        let mut baseline = self.baseline.lock().unwrap_or_else(|p| p.into_inner());
        let new_process_count = if baseline.is_empty() {
            0
        } else {
            current_names.difference(&*baseline).count()
        };
        *baseline = current_names.clone();

        // Build pid→name map for connection enrichment
        let pid_names: HashMap<u32, String> = sys.processes().iter()
            .map(|(pid, proc)| (pid.as_u32(), proc.name().to_string_lossy().to_string()))
            .collect();

        let connections = active_connections(&pid_names);
        let connection_count = connections.len();

        json!({
            "processes": all_processes,
            "connections": connections,
            "suspicious_activities": suspicious,
            "process_count": current_names.len(),
            "connection_count": connection_count,
            "active_processes": current_names.len(),
            "new_processes": new_process_count,
            "scan_time": scan_time,
        })
    }
}

/// Parse `netstat -ano` output into a list of active connections enriched with process names.
fn active_connections(pid_names: &HashMap<u32, String>) -> Vec<Value> {
    let output = std::process::Command::new("netstat")
        .args(["-ano"])
        .output();

    let text = match output {
        Ok(o) => String::from_utf8_lossy(&o.stdout).to_string(),
        Err(_) => return vec![],
    };

    let mut connections: Vec<Value> = Vec::new();

    for line in text.lines() {
        let parts: Vec<&str> = line.split_whitespace().collect();
        // netstat -ano columns: Proto  Local  Foreign  State  PID  (TCP)
        //                       Proto  Local  Foreign         PID  (UDP)
        if parts.len() < 4 {
            continue;
        }
        let proto = parts[0].to_uppercase();
        if proto != "TCP" && proto != "UDP" {
            continue;
        }

        let (local, remote, state, pid_str) = if proto == "TCP" && parts.len() >= 5 {
            (parts[1], parts[2], parts[3], parts[4])
        } else if proto == "UDP" && parts.len() >= 4 {
            (parts[1], parts[2], "-", parts[3])
        } else {
            continue;
        };

        let pid: u32 = match pid_str.parse() {
            Ok(p) => p,
            Err(_) => continue,
        };

        let process_name = pid_names.get(&pid).cloned().unwrap_or_default();

        connections.push(json!({
            "protocol": proto,
            "local_address": local,
            "remote_address": remote,
            "state": state,
            "pid": pid,
            "process": process_name,
        }));
    }

    // Cap at 50 to avoid flooding the payload
    connections.truncate(50);
    connections
}
