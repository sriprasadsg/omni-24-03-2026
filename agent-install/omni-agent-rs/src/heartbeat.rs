use crate::{buffer::MessageBuffer, capabilities::CapabilityManager, config::Config};
use serde_json::{json, Value};
use std::sync::{OnceLock, RwLock};
use sysinfo::{Disks, Networks, System};

// ── Public (WAN / ISP-assigned) IP ──────────────────────────────────────────
// best_ip() returns the local LAN interface address. The public IP the ISP
// assigns to the network's gateway can only be discovered by asking an external
// echo service. It rarely changes, so it is resolved asynchronously and cached;
// the (synchronous) heartbeat payload builder reads the cached value.

static PUBLIC_IP: OnceLock<RwLock<Option<String>>> = OnceLock::new();

fn public_ip_cell() -> &'static RwLock<Option<String>> {
    PUBLIC_IP.get_or_init(|| RwLock::new(None))
}

/// Last-known public (ISP-assigned) IP, if it has been resolved.
pub fn cached_public_ip() -> Option<String> {
    public_ip_cell().read().ok().and_then(|g| g.clone())
}

/// Query public IP echo services to discover the WAN address assigned by the
/// ISP. Tries several providers in order and caches the first valid result.
/// Best-effort: on total failure the previous cached value (if any) is kept.
pub async fn refresh_public_ip(client: &reqwest::Client) {
    const ENDPOINTS: &[&str] = &[
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ];
    for url in ENDPOINTS {
        match client
            .get(*url)
            .timeout(std::time::Duration::from_secs(10))
            .send()
            .await
        {
            Ok(resp) if resp.status().is_success() => {
                if let Ok(body) = resp.text().await {
                    let ip = body.trim();
                    if ip.parse::<std::net::IpAddr>().is_ok() {
                        if let Ok(mut g) = public_ip_cell().write() {
                            if g.as_deref() != Some(ip) {
                                log::info!("Public IP resolved: {ip}");
                                *g = Some(ip.to_string());
                            }
                        }
                        return;
                    }
                }
            }
            Ok(resp) => log::debug!("public-ip {url} -> {}", resp.status()),
            Err(e) => log::debug!("public-ip {url} failed: {e}"),
        }
    }
    log::warn!("Could not resolve public IP from any provider");
}

pub fn best_ip() -> String {
    if let Ok(sock) = std::net::UdpSocket::bind("0.0.0.0:0") {
        if sock.connect("8.8.8.8:80").is_ok() {
            if let Ok(addr) = sock.local_addr() {
                let ip = addr.ip().to_string();
                if !ip.starts_with("127.") {
                    return ip;
                }
            }
        }
    }

    if let Ok(addrs) = dns_lookup_interfaces() {
        for prefix in &["192.168.", "10.", "172."] {
            if let Some(ip) = addrs.iter().find(|a| a.starts_with(prefix)) {
                return ip.clone();
            }
        }
        if let Some(ip) = addrs.first() {
            return ip.clone();
        }
    }
    "127.0.0.1".to_string()
}

fn dns_lookup_interfaces() -> Result<Vec<String>, Box<dyn std::error::Error>> {
    use std::net::ToSocketAddrs;
    let hostname = hostname_str();
    let addrs: Vec<String> = (hostname.as_str(), 0u16)
        .to_socket_addrs()?
        .map(|a| a.ip().to_string())
        .filter(|ip| !ip.starts_with("127.") && !ip.contains(':'))
        .collect();
    Ok(addrs)
}

pub fn hostname_str() -> String {
    hostname::get()
        .map(|h| h.to_string_lossy().into_owned())
        .unwrap_or_else(|_| "unknown".to_string())
}

fn os_info() -> Value {
    // Use sysinfo static helpers — no wmic dependency (wmic removed in Windows 11 24H2).
    let os_name    = System::name().unwrap_or_default();
    let os_ver     = System::os_version().unwrap_or_default();
    let long_ver   = System::long_os_version().unwrap_or_default();
    let kernel_ver = System::kernel_version().unwrap_or_default();

    let full_name = if !long_ver.is_empty() { long_ver.clone() } else { os_name.clone() };

    json!({
        "os":            std::env::consts::OS,
        "arch":          std::env::consts::ARCH,
        "os_full_name":  full_name,
        "os_release":    os_ver,
        "kernel_version": kernel_ver,
    })
}

// ── Logged-in (console) user ────────────────────────────────────────────────
// The agent runs as a system service (LocalSystem on Windows, root on
// Linux/macOS), so env vars like USERNAME/USER reflect the service account,
// not whoever is actually sitting at the machine. Each platform below queries
// the real interactive/console session instead. Single active user only
// (first/console session) — multi-session (RDP + console simultaneously) is
// out of scope for now.

#[cfg(windows)]
fn logged_in_user() -> Option<String> {
    use winapi::shared::minwindef::{BOOL, DWORD};
    use winapi::um::winbase::WTSGetActiveConsoleSessionId;
    use winapi::um::winnt::HANDLE;

    // winapi 0.3's wtsapi32 bindings only cover WTSQueryUserToken; declare the
    // two functions this needs ourselves — same DLL is already linked in for
    // WTSQueryUserToken (see chat_ui.rs), so no new link dependency.
    #[allow(non_snake_case)]
    #[link(name = "wtsapi32")]
    extern "system" {
        fn WTSQuerySessionInformationW(
            hServer: HANDLE,
            SessionId: DWORD,
            WTSInfoClass: i32,
            ppBuffer: *mut *mut u16,
            pBytesReturned: *mut DWORD,
        ) -> BOOL;
        fn WTSFreeMemory(pMemory: *mut u16);
    }

    const WTS_USER_NAME: i32 = 5;

    unsafe {
        let session = WTSGetActiveConsoleSessionId();
        if session == 0xFFFF_FFFF {
            return None; // no interactive user logged on
        }

        let mut buffer: *mut u16 = std::ptr::null_mut();
        let mut bytes: DWORD = 0;
        let ok = WTSQuerySessionInformationW(
            std::ptr::null_mut(), // WTS_CURRENT_SERVER_HANDLE
            session,
            WTS_USER_NAME,
            &mut buffer,
            &mut bytes,
        );
        if ok == 0 || buffer.is_null() {
            return None;
        }

        let len = (0isize..).take_while(|&i| *buffer.offset(i) != 0).count();
        let name = String::from_utf16_lossy(std::slice::from_raw_parts(buffer, len));
        WTSFreeMemory(buffer);

        if name.is_empty() { None } else { Some(name) }
    }
}

#[cfg(target_os = "linux")]
fn logged_in_user() -> Option<String> {
    // `who` reads utmp system-wide — reflects real logged-in sessions
    // regardless of the calling (root/service) process's own context.
    let out = std::process::Command::new("who").output().ok()?;
    if !out.status.success() {
        return None;
    }
    String::from_utf8_lossy(&out.stdout)
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().next())
        .map(|s| s.to_string())
}

#[cfg(target_os = "macos")]
fn logged_in_user() -> Option<String> {
    // Owner of /dev/console is the interactively logged-in user, or "root"
    // when nobody is logged in at the console.
    let out = std::process::Command::new("stat")
        .args(["-f%Su", "/dev/console"])
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    let name = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if name.is_empty() || name == "root" { None } else { Some(name) }
}

#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
fn logged_in_user() -> Option<String> {
    None
}

pub fn collect_metrics(sys: &System) -> Value {
    let cpus = sys.cpus();
    let avg_cpu = if cpus.is_empty() {
        0.0
    } else {
        cpus.iter().map(|c| c.cpu_usage()).sum::<f32>() / cpus.len() as f32
    };

    let total_mem = sys.total_memory();
    let used_mem = sys.used_memory();
    let mem_pct = if total_mem > 0 {
        (used_mem as f64 / total_mem as f64 * 100.0) as f32
    } else {
        0.0
    };

    json!({
        "cpu_percent": (avg_cpu * 100.0).round() / 100.0,
        "memory_percent": (mem_pct * 100.0).round() / 100.0,
        "memory_total_mb": total_mem / 1024 / 1024,
        "memory_used_mb": used_mem / 1024 / 1024,
        "process_count": sys.processes().len(),
    })
}

pub fn build_payload(cfg: &Config, sys: &System, cap_mgr: &CapabilityManager) -> Value {
    let cap_data = cap_mgr.collect_all(sys);
    let cap_ids = cap_mgr.ids();
    let cap_statuses = cap_mgr.statuses(&cap_data);

    let cpus = sys.cpus();
    let num_cpus = cpus.len().max(1) as f32;
    let total_mem = sys.total_memory();
    let used_mem = sys.used_memory();
    let mem_pct = if total_mem > 0 {
        used_mem as f32 / total_mem as f32 * 100.0
    } else {
        0.0f32
    };
    let total_mem_gb = (total_mem as f64 / 1_073_741_824.0 * 100.0).round() / 100.0;
    let avail_mem_gb = ((total_mem - used_mem) as f64 / 1_073_741_824.0 * 100.0).round() / 100.0;

    // Agent's own process CPU, normalised to 0-100% of total system capacity.
    // sysinfo cpu_usage() returns per-core % (can exceed 100 on multi-core), so we
    // divide by the number of logical CPUs to get the fraction of total capacity.
    let self_pid = sysinfo::Pid::from(std::process::id() as usize);
    let agent_cpu = sys.process(self_pid)
        .map(|p| (p.cpu_usage() / num_cpus * 10.0).round() / 10.0)
        .unwrap_or(0.0_f32);

    // Disk info for the first (system) drive
    let disks = Disks::new_with_refreshed_list();
    let (disk_pct, disk_total_gb, disk_used_gb, disk_free_gb) = disks.iter().next()
        .map(|d| {
            let total = d.total_space() as f64;
            let free  = d.available_space() as f64;
            let used  = total - free;
            let pct   = if total > 0.0 { (used / total * 100.0 * 10.0).round() / 10.0 } else { 0.0 };
            (pct, (total / 1_073_741_824.0 * 100.0).round() / 100.0,
                  (used  / 1_073_741_824.0 * 100.0).round() / 100.0,
                  (free  / 1_073_741_824.0 * 100.0).round() / 100.0)
        })
        .unwrap_or((0.0, 0.0, 0.0, 0.0));

    // CPU model from sysinfo brand string (e.g. "Intel(R) Core(TM) i7-1185G7 @ 3.00GHz")
    let cpu_model = sys.cpus().first()
        .map(|c| c.brand().to_string())
        .unwrap_or_default();

    // Network interfaces — MAC addresses
    let networks = Networks::new_with_refreshed_list();
    let mac_list: Vec<Value> = networks.iter()
        .filter_map(|(name, data)| {
            let mac = data.mac_address().to_string();
            if mac != "00:00:00:00:00:00" {
                Some(json!({ "interface": name, "mac": mac }))
            } else {
                None
            }
        })
        .collect();
    let primary_mac = mac_list.first()
        .and_then(|m| m["mac"].as_str())
        .unwrap_or("00:00:00:00:00:00")
        .to_string();

    let mut meta = os_info();

    // os_version: "Microsoft Windows 11 Pro (10.0.26200.8524)"
    let os_version = {
        let full = meta["os_full_name"].as_str().unwrap_or("").to_string();
        let release = meta["os_release"].as_str().unwrap_or("").to_string();
        match (full.is_empty(), release.is_empty()) {
            (false, false) => format!("{} ({})", full, release),
            (false, true)  => full,
            _              => release,
        }
    };

    meta["system"] = collect_metrics(sys);
    meta["agent_type"] = json!("rust");

    // Flat keys expected by the backend heartbeat handler
    meta["os_version"]        = json!(os_version);
    meta["cpu_model"]         = json!(cpu_model);
    meta["mac_address"]       = json!(primary_mac);
    meta["mac_addresses"]     = json!(mac_list);
    meta["current_cpu"]       = json!(agent_cpu);
    meta["current_memory"]    = json!((mem_pct * 100.0).round() / 100.0);
    meta["disk_usage"]        = json!(disk_pct);
    meta["total_memory_gb"]   = json!(total_mem_gb);
    meta["available_memory_gb"] = json!(avail_mem_gb);
    meta["disk_total_gb"]     = json!(disk_total_gb);
    meta["disk_used_gb"]      = json!(disk_used_gb);
    meta["disk_free_gb"]      = json!(disk_free_gb);
    if let Some(user) = logged_in_user() {
        meta["logged_in_user"] = json!(user);
    }

    // Merge each capability's collected data into meta
    for (id, data) in &cap_data {
        meta[id.as_str()] = data.clone();
    }
    meta["capabilities"] = json!(cap_ids);
    meta["capabilities_status"] = json!(cap_statuses);

    // WAN / ISP-assigned address (resolved asynchronously, cached). Present only
    // once discovered; absent on the very first heartbeat if resolution is slow.
    let public_ip = cached_public_ip();
    if let Some(ref pub_ip) = public_ip {
        meta["public_ip"] = json!(pub_ip);
    }

    json!({
        "hostname": hostname_str(),
        "tenantId": cfg.tenant_id,
        "status": "Online",
        "platform": if cfg!(windows) { "Windows" } else { "Linux" },
        "version": env!("CARGO_PKG_VERSION"),
        "ipAddress": best_ip(),
        "publicIp": public_ip,
        "meta": meta,
    })
}

pub async fn send(
    cfg: &Config,
    payload: Value,
    buffer: &MessageBuffer,
    client: &reqwest::Client,
) -> bool {
    if cfg.agent_id.is_empty() {
        log::debug!("Skipping heartbeat — agent not yet registered");
        return false;
    }
    let url = format!(
        "{}/api/agents/{}/heartbeat",
        cfg.api_base_url.trim_end_matches('/'),
        cfg.agent_id
    );
    let mut req = client.post(&url).json(&payload);
    if !cfg.agent_token.is_empty() {
        req = req.bearer_auth(&cfg.agent_token);
    }
    let result = req.send().await;

    match result {
        Ok(resp) => {
            let status = resp.status().as_u16();
            log::info!("Heartbeat -> {status}");
            if status == 200 {
                flush_buffer(cfg, buffer, client, &url).await;
                true
            } else {
                buffer.push(&payload);
                false
            }
        }
        Err(e) => {
            log::error!("Heartbeat failed: {e}");
            buffer.push(&payload);
            false
        }
    }
}

async fn flush_buffer(
    cfg: &Config,
    buffer: &MessageBuffer,
    client: &reqwest::Client,
    url: &str,
) {
    let pending = buffer.pending(5);
    if pending.is_empty() {
        return;
    }
    log::info!("Flushing {} buffered heartbeats", pending.len());
    for (id, payload) in pending {
        let mut req = client.post(url).json(&payload);
        if !cfg.agent_token.is_empty() {
            req = req.bearer_auth(&cfg.agent_token);
        }
        match req.send().await {
            Ok(r) if r.status().is_success() => buffer.delete(id),
            Ok(r) => {
                log::warn!("Buffer flush {id} rejected: {}", r.status());
                break;
            }
            Err(e) => {
                log::warn!("Buffer flush {id} error: {e}");
                break;
            }
        }
    }
}
