/*!
 * Core agent logic: registration, heartbeat (with full system data), main loop.
 */
use std::{
    sync::{Arc, atomic::{AtomicBool, Ordering}},
    time::Duration,
};

use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sysinfo::System;
use tokio::sync::RwLock;

use chrono::Utc;
use crate::{agentic, caps, caps2, caps3, cissp, compliance_native, config, http, olog, poll, shell, ws, yara_scan};

const VERSION:          &str = "2.0.0-rust";
const DEFAULT_INTERVAL: u64  = 15;

// ── Registration ───────────────────────────────────────────────────────────────

#[derive(Serialize)]
struct RegPayload<'a> {
    hostname:         &'a str,
    #[serde(rename = "registrationKey")]
    registration_key: &'a str,
    platform:         &'static str,
    version:          &'static str,
    #[serde(rename = "ipAddress")]
    ip_address:       String,
}

#[derive(Deserialize)]
struct RegResponse {
    agent_id:     Option<String>,
    #[serde(rename = "agentId")] agent_id2: Option<String>,
    id:           Option<String>,
    token:        Option<String>,
    agent_token:  Option<String>,
    access_token: Option<String>,
}
impl RegResponse {
    fn id(&self)    -> Option<&str> { self.agent_id.as_deref().or(self.agent_id2.as_deref()).or(self.id.as_deref()) }
    fn token(&self) -> Option<&str> { self.token.as_deref().or(self.agent_token.as_deref()).or(self.access_token.as_deref()) }
}

async fn register(client: &Client, base: &str, key: &str, hostname: &str) -> Result<(String, String), String> {
    let r: RegResponse = client
        .post(format!("{}/api/agents/register", base))
        .json(&RegPayload {
            hostname,
            registration_key: key,
            platform: "Windows",
            version: VERSION,
            ip_address: http::local_ip(),
        })
        .send().await.map_err(|e| e.to_string())?
        .error_for_status().map_err(|e| e.to_string())?
        .json().await.map_err(|e| e.to_string())?;
    match (r.id(), r.token()) {
        (Some(id), Some(tok)) => Ok((id.into(), tok.into())),
        _ => Err("Registration response missing id or token".into()),
    }
}

// ── Heartbeat ──────────────────────────────────────────────────────────────────

// ── Compliance score from live check data ─────────────────────────────────────

fn calc_compliance_score(sec_data: &Value) -> f64 {
    // compliance_enforcement is now a {compliance_checks:[{check,status,details}]} object
    let checks = sec_data
        .get("compliance_enforcement")
        .and_then(|v| v.get("compliance_checks"))
        .and_then(|v| v.as_array());
    let Some(checks) = checks else { return 100.0 };
    if checks.is_empty() { return 100.0 }
    let passed = checks.iter()
        .filter(|c| c.get("status").and_then(|s| s.as_str()) == Some("Pass"))
        .count();
    (passed as f64 / checks.len() as f64) * 100.0
}

const ALL_CAPS: &[&str] = &[
    "metrics_collection","process_monitor","software_management",
    "system_patching","vulnerability_scanning","compliance_enforcement",
    "fim","real_time_fim","pii_scanner","shadow_ai","persistence_detection",
    "network_discovery","log_collection","autonomous_response",
    "edr_realtime","threat_intel","playbook_execution",
    "runtime_security","predictive_health","ueba","sbom_analysis",
    "web_monitor","vss_manager","log_shipper","compliance_evidence_collector",
    "vendor_risk","backup_verifier","deception_monitor","ticket_reporter",
    "cloud_metadata","remote_access","agent_update","patch_installer",
    "agentic_reasoning","yara_scanner","websocket_realtime",
    "cissp_analysis","remediation_executor","process_injection_simulation",
    "chat_window",
];

async fn collect_meta(
    sys: &mut System, software_cache: &Value, hotfix_cache: &Value,
    hw_info: &Value, sec_data: &Value, is_admin: bool,
) -> Value {
    sys.refresh_all();
    sys.refresh_memory();
    sys.refresh_processes();
    let cpu        = sys.global_cpu_info().cpu_usage();
    let mem_used   = sys.used_memory();
    let mem_tot    = sys.total_memory();
    let mem_avail  = sys.available_memory();
    let mem_pct    = if mem_tot > 0 { mem_used as f32 / mem_tot as f32 * 100.0 } else { 0.0 };
    let proc_count = sys.processes().len();
    let cpu_model  = sys.cpus().first().map(|c| c.brand().to_string()).unwrap_or_else(|| "Unknown".into());

    let disks: Vec<Value> = {
        use sysinfo::Disks;
        Disks::new_with_refreshed_list().iter().map(|d| json!({
            "mount":    d.mount_point().to_string_lossy(),
            "total_gb": d.total_space() as f64 / 1_073_741_824.0,
            "free_gb":  d.available_space() as f64 / 1_073_741_824.0,
            "used_gb":  (d.total_space().saturating_sub(d.available_space())) as f64 / 1_073_741_824.0,
            "kind":     format!("{:?}", d.kind()),
        })).collect()
    };

    let (disk_total, disk_used, disk_free) = disks.iter().fold((0.0f64, 0.0f64, 0.0f64), |acc, d| (
        acc.0 + d["total_gb"].as_f64().unwrap_or(0.0),
        acc.1 + d["used_gb"].as_f64().unwrap_or(0.0),
        acc.2 + d["free_gb"].as_f64().unwrap_or(0.0),
    ));
    let disk_pct = if disk_total > 0.0 { disk_used / disk_total * 100.0 } else { 0.0 };

    let current_user = std::env::var("USERNAME").unwrap_or_else(|_| "unknown".into());
    let os_ver = System::os_version().unwrap_or_else(|| "Unknown".into());
    let kernel = System::kernel_version().unwrap_or_else(|| "Unknown".into());

    let sw_inventory: Vec<Value> = software_cache.as_array().map(|arr| {
        arr.iter().map(|sw| json!({
            "name":            sw.get("name").cloned().unwrap_or(Value::Null),
            "current_version": sw.get("version").cloned().unwrap_or(Value::Null),
            "pkg_type":        "installed",
            "is_outdated":     false,
        })).collect()
    }).unwrap_or_default();

    // All capabilities are active in the Rust agent (no dynamic enable/disable)
    let capabilities_status: Vec<Value> = ALL_CAPS.iter().map(|id| json!({
        "id": id, "name": id.replace('_', " "), "enabled": true, "status": "active"
    })).collect();

    let mut meta = json!({
        "current_cpu":          cpu,
        "current_memory":       mem_pct,
        "total_memory_gb":      mem_tot as f64 / 1_073_741_824.0,
        "used_memory_gb":       mem_used as f64 / 1_073_741_824.0,
        "available_memory_gb":  mem_avail as f64 / 1_073_741_824.0,
        "memory_gb":            mem_tot as f64 / 1_073_741_824.0,
        "cpu_model":            cpu_model,
        "os":                   System::name().unwrap_or_else(|| "Windows".into()),
        "os_version":           os_ver,
        "os_release":           System::os_version().unwrap_or_else(|| "Unknown".into()),
        "os_full_name":         System::long_os_version().unwrap_or_else(|| "Unknown".into()),
        "os_version_detail":    kernel,
        "kernel_version":       System::kernel_version().unwrap_or_else(|| "Unknown".into()),
        "uptime_seconds":       System::uptime(),
        "process_count":        proc_count,
        "agent_type":           "rust",
        "agent_version":        VERSION,
        "disks":                disks,
        "disk_usage":           disk_pct,
        "disk_total_gb":        disk_total,
        "disk_used_gb":         disk_used,
        "disk_free_gb":         disk_free,
        "current_user":         current_user,
        "installed_software":   software_cache,
        "software_inventory":   sw_inventory,
        "hotfixes":             hotfix_cache,
        "capabilities":         ALL_CAPS,
        "available_capabilities": ALL_CAPS,
        "capabilities_status":  capabilities_status,
        "is_admin":             is_admin,
        "privilege_level":      if is_admin { "Administrator" } else { "Standard User" },
        "evidence_collection_complete": is_admin,
    });

    // Merge hardware info (mac_address, serial_number, device_type) when available
    if let Some(obj) = hw_info.as_object() {
        if let Some(m) = meta.as_object_mut() {
            for (k, v) in obj { m.insert(k.clone(), v.clone()); }
        }
    }

    // Merge security scan cache: compliance_enforcement, fim, shadow_ai, ueba,
    // persistence_detection, pii_scanner, runtime_security — backend processes each.
    let compliance_score = calc_compliance_score(sec_data);
    if let Some(m) = meta.as_object_mut() {
        m.insert("compliance_score".into(), json!(compliance_score));
        if let Some(sec_obj) = sec_data.as_object() {
            // Skip null entries — a null means the PowerShell check failed; sending null
            // would cause the backend to crash inside process_automated_evidence().
            for (k, v) in sec_obj {
                if !v.is_null() { m.insert(k.clone(), v.clone()); }
            }
        }
    }

    meta
}

async fn send_heartbeat(
    client: &Client, base: &str, id: &str, token: &str,
    hostname: &str, sys: &mut System,
    sw_cache: &Value, hf_cache: &Value, hw_info: &Value, sec_data: &Value, is_admin: bool,
) {
    let meta = collect_meta(sys, sw_cache, hf_cache, hw_info, sec_data, is_admin).await;
    let payload = json!({
        "status":    "Online",
        "platform":  "Windows",
        "version":   VERSION,
        "ipAddress": http::local_ip(),
        "hostname":  hostname,
        "meta":      meta,
    });
    match client.post(format!("{}/api/agents/{}/heartbeat", base, id))
        .bearer_auth(token).json(&payload).send().await
    {
        Ok(r) => {
            let status = r.status();
            if status.is_success() {
                olog!("[heartbeat] ok ({})  cpu={:.1}%  mem={:.1}%",
                    status.as_u16(),
                    payload["meta"]["current_cpu"].as_f64().unwrap_or(0.0),
                    payload["meta"]["current_memory"].as_f64().unwrap_or(0.0));
            } else {
                let body = r.text().await.unwrap_or_default();
                olog!("[heartbeat] server error {} — {}", status, &body[..body.len().min(200)]);
            }
        },
        Err(e) => olog!("[heartbeat] FAILED (network): {}", e),
    }
}

// ── Proactive threat hunt (every 30 min) ──────────────────────────────────────

async fn proactive_hunt(client: &Client, base: &str, id: &str, token: &str) {
    olog!("[hunt] Proactive threat hunt starting…");
    let results = caps::run_threat_hunt().await;
    let url = format!("{}/api/agents/{}/threat-hunt-results", base, id);
    let _ = client.post(&url).bearer_auth(token)
        .json(&json!({
            "results":      results,
            "triggered_by": "proactive_schedule",
            "timestamp":    Utc::now().to_rfc3339(),
        }))
        .send().await;
    olog!("[hunt] Proactive hunt complete.");
}

// ── Main agent loop ────────────────────────────────────────────────────────────

pub async fn agent_loop(running: Arc<AtomicBool>) {
    let path     = config::config_path();
    let mut cfg  = config::load_config(&path);
    let base_url = cfg.api_base_url.trim_end_matches('/').to_string();
    let hostname = System::host_name().unwrap_or_else(|| "unknown-host".into());
    let client   = Arc::new(http::build_client());

    // Log loaded config so the log file shows exactly what was read
    olog!("[start] OmniAgent v{}", VERSION);
    olog!("[config] path:              {}", path.display());
    olog!("[config] api_base_url:      {}", base_url);
    olog!("[config] registration_key:  {}", cfg.registration_key.as_deref().unwrap_or("(MISSING — edit config.yaml)"));
    olog!("[config] agent_id:          {}", cfg.agent_id.as_deref().unwrap_or("(none — will register)"));
    olog!("[config] hostname:          {}", hostname);

    // Check and log Windows administrator privilege — all evidence collection requires it.
    let running_as_admin = http::is_admin().await;
    if running_as_admin {
        olog!("[privilege] Running as Administrator — full evidence collection available.");
    } else {
        olog!("[privilege] WARNING: NOT running as Administrator.");
        olog!("[privilege] Privileged evidence (BitLocker, Defender, audit policy, UEBA, VSS, SBOM)");
        olog!("[privilege] will be incomplete.  Install as a Windows service running as SYSTEM or");
        olog!("[privilege] launch the agent with 'Run as Administrator'.");
    }

    if cfg.agent_id.is_none() || cfg.agent_token.is_none() {
        let key = cfg.registration_key.clone().unwrap_or_default();
        if key.is_empty() {
            olog!("[register] SKIP — registration_key missing in config.yaml");
            olog!("[register] Fix: Stop-Service OmniAgentRust; edit config.yaml; Start-Service OmniAgentRust");
        } else {
            match register(&client, &base_url, &key, &hostname).await {
                Ok((id, tok)) => {
                    olog!("[register] SUCCESS — agent_id: {}", id);
                    cfg.agent_id    = Some(id);
                    cfg.agent_token = Some(tok);
                    config::save_config(&path, &cfg);
                }
                Err(e) => olog!("[register] FAILED: {}", e),
            }
        }
    } else {
        olog!("[register] Already registered — agent_id: {}", cfg.agent_id.as_deref().unwrap_or("?"));
    }

    let shared_cfg = Arc::new(RwLock::new(cfg.clone()));
    let interval   = cfg.interval_seconds.unwrap_or(DEFAULT_INTERVAL);
    olog!("[start] heartbeat interval={}s  offline_threshold=5min", interval);

    // Shared software/hotfix cache — refreshed in background every 5 heartbeats
    let sw_hf_cache: Arc<RwLock<(Value, Value)>> = Arc::new(RwLock::new((json!([]), json!([]))));

    // Security scan cache — each key refreshed at its own interval (backgrounded)
    let sec_cache: Arc<RwLock<Value>> = Arc::new(RwLock::new(json!({})));

    // Static hardware info — collected once in background (WMI can be slow)
    let hw_info_arc: Arc<RwLock<Value>> = Arc::new(RwLock::new(json!({})));
    {
        let hw = hw_info_arc.clone();
        tokio::spawn(async move {
            let (mac, serial, is_vm) = tokio::join!(
                http::run_ps("(Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1).MacAddress"),
                http::run_ps("(Get-WmiObject Win32_BIOS | Select-Object -ExpandProperty SerialNumber)"),
                http::run_ps("$m=(Get-WmiObject Win32_ComputerSystem).Model; if ($m -match 'Virtual|VMware|VirtualBox|HVM|KVM|QEMU') {'virtual'} else {'physical'}")
            );
            *hw.write().await = json!({
                "mac_address":   mac.trim(),
                "serial_number": serial.trim(),
                "is_virtual":    is_vm.trim() == "virtual",
                "device_type":   if is_vm.trim() == "virtual" { "virtual" } else { "workstation" },
            });
        });
    }

    // Spawn all polling and monitoring background tasks
    let tasks: Vec<tokio::task::JoinHandle<()>> = vec![
        tokio::spawn(poll::instruction_poller(shared_cfg.clone(), client.clone(), running.clone())),
        tokio::spawn(poll::edr_poller(shared_cfg.clone(), client.clone(), running.clone())),
        tokio::spawn(poll::playbook_poller(shared_cfg.clone(), client.clone(), running.clone())),
        tokio::spawn(poll::threat_intel_poller(shared_cfg.clone(), client.clone(), running.clone())),
        tokio::spawn(shell::shell_poller(shared_cfg.clone(), client.clone(), running.clone())),
        tokio::spawn(agentic::agentic_poller(shared_cfg.clone(), client.clone(), running.clone())),
        tokio::spawn(agentic::realtime_fim_poller(shared_cfg.clone(), client.clone(), running.clone())),
        tokio::spawn(ws::ws_client(shared_cfg.clone(), running.clone())),
    ];
    drop(tasks); // tasks run independently; we don't join them

    let mut sys = System::new_all();
    let mut tick: u64 = 0;
    let mut hunt_tick: u64 = 0;

    while running.load(Ordering::Relaxed) {
        // Re-register if needed (retries every 30 s until the backend accepts us)
        if cfg.agent_id.is_none() || cfg.agent_token.is_none() {
            let key = cfg.registration_key.clone().unwrap_or_default();
            if !key.is_empty() {
                olog!("[register] Retrying registration…");
                match register(&client, &base_url, &key, &hostname).await {
                    Ok((id, tok)) => {
                        olog!("[register] SUCCESS (retry) — agent_id: {}", id);
                        cfg.agent_id    = Some(id.clone());
                        cfg.agent_token = Some(tok.clone());
                        config::save_config(&path, &cfg);
                        let mut w = shared_cfg.write().await;
                        w.agent_id    = Some(id);
                        w.agent_token = Some(tok);
                    }
                    Err(e) => olog!("[register] Retry FAILED: {}", e),
                }
            }
        }

        // Software/hotfix cache refresh every 20 heartbeats (~5 min)
        if tick % 20 == 0 {
            let cache_ref = sw_hf_cache.clone();
            tokio::spawn(async move {
                let (sw, hf) = tokio::join!(caps::collect_software(), caps::collect_hotfixes());
                *cache_ref.write().await = (
                    sw.get("software").cloned().unwrap_or(json!([])),
                    hf.get("hotfixes").cloned().unwrap_or(json!([])),
                );
            });
        }

        // Security scan refreshes — staggered so they never all fire on the same tick
        // runtime_security + shadow_ai: every 20 ticks (~5 min)
        if tick % 20 == 1 {
            let sc = sec_cache.clone();
            tokio::spawn(async move {
                let (rs, sa) = tokio::join!(caps2::run_runtime_security(), caps::run_shadow_ai_scan());
                let mut w = sc.write().await;
                if let Some(o) = w.as_object_mut() {
                    o.insert("runtime_security".into(), rs);
                    o.insert("shadow_ai".into(), sa);
                }
            });
        }
        // compliance_enforcement + persistence + ueba: every 40 ticks (~10 min)
        if tick % 40 == 2 {
            let sc = sec_cache.clone();
            tokio::spawn(async move {
                // native runs in blocking thread (fast registry reads), PS batches run async
                let (native, comp, comp_ext, pers, ueba) = tokio::join!(
                    tokio::task::spawn_blocking(compliance_native::run_native_compliance),
                    caps::run_compliance_check(),
                    caps3::run_compliance_check_extended(),
                    caps::run_persistence_scan(),
                    caps2::run_ueba_scan(),
                );
                let native = native.unwrap_or(serde_json::Value::Null);
                // native first so PS results override it when PS works;
                // if PS fails (null-filtered), native provides the data.
                let merged = caps3::merge_compliance_checks(
                    caps3::merge_compliance_checks(native, comp),
                    comp_ext,
                );
                let mut w = sc.write().await;
                if let Some(o) = w.as_object_mut() {
                    o.insert("compliance_enforcement".into(), merged);
                    o.insert("persistence_detection".into(), pers);
                    o.insert("ueba".into(), ueba);
                }
            });
        }
        // fim: every 80 ticks (~20 min)
        if tick % 80 == 3 {
            let sc = sec_cache.clone();
            tokio::spawn(async move {
                let fim = caps::run_fim_scan(&[]).await;
                let mut w = sc.write().await;
                if let Some(o) = w.as_object_mut() { o.insert("fim".into(), fim); }
            });
        }
        // pii_scanner: every 120 ticks (~30 min, most expensive)
        if tick % 120 == 4 {
            let sc = sec_cache.clone();
            tokio::spawn(async move {
                let pii = caps::run_pii_scan(&[]).await;
                let mut w = sc.write().await;
                if let Some(o) = w.as_object_mut() { o.insert("pii_scanner".into(), pii); }
            });
        }
        // yara_scan: every 240 ticks (~60 min)
        if tick % 240 == 5 {
            let sc = sec_cache.clone();
            tokio::spawn(async move {
                let yara = yara_scan::run_yara_scan(&[]).await;
                let mut w = sc.write().await;
                if let Some(o) = w.as_object_mut() { o.insert("yara_scan".into(), yara); }
            });
        }
        // cissp_assessment: every 480 ticks (~120 min, all 8 domains)
        if tick % 480 == 6 {
            let sc = sec_cache.clone();
            tokio::spawn(async move {
                let cissp = cissp::run_cissp_assessment().await;
                let mut w = sc.write().await;
                if let Some(o) = w.as_object_mut() { o.insert("cissp_assessment".into(), cissp); }
            });
        }

        if let (Some(id), Some(tok)) = (&cfg.agent_id, &cfg.agent_token) {
            let (sw_cache, hf_cache) = {
                let c = sw_hf_cache.read().await;
                (c.0.clone(), c.1.clone())
            };
            let hw_info  = hw_info_arc.read().await.clone();
            let sec_data = sec_cache.read().await.clone();
            send_heartbeat(&client, &base_url, id, tok, &hostname, &mut sys, &sw_cache, &hf_cache, &hw_info, &sec_data, running_as_admin).await;

            // Proactive hunt every 120 ticks (~30 min)
            if hunt_tick % 120 == 0 {
                let (ic, ib, it) = (client.clone(), base_url.clone(), tok.clone());
                let iid = id.clone();
                tokio::spawn(async move { proactive_hunt(&ic, &ib, &iid, &it).await; });
            }
            hunt_tick += 1;
        }

        tick += 1;
        for _ in 0..interval {
            if !running.load(Ordering::Relaxed) { return; }
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
    }
}
