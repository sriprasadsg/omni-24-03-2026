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
                        .or_else(|| item.get("type"))
                        .and_then(|v| v.as_str())
                        .unwrap_or_default();
                    let action = raw_action.to_lowercase();
                    let task_id = item
                        .get("task_id")
                        .and_then(|v| v.as_str())
                        .unwrap_or_default();
                    log::info!("Instruction received: {action}");
                    execute_instruction(&action, raw_action, task_id, &item, cfg, client).await;
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
    task_id: &str,
    item: &Value,
    cfg: &Config,
    client: &reqwest::Client,
) {
    let result: Value = match compute_instruction_result(action, raw_action, item, cfg, client).await {
        Some(v) => v,
        // Preserves the pre-refactor early-exit behavior for malformed
        // "start remote session" strings: no result to report, skip the
        // POST entirely rather than reporting a synthetic status.
        None => return,
    };

    let report_url = format!(
        "{}/api/agents/{}/instructions/result",
        cfg.api_base_url.trim_end_matches('/'),
        hostname_str()
    );
    // Backend (agent_tasks_endpoints.report_instruction_result) keys the
    // instruction-status update on task_id and reads status at the top level.
    let status = result
        .get("status")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown")
        .to_string();
    let _ = client
        .post(&report_url)
        .bearer_auth(&cfg.agent_token)
        .json(&serde_json::json!({
            "task_id": task_id,
            "action": action,
            "type": action,
            "status": status,
            "result": result,
            "timestamp": chrono::Utc::now().to_rfc3339(),
        }))
        .send()
        .await;
}

/// Pure dispatch: matches `action` against every supported instruction and
/// returns the resulting status JSON, with no network side effect of its
/// own beyond what a given arm needs (e.g. `network_scan` posting discovery
/// results). Split out from `execute_instruction` so the dispatch arms
/// themselves — not just their underlying capability functions — are
/// directly testable without a live instructions-result endpoint. Returns
/// `None` only for the legacy malformed "start remote session" string case,
/// preserving that arm's pre-refactor silent-skip behavior.
pub async fn compute_instruction_result(
    action: &str,
    raw_action: &str,
    item: &Value,
    cfg: &Config,
    client: &reqwest::Client,
) -> Option<Value> {
    Some(match action {
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
        "scan_file" | "scan_url" | "scan_hash" | "scan_ip" => {
            let kind = &action[5..]; // file|url|hash|ip
            let param_key = if kind == "file" { "path" } else { "target" };
            let target = item
                .get("parameters")
                .and_then(|p| p.get(param_key))
                .and_then(|v| v.as_str())
                .unwrap_or_default()
                .to_string();
            if target.is_empty() {
                serde_json::json!({"status": "error", "error": format!("missing {param_key}")})
            } else {
                // Refresh the verified feed + run the (blocking) scan off the async runtime.
                let api = cfg.api_base_url.clone();
                let tok = cfg.agent_token.clone();
                let kind_owned = kind.to_string();
                let target_scan = target.clone();
                let verdict = tokio::task::spawn_blocking(move || {
                    let _ = crate::capabilities::feed_bundle::update(&api, &tok); // best-effort
                    match kind_owned.as_str() {
                        "file" => crate::capabilities::security_scan::scan_file(&target_scan),
                        "url" => crate::capabilities::security_scan::scan_url(&target_scan),
                        "hash" => crate::capabilities::security_scan::scan_hash(&target_scan),
                        _ => crate::capabilities::security_scan::scan_ip(&target_scan),
                    }
                })
                .await
                .unwrap_or_else(|e| serde_json::json!({"verdict": "error", "error": format!("scan task: {e}")}));

                // POST the verdict (enriched with type + target) to the ingestion endpoint.
                let mut body = verdict.clone();
                if let Some(obj) = body.as_object_mut() {
                    obj.insert("type".to_string(), serde_json::json!(kind));
                    obj.insert("target".to_string(), serde_json::json!(target));
                }
                let url = format!(
                    "{}/api/agents/{}/security/scan-result",
                    cfg.api_base_url.trim_end_matches('/'),
                    hostname_str()
                );
                let _ = client.post(&url).bearer_auth(&cfg.agent_token).json(&body).send().await;
                verdict
            }
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
        // Download and self-replace the binary. Accept every name the backend
        // dispatches: the UI "Update Agent" button queues `check_agent_update`
        // (agent_tasks_endpoints), the heartbeat auto-push queues `agent_update`
        // when an endpoint is behind, and older callers use `apply_agent_update`.
        "apply_agent_update" | "check_agent_update" | "agent_update" | "update_agent" => {
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
                match install_custom_software(&dl_url, &filename, None, client, &cfg.agent_token).await {
                    Ok(msg) => serde_json::json!({"status": "success", "message": msg}),
                    Err(e) => serde_json::json!({"status": "error", "error": e}),
                }
            }
        }

        // Software deployment from the dashboard: instruction is "install_software: <file>"
        // (or "upgrade_software: <file>") and payload carries {download_url, package,
        // install_args}. download_url may be an external vendor URL (python.org, vscode…)
        // or a platform-relative "/api/software/download/…" path. Prefix-matched because
        // the filename is appended to the instruction string.
        a if a.starts_with("install_software:") || a.starts_with("upgrade_software:") => {
            let payload = item.get("payload").cloned().unwrap_or(Value::Null);
            let dl_url = payload.get("download_url").and_then(|v| v.as_str()).unwrap_or("");
            let install_args = payload.get("install_args").and_then(|v| v.as_str());
            let filename = payload
                .get("package")
                .and_then(|v| v.as_str())
                .filter(|s| !s.is_empty())
                .map(|s| s.to_string())
                .unwrap_or_else(|| raw_action.splitn(2, ':').nth(1).map(|s| s.trim()).unwrap_or("installer").to_string());

            if !dl_url.is_empty() {
                let full_url = if dl_url.starts_with("http://") || dl_url.starts_with("https://") {
                    dl_url.to_string()
                } else {
                    format!("{}{}", cfg.api_base_url.trim_end_matches('/'), dl_url)
                };
                match install_custom_software(&full_url, &filename, install_args, client, &cfg.agent_token).await {
                    Ok(msg) => serde_json::json!({"status": "success", "message": msg}),
                    Err(e) => serde_json::json!({"status": "error", "error": e}),
                }
            } else {
                // No download URL — treat the trailing token as a winget package id.
                match crate::capabilities::software_management::install_package(&filename, a.starts_with("upgrade")) {
                    Ok(out) => serde_json::json!({"status": "success", "output": out}),
                    Err(e) => serde_json::json!({"status": "error", "error": e}),
                }
            }
        }

        // "Start Remote Session <session_id> <ws_url>" OR instruction="start_remote_session" + payload
        a if a.contains("start remote session") || a == "start_remote_session" => {
            let payload = item.get("payload").unwrap_or(&Value::Null);
            let sid_from_payload = payload.get("session_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let url_from_payload = payload.get("url").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let (session_id, url) = if !sid_from_payload.is_empty() && !url_from_payload.is_empty() {
                (sid_from_payload, url_from_payload)
            } else {
                // Legacy: parse "Start Remote Session <session_id> <ws_url>" from instruction string
                let words: Vec<&str> = raw_action.split_whitespace().collect();
                if words.len() >= 5 {
                    (words[words.len() - 2].to_string(), words[words.len() - 1].to_string())
                } else {
                    return None;
                }
            };
            // A "start_remote_session" instruction carries the session kind in
            // payload.type: the dashboard's Live Desktop requests "desktop"/"vnc",
            // the remote terminal requests "shell" (default). Both use the same
            // tunnel URL — the agent just streams JPEG frames instead of shell I/O.
            let session_kind = payload
                .get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("shell")
                .to_lowercase();
            if session_kind == "desktop" || session_kind == "vnc" {
                crate::capabilities::remote_access::start_desktop_stream(session_id, url);
                serde_json::json!({"status": "success", "message": "Desktop stream started"})
            } else {
                crate::capabilities::remote_access::start_reverse_shell(session_id, url);
                serde_json::json!({"status": "success", "message": "Reverse shell session started"})
            }
        }
        // "Start Desktop Stream <session_id> <ws_url>" OR instruction="start_desktop_stream" + payload
        a if a.contains("start desktop stream") || a == "start_desktop_stream" => {
            let payload = item.get("payload").unwrap_or(&Value::Null);
            let sid_from_payload = payload.get("session_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let url_from_payload = payload.get("url").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let (session_id, url) = if !sid_from_payload.is_empty() && !url_from_payload.is_empty() {
                (sid_from_payload, url_from_payload)
            } else {
                // Legacy: parse "Start Desktop Stream <session_id> <ws_url>" from instruction string
                let words: Vec<&str> = raw_action.split_whitespace().collect();
                if words.len() >= 5 {
                    (words[words.len() - 2].to_string(), words[words.len() - 1].to_string())
                } else {
                    return None;
                }
            };
            crate::capabilities::remote_access::start_desktop_stream(session_id, url);
            serde_json::json!({"status": "success", "message": "Desktop stream started"})
        }
        // ── Ticketing (ticket_reporter) ──────────────────────────────────────
        // Agent raises a ticket via the agent-key-authenticated endpoint.
        "create_ticket" | "report_ticket" => {
            let params = item
                .get("payload")
                .or_else(|| item.get("parameters"))
                .cloned()
                .unwrap_or_else(|| serde_json::json!({}));
            let title = params.get("title").and_then(|v| v.as_str()).unwrap_or("Agent-generated ticket");
            let desc = params.get("description").and_then(|v| v.as_str()).unwrap_or("");
            let sev = params.get("severity").and_then(|v| v.as_str()).unwrap_or("medium");
            let url = format!(
                "{}/api/agents/{}/ticket",
                cfg.api_base_url.trim_end_matches('/'),
                cfg.agent_id
            );
            match client
                .post(&url)
                .bearer_auth(&cfg.agent_token)
                .json(&serde_json::json!({
                    "title": title,
                    "description": desc,
                    "priority": sev,
                    "tags": ["agent-raised", "omni-agent-rust"],
                }))
                .send()
                .await
            {
                Ok(r) => serde_json::json!({"status": "success", "ticket_created": true, "http_status": r.status().as_u16()}),
                Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
            }
        }

        // ── Chat (chat_window) ───────────────────────────────────────────────
        // Admin-to-endpoint messaging. The agent runs as a session-0 service, so
        // it shows admin messages on the active desktop via msg.exe rather than
        // drawing its own window, then acks back to the admin so the round-trip
        // is visible on both ends. Endpoint-user free-text reply requires the
        // GUI helper / Python agent; msg.exe display is one-way.
        "start_agent_chat" => {
            let payload = item.get("payload").cloned().unwrap_or_else(|| serde_json::json!({}));
            let session_id = payload.get("session_id").and_then(|v| v.as_str()).unwrap_or("");
            let sender = payload.get("sender").and_then(|v| v.as_str()).unwrap_or("Administrator");
            let subject = payload.get("subject").and_then(|v| v.as_str()).unwrap_or("Chat Session");
            let initial = payload.get("initial_message").and_then(|v| v.as_str()).unwrap_or("");
            let backend_url = payload
                .get("backend_url")
                .and_then(|v| v.as_str())
                .filter(|s| !s.is_empty())
                .unwrap_or(&cfg.api_base_url);
            log::info!("Chat session {session_id} started by {sender}: {subject}");

            // Prefer a real two-way window in the active user session; fall back
            // to a one-way msg.exe notice when no interactive session exists.
            let outcome = crate::chat_ui::launch_interactive(
                session_id, subject, initial, sender, backend_url, &cfg.agent_token,
            );

            let reply = match outcome {
                Ok(()) => {
                    log::info!("Interactive chat window launched for {session_id}");
                    "Interactive chat window opened on the endpoint. \
                     The user can now reply here.".to_string()
                }
                Err(e) => {
                    log::warn!("Interactive chat launch failed ({e}); using one-way display");
                    let screen_body = if initial.is_empty() { subject } else { initial };
                    match crate::chat_display::show_message(sender, screen_body) {
                        Ok(()) => "Message shown on the endpoint screen (one-way notice — \
                                   no interactive session to open a reply window).".to_string(),
                        Err(de) => format!(
                            "Endpoint reachable, but no on-screen delivery was possible \
                             (interactive: {e}; notice: {de})."
                        ),
                    }
                }
            };

            if !session_id.is_empty() {
                let url = format!(
                    "{}/api/agent-chat/sessions/{}/user-message",
                    cfg.api_base_url.trim_end_matches('/'),
                    session_id
                );
                let _ = client
                    .post(&url)
                    .bearer_auth(&cfg.agent_token)
                    .json(&serde_json::json!({"content": reply}))
                    .send()
                    .await;
            }
            serde_json::json!({"status": "success", "session_id": session_id})
        }
        "agent_chat_message" => {
            let payload = item.get("payload").cloned().unwrap_or_else(|| serde_json::json!({}));
            let session_id = payload.get("session_id").and_then(|v| v.as_str()).unwrap_or("");
            let content = payload.get("content").and_then(|v| v.as_str()).unwrap_or("");
            let sender = payload.get("sender").and_then(|v| v.as_str()).unwrap_or("Administrator");
            let preview: String = content.chars().take(120).collect();
            log::info!("Chat [{session_id}] from {sender}: {preview}");

            // If the interactive window is already open it polls new admin messages
            // on its own. Otherwise open a real two-way chat window with this message
            // as the opener, so admin↔endpoint is a genuine interactive session — not
            // a one-way msg.exe popup. Fall back to the one-way notice only when no
            // interactive session can be opened (no logged-on user / non-Windows).
            if crate::chat_ui::is_active(session_id) {
                log::debug!("Interactive window active for {session_id}; UI will poll this message");
            } else if let Err(e) = crate::chat_ui::launch_interactive(
                session_id,
                "Support Chat",
                content,
                sender,
                cfg.api_base_url.trim_end_matches('/'),
                &cfg.agent_token,
            ) {
                log::warn!("Interactive chat launch failed ({e}); using one-way display");
                if let Err(de) = crate::chat_display::show_message(sender, content) {
                    log::warn!("Chat on-screen display failed: {de}");
                    if !session_id.is_empty() {
                        let url = format!(
                            "{}/api/agent-chat/sessions/{}/user-message",
                            cfg.api_base_url.trim_end_matches('/'),
                            session_id
                        );
                        let _ = client
                            .post(&url)
                            .bearer_auth(&cfg.agent_token)
                            .json(&serde_json::json!({"content": format!("⚠ Could not display on endpoint: {de}")}))
                            .send()
                            .await;
                    }
                }
            }
            serde_json::json!({"status": "success", "received": true})
        }

        "close_agent_chat" => {
            let payload = item.get("payload").cloned().unwrap_or_else(|| serde_json::json!({}));
            let session_id = payload.get("session_id").and_then(|v| v.as_str()).unwrap_or("");
            log::info!("Chat session {session_id} closed by admin");
            match crate::chat_ui::signal_close(session_id) {
                Ok(()) => serde_json::json!({"status": "success", "closed": true}),
                Err(e) => serde_json::json!({"status": "error", "error": e}),
            }
        }
        "kill_process" => {
            let target = item.get("parameters").and_then(|p| p.get("target")).and_then(|v| v.as_str()).unwrap_or("");
            match crate::capabilities::remediation_actions::kill_process(target).await {
                Ok(()) => serde_json::json!({"status": "success", "message": "Process kill initiated"}),
                Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
            }
        }
        "restore_file" => {
            let path = item.get("parameters").and_then(|p| p.get("path")).and_then(|v| v.as_str()).unwrap_or("");
            let backup = item.get("parameters").and_then(|p| p.get("backup_path")).and_then(|v| v.as_str());
            match crate::capabilities::remediation_actions::restore_file(path, backup).await {
                Ok(()) => serde_json::json!({"status": "success", "message": "File restore initiated"}),
                Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
            }
        }
        "block_ip" => {
            let ip = item.get("parameters").and_then(|p| p.get("ip_address")).and_then(|v| v.as_str()).unwrap_or("");
            match crate::capabilities::remediation_actions::block_ip(ip).await {
                Ok(()) => serde_json::json!({"status": "success", "message": "IP block initiated"}),
                Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
            }
        }
        "unblock_ip" => {
            let ip = item.get("parameters").and_then(|p| p.get("ip_address")).and_then(|v| v.as_str()).unwrap_or("");
            match crate::capabilities::remediation_actions::unblock_ip(ip).await {
                Ok(()) => serde_json::json!({"status": "success", "message": "IP unblock initiated"}),
                Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
            }
        }
        "disable_service" => {
            let service = item.get("parameters").and_then(|p| p.get("service_name")).and_then(|v| v.as_str()).unwrap_or("");
            match crate::capabilities::remediation_actions::disable_service(service).await {
                Ok(()) => serde_json::json!({"status": "success", "message": "Service disable initiated"}),
                Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
            }
        }
        "enable_service" => {
            let service = item.get("parameters").and_then(|p| p.get("service_name")).and_then(|v| v.as_str()).unwrap_or("");
            match crate::capabilities::remediation_actions::enable_service(service).await {
                Ok(()) => serde_json::json!({"status": "success", "message": "Service enable initiated"}),
                Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
            }
        }
        "rotate_key" => {
            let fingerprint = item.get("parameters").and_then(|p| p.get("fingerprint")).and_then(|v| v.as_str()).unwrap_or("");
            let authorized_keys_path = item.get("parameters").and_then(|p| p.get("authorized_keys_path")).and_then(|v| v.as_str()).unwrap_or("");
            match crate::capabilities::remediation_actions::rotate_key(authorized_keys_path, fingerprint).await {
                Ok(outcome) => serde_json::json!({"status": "success", "new_fingerprint": outcome.new_fingerprint, "new_comment": outcome.new_comment}),
                Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
            }
        }
        "rotate_key_rollback" => {
            let authorized_keys_path = item.get("parameters").and_then(|p| p.get("authorized_keys_path")).and_then(|v| v.as_str()).unwrap_or("");
            match crate::capabilities::remediation_actions::rotate_key_rollback(authorized_keys_path).await {
                Ok(()) => serde_json::json!({"status": "success", "message": "Key rotation rollback complete"}),
                Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
            }
        }
        _ => {
            // Report instead of silently returning: an unhandled instruction must
            // surface as an error in the dashboard, not sit "sent" forever looking
            // like the agent hung.
            log::warn!("Unknown instruction action: {action}");
            serde_json::json!({
                "status": "error",
                "error": format!("Agent does not support instruction '{}'", raw_action)
            })
        }
    })
}

/// Download a file from `url` and run it as a silent installer.
/// Supports .exe (silent flags /S /quiet) and .msi (msiexec /quiet).
async fn install_custom_software(
    url: &str,
    filename: &str,
    install_args: Option<&str>,
    client: &reqwest::Client,
    token: &str,
) -> Result<String, String> {
    // Bearer auth is only meaningful for the platform's own repo; sending it to an
    // arbitrary external vendor URL (python.org, microsoft.com) is harmless (ignored)
    // but we only attach it for same-origin api_base_url downloads is overkill — the
    // header is ignored by third parties, so keep one code path.
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

    // Split caller-supplied silent-install args on whitespace; fall back to sane
    // per-type defaults when the deployment didn't specify any.
    let custom_args: Option<Vec<String>> = install_args
        .map(|s| s.split_whitespace().map(|w| w.to_string()).collect::<Vec<_>>())
        .filter(|v| !v.is_empty());

    let status = match ext.as_str() {
        "exe" => {
            let mut cmd = tokio::process::Command::new(&temp_path);
            match &custom_args {
                Some(a) => { cmd.args(a); }
                None => { cmd.args(["/S", "/quiet", "/norestart"]); }
            }
            cmd.status().await.map_err(|e| e.to_string())
        }
        "msi" => {
            let mut cmd = tokio::process::Command::new("msiexec");
            cmd.args(["/i", temp_path.to_str().unwrap_or("")]);
            match &custom_args {
                Some(a) => { cmd.args(a); }
                None => { cmd.args(["/quiet", "/norestart"]); }
            }
            cmd.status().await.map_err(|e| e.to_string())
        }
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
