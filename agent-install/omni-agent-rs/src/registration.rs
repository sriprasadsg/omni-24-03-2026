use crate::{capabilities::CapabilityManager, config, heartbeat::hostname_str};
use serde_json::json;

pub async fn ensure_registered(
    cfg: &mut config::Config,
    client: &reqwest::Client,
    cap_mgr: &CapabilityManager,
) -> bool {
    if !cfg.agent_token.is_empty() {
        return true;
    }
    if cfg.registration_key.is_empty() {
        log::warn!("No agent_token and no registration_key in config.yaml — cannot register");
        return false;
    }

    log::info!("Auto-registering agent with registration_key...");
    let url = format!("{}/api/agents/register", cfg.api_base_url.trim_end_matches('/'));
    let hostname = hostname_str();
    let capabilities: Vec<&'static str> = cap_mgr.ids();

    let payload = json!({
        "registrationKey": cfg.registration_key,
        "hostname": hostname,
        "platform": if cfg!(windows) { "Windows" } else { "Linux" },
        "version": "2.0.0",
        "ipAddress": crate::heartbeat::best_ip(),
        "meta": {
            "agent_type": "rust",
            "availableCapabilities": capabilities,
        },
    });

    match client.post(&url).json(&payload).send().await {
        Ok(resp) if resp.status().is_success() => {
            match resp.json::<serde_json::Value>().await {
                Ok(body) => {
                    let agent_id = body.get("agentId")
                        .and_then(|v| v.as_str())
                        .unwrap_or_default()
                        .to_string();
                    let token = body.get("token")
                        .and_then(|v| v.as_str())
                        .unwrap_or_default()
                        .to_string();

                    if token.is_empty() {
                        log::error!("Registration succeeded but returned empty token");
                        return false;
                    }

                    cfg.agent_id = agent_id.clone();
                    cfg.agent_token = token;
                    // tenant_id is embedded in the JWT; persist the agentId for reference
                    if let Err(e) = config::save(cfg) {
                        log::warn!("Could not persist registration to config.yaml: {e}");
                    } else {
                        log::info!("Registered as {agent_id}, token saved to config.yaml");
                    }
                    true
                }
                Err(e) => {
                    log::error!("Registration response parse error: {e}");
                    false
                }
            }
        }
        Ok(resp) => {
            log::error!("Registration rejected: {}", resp.status());
            false
        }
        Err(e) => {
            log::error!("Registration request failed: {e}");
            false
        }
    }
}
