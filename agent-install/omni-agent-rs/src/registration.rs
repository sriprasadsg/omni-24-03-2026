use crate::{capabilities::CapabilityManager, config, heartbeat::hostname_str};
use serde_json::{json, Value};
use std::sync::Mutex;
use std::time::Duration;

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

/// Whether the platform has admitted this agent (spec C3). An enrollment past
/// the tenant's license is held Pending until a platform administrator
/// approves or rejects it; meanwhile the agent only checks back now and then
/// and collects nothing.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Admission {
    Admitted,
    Pending,
    Rejected,
}

static ADMISSION: Mutex<Admission> = Mutex::new(Admission::Admitted);

/// How often a Pending agent checks back (the platform's retryAfterSeconds).
pub const PENDING_RETRY: Duration = Duration::from_secs(300);
/// A rejection can be lifted by approving the agent later, so look once an hour.
pub const REJECTED_RETRY: Duration = Duration::from_secs(3600);

pub fn admission() -> Admission {
    ADMISSION.lock().map(|a| *a).unwrap_or(Admission::Admitted)
}

fn set_admission(state: Admission) {
    if let Ok(mut a) = ADMISSION.lock() {
        *a = state;
    }
}

/// How long to wait before the next enrollment attempt or Pending check-in.
pub fn retry_interval(admitted_default: Duration) -> Duration {
    match admission() {
        Admission::Admitted => admitted_default,
        Admission::Pending => PENDING_RETRY,
        Admission::Rejected => REJECTED_RETRY,
    }
}

fn pending_text(reason: &str) -> String {
    match reason {
        "seat_limit" => "Waiting for approval (license limit). Your provider has been notified; \
                         the agent connects by itself once approved."
            .to_string(),
        "duplicate_hardware_id" => "Waiting for approval: this computer is already enrolled under \
                                    another name. Your provider has been notified."
            .to_string(),
        other => format!("Waiting for approval by your provider ({other})."),
    }
}

const REJECTED_TEXT: &str = "This computer was rejected by your provider. Contact IT if this is a mistake.";

pub fn note_pending(reason: &str) {
    if admission() != Admission::Pending {
        log::warn!("The platform is holding this agent for approval ({reason})");
    }
    set_admission(Admission::Pending);
    set_problem(Some(pending_text(reason)));
}

pub fn note_rejected() {
    if admission() != Admission::Rejected {
        log::error!("The platform rejected this agent");
    }
    set_admission(Admission::Rejected);
    set_problem(Some(REJECTED_TEXT.to_string()));
}

/// A 200 from the platform: admitted (again). Clears a Pending/Rejected notice.
pub fn note_admitted() {
    if admission() != Admission::Admitted {
        log::info!("The platform admitted this agent");
        set_admission(Admission::Admitted);
        set_problem(None);
    }
}

/// The refusal text of a platform error body. The platform's envelope is
/// `{"error": ...}`; `detail` is FastAPI's default shape, kept for older servers.
pub fn refusal_detail(body: &Value) -> String {
    body.get("error")
        .or_else(|| body.get("detail"))
        .and_then(|d| d.as_str())
        .unwrap_or_default()
        .to_string()
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
        // Seat licensing: the machine's identity, and that a 202 "pending"
        // answer is understood (spec C2/C3).
        "hardware": crate::identity::hardware_block(),
        "supportsPending": true,
    });

    if !cfg.agent_secret.is_empty() {
        payload["agentSecret"] = json!(cfg.agent_secret);
    }
    if let Some(token) = previous_token {
        payload["previousToken"] = json!(token);
    }

    match client.post(&url).json(&payload).send().await {
        Ok(resp) if resp.status().as_u16() == 202 => {
            // Held for approval: keep the id and secret (the secret proves this
            // agent when it checks back), but there is no token yet.
            let body = resp.json::<Value>().await.unwrap_or(Value::Null);
            if let Some(agent_id) = body.get("agentId").and_then(|v| v.as_str()) {
                cfg.agent_id = agent_id.to_string();
            }
            if let Some(secret) = body.get("agentSecret").and_then(|v| v.as_str()) {
                cfg.agent_secret = secret.to_string();
            }
            if let Err(e) = config::save(cfg) {
                log::warn!("Could not persist the pending enrollment to config.yaml: {e}");
            }
            note_pending(body.get("pendingReason").and_then(|v| v.as_str()).unwrap_or("seat_limit"));
            false
        }
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
                    set_admission(Admission::Admitted);
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
                .json::<Value>()
                .await
                .map(|b| refusal_detail(&b))
                .unwrap_or_default();
            log::error!("Registration rejected: {status} {detail}");
            if status == 403 && detail.starts_with("agent_rejected") {
                note_rejected();
            } else {
                set_problem(Some(rejection_text(status, &detail)));
            }
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
    use super::*;

    #[test]
    fn refusal_detail_reads_the_platform_envelope() {
        assert_eq!(refusal_detail(&json!({"error": "agent_rejected: no"})), "agent_rejected: no");
        assert_eq!(refusal_detail(&json!({"detail": "This hostname is already enrolled."})),
                   "This hostname is already enrolled.");
        assert_eq!(refusal_detail(&json!({"status_code": 500})), "");
        // The envelope's "error" is what reaches rejection_text, so the
        // already-enrolled advice now actually shows.
        let detail = refusal_detail(&json!({"error": "This hostname is already enrolled. Re-enrollment requires..."}));
        assert!(rejection_text(409, &detail).contains("delete it"));
    }

    #[test]
    fn admission_states_set_the_tray_notice_and_retry_pace() {
        let default = Duration::from_secs(120);
        note_pending("seat_limit");
        assert_eq!(admission(), Admission::Pending);
        assert_eq!(retry_interval(default), PENDING_RETRY);
        assert!(last_problem().unwrap().starts_with("Waiting for approval (license limit)"));
        note_pending("duplicate_hardware_id");
        assert!(last_problem().unwrap().contains("already enrolled under another name"));
        note_rejected();
        assert_eq!(retry_interval(default), REJECTED_RETRY);
        assert!(last_problem().unwrap().contains("rejected by your provider"));
        note_admitted();
        assert_eq!(admission(), Admission::Admitted);
        assert_eq!(retry_interval(default), default);
        assert!(last_problem().is_none());
    }

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
