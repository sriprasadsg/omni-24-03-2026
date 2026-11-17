use super::Capability;
use serde_json::{json, Value};
use std::net::IpAddr;
use std::process::Command;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};
use sysinfo::System;

/// How often the route to the platform server is traced again (one trace takes up to ~30 s).
const ROUTE_EVERY: Duration = Duration::from_secs(15 * 60);
const MAX_HOPS: u32 = 20;

pub struct NetworkDiscoveryCapability;

impl Capability for NetworkDiscoveryCapability {
    fn id(&self) -> &'static str { "network_discovery" }
    fn name(&self) -> &'static str { "Network Discovery" }

    fn collect(&self, _sys: &System) -> Value {
        let local_ip = crate::heartbeat::best_ip();
        let subnet = subnet_from_ip(&local_ip);
        let devices = arp_hosts();
        let device_count = devices.len();
        let mut out = json!({
            "local_ip": local_ip,
            "subnet": subnet,
            "devices": devices,
            "device_count": device_count,
            "scanned": device_count > 0,
            "timestamp": chrono::Utc::now().to_rfc3339(),
        });
        if let Some(route) = route_to_server() {
            out["route"] = route;
        }
        out
    }
}

// ── Route to the platform server ────────────────────────────────────────────

#[derive(Default)]
struct RouteState {
    last: Option<Value>,
    started: Option<Instant>,
    running: bool,
}

static ROUTE: OnceLock<Mutex<RouteState>> = OnceLock::new();

/// The last route traced to the platform server; starts a new trace in the background when one is
/// due, so a heartbeat never waits for it.
fn route_to_server() -> Option<Value> {
    let state = ROUTE.get_or_init(|| Mutex::new(RouteState::default()));
    let mut st = state.lock().ok()?;
    let due = st.started.map_or(true, |t| t.elapsed() >= ROUTE_EVERY);
    if due && !st.running {
        if let Some(target) = server_host() {
            st.running = true;
            st.started = Some(Instant::now());
            std::thread::spawn(move || {
                let traced = trace(&target);
                if let Ok(mut st) = state.lock() {
                    st.running = false;
                    if traced.is_some() {
                        st.last = traced;
                    }
                }
            });
        }
    }
    st.last.clone()
}

/// The platform server's host from the agent's config; None for an agent on the server itself.
fn server_host() -> Option<String> {
    let cfg = crate::config::load().ok()?;
    let url = reqwest::Url::parse(&cfg.api_base_url).ok()?;
    let host = url.host_str()?.trim_matches(|c| c == '[' || c == ']').to_string();
    let loopback = host.eq_ignore_ascii_case("localhost") || host.parse::<IpAddr>().map(|ip| ip.is_loopback()).unwrap_or(false);
    (!loopback).then_some(host)
}

fn trace(target: &str) -> Option<Value> {
    let max = MAX_HOPS.to_string();
    #[cfg(windows)]
    let (out, parse): (_, fn(&str) -> Vec<Hop>) = (
        Command::new("tracert").args(["-d", "-h", &max, "-w", "500", target]).output().ok()?,
        parse_tracert,
    );
    #[cfg(not(windows))]
    let (out, parse): (_, fn(&str) -> Vec<Hop>) = (
        Command::new("tracepath").args(["-n", "-m", &max, target]).output().ok()?,
        parse_tracepath,
    );
    let hops = parse(&String::from_utf8_lossy(&out.stdout));
    if hops.is_empty() {
        return None;
    }
    let target_ip = std::net::ToSocketAddrs::to_socket_addrs(&(target, 0)).ok()
        .and_then(|mut a| a.next()).map(|a| a.ip());
    let reached = matches!((target_ip, hops.last().and_then(|h| h.ip)), (Some(t), Some(last)) if t == last);
    Some(json!({
        "target": target,
        "traced_at": chrono::Utc::now().to_rfc3339(),
        "reached": reached,
        "hops": hops.iter().map(|h| json!({"hop": h.hop, "ip": h.ip.map(|ip| ip.to_string()), "rtt_ms": h.rtt_ms})).collect::<Vec<_>>(),
    }))
}

#[derive(Debug, PartialEq)]
pub(crate) struct Hop {
    pub hop: u32,
    pub ip: Option<IpAddr>,
    pub rtt_ms: Option<f64>,
}

/// `tracert -d` output: "  2     5 ms     4 ms    <1 ms  10.10.0.1", "  3     *        *        *     Request timed out."
#[cfg_attr(not(windows), allow(dead_code))] // traced with tracepath off Windows; kept for tests
pub(crate) fn parse_tracert(text: &str) -> Vec<Hop> {
    let mut hops = vec![];
    for line in text.lines() {
        let t: Vec<&str> = line.split_whitespace().collect();
        let Some(hop) = t.first().and_then(|n| n.parse::<u32>().ok()) else { continue };
        let (mut i, mut probes, mut times) = (1, 0, vec![]);
        while i < t.len() && probes < 3 {
            if t[i] == "*" {
                probes += 1;
                i += 1;
                continue;
            }
            let value = t[i].trim_start_matches('<');
            let Ok(ms) = value.trim_end_matches("ms").parse::<f64>() else { break };
            times.push(ms);
            probes += 1;
            i += 1;
            // The unit after a time ("ms", or its translation), unless the next token is already data.
            if i < t.len() && t[i] != "*" && t[i].trim_start_matches('<').parse::<f64>().is_err() && t[i].parse::<IpAddr>().is_err() {
                i += 1;
            }
        }
        if probes == 0 {
            continue;
        }
        let ip = t.last().and_then(|s| s.trim_matches(|c| c == '[' || c == ']').parse::<IpAddr>().ok());
        hops.push(Hop { hop, ip, rtt_ms: average(&times) });
    }
    hops
}

/// `tracepath -n` output: " 1:  192.168.0.1   0.512ms", " 2:  no reply"; a hop may print twice.
#[cfg_attr(windows, allow(dead_code))] // traced with tracert on Windows; kept for tests
pub(crate) fn parse_tracepath(text: &str) -> Vec<Hop> {
    let mut hops: Vec<Hop> = vec![];
    for line in text.lines() {
        let t: Vec<&str> = line.split_whitespace().collect();
        let Some(hop) = t.first().and_then(|n| n.trim_end_matches(':').trim_end_matches('?').parse::<u32>().ok()) else { continue };
        if t.get(1) == Some(&"[LOCALHOST]") {
            continue;
        }
        let ip = t.get(1).and_then(|s| s.parse::<IpAddr>().ok());
        let rtt_ms = t.iter().find_map(|s| s.strip_suffix("ms").and_then(|v| v.parse::<f64>().ok()));
        match hops.iter_mut().find(|h| h.hop == hop) {
            Some(h) if h.ip.is_none() && ip.is_some() => *h = Hop { hop, ip, rtt_ms },
            Some(_) => {}
            None => hops.push(Hop { hop, ip, rtt_ms }),
        }
    }
    hops
}

fn average(times: &[f64]) -> Option<f64> {
    (!times.is_empty()).then(|| (times.iter().sum::<f64>() / times.len() as f64 * 10.0).round() / 10.0)
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

/// Ports checked on each scanned host (short timeout each); the open ones are reported.
const PROBE_PORTS: [u16; 10] = [22, 53, 80, 135, 139, 443, 445, 3389, 8080, 8443];

/// The probed ports that accept a connection.
fn open_ports(ip: &str) -> Vec<u16> {
    PROBE_PORTS.iter().copied().filter(|port| {
        format!("{}:{}", ip, port).parse::<std::net::SocketAddr>()
            .map(|addr| std::net::TcpStream::connect_timeout(&addr, Duration::from_millis(200)).is_ok())
            .unwrap_or(false)
    }).collect()
}

/// A device type guessed from its open ports.
pub(crate) fn device_type(open: &[u16]) -> &'static str {
    let has = |p: u16| open.contains(&p);
    if has(3389) { "Windows (RDP)" }
    else if has(445) { "Windows (SMB)" }
    else if has(22) { "Linux/SSH" }
    else if has(53) && (has(80) || has(443)) { "Router/Firewall" }
    else if has(80) || has(443) || has(8080) || has(8443) { "Web Server" }
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
                let open = open_ports(&ip);
                h["device_type"] = json!(device_type(&open));
                h["open_ports"] = json!(open);
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

#[cfg(test)]
mod route_tests {
    use super::*;

    #[test]
    fn tracert_output_gives_each_hop_its_address_and_average_time() {
        let text = "\r\nTracing route to 57.154.210.55 over a maximum of 20 hops\r\n\r\n  1    <1 ms    <1 ms    <1 ms  192.168.0.1\r\n  2     5 ms     4 ms     6 ms  100.64.0.1\r\n  3     *        *        *     Request timed out.\r\n  4    31 ms     *       32 ms  57.154.210.55\r\n\r\nTrace complete.\r\n";
        let hops = parse_tracert(text);
        assert_eq!(hops.len(), 4);
        assert_eq!(hops[0], Hop { hop: 1, ip: "192.168.0.1".parse().ok(), rtt_ms: Some(1.0) });
        assert_eq!(hops[1].rtt_ms, Some(5.0));
        assert_eq!(hops[2], Hop { hop: 3, ip: None, rtt_ms: None });
        assert_eq!(hops[3], Hop { hop: 4, ip: "57.154.210.55".parse().ok(), rtt_ms: Some(31.5) });
    }

    #[test]
    fn tracepath_output_skips_localhost_and_keeps_the_answering_line_of_a_hop() {
        let text = " 1?: [LOCALHOST]                      pmtu 1500\n 1:  no reply\n 2:  10.0.0.1      0.512ms\n 2:  10.0.0.1      0.733ms\n 3:  51.10.5.89   3.827ms asymm 11\n     Resume: pmtu 1500\n";
        let hops = parse_tracepath(text);
        assert_eq!(hops, vec![
            Hop { hop: 1, ip: None, rtt_ms: None },
            Hop { hop: 2, ip: "10.0.0.1".parse().ok(), rtt_ms: Some(0.512) },
            Hop { hop: 3, ip: "51.10.5.89".parse().ok(), rtt_ms: Some(3.827) },
        ]);
    }

    #[test]
    fn device_type_names_a_gateway_from_dns_and_web_admin() {
        assert_eq!(device_type(&[53, 80, 443]), "Router/Firewall");
        assert_eq!(device_type(&[80]), "Web Server");
        assert_eq!(device_type(&[22, 80]), "Linux/SSH");
        assert_eq!(device_type(&[]), "Unknown");
    }
}
