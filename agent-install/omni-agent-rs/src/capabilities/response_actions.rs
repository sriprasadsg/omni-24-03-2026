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
//!
//! `isolate_host` and `restore_host` change the host's whole network, so they run off the poll
//! loop: the instruction answers `accepted`, and `isolation` posts the final body to the same
//! result route under the same task id (see `background_arm`).

use crate::capabilities::firewall::{self, Os, Target};
use crate::capabilities::isolation;
use crate::capabilities::net_safety;
use crate::capabilities::process_kill;
use crate::capabilities::quarantine;
use crate::capabilities::remediation_actions::{self, RemediationError};
use crate::capabilities::response_state::{ClaimAdded, Store};
use crate::capabilities::service_watch;
use crate::config::Config;
use serde_json::{json, Value};

/// The feature tokens this build reports in every heartbeat (`meta.response_actions.tokens`).
/// The backend acts on an agent only when the token for the command is in this list.
pub const SUPPORTED_TOKENS: &[&str] = &[
    "block_ip_ttl", "block_ip_range", "quarantine_file", "unquarantine_file", "kill_process_exe",
    "restart_service", "service_failures", "isolate_host", "restore_host",
];
pub const BLOCK_TTL_MIN: i64 = 3_600;
pub const BLOCK_TTL_MAX: i64 = 604_800;
pub const BLOCK_TTL_DEFAULT: i64 = 86_400;

const SUPPORT_REPORT_VERSION: u32 = 1;

/// True for the commands this module answers.
pub fn handles(action: &str) -> bool {
    matches!(
        action,
        "block_ip" | "unblock_ip" | "quarantine_file" | "unquarantine_file" | "kill_process" | "restart_service" | "isolate_host" | "restore_host"
    )
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
/// nothing from the platform, so call it before registration. The same passes end an isolation
/// whose revert time has come (`isolation::revert_due`, called from `response_sweeper`).
pub fn spawn_sweeper(stop_rx: Option<tokio::sync::watch::Receiver<bool>>) {
    crate::capabilities::response_sweeper::spawn(stop_rx);
}

/// Answer one response instruction. Never panics; every failure is a result body.
pub async fn handle(action: &str, item: &Value, cfg: &Config, client: &reqwest::Client) -> Value {
    match action {
        "isolate_host" | "restore_host" => return background_arm(action, item, cfg, client),
        "restart_service" => return service_watch::restart_arm(item, cfg, client),
        "quarantine_file" => return quarantine_arm(item).await,
        "unquarantine_file" => return unquarantine_arm(item).await,
        "kill_process" => return kill_arm(item).await,
        _ => {}
    }
    handle_at(action, item, cfg, Os::current(), &Store::default(), now_epoch())
}

/// How long the final isolation body waits, so the `accepted` answer is posted first and the
/// final body is the last word the platform hears for the task.
pub(crate) const ACCEPTED_HEAD_START: std::time::Duration = std::time::Duration::from_secs(2);

/// `isolate_host` / `restore_host`: check the input, answer `accepted`, and do the work on a
/// blocking thread. The final body is posted with the same task id as the `accepted` one.
fn background_arm(action: &str, item: &Value, cfg: &Config, client: &reqwest::Client) -> Value {
    let Some(os) = Os::current() else {
        return refused("This platform does not support isolating a host.");
    };
    let Some(task_id) = item.get("task_id").and_then(Value::as_str).filter(|id| valid_id(id)).map(str::to_string) else {
        return refused("The instruction id is missing or not valid.");
    };
    let restoring = action == "restore_host";
    let id = if restoring {
        match param(item, "isolation_id").and_then(Value::as_str).filter(|id| valid_id(id)) {
            Some(id) => id.to_string(),
            None => return refused("isolation_id is required."),
        }
    } else {
        if !isolation::platform_has_host(cfg) {
            return refused("The platform address has no host, so no way to it can be kept open and the host is not isolated.");
        }
        task_id.clone()
    };
    let (cfg, client, action) = (cfg.clone(), client.clone(), action.to_string());
    tokio::spawn(async move {
        tokio::time::sleep(ACCEPTED_HEAD_START).await;
        let work = {
            let cfg = cfg.clone();
            move || {
                let store = Store::default();
                if restoring {
                    isolation::restore(&store, os, &id, now_epoch())
                } else {
                    isolation::apply(&store, os, &cfg, &id, now_epoch(), &isolation::tcp_self_test)
                }
            }
        };
        let body = tokio::task::spawn_blocking(work)
            .await
            .unwrap_or_else(|_| failed(RemediationError::OperationFailed("The isolation task stopped unexpectedly.".into())));
        crate::instructions::report_result(&client, &cfg, &task_id, &action, &body).await;
    });
    json!({"status": "accepted"})
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

/// `kill_process`. With `expected_exe` it ends only the approved program (see `process_kill`);
/// with `quarantine_id` it also ends the quarantined image, whose stored path the agent works out
/// itself, because the instruction never carries one. With only `target` it is the Phase 53 kill
/// that the UEBA path uses, with the same result body as before.
async fn kill_arm(item: &Value) -> Value {
    if param(item, "expected_exe").is_none() {
        let target = param(item, "target").and_then(Value::as_str).unwrap_or("");
        return match remediation_actions::kill_process(target).await {
            Ok(()) => json!({"status": "success", "message": "Process kill initiated"}),
            Err(e) => json!({"status": "error", "error": e.to_string()}),
        };
    }
    let params = item.get("parameters").cloned().unwrap_or_else(|| json!({}));
    let (expected_exe, listed) = match process_kill::parse_request(&params) {
        Ok(parsed) => parsed,
        Err(why) => return process_kill::refused_body(&why),
    };
    let moved_exe = match param(item, "quarantine_id") {
        None => None,
        Some(v) => match v.as_str().filter(|id| valid_id(id)) {
            Some(id) => Some(quarantine::stored_path(&quarantine::QuarantinePaths::system(), id).to_string_lossy().into_owned()),
            None => return process_kill::refused_body("quarantine_id is not valid."),
        },
    };
    process_kill::kill_by_exe(process_kill::KillRequest { expected_exe, moved_exe, listed }).await
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

pub(crate) fn refused(why: &str) -> Value {
    json!({"status": "error", "outcome": "refused", "error": why})
}

pub(crate) fn failed(err: RemediationError) -> Value {
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
