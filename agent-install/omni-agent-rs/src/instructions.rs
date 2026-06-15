use crate::config::Config;
use crate::heartbeat::hostname_str;
use serde_json::Value;

pub async fn poll(cfg: &Config, client: &reqwest::Client) {
    let hostname = hostname_str();
    let url = format!(
        "{}/api/agents/{}/instructions",
        cfg.api_base_url.trim_end_matches('/'),
        hostname
    );

    let resp = client
        .get(&url)
        .bearer_auth(&cfg.agent_token)
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            if let Ok(items) = r.json::<Vec<Value>>().await {
                for item in items {
                    // Keep raw for URL/session_id extraction; lowercase for matching
                    let raw_action = item
                        .get("action")
                        .or_else(|| item.get("instruction"))
                        .and_then(|v| v.as_str())
                        .unwrap_or_default();
                    let action = raw_action.to_lowercase();
                    log::info!("Instruction received: {action}");
                    execute_instruction(&action, raw_action, &item, cfg, client).await;
                }
            }
        }
        Ok(r) => log::debug!("Instructions poll -> {}", r.status()),
        Err(e) => log::debug!("Instructions poll error: {e}"),
    }
}

async fn execute_instruction(
    action: &str,
    raw_action: &str,
    item: &Value,
    cfg: &Config,
    client: &reqwest::Client,
) {
    let result: Value = match action {
        "enable_rdp" => {
            match crate::capabilities::remote_access::set_rdp(true) {
                Ok(()) => serde_json::json!({"status": "success", "message": "RDP enabled"}),
                Err(e) => serde_json::json!({"status": "error", "error": e}),
            }
        }
        "disable_rdp" => {
            match crate::capabilities::remote_access::set_rdp(false) {
                Ok(()) => serde_json::json!({"status": "success", "message": "RDP disabled"}),
                Err(e) => serde_json::json!({"status": "error", "error": e}),
            }
        }
        "network_scan" => {
            let scan = crate::capabilities::network_discovery::scan_now();
            let device_count = scan["device_count"].as_u64().unwrap_or(0);
            log::info!("Network scan: {} devices found", device_count);
            // POST results to the dedicated discovery endpoint (mirrors Python agent behaviour)
            let disc_url = format!(
                "{}/api/agents/{}/discovery/results",
                cfg.api_base_url.trim_end_matches('/'),
                hostname_str()
            );
            let _ = client
                .post(&disc_url)
                .bearer_auth(&cfg.agent_token)
                .json(&scan["devices"])
                .send()
                .await;
            serde_json::json!({"status": "success", "result": scan})
        }
        "install_software" => {
            let pkg = item
                .get("parameters")
                .and_then(|p| p.get("packageId"))
                .and_then(|v| v.as_str())
                .unwrap_or_default();
            if pkg.is_empty() {
                serde_json::json!({"status": "error", "error": "missing packageId"})
            } else {
                match crate::capabilities::software_management::install_package(pkg, false) {
                    Ok(out) => serde_json::json!({"status": "success", "output": out}),
                    Err(e) => serde_json::json!({"status": "error", "error": e}),
                }
            }
        }
        "upgrade_software" => {
            let pkg = item
                .get("parameters")
                .and_then(|p| p.get("packageId"))
                .and_then(|v| v.as_str())
                .unwrap_or_default();
            if pkg.is_empty() {
                serde_json::json!({"status": "error", "error": "missing packageId"})
            } else {
                match crate::capabilities::software_management::install_package(pkg, true) {
                    Ok(out) => serde_json::json!({"status": "success", "output": out}),
                    Err(e) => serde_json::json!({"status": "error", "error": e}),
                }
            }
        }
        // "apply_agent_update" — download and self-replace the binary
        "apply_agent_update" => {
            let cfg_clone = cfg.clone();
            let result = tokio::task::spawn_blocking(move || {
                crate::capabilities::agent_update::apply_update(&cfg_clone)
            })
            .await
            .unwrap_or_else(|e| Err(e.to_string()));
            match result {
                Ok(msg) => serde_json::json!({"status": "success", "message": msg}),
                Err(e) => serde_json::json!({"status": "error", "error": e}),
            }
        }

        // "Download and install custom software '{filename}' from the internal repository"
        a if a.contains("download and install custom software") => {
            let start = raw_action.find('\'').map(|i| i + 1).unwrap_or(0);
            let end = raw_action[start..].find('\'').map(|i| i + start).unwrap_or(raw_action.len());
            let filename = raw_action[start..end].to_string();
            if filename.is_empty() {
                serde_json::json!({"status": "error", "error": "could not parse filename from instruction"})
            } else {
                let dl_url = format!(
                    "{}/api/software/download/{}",
                    cfg.api_base_url.trim_end_matches('/'),
                    filename
                );
                match install_custom_software(&dl_url, &filename, client, &cfg.agent_token).await {
                    Ok(msg) => serde_json::json!({"status": "success", "message": msg}),
                    Err(e) => serde_json::json!({"status": "error", "error": e}),
                }
            }
        }

        // "Start Remote Session <session_id> <ws_url>"
        a if a.contains("start remote session") || a == "start_remote_session" => {
            let words: Vec<&str> = raw_action.split_whitespace().collect();
            if words.len() >= 5 {
                let session_id = words[words.len() - 2].to_string();
                let url = words[words.len() - 1].to_string();
                crate::capabilities::remote_access::start_reverse_shell(session_id, url);
                serde_json::json!({"status": "success", "message": "Reverse shell session started"})
            } else {
                serde_json::json!({"status": "error", "error": "expected: Start Remote Session <session_id> <ws_url>"})
            }
        }
        // "Start Desktop Stream <session_id> <ws_url>"
        a if a.contains("start desktop stream") || a == "start_desktop_stream" => {
            let words: Vec<&str> = raw_action.split_whitespace().collect();
            if words.len() >= 5 {
                let session_id = words[words.len() - 2].to_string();
                let url = words[words.len() - 1].to_string();
                crate::capabilities::remote_access::start_desktop_stream(session_id, url);
                serde_json::json!({"status": "success", "message": "Desktop stream started"})
            } else {
                serde_json::json!({"status": "error", "error": "expected: Start Desktop Stream <session_id> <ws_url>"})
            }
        }
        _ => {
            log::debug!("Unknown instruction action: {action}");
            return;
        }
    };

    let report_url = format!(
        "{}/api/agents/{}/instruction-result",
        cfg.api_base_url.trim_end_matches('/'),
        hostname_str()
    );
    let _ = client
        .post(&report_url)
        .bearer_auth(&cfg.agent_token)
        .json(&serde_json::json!({
            "action": action,
            "result": result,
            "timestamp": chrono::Utc::now().to_rfc3339(),
        }))
        .send()
        .await;
}

/// Download a file from `url` and run it as a silent installer.
/// Supports .exe (silent flags /S /quiet) and .msi (msiexec /quiet).
async fn install_custom_software(
    url: &str,
    filename: &str,
    client: &reqwest::Client,
    token: &str,
) -> Result<String, String> {
    let resp = client
        .get(url)
        .bearer_auth(token)
        .send()
        .await
        .map_err(|e| format!("Download failed: {}", e))?;

    if !resp.status().is_success() {
        return Err(format!("Server returned {}", resp.status()));
    }

    let bytes = resp.bytes().await.map_err(|e| e.to_string())?;
    let temp_path = std::env::temp_dir().join(filename);
    std::fs::write(&temp_path, &bytes).map_err(|e| e.to_string())?;

    let ext = std::path::Path::new(filename)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    let status = match ext.as_str() {
        "exe" => tokio::process::Command::new(&temp_path)
            .args(["/S", "/quiet", "/norestart"])
            .status()
            .await
            .map_err(|e| e.to_string()),
        "msi" => tokio::process::Command::new("msiexec")
            .args(["/i", temp_path.to_str().unwrap_or(""), "/quiet", "/norestart"])
            .status()
            .await
            .map_err(|e| e.to_string()),
        _ => {
            let _ = std::fs::remove_file(&temp_path);
            return Err(format!("Unsupported file extension: {}", ext));
        }
    };

    let _ = std::fs::remove_file(&temp_path);

    status.and_then(|s| {
        if s.success() {
            Ok(format!("Successfully installed {}", filename))
        } else {
            Err(format!("Installer exited with code {:?}", s.code()))
        }
    })
}
