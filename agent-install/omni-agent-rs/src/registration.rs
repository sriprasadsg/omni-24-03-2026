use crate::{capabilities::CapabilityManager, config, heartbeat::hostname_str};
use serde_json::json;
use std::sync::Mutex;

/// Why the last enrollment attempt failed, in words the endpoint user can pass
/// on to IT. Published to the tray (tray-config.json), which otherwise could
/// only say "check connection" when it has no token to send.
static LAST_PROBLEM: Mutex<Option<String>> = Mutex::new(None);

pub fn last_problem() -> Option<String> {
    LAST_PROBLEM.lock().ok().and_then(|p| p.clone())
}

fn set_problem(problem: Option<String>) {
    if let Ok(mut p) = LAST_PROBLEM.lock() {
        *p = problem;
    }
}

/// Explain a rejected registration. 409 is the expected answer when this host
/// was enrolled before and its per-agent secret is gone (a reinstall over a
/// config.yaml without it): only an administrator can release the hostname.
fn rejection_text(status: u16, detail: &str) -> String {
    match status {
        409 if detail.contains("already enrolled") => "This computer is already enrolled from an earlier install. Ask IT to delete it \
                under Agents so it can enroll again (it reconnects by itself within a few minutes)."
            .to_string(),
        404 => "The installer's registration key is not valid. Reinstall the agent with an \
                installer downloaded from the platform."
            .to_string(),
        _ if detail.is_empty() => format!("The platform refused enrollment (HTTP {status})."),
        _ => format!("The platform refused enrollment (HTTP {status}): {detail}"),
    }
}

pub async fn ensure_registered(
    cfg: &mut config::Config,
    client: &reqwest::Client,
    cap_mgr: &CapabilityManager,
) -> bool {
    if !cfg.agent_token.is_empty() {
        if cfg.agent_secret.is_empty() && !cfg.registration_key.is_empty() {
            // One-time upgrade for agents enrolled before per-agent secrets:
            // prove identity with the current token to receive a secret.
            let previous = cfg.agent_token.clone();
            if !enroll(cfg, client, cap_mgr, Some(&previous)).await {
                log::warn!("Could not obtain an agent secret; will retry on next start");
            }
        }
        return true;
    }
    if cfg.registration_key.is_empty() {
        log::warn!("No agent_token and no registration_key in config.yaml — cannot register");
        set_problem(Some("The agent has no registration key. Reinstall it from the platform.".to_string()));
        return false;
    }
    enroll(cfg, client, cap_mgr, None).await
}

async fn enroll(
    cfg: &mut config::Config,
    client: &reqwest::Client,
    cap_mgr: &CapabilityManager,
    previous_token: Option<&str>,
) -> bool {
    log::info!("Registering agent with registration_key...");
    let url = format!("{}/api/agents/register", cfg.api_base_url.trim_end_matches('/'));
    let hostname = hostname_str();
    let capabilities: Vec<&'static str> = cap_mgr.ids();

    let mut payload = json!({
        "registrationKey": cfg.registration_key,
        "hostname": hostname,
        "platform": if cfg!(windows) { "Windows" } else { "Linux" },
        "version": env!("CARGO_PKG_VERSION"),
        "ipAddress": crate::heartbeat::best_ip(),
        "publicIp": crate::heartbeat::cached_public_ip(),
        "meta": {
            "agent_type": "rust",
            "availableCapabilities": capabilities,
        },
    });

    if !cfg.agent_secret.is_empty() {
        payload["agentSecret"] = json!(cfg.agent_secret);
    }
    if let Some(token) = previous_token {
        payload["previousToken"] = json!(token);
    }

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
                        set_problem(Some("The platform accepted enrollment but sent no token.".to_string()));
                        return false;
                    }

                    cfg.agent_id = agent_id.clone();
                    cfg.agent_token = token;
                    if let Some(secret) = body.get("agentSecret").and_then(|v| v.as_str()) {
                        cfg.agent_secret = secret.to_string();
                    }
                    // tenant_id is embedded in the JWT; persist the agentId for reference
                    if let Err(e) = config::save(cfg) {
                        log::warn!("Could not persist registration to config.yaml: {e}");
                    } else {
                        log::info!("Registered as {agent_id}, token saved to config.yaml");
                    }
                    set_problem(None);
                    true
                }
                Err(e) => {
                    log::error!("Registration response parse error: {e}");
                    set_problem(Some(format!("The platform's enrollment reply was unreadable: {e}")));
                    false
                }
            }
        }
        Ok(resp) => {
            let status = resp.status().as_u16();
            let detail = resp
                .json::<serde_json::Value>()
                .await
                .ok()
                .and_then(|b| b.get("detail").and_then(|d| d.as_str()).map(str::to_string))
                .unwrap_or_default();
            log::error!("Registration rejected: {status} {detail}");
            set_problem(Some(rejection_text(status, &detail)));
            false
        }
        Err(e) => {
            log::error!("Registration request failed: {e}");
            set_problem(Some(format!("Could not reach the platform at {}: {e}", cfg.api_base_url)));
            false
        }
    }
}

#[cfg(test)]
mod tests {
    use super::rejection_text;

    #[test]
    fn rejection_text_tells_the_user_what_it_takes() {
        assert!(rejection_text(409, "This hostname is already enrolled.").contains("delete it"));
        assert!(rejection_text(409, "Concurrent enrollment for this hostname; retry").contains("retry"));
        assert!(rejection_text(404, "Invalid registration key").contains("registration key"));
        assert_eq!(
            rejection_text(403, "Agent limit reached (5)."),
            "The platform refused enrollment (HTTP 403): Agent limit reached (5)."
        );
        assert_eq!(rejection_text(500, ""), "The platform refused enrollment (HTTP 500).");
    }
}
