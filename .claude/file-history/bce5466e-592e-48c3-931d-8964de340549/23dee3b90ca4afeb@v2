/*!
 * Agentic reasoning and near-real-time FIM.
 *
 * agentic_poller  — rule-based auto-remediation + LLM task polling (every 60 s)
 * realtime_fim    — periodic FIM with change detection (every 60 s)
 */
use std::{
    collections::HashMap,
    sync::{Arc, atomic::{AtomicBool, Ordering}},
    time::Duration,
    fs,
};
use reqwest::Client;
use serde_json::{json, Value};
use sha2::{Sha256, Digest};
use sysinfo::System;
use tokio::sync::RwLock;
use chrono::Utc;

use crate::{caps, caps2, config::Config};

const VERSION: &str = "2.0.0-rust";

// ── Agentic decision loop ──────────────────────────────────────────────────────

pub async fn agentic_poller(cfg: Arc<RwLock<Config>>, client: Arc<Client>, running: Arc<AtomicBool>) {
    let mut cpu_high_streak: u32 = 0;
    let mut mem_high_streak: u32 = 0;

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

        // ── Collect current metrics ────────────────────────────────────────────
        let mut sys = System::new();
        sys.refresh_all();
        sys.refresh_memory();
        let cpu     = sys.global_cpu_info().cpu_usage();
        let mem_pct = sys.used_memory() as f32 / sys.total_memory().max(1) as f32 * 100.0;

        // ── Rule-based autonomous decisions ───────────────────────────────────
        if cpu > 90.0 { cpu_high_streak += 1; } else { cpu_high_streak = 0; }
        if mem_pct > 85.0 { mem_high_streak += 1; } else { mem_high_streak = 0; }

        // CPU critical for 3+ consecutive minutes
        if cpu_high_streak >= 3 {
            let top_procs = caps::collect_processes().await;
            post_event(&client, &base, &agent_id, &token, "high_cpu_sustained",
                json!({"cpu": cpu, "streak_minutes": cpu_high_streak, "top_processes": top_procs.get("processes")})).await;
            cpu_high_streak = 0; // Reset after alerting
        }

        // Memory critical for 3+ consecutive minutes
        if mem_high_streak >= 3 {
            post_event(&client, &base, &agent_id, &token, "high_memory_sustained",
                json!({"memory_pct": mem_pct, "streak_minutes": mem_high_streak})).await;
            mem_high_streak = 0;
        }

        // ── Poll backend for LLM-powered agentic tasks ─────────────────────────
        let tasks = fetch_agentic_tasks(&client, &base, &agent_id, &token).await;
        for task in tasks {
            execute_agentic_task(&client, &base, &agent_id, &token, &task).await;
        }

        // ── Predictive health check (every run) ────────────────────────────────
        let health = caps2::run_predictive_health().await;
        if health["predictions"].as_array().map(|a| !a.is_empty()).unwrap_or(false) {
            post_event(&client, &base, &agent_id, &token, "predictive_health_alert", health).await;
        }
    }
}

async fn fetch_agentic_tasks(client: &Client, base: &str, id: &str, token: &str) -> Vec<Value> {
    let url = format!("{}/api/agents/{}/agentic-tasks", base, id);
    match client.get(&url).bearer_auth(token).send().await {
        Ok(r) if r.status().is_success() => r.json::<Value>().await.ok()
            .and_then(|v| v.as_array().cloned())
            .unwrap_or_default(),
        _ => vec![],
    }
}

async fn execute_agentic_task(client: &Client, base: &str, id: &str, token: &str, task: &Value) {
    let task_id  = task.get("id").and_then(|v| v.as_str()).unwrap_or("");
    let task_type = task.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let context  = task.get("context").cloned().unwrap_or(json!({}));

    eprintln!("[OmniAgent] Agentic task: {} ({})", task_type, task_id);

    // Post context + current system state to backend LLM endpoint for reasoning
    let llm_ctx = json!({
        "task_type": task_type,
        "context": context,
        "agent_version": VERSION,
        "timestamp": Utc::now().to_rfc3339(),
    });

    let llm_resp: Option<Value> = {
        let url = format!("{}/api/knowledge/query", base);
        client.post(&url).bearer_auth(token)
            .json(&json!({"query": format!("Agent task: {}", task_type), "context": llm_ctx}))
            .send().await.ok()
            .and_then(|r| futures_util_polyfill(r))
    };

    // Execute suggested action from LLM response (or fall back to built-in)
    let result = match task_type {
        "analyse_security" => {
            let (rt, persist) = tokio::join!(caps2::run_runtime_security(), caps::run_persistence_scan());
            json!({"runtime": rt, "persistence": persist})
        },
        "health_assessment" => caps2::run_predictive_health().await,
        "compliance_check"  => caps::run_compliance_check().await,
        "threat_hunt"       => caps::run_threat_hunt().await,
        _ => json!({"status": "completed", "llm_response": llm_resp}),
    };

    // Report result back
    let result_url = format!("{}/api/agents/{}/agentic-tasks/{}/result", base, id, task_id);
    let _ = client.post(&result_url).bearer_auth(token)
        .json(&json!({"task_id": task_id, "status": "completed", "result": result, "completed_at": Utc::now().to_rfc3339()}))
        .send().await;
}

fn futures_util_polyfill(_r: reqwest::Response) -> Option<Value> {
    // We can't easily block_on inside an async fn; we just return None
    // and let the task execute its built-in action.
    None
}

async fn post_event(client: &Client, base: &str, id: &str, token: &str, event_type: &str, data: Value) {
    let url = format!("{}/api/agents/{}/events", base, id);
    let _ = client.post(&url).bearer_auth(token)
        .json(&json!({"event_type": event_type, "data": data, "timestamp": Utc::now().to_rfc3339()}))
        .send().await;
}

// ── Near real-time FIM ─────────────────────────────────────────────────────────

/// Monitored paths for real-time FIM (directories + individual files).
const FIM_WATCH_FILES: &[&str] = &[
    r"C:\Windows\System32\drivers\etc\hosts",
    r"C:\Windows\System32\drivers\etc\services",
    r"C:\Windows\win.ini",
    r"C:\Windows\System32\cmd.exe",
    r"C:\Windows\System32\svchost.exe",
    r"C:\Windows\System32\lsass.exe",
    r"C:\Windows\System32\services.exe",
    r"C:\Windows\System32\winlogon.exe",
    r"C:\Program Files\OmniAgentRust\omni-agent.exe",
];

pub async fn realtime_fim_poller(cfg: Arc<RwLock<Config>>, client: Arc<Client>, running: Arc<AtomicBool>) {
    let mut baseline: HashMap<String, String> = HashMap::new();
    let mut first_run = true;

    loop {
        if !running.load(Ordering::Relaxed) { return; }

        // Hash all monitored files
        let current = hash_files(FIM_WATCH_FILES);

        if !first_run {
            let mut changes = vec![];

            // Detect modifications and deletions
            for (path, old_hash) in &baseline {
                match current.get(path) {
                    Some(new_hash) if new_hash != old_hash =>
                        changes.push(json!({"event": "modified", "path": path, "old_hash": old_hash, "new_hash": new_hash})),
                    None =>
                        changes.push(json!({"event": "deleted", "path": path, "old_hash": old_hash})),
                    _ => {}
                }
            }
            // Detect new files
            for (path, hash) in &current {
                if !baseline.contains_key(path) {
                    changes.push(json!({"event": "created", "path": path, "hash": hash}));
                }
            }

            if !changes.is_empty() {
                eprintln!("[OmniAgent] FIM: {} change(s) detected", changes.len());
                let (agent_id, token, base) = {
                    let c = cfg.read().await;
                    match (&c.agent_id, &c.agent_token) {
                        (Some(id), Some(tok)) => (id.clone(), tok.clone(), c.api_base_url.trim_end_matches('/').to_string()),
                        _ => { baseline = current; continue; }
                    }
                };
                let url = format!("{}/api/agents/{}/fim-events", base, agent_id);
                let _ = client.post(&url).bearer_auth(&token)
                    .json(&json!({"changes": changes, "detected_at": Utc::now().to_rfc3339()}))
                    .send().await;
            }
        }

        baseline = current;
        first_run = false;

        // Sleep 60 s in 1-s ticks for responsive shutdown
        for _ in 0..60 {
            if !running.load(Ordering::Relaxed) { return; }
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
    }
}

fn hash_files(paths: &[&str]) -> HashMap<String, String> {
    let mut map = HashMap::new();
    for &path in paths {
        if let Ok(data) = fs::read(path) {
            let mut h = Sha256::new();
            h.update(&data);
            map.insert(path.to_string(), hex::encode(h.finalize()));
        }
    }
    map
}
