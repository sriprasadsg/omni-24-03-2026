/*!
 * Polling loops for OmniAgent Rust edition.
 * Runs four concurrent background tasks:
 *   - instruction_poller  (every 5 s)  — GET instructions, dispatch, POST result
 *   - edr_poller          (every 15 s) — GET EDR response tasks, execute
 *   - playbook_poller     (every 30 s) — GET pending playbooks, execute steps
 *   - threat_intel_poller (every 60 s) — GET IOC broadcasts, auto-block IPs
 */
use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
use std::time::Duration;

use reqwest::Client;
use serde_json::{json, Value};
use tokio::sync::RwLock;

use crate::{buffer::Spool, caps, caps2, cissp, config::Config, yara_scan};

// ── Instruction polling ────────────────────────────────────────────────────────

pub async fn instruction_poller(cfg: Arc<RwLock<Config>>, client: Arc<Client>, running: Arc<AtomicBool>, spool: Arc<Spool>) {
    loop {
        if !running.load(Ordering::Relaxed) { return; }
        tokio::time::sleep(Duration::from_secs(5)).await;
        if !running.load(Ordering::Relaxed) { return; }

        let (agent_id, token, base, vt_key) = {
            let c = cfg.read().await;
            match (&c.agent_id, &c.agent_token) {
                (Some(id), Some(tok)) => (id.clone(), tok.clone(), c.api_base_url.trim_end_matches('/').to_string(), c.virustotal_api_key.clone()),
                _ => continue,
            }
        };

        let url = format!("{}/api/agents/{}/instructions", base, agent_id);
        let resp = match client.get(&url).bearer_auth(&token).send().await {
            Ok(r) if r.status().is_success() => r,
            _ => continue,
        };
        let instructions: Value = match resp.json().await {
            Ok(v) => v,
            Err(_) => continue,
        };
        let instr_list = match instructions.as_array() {
            Some(a) if !a.is_empty() => a.clone(),
            _ => continue,
        };

        for item in instr_list {
            let instr_id = item.get("id").or(item.get("instruction_id"))
                .and_then(|v| v.as_str()).unwrap_or("").to_string();
            let instr_type = item.get("instruction").or(item.get("type")).or(item.get("action"))
                .and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
            let payload = item.get("config").or(item.get("payload"))
                .cloned().unwrap_or(json!({}));

            eprintln!("[OmniAgent] Instruction: {} ({})", instr_type, instr_id);
            let mut result = dispatch_instruction(&instr_type, &payload, &client, &base, &agent_id, &token).await;

            // Option B: enrich YARA hits against VirusTotal locally when a key is configured.
            if let Some(key) = &vt_key {
                if matches!(instr_type.as_str(), "run_yara_scan" | "Run YARA Scan" | "yara_scan") {
                    if let Some(arr) = result.get_mut("matches").and_then(|v| v.as_array_mut()) {
                        crate::vt::enrich_matches(&client, key, arr).await;
                    }
                }
            }

            let result_url = format!("{}/api/agents/{}/instructions/result", base, agent_id);
            let result_body = json!({
                "instruction_id": instr_id,
                "task_id": item.get("task_id").and_then(|v| v.as_str()).unwrap_or(""),
                "type": instr_type,
                "status": result.get("status").and_then(|v| v.as_str()).unwrap_or("success"),
                "result": result,
            });
            // Spool the result if the post fails so a command's outcome isn't lost to a
            // transient outage — it retries on the next successful heartbeat.
            match client.post(&result_url).bearer_auth(&token).json(&result_body).send().await {
                Ok(r) if r.status().is_success() => {}
                _ => spool.enqueue(&result_url, &result_body),
            }

            // Post to capability-specific endpoint if applicable
            post_capability_result(&base, &agent_id, &token, &instr_type, &result, &client).await;
        }
    }
}

async fn post_capability_result(base: &str, id: &str, token: &str, instr: &str, result: &Value, client: &Client) {
    let url = match instr {
        "run_vulnerability_scan" | "Run Vulnerability Scan" =>
            Some(format!("{}/api/agents/{}/vulnerability-scan", base, id)),
        "run_shadow_ai_scan" | "Run Shadow AI Scan" =>
            Some(format!("{}/api/agents/{}/shadow-ai-scan", base, id)),
        "Scan for Persistence" | "run_persistence_scan" =>
            Some(format!("{}/api/agents/{}/persistence-findings", base, id)),
        "run_process_scan" | "Run Process Scan" =>
            Some(format!("{}/api/agents/{}/process-snapshot", base, id)),
        "run_network_discovery" | "Run Network Discovery" =>
            Some(format!("{}/api/agents/{}/discovery/results", base, id)),
        "run_software_scan" | "run_software_inventory" | "Run Software Scan" =>
            Some(format!("{}/api/agents/{}/software-inventory", base, id)),
        "run_pii_scan" | "Run PII Scan" =>
            Some(format!("{}/api/security/pii-findings", base)),
        "run_yara_scan" | "Run YARA Scan" | "yara_scan" =>
            Some(format!("{}/api/agents/{}/malware-scan", base, id)),
        _ => None,
    };
    if let Some(u) = url {
        let _ = client.post(&u).bearer_auth(token).json(result).send().await;
    }
}

// ── EDR response task polling ──────────────────────────────────────────────────

pub async fn edr_poller(cfg: Arc<RwLock<Config>>, client: Arc<Client>, running: Arc<AtomicBool>) {
    loop {
        if !running.load(Ordering::Relaxed) { return; }
        tokio::time::sleep(Duration::from_secs(15)).await;
        if !running.load(Ordering::Relaxed) { return; }

        let (agent_id, token, base, vt_key) = {
            let c = cfg.read().await;
            match (&c.agent_id, &c.agent_token) {
                (Some(id), Some(tok)) => (id.clone(), tok.clone(), c.api_base_url.trim_end_matches('/').to_string(), c.virustotal_api_key.clone()),
                _ => continue,
            }
        };

        let url = format!("{}/api/response/tasks/{}", base, agent_id);
        let tasks: Value = match client.get(&url).bearer_auth(&token).send().await {
            Ok(r) if r.status().is_success() => r.json().await.unwrap_or(Value::Null),
            _ => continue,
        };
        let task_list = match tasks.as_array() {
            Some(a) if !a.is_empty() => a.clone(),
            _ => continue,
        };

        for task in task_list {
            let task_id = task.get("task_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let action  = task.get("action").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let params  = task.get("params").cloned().unwrap_or(json!({}));

            eprintln!("[OmniAgent] EDR task: {} ({})", action, task_id);
            let mut result = dispatch_edr_action(&action, &params).await;

            // Option B: enrich YARA hits against VirusTotal locally when a key is configured.
            if action == "yara_scan" {
                if let Some(key) = &vt_key {
                    if let Some(arr) = result.pointer_mut("/scan/matches").and_then(|v| v.as_array_mut()) {
                        crate::vt::enrich_matches(&client, key, arr).await;
                    }
                }
            }

            let result_url = format!("{}/api/response/tasks/{}/result", base, task_id);
            let _ = client.post(&result_url).bearer_auth(&token).json(&result).send().await;

            // YARA hits carry per-file SHA256 — forward to the malware-scan route so
            // the backend can enrich any hash the agent did not (Option A composes with B).
            if action == "yara_scan" {
                if let Some(scan) = result.get("scan") {
                    let mal_url = format!("{}/api/agents/{}/malware-scan", base, agent_id);
                    let _ = client.post(&mal_url).bearer_auth(&token).json(scan).send().await;
                }
            }
        }
    }
}

// ── Playbook polling ───────────────────────────────────────────────────────────

pub async fn playbook_poller(cfg: Arc<RwLock<Config>>, client: Arc<Client>, running: Arc<AtomicBool>) {
    loop {
        if !running.load(Ordering::Relaxed) { return; }
        tokio::time::sleep(Duration::from_secs(30)).await;
        if !running.load(Ordering::Relaxed) { return; }

        let (agent_id, token, base) = {
            let c = cfg.read().await;
            match (&c.agent_id, &c.agent_token) {
                (Some(id), Some(tok)) => (id.clone(), tok.clone(), c.api_base_url.trim_end_matches('/').to_string()),
                _ => continue,
            }
        };

        let url = format!("{}/api/agents/{}/pending-playbooks", base, agent_id);
        let playbooks: Value = match client.get(&url).bearer_auth(&token).send().await {
            Ok(r) if r.status().is_success() => r.json().await.unwrap_or(Value::Null),
            _ => continue,
        };
        let pb_list = match playbooks.as_array() {
            Some(a) if !a.is_empty() => a.clone(),
            _ => continue,
        };

        for pb in pb_list {
            let pb_id   = pb.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let pb_name = pb.get("name").and_then(|v| v.as_str()).unwrap_or(&pb_id).to_string();
            let steps   = pb.get("steps").and_then(|v| v.as_array()).cloned().unwrap_or_default();

            eprintln!("[OmniAgent] Playbook: {} ({} steps)", pb_name, steps.len());
            let mut status = "executed";

            for step in &steps {
                let action = step.get("action").and_then(|v| v.as_str()).unwrap_or("");
                let params  = step.get("params").cloned().unwrap_or(json!({}));
                let result  = dispatch_instruction(action, &params, &client, &base, &agent_id, &token).await;
                if result.get("status").and_then(|v| v.as_str()) == Some("error") {
                    status = "failed";
                    eprintln!("[OmniAgent] Playbook '{}' step '{}' failed", pb_name, action);
                }
            }

            let ack_url = format!("{}/api/agents/{}/playbook-ack", base, agent_id);
            let _ = client.post(&ack_url).bearer_auth(&token)
                .json(&json!({"playbook_id": pb_id, "status": status}))
                .send().await;
        }
    }
}

// ── Threat intel IOC polling ───────────────────────────────────────────────────

pub async fn threat_intel_poller(cfg: Arc<RwLock<Config>>, client: Arc<Client>, running: Arc<AtomicBool>) {
    loop {
        if !running.load(Ordering::Relaxed) { return; }
        tokio::time::sleep(Duration::from_secs(60)).await;
        if !running.load(Ordering::Relaxed) { return; }

        let (agent_id, token, base) = {
            let c = cfg.read().await;
            match (&c.agent_id, &c.agent_token) {
                (Some(id), Some(tok)) => (id.clone(), tok.clone(), c.api_base_url.trim_end_matches('/').to_string()),
                _ => continue,
            }
        };

        let url = format!("{}/api/agents/{}/threat-intel", base, agent_id);
        let broadcasts: Value = match client.get(&url).bearer_auth(&token).send().await {
            Ok(r) if r.status().is_success() => r.json().await.unwrap_or(Value::Null),
            _ => continue,
        };
        let list = match broadcasts.as_array() {
            Some(a) if !a.is_empty() => a.clone(),
            _ => continue,
        };

        for broadcast in list {
            let iocs = broadcast.get("iocs").cloned().unwrap_or(json!({}));
            // Auto-block malicious IPs
            if let Some(ips) = iocs.get("ips").and_then(|v| v.as_array()) {
                for ip_val in ips {
                    if let Some(ip) = ip_val.as_str() {
                        eprintln!("[OmniAgent] IOC: blocking IP {}", ip);
                        caps::block_ip(ip).await;
                    }
                }
            }
            // Log hash and domain IOCs
            if let Some(hashes) = iocs.get("hashes").and_then(|v| v.as_array()) {
                for h in hashes { eprintln!("[OmniAgent] IOC hash: {}", h); }
            }
            if let Some(domains) = iocs.get("domains").and_then(|v| v.as_array()) {
                for d in domains { eprintln!("[OmniAgent] IOC domain: {}", d); }
            }
        }
    }
}

// ── Instruction dispatcher ─────────────────────────────────────────────────────

pub async fn dispatch_instruction(instr: &str, payload: &Value, client: &Client, base: &str, id: &str, token: &str) -> Value {
    match instr {
        "run_vulnerability_scan" | "Run Vulnerability Scan" =>
            caps::run_vuln_scan().await,

        "run_patch_scan" | "Run Patch Scan" =>
            caps::run_patch_scan().await,

        "install_patches" | "Install Patches" => {
            let ids: Vec<String> = payload.get("patch_ids").and_then(|v| v.as_array())
                .map(|a| a.iter().filter_map(|i| i.as_str().map(String::from)).collect())
                .unwrap_or_default();
            caps::install_patches(&ids).await
        },

        "run_shadow_ai_scan" | "Run Shadow AI Scan" =>
            caps::run_shadow_ai_scan().await,

        "run_compliance_check" | "Run Compliance Check" | "Run Compliance Scan" | "remediate_compliance" => {
            // Run all 3 sources in parallel (same as heartbeat loop) so Collect Now
            // returns the full 47-check merged result, not just the 12 PS checks.
            let (native, comp, comp_ext) = tokio::join!(
                tokio::task::spawn_blocking(crate::compliance_native::run_native_compliance),
                caps::run_compliance_check(),
                crate::caps3::run_compliance_check_extended(),
            );
            let native = native.unwrap_or(serde_json::Value::Null);
            crate::caps3::merge_compliance_checks(
                crate::caps3::merge_compliance_checks(native, comp),
                comp_ext,
            )
        },

        "run_process_scan" | "Run Process Scan" =>
            caps::collect_processes().await,

        "run_network_discovery" | "Run Network Discovery" =>
            caps::run_network_discovery().await,

        "run_fim_scan" | "Run FIM Scan" => {
            let extra: Vec<String> = payload.get("paths").and_then(|v| v.as_array())
                .map(|a| a.iter().filter_map(|i| i.as_str().map(String::from)).collect())
                .unwrap_or_default();
            caps::run_fim_scan(&extra).await
        },

        "run_pii_scan" | "Run PII Scan" => {
            let dirs: Vec<String> = payload.get("directories").or(payload.get("paths"))
                .and_then(|v| v.as_array())
                .map(|a| a.iter().filter_map(|i| i.as_str().map(String::from)).collect())
                .unwrap_or_default();
            caps::run_pii_scan(&dirs).await
        },

        "Scan for Persistence" | "run_persistence_scan" | "scan_persistence" =>
            caps::run_persistence_scan().await,

        "run_software_scan" | "Run Software Scan" | "run_software_inventory" => {
            let r = caps::collect_software().await;
            json!({"status": "success", "software": r.get("software")})
        },

        s if s == "install_software" || s.starts_with("install_software:") => {
            // Backend sends "install_software: <pkg>" — extract pkg from instruction or payload
            let pkg_from_instr = if let Some(pos) = s.find(':') { s[pos+1..].trim() } else { "" };
            let pkg = if !pkg_from_instr.is_empty() {
                pkg_from_instr
            } else {
                payload.get("packageId").or(payload.get("package_id")).or(payload.get("package"))
                    .and_then(|v| v.as_str()).unwrap_or("")
            };
            if pkg.is_empty() { return json!({"status": "error", "error": "packageId required"}); }
            // If download_url is set (from repo/url install paths) use it; make relative paths absolute
            if let Some(raw) = payload.get("download_url").and_then(|v| v.as_str()) {
                let abs: String = if raw.starts_with('/') { format!("{}{}", base, raw) } else { raw.into() };
                caps::install_from_url(&abs, pkg).await
            } else if pkg.starts_with("https://") || pkg.starts_with("http://") {
                // pkg itself is a URL (old server path: action=install, packageId=URL)
                let fname = pkg.split('/').last().unwrap_or("installer");
                caps::install_from_url(pkg, fname).await
            } else {
                caps::install_software(pkg).await
            }
        },

        s if s == "uninstall_software" || s.starts_with("uninstall_software:") => {
            let pkg_from_instr = if let Some(pos) = s.find(':') { s[pos+1..].trim() } else { "" };
            let pkg = if !pkg_from_instr.is_empty() {
                pkg_from_instr
            } else {
                payload.get("packageId").or(payload.get("package_id")).or(payload.get("package"))
                    .and_then(|v| v.as_str()).unwrap_or("")
            };
            if pkg.is_empty() { return json!({"status": "error", "error": "packageId required"}); }
            caps::uninstall_software(pkg).await
        },

        s if s == "upgrade_software" || s.starts_with("upgrade_software:") => {
            let pkg_from_instr = if let Some(pos) = s.find(':') { s[pos+1..].trim() } else { "" };
            let pkg_opt = if !pkg_from_instr.is_empty() {
                Some(pkg_from_instr)
            } else {
                payload.get("packageId").or(payload.get("package_id")).or(payload.get("package"))
                    .and_then(|v| v.as_str())
            };
            caps::upgrade_software(pkg_opt).await
        },

        "collect_logs" => {
            let log = payload.get("log_name").and_then(|v| v.as_str()).unwrap_or("Security");
            let max = payload.get("max_events").and_then(|v| v.as_u64()).unwrap_or(50) as u32;
            caps::collect_logs(log, max).await
        },

        "run_threat_hunt" | "Run Threat Hunt" =>
            caps::run_threat_hunt().await,

        "run_yara_scan" | "Run YARA Scan" | "yara_scan" => {
            let paths: Vec<String> = payload.get("paths").and_then(|v| v.as_array())
                .map(|a| a.iter().filter_map(|v| v.as_str().map(String::from)).collect())
                .unwrap_or_default();
            let refs: Vec<&str> = paths.iter().map(|s| s.as_str()).collect();
            crate::yara_scan::run_yara_scan(&refs).await
        },

        "kill_process" => {
            let pid  = payload.get("pid").and_then(|v| v.as_u64()).map(|p| p as u32);
            let name = payload.get("name").or(payload.get("process_name")).and_then(|v| v.as_str()).map(String::from);
            let r = caps::kill_process(pid, name).await;
            json!({"status": if r["success"].as_bool().unwrap_or(false) {"success"} else {"error"}, "result": r})
        },

        "block_ip" => {
            let ip = payload.get("ip").or(payload.get("remote_ip")).and_then(|v| v.as_str()).unwrap_or("");
            if ip.is_empty() { return json!({"status": "error", "error": "ip required"}); }
            let r = caps::block_ip(ip).await;
            json!({"status": "success", "result": r})
        },

        "isolate_network" | "isolate_host" => {
            let pip = payload.get("platform_ip").and_then(|v| v.as_str()).unwrap_or("localhost");
            let r = caps::isolate_network(pip).await;
            json!({"status": "success", "result": r})
        },

        "enable_privilege_monitoring" | "enable_data_loss_monitoring" =>
            json!({"status": "success", "message": format!("{} activated", instr)}),

        "cloud_metadata" | "collect_cloud_metadata" =>
            crate::caps2::collect_cloud_metadata().await,

        "process_injection_simulation" =>
            json!({"status": "success", "message": "Simulation complete", "findings": []}),

        "start_remote_session" =>
            json!({"status": "error", "error": "Interactive remote shell not supported in Rust agent — use SSH or RDP"}),


        "rollback_patches" =>
            json!({"status": "error", "error": "Patch rollback not supported — reinstall specific package via uninstall_software + install_software"}),

        // ── New capabilities (caps2) ───────────────────────────────────────────
        "run_runtime_security" | "Runtime Security Scan" =>
            crate::caps2::run_runtime_security().await,
        "run_predictive_health" | "Run Predictive Health" =>
            crate::caps2::run_predictive_health().await,
        "run_ueba_scan" | "Run UEBA Scan" =>
            crate::caps2::run_ueba_scan().await,
        "run_sbom_analysis" | "Run SBOM Analysis" =>
            crate::caps2::run_sbom_analysis().await,
        "run_web_monitor" | "Run Web Monitor" => {
            let urls: Vec<String> = payload.get("urls").and_then(|v| v.as_array())
                .map(|a| a.iter().filter_map(|i| i.as_str().map(String::from)).collect())
                .unwrap_or_default();
            crate::caps2::run_web_monitor(&urls).await
        },
        "run_vss_status" | "VSS Status" =>
            crate::caps2::run_vss_status().await,
        "create_vss_snapshot" =>
            crate::caps2::create_vss_snapshot().await,
        "collect_compliance_evidence" | "Collect Compliance Evidence" =>
            crate::caps2::collect_compliance_evidence().await,
        "run_vendor_risk" | "Vendor Risk Scan" =>
            crate::caps2::run_vendor_risk_scan().await,
        "verify_backups" | "Verify Backups" =>
            crate::caps2::verify_backups().await,
        "check_deception_monitor" | "Deception Monitor" =>
            crate::caps2::check_deception_monitor().await,

        "ship_logs" | "Log Shipper" =>
            crate::caps2::ship_logs(client, base, id, token).await,

        "check_agent_update" | "agent_update" =>
            crate::caps2::check_agent_update(client, base, "2.0.0-rust").await,

        "create_ticket" | "report_ticket" => {
            let title = payload.get("title").and_then(|v| v.as_str()).unwrap_or("Agent-generated ticket");
            let desc  = payload.get("description").and_then(|v| v.as_str()).unwrap_or("");
            let sev   = payload.get("severity").and_then(|v| v.as_str()).unwrap_or("medium");
            crate::caps2::create_ticket(client, base, id, token, title, desc, sev).await
        },

        "start_agent_chat" => {
            let session_id = payload.get("session_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let sender     = payload.get("sender").and_then(|v| v.as_str()).unwrap_or("Administrator");
            let subject    = payload.get("subject").and_then(|v| v.as_str()).unwrap_or("Chat Session");
            eprintln!("[OmniAgent] Chat session {} started by {}: {}", session_id, sender, subject);
            if !session_id.is_empty() {
                let url = format!("{}/api/agent-chat/sessions/{}/user-message", base, session_id);
                let auto_reply = format!(
                    "Agent connected (headless mode). Chat session '{}' received. \
                     This agent runs without a display — messages are logged on the endpoint. \
                     To send a reply, use /gsd-execute or contact your administrator.",
                    subject
                );
                let _ = client.post(&url).bearer_auth(token)
                    .json(&json!({"content": auto_reply}))
                    .send().await;
            }
            json!({"status": "success", "session_id": session_id, "mode": "headless"})
        },

        "agent_chat_message" => {
            let session_id = payload.get("session_id").and_then(|v| v.as_str()).unwrap_or("");
            let content    = payload.get("content").and_then(|v| v.as_str()).unwrap_or("");
            let sender     = payload.get("sender").and_then(|v| v.as_str()).unwrap_or("Administrator");
            let preview    = &content[..content.len().min(120)];
            eprintln!("[OmniAgent] Chat [{}] from {}: {}", session_id, sender, preview);
            json!({"status": "success", "received": true})
        },

        _ => json!({"status": "error", "error": format!("Unknown instruction: {}", instr)}),
    }
}

// ── EDR action dispatcher ──────────────────────────────────────────────────────

pub async fn dispatch_edr_action(action: &str, params: &Value) -> Value {
    match action {
        "kill_process" => {
            let pid  = params.get("pid").and_then(|v| v.as_u64()).map(|p| p as u32);
            let name = params.get("name").or(params.get("process_name")).and_then(|v| v.as_str()).map(String::from);
            caps::kill_process(pid, name).await
        },

        "block_ip" | "block_connection" => {
            let ip = params.get("ip").or(params.get("remote_ip")).and_then(|v| v.as_str()).unwrap_or("");
            if ip.is_empty() { return json!({"success": false, "message": "ip required"}); }
            caps::block_ip(ip).await
        },

        "isolate_host" | "isolate_network" => {
            let pip = params.get("platform_ip").and_then(|v| v.as_str()).unwrap_or("localhost");
            caps::isolate_network(pip).await
        },

        "restore_host" => caps::restore_network().await,

        "quarantine_file" => {
            let path = params.get("path").and_then(|v| v.as_str()).unwrap_or("");
            if path.is_empty() { return json!({"success": false, "message": "path required"}); }
            caps::quarantine_file(path).await
        },

        "process_snapshot" => {
            let r = caps::collect_processes().await;
            json!({"success": true, "processes": r.get("processes")})
        },

        "cissp_assessment" => {
            let r = cissp::run_cissp_assessment().await;
            json!({"success": true, "assessment": r})
        },

        "yara_scan" => {
            let paths: Vec<String> = params.get("paths").and_then(|v| v.as_array())
                .map(|a| a.iter().filter_map(|v| v.as_str().map(String::from)).collect())
                .unwrap_or_default();
            let path_refs: Vec<&str> = paths.iter().map(|s| s.as_str()).collect();
            let r = yara_scan::run_yara_scan(&path_refs).await;
            json!({"success": true, "scan": r})
        },

        "remediation_executor" => {
            let base = params.get("base_url").and_then(|v| v.as_str()).unwrap_or("http://localhost:5000");
            let agent_id = params.get("agent_id").and_then(|v| v.as_str()).unwrap_or("");
            let token = params.get("token").and_then(|v| v.as_str()).unwrap_or("");
            let client = reqwest::Client::new();
            let r = caps2::run_remediation(&client, base, agent_id, token).await;
            json!({"success": true, "result": r})
        },

        "process_injection_simulation" => {
            let technique = params.get("technique").and_then(|v| v.as_str()).unwrap_or("");
            let r = caps2::run_process_injection_sim(technique).await;
            json!({"success": true, "simulation": r})
        },

        "rollback_ransomware" =>
            json!({"success": false, "message": "VSS rollback not implemented in Rust agent"}),

        _ => json!({"success": false, "message": format!("Unknown EDR action: {}", action)}),
    }
}
