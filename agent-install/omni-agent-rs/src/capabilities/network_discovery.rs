use super::Capability;
use serde_json::{json, Value};
use std::process::Command;
use sysinfo::System;

pub struct NetworkDiscoveryCapability;

impl Capability for NetworkDiscoveryCapability {
    fn id(&self) -> &'static str { "network_discovery" }
    fn name(&self) -> &'static str { "Network Discovery" }

    fn collect(&self, _sys: &System) -> Value {
        let local_ip = crate::heartbeat::best_ip();
        let subnet = subnet_from_ip(&local_ip);
        let devices = arp_hosts();
        let device_count = devices.len();
        json!({
            "local_ip": local_ip,
            "subnet": subnet,
            "devices": devices,
            "device_count": device_count,
            "scanned": device_count > 0,
            "timestamp": chrono::Utc::now().to_rfc3339(),
        })
    }
}

fn arp_hosts() -> Vec<Value> {
    let output = Command::new("arp").args(["-a"]).output();
    let text = match output {
        Ok(o) => String::from_utf8_lossy(&o.stdout).to_string(),
        Err(_) => return vec![],
    };

    let mut hosts = vec![];
    for line in text.lines() {
        let line = line.trim();
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() >= 2 {
            let ip = parts[0];
            let mac = parts[1];
            if ip.contains('.') && mac.contains('-') {
                let entry_type = if parts.len() >= 3 { parts[2] } else { "unknown" };
                hosts.push(json!({ "ip": ip, "mac": mac, "type": entry_type }));
            }
        }
    }
    hosts
}

fn subnet_from_ip(ip: &str) -> String {
    let parts: Vec<&str> = ip.split('.').collect();
    if parts.len() == 4 {
        format!("{}.{}.{}.0/24", parts[0], parts[1], parts[2])
    } else {
        String::new()
    }
}

fn subnet_prefix(ip: &str) -> Option<String> {
    let parts: Vec<&str> = ip.split('.').collect();
    if parts.len() == 4 {
        Some(format!("{}.{}.{}", parts[0], parts[1], parts[2]))
    } else {
        None
    }
}

/// Batch-parallel ICMP ping sweep to populate the OS ARP cache before reading it.
fn ping_sweep(prefix: &str) {
    const BATCH: usize = 32;
    let ips: Vec<String> = (1u8..=254).map(|i| format!("{}.{}", prefix, i)).collect();
    for chunk in ips.chunks(BATCH) {
        let handles: Vec<_> = chunk.iter().map(|ip| {
            let ip = ip.clone();
            std::thread::spawn(move || {
                #[cfg(windows)]
                let _ = Command::new("ping")
                    .args(["-n", "1", "-w", "100", &ip])
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .output();
                #[cfg(not(windows))]
                let _ = Command::new("ping")
                    .args(["-c", "1", "-W", "1", &ip])
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .output();
            })
        }).collect();
        for h in handles { let _ = h.join(); }
    }
}

/// Check a few well-known ports to classify the device type. Runs with a short timeout.
fn probe_device_type(ip: &str) -> &'static str {
    let check = |port: u16| -> bool {
        let addr: std::net::SocketAddr = match format!("{}:{}", ip, port).parse() {
            Ok(a) => a,
            Err(_) => return false,
        };
        std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_millis(200)).is_ok()
    };

    if check(3389) { "Windows (RDP)" }
    else if check(445) { "Windows (SMB)" }
    else if check(22) { "Linux/SSH" }
    else if check(80) { "Web Server" }
    else { "Unknown" }
}

/// Active scan: ping sweep → ARP read → parallel port-based device classification.
pub fn scan_now() -> Value {
    let local_ip = crate::heartbeat::best_ip();
    if let Some(prefix) = subnet_prefix(&local_ip) {
        log::info!("Network scan: pinging {}.0/24", prefix);
        ping_sweep(&prefix);
    }

    let subnet = subnet_from_ip(&local_ip);
    let raw_hosts = arp_hosts();

    // Classify all discovered hosts in parallel
    let handles: Vec<_> = raw_hosts.into_iter().map(|host| {
        std::thread::spawn(move || {
            let mut h = host;
            if let Some(ip) = h.get("ip").and_then(|v| v.as_str()).map(|s| s.to_string()) {
                h["device_type"] = json!(probe_device_type(&ip));
            }
            h
        })
    }).collect();

    let devices: Vec<Value> = handles.into_iter()
        .filter_map(|h| h.join().ok())
        .collect();
    let device_count = devices.len();

    json!({
        "local_ip": local_ip,
        "subnet": subnet,
        "devices": devices,
        "device_count": device_count,
        "scan_type": "active",
        "timestamp": chrono::Utc::now().to_rfc3339(),
    })
}
