//! The agent side of the Autonomous Ops response commands: `block_ip` with a time limit and
//! `unblock_ip` that removes one claim. The result bodies follow `shared/agent-response-contract.json`,
//! which the backend and the contract test both read.
//!
//! A block runs in this order: validate every parameter, write the claim to `response_state.json`,
//! add the firewall rules, check that they are there, answer. The claim is written first so that a
//! crash after the firewall changed still leaves something that will expire the rule. A rule the
//! check cannot find answers `verify.ok = false` and keeps the claim, so the expiry still removes
//! whatever was added.
//!
//! The parameters come from a backend instruction, so the agent validates all of them itself: a
//! time limit outside 1 hour..7 days is refused (a missing one is 24 hours, so no block is ever
//! open-ended), as is an instruction id that is not 1 to 64 characters of letters, digits or
//! hyphens, and an address or network that must never be blocked (`net_safety::refuse_reason`: not
//! on the public internet, too wide, the platform, the gateway, a DNS server). A network goes in
//! `cidr` and is one rule under the same claim rules; the token `block_ip_range` says so.

use crate::capabilities::firewall::{self, Os, Target};
use crate::capabilities::net_safety;
use crate::capabilities::quarantine;
use crate::capabilities::remediation_actions::RemediationError;
use crate::capabilities::response_state::{ClaimAdded, Store};
use crate::config::Config;
use serde_json::{json, Value};

/// The feature tokens this build reports in every heartbeat (`meta.response_actions.tokens`).
/// The backend acts on an agent only when the token for the command is in this list.
pub const SUPPORTED_TOKENS: &[&str] =
    &["block_ip_ttl", "block_ip_range", "quarantine_file", "unquarantine_file"];
pub const BLOCK_TTL_MIN: i64 = 3_600;
pub const BLOCK_TTL_MAX: i64 = 604_800;
pub const BLOCK_TTL_DEFAULT: i64 = 86_400;

const SUPPORT_REPORT_VERSION: u32 = 1;

/// True for the commands this module answers.
pub fn handles(action: &str) -> bool {
    matches!(action, "block_ip" | "unblock_ip" | "quarantine_file" | "unquarantine_file")
}

/// What the heartbeat carries as `meta.response_actions`: which platform this is and which
/// response features it supports. Any platform without a firewall plan reports no tokens.
pub fn support_report() -> Value {
    support_report_for(Os::current())
}

pub(crate) fn support_report_for(os: Option<Os>) -> Value {
    let tokens: &[&str] = if os.is_some() { SUPPORTED_TOKENS } else { &[] };
    json!({
        "v": SUPPORT_REPORT_VERSION,
        "platform": os.map_or(std::env::consts::OS, Os::name),
        "tokens": tokens,
    })
}

/// Start the task that ends blocks on time: a start-up pass, then one every 15 seconds. It needs
/// nothing from the platform, so call it before registration.
pub fn spawn_sweeper(stop_rx: Option<tokio::sync::watch::Receiver<bool>>) {
    crate::capabilities::response_sweeper::spawn(stop_rx);
}

/// Answer one response instruction. Never panics; every failure is a result body.
pub async fn handle(action: &str, item: &Value, cfg: &Config, _client: &reqwest::Client) -> Value {
    match action {
        "quarantine_file" => return quarantine_arm(item).await,
        "unquarantine_file" => return unquarantine_arm(item).await,
        _ => {}
    }
    handle_at(action, item, cfg, Os::current(), &Store::default(), now_epoch())
}

/// Move a flagged file into quarantine. The process list is read just before the move so the
/// answer can name what still runs from the file afterwards. File work runs off the async
/// threads, and the paths are read here, on the calling thread.
async fn quarantine_arm(item: &Value) -> Value {
    let (Some(path), Some(sha256)) = (
        param(item, "path").and_then(Value::as_str),
        param(item, "sha256").and_then(Value::as_str),
    ) else {
        return refused("path and sha256 are required.");
    };
    let req = quarantine::QuarantineRequest {
        path: path.to_string(),
        sha256: sha256.to_string(),
        allow_protected: param(item, "allow_protected").and_then(Value::as_bool).unwrap_or(false),
        id: item.get("task_id").and_then(Value::as_str).unwrap_or("").to_string(),
    };
    let paths = quarantine::QuarantinePaths::system();
    tokio::task::spawn_blocking(move || {
        let running = quarantine::running_now();
        quarantine::quarantine_at(&paths, &req, now_epoch(), &running)
    })
    .await
    .unwrap_or_else(|_| failed(RemediationError::OperationFailed("The quarantine task stopped unexpectedly.".into())))
}

/// Put a quarantined file back. Only the id travels in the instruction; the destination comes
/// from the manifest the agent wrote.
async fn unquarantine_arm(item: &Value) -> Value {
    let Some(id) = param(item, "quarantine_id").and_then(Value::as_str).map(str::to_string) else {
        return refused("quarantine_id is required.");
    };
    let paths = quarantine::QuarantinePaths::system();
    tokio::task::spawn_blocking(move || quarantine::restore_at(&paths, &id))
        .await
        .unwrap_or_else(|_| failed(RemediationError::OperationFailed("The restore task stopped unexpectedly.".into())))
}

pub(crate) fn now_epoch() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// The dispatch with its time, platform and state file supplied, so tests control all three.
pub(crate) fn handle_at(
    action: &str,
    item: &Value,
    cfg: &Config,
    os: Option<Os>,
    store: &Store,
    now: i64,
) -> Value {
    let Some(os) = os else {
        return refused("This platform does not support blocking an address.");
    };
    match action {
        "block_ip" => block(item, cfg, os, store, now),
        "unblock_ip" => unblock(item, os, store, now),
        _ => refused("Not a response command."),
    }
}

fn refused(why: &str) -> Value {
    json!({"status": "error", "outcome": "refused", "error": why})
}

fn failed(err: RemediationError) -> Value {
    // A security product stopped the command: its own outcome, and nothing retries it.
    if matches!(err, RemediationError::BlockedByLocalSecurity(_)) {
        return json!({"status": "error", "outcome": "blocked_by_local_security", "error": err.to_string()});
    }
    json!({"status": "error", "error": err.to_string()})
}

fn param<'a>(item: &'a Value, key: &str) -> Option<&'a Value> {
    item.get("parameters").and_then(|p| p.get(key)).filter(|v| !v.is_null())
}

/// An instruction id the agent will accept as a claim key.
pub(crate) fn valid_id(id: &str) -> bool {
    (1..=64).contains(&id.len()) && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-')
}

fn ttl_seconds(item: &Value) -> Result<i64, String> {
    match param(item, "ttl_seconds") {
        None => Ok(BLOCK_TTL_DEFAULT),
        Some(v) => match v.as_i64() {
            Some(n) if (BLOCK_TTL_MIN..=BLOCK_TTL_MAX).contains(&n) => Ok(n),
            _ => Err(format!(
                "ttl_seconds must be a whole number from {BLOCK_TTL_MIN} to {BLOCK_TTL_MAX}."
            )),
        },
    }
}

/// The address (`ip_address`) or the network (`cidr`) the instruction names, but not both.
fn parse_target_param(item: &Value) -> Result<Target, String> {
    match (param(item, "ip_address"), param(item, "cidr")) {
        (Some(_), Some(_)) => Err("Give either ip_address or cidr, not both.".to_string()),
        (None, Some(cidr)) => cidr
            .as_str()
            .and_then(net_safety::parse_network)
            .map(|(ip, prefix)| Target::network(ip, prefix))
            .ok_or_else(|| "cidr is not a valid network.".to_string()),
        (ip, None) => ip
            .and_then(Value::as_str)
            .ok_or_else(|| "ip_address is required.".to_string())?
            .parse::<std::net::IpAddr>()
            .map(Target::host)
            .map_err(|_| "ip_address is not a valid IP address.".to_string()),
    }
}

fn block(item: &Value, cfg: &Config, os: Os, store: &Store, now: i64) -> Value {
    let target = match parse_target_param(item) {
        Ok(target) => target,
        Err(why) => return refused(&why),
    };
    if let Some(why) = net_safety::refuse_reason(&target, cfg, os, &net_safety::system_lookup) {
        return refused(why);
    }
    let ttl = match ttl_seconds(item) {
        Ok(ttl) => ttl,
        Err(why) => return refused(&why),
    };
    let block_id = match item.get("task_id").and_then(Value::as_str) {
        Some(id) if valid_id(id) => id,
        _ => return refused("The instruction id is missing or not valid."),
    };
    let key = target.to_string();

    // 1. The claim goes to disk before the firewall changes.
    let added = match store.update(|s| s.add_claim(&key, block_id, now + ttl, now)) {
        Ok(added) => added,
        Err(e) => return failed(e),
    };
    let (outcome, expires_at) = match added {
        ClaimAdded::New => ("applied", now + ttl),
        ClaimAdded::Existing { expires_at } => ("already_applied", expires_at),
    };

    // 2. Add what is missing. Nothing is added twice.
    if let Err(e) = firewall::apply_block(os, target) {
        if added == ClaimAdded::New {
            undo_failed_block(store, os, target, block_id, now);
        }
        return failed(e);
    }

    // 3. Check it is there, and say so.
    let present = firewall::rule_present(os, target).unwrap_or(false);
    let mut body = json!({
        "status": "success",
        "outcome": outcome,
        "verify": {"ok": present, "check": "firewall_rule_present"},
    });
    if present {
        body["expires_in"] = json!((expires_at - now).max(0));
    }
    body
}

/// The firewall step failed after the claim was written: drop the claim, and take out whatever
/// part of the rule was added unless another live claim still needs it.
fn undo_failed_block(store: &Store, os: Os, target: Target, block_id: &str, now: i64) {
    let key = target.to_string();
    let _ = store.update(|s| {
        s.remove_claims(&key, Some(block_id));
        if s.live_for(&key, now) == 0 {
            let _ = firewall::remove_block(os, target);
        }
    });
}

fn unblock(item: &Value, os: Os, store: &Store, now: i64) -> Value {
    let target = match parse_target_param(item) {
        Ok(target) => target,
        Err(why) => return refused(&why),
    };
    let block_id = match param(item, "block_id") {
        None => None,
        Some(Value::String(id)) if valid_id(id) => Some(id.as_str()),
        Some(_) => return refused("block_id is not valid."),
    };
    let key = target.to_string();

    // The claim is removed, and the rule with it only when no live claim is left. The change is
    // kept only if the rule removal worked, so a failed removal leaves the claims in place.
    let done = store.update(|state| -> Result<(usize, bool, bool), RemediationError> {
        let mut next = state.clone();
        let claims_removed = next.remove_claims(&key, block_id);
        let still_held = next.live_for(&key, now) > 0;
        let mut rule_removed = false;
        if !still_held {
            rule_removed = firewall::remove_block(os, target)?;
            next.drop_expired(&key, now);
        }
        *state = next;
        Ok((claims_removed, still_held, rule_removed))
    });
    let (claims_removed, still_held, rule_removed) = match done {
        Ok(Ok(parts)) => parts,
        Ok(Err(e)) | Err(e) => return failed(e),
    };

    let outcome = if claims_removed > 0 || rule_removed { "removed" } else { "not_found" };
    let present = firewall::rule_present(os, target).unwrap_or(false);
    let verify = if still_held {
        // Another instruction still holds this address, so the rule is meant to stay.
        json!({"ok": present, "check": "firewall_rule_present"})
    } else {
        json!({"ok": !present, "check": "firewall_rule_absent"})
    };
    json!({"status": "success", "outcome": outcome, "verify": verify})
}

#[cfg(test)]
#[path = "response_actions_tests.rs"]
mod tests;
