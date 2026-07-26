/*!
 * Remote command execution via HTTP polling.
 * Polls GET /api/agents/{id}/remote-commands every 2 s, executes each command,
 * POSTs results back to /api/agents/{id}/remote-commands/{cmd_id}/result.
 *
 * All commands are authenticated by the agent's bearer token; the backend
 * must enforce RBAC before enqueuing commands.
 */
use std::{sync::{Arc, atomic::{AtomicBool, Ordering}}, time::Duration};
use reqwest::Client;
use serde_json::{json, Value};
use tokio::sync::RwLock;

use crate::config::Config;

pub async fn shell_poller(cfg: Arc<RwLock<Config>>, client: Arc<Client>, running: Arc<AtomicBool>) {
    loop {
        if !running.load(Ordering::Relaxed) { return; }
        tokio::time::sleep(Duration::from_secs(10)).await;
        if !running.load(Ordering::Relaxed) { return; }

        let (agent_id, token, base) = {
            let c = cfg.read().await;
            match (&c.agent_id, &c.agent_token) {
                (Some(id), Some(tok)) => (id.clone(), tok.clone(), c.api_base_url.trim_end_matches('/').to_string()),
                _ => continue,
            }
        };

        let url = format!("{}/api/agents/{}/remote-commands", base, agent_id);
        let commands: Value = match client.get(&url).bearer_auth(&token).send().await {
            Ok(r) if r.status().is_success() => r.json().await.unwrap_or(Value::Null),
            _ => continue,
        };
        let cmd_list = match commands.as_array() {
            Some(a) if !a.is_empty() => a.clone(),
            _ => continue,
        };

        for item in cmd_list {
            let cmd_id  = item.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let command = item.get("command").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let shell   = item.get("shell").and_then(|v| v.as_str()).unwrap_or("powershell");

            if command.is_empty() { continue; }
            eprintln!("[OmniAgent] Remote cmd [{}]: {}", shell, &command[..command.len().min(60)]);

            let (output, exit_code) = execute_command(shell, &command).await;

            let result_url = format!("{}/api/agents/{}/remote-commands/{}/result", base, agent_id, cmd_id);
            let _ = client.post(&result_url).bearer_auth(&token)
                .json(&json!({"cmd_id": cmd_id, "output": output, "exit_code": exit_code, "shell": shell}))
                .send().await;
        }
    }
}

async fn execute_command(shell: &str, command: &str) -> (String, i32) {
    let result = match shell {
        "cmd" => {
            tokio::process::Command::new("cmd")
                .args(["/c", command])
                .output().await
        },
        _ => {
            // Use the full executable path so the agent finds PowerShell even in a
            // stripped Windows service PATH, and bypass execution policy for evidence scripts.
            tokio::process::Command::new(crate::http::PS_EXE)
                .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command])
                .output().await
        },
    };

    match result {
        Ok(o) => {
            let stdout = String::from_utf8_lossy(&o.stdout).to_string();
            let stderr = String::from_utf8_lossy(&o.stderr).to_string();
            let combined = if stderr.is_empty() { stdout } else { format!("{}{}", stdout, stderr) };
            let code = o.status.code().unwrap_or(-1);
            (combined.trim().to_string(), code)
        },
        Err(e) => (e.to_string(), -1),
    }
}
