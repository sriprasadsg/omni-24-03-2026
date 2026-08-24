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

// ── Hardware serial number ──────────────────────────────────────────────────
// Resolved once and cached: the underlying platform call (a `powershell`
// spawn on Windows) is too slow to repeat every heartbeat, and the value
// never changes for the life of the process.

static SERIAL_NUMBER: OnceLock<String> = OnceLock::new();

fn serial_number() -> String {
    SERIAL_NUMBER.get_or_init(detect_serial_number).clone()
}

fn fallback_serial() -> String {
    format!("SN-{}", hostname_str().chars().take(12).collect::<String>())
}

#[cfg(windows)]
fn detect_serial_number() -> String {
    // wmic.exe was removed starting Windows 11 24H2; Get-CimInstance talks to
    // the same underlying WMI/CIM subsystem and is still present everywhere.
    let out = std::process::Command::new("powershell")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "(Get-CimInstance -ClassName Win32_BIOS).SerialNumber",
        ])
        .output();
    if let Ok(out) = out {
        let serial = String::from_utf8_lossy(&out.stdout).trim().to_string();
        if !serial.is_empty() && serial != "To Be Filled By O.E.M." {
            return serial;
        }
    }
    fallback_serial()
}

#[cfg(target_os = "linux")]
fn detect_serial_number() -> String {
    std::fs::read_to_string("/sys/class/dmi/id/product_serial")
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(fallback_serial)
}

#[cfg(target_os = "macos")]
fn detect_serial_number() -> String {
    let out = std::process::Command::new("system_profiler")
        .arg("SPHardwareDataType")
        .output();
    if let Ok(out) = out {
        let text = String::from_utf8_lossy(&out.stdout);
        for line in text.lines() {
            if let Some((_, val)) = line.split_once("Serial Number") {
                let val = val.trim_start_matches(':').trim();
                if !val.is_empty() {
                    return val.to_string();
                }
            }
        }
    }
    fallback_serial()
}

#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
fn detect_serial_number() -> String {
    fallback_serial()
}

// ── Device type / chassis classification ────────────────────────────────────
// Resolved once and cached — same rationale as serial_number above. Mirrors
// the Python agent's PlatformUtils.detect_device_type() core detection paths
// (chassis code + VM check); the deepest last-resort fallbacks there (battery
// presence, hostname substring guessing) are skipped as low-value.

static DEVICE_TYPE: OnceLock<Value> = OnceLock::new();

fn device_type_info() -> Value {
    DEVICE_TYPE.get_or_init(detect_device_type).clone()
}

const CHASSIS_LABELS: &[(u32, &str)] = &[
    (1, "Other"), (2, "Unknown"), (3, "Desktop"), (4, "Low Profile Desktop"),
    (5, "Pizza Box"), (6, "Mini Tower"), (7, "Tower"), (8, "Portable"),
    (9, "Laptop"), (10, "Notebook"), (11, "Hand Held"), (12, "Docking Station"),
    (13, "All In One"), (14, "Sub Notebook"), (15, "Space-saving"),
    (16, "Lunch Box"), (17, "Main Server Chassis"), (18, "Expansion Chassis"),
    (19, "Sub Chassis"), (20, "Bus Expansion Chassis"), (21, "Peripheral Chassis"),
    (22, "RAID Chassis"), (23, "Rack Mount Chassis"), (24, "Sealed-Case PC"),
    (25, "Multi-system Chassis"), (26, "CompactPCI"), (27, "AdvancedTCA"),
    (28, "Blade"), (29, "Blade Enclosure"), (30, "Tablet"),
    (31, "Convertible"), (32, "Detachable"), (33, "IoT Gateway"),
    (34, "Embedded PC"), (35, "Mini PC"), (36, "Stick PC"),
];
const LAPTOP_CODES: &[u32] = &[8, 9, 10, 11, 14, 30, 31, 32];
const SERVER_CODES: &[u32] = &[17, 18, 19, 20, 21, 22, 23, 25, 26, 27, 28, 29];
const DESKTOP_CODES: &[u32] = &[3, 4, 5, 6, 7, 12, 13, 15, 16, 24, 34, 35, 36];
const VM_STRINGS: &[&str] = &[
    "virtualbox", "vmware", "virtual machine", "kvm", "qemu",
    "hyper-v", "xen", "parallels", "bochs", "innotek",
];

fn chassis_label(code: u32) -> &'static str {
    CHASSIS_LABELS.iter().find(|(c, _)| *c == code).map(|(_, l)| *l).unwrap_or("Unknown")
}

fn is_vm_by_strings(text: &str) -> bool {
    let lower = text.to_lowercase();
    VM_STRINGS.iter().any(|s| lower.contains(s))
}

fn unknown_device() -> Value {
    json!({ "device_type": "unknown", "chassis_label": "Unknown", "is_virtual": false })
}

fn vm_device() -> Value {
    json!({ "device_type": "virtual_machine", "chassis_label": "Virtual Machine", "is_virtual": true })
}

#[cfg(windows)]
fn detect_device_type() -> Value {
    fn ps(cmd: &str) -> String {
        std::process::Command::new("powershell")
            .args(["-NoProfile", "-NonInteractive", "-Command", cmd])
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
            .unwrap_or_default()
    }

    let model = ps("(Get-CimInstance Win32_ComputerSystem).Model");
    if is_vm_by_strings(&model) {
        return vm_device();
    }

    let chassis_code: Option<u32> = ps("(Get-CimInstance Win32_SystemEnclosure).ChassisTypes")
        .trim_matches(|c| c == '{' || c == '}')
        .split(',')
        .next()
        .and_then(|s| s.trim().parse().ok());

    if let Some(code) = chassis_code {
        let label = chassis_label(code);
        if LAPTOP_CODES.contains(&code) {
            return json!({ "device_type": "laptop", "chassis_label": label, "is_virtual": false });
        }
        if SERVER_CODES.contains(&code) {
            return json!({ "device_type": "server", "chassis_label": label, "is_virtual": false });
        }
    }

    let pc_type: Option<u32> = ps("(Get-CimInstance Win32_ComputerSystem).PCSystemType").parse().ok();
    let device_type = match pc_type {
        Some(1) | Some(6) => "desktop",
        Some(2) => "laptop",
        Some(3) => "workstation",
        Some(4) | Some(5) | Some(7) => "server",
        _ => "unknown",
    };
    if device_type != "unknown" {
        return json!({
            "device_type": device_type,
            "chassis_label": chassis_code.map(chassis_label).unwrap_or("Unknown"),
            "is_virtual": false,
        });
    }

    unknown_device()
}

#[cfg(target_os = "linux")]
fn detect_device_type() -> Value {
    let sys_vendor = std::fs::read_to_string("/sys/class/dmi/id/sys_vendor").unwrap_or_default();
    let product_name = std::fs::read_to_string("/sys/class/dmi/id/product_name").unwrap_or_default();
    let is_virtual = std::process::Command::new("systemd-detect-virt")
        .arg("--quiet")
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
        || is_vm_by_strings(&format!("{sys_vendor} {product_name}"));

    if is_virtual {
        return vm_device();
    }

    let chassis_code: Option<u32> = std::fs::read_to_string("/sys/class/dmi/id/chassis_type")
        .ok()
        .and_then(|s| s.trim().parse().ok());

    if let Some(code) = chassis_code {
        let label = chassis_label(code);
        if LAPTOP_CODES.contains(&code) {
            return json!({ "device_type": "laptop", "chassis_label": label, "is_virtual": false });
        }
        if SERVER_CODES.contains(&code) {
            return json!({ "device_type": "server", "chassis_label": label, "is_virtual": false });
        }
        if DESKTOP_CODES.contains(&code) {
            let cpu_count = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1);
            let device_type = if cpu_count >= 8 { "workstation" } else { "desktop" };
            return json!({ "device_type": device_type, "chassis_label": label, "is_virtual": false });
        }
    }

    unknown_device()
}

#[cfg(target_os = "macos")]
fn detect_device_type() -> Value {
    let model_line = std::process::Command::new("system_profiler")
        .arg("SPHardwareDataType")
        .output()
        .ok()
        .map(|o| String::from_utf8_lossy(&o.stdout).to_lowercase())
        .and_then(|text| {
            text.lines()
                .find(|l| l.contains("model name") || l.contains("model identifier"))
                .map(|l| l.to_string())
        })
        .unwrap_or_default();

    if model_line.contains("macbook") {
        json!({ "device_type": "laptop", "chassis_label": "MacBook", "is_virtual": false })
    } else if model_line.contains("xserve") {
        json!({ "device_type": "server", "chassis_label": "Xserve", "is_virtual": false })
    } else if model_line.contains("mac pro") {
        json!({ "device_type": "workstation", "chassis_label": "Mac Pro", "is_virtual": false })
    } else if model_line.contains("imac") || model_line.contains("mac mini") {
        json!({ "device_type": "desktop", "chassis_label": "Mac Desktop", "is_virtual": false })
    } else if is_vm_by_strings(&model_line) {
        vm_device()
    } else {
        unknown_device()
    }
}

#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
fn detect_device_type() -> Value {
    unknown_device()
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
    meta["serial_number"]     = json!(serial_number());
    let device_info = device_type_info();
    meta["device_type"]    = device_info["device_type"].clone();
    meta["chassis_label"]  = device_info["chassis_label"].clone();
    meta["is_virtual"]     = device_info["is_virtual"].clone();
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
