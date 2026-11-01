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
//! hyphens, and an address that cannot sensibly be blocked.

use crate::capabilities::firewall::{self, Os};
use crate::capabilities::remediation_actions::RemediationError;
use crate::capabilities::response_state::{ClaimAdded, Store};
use crate::config::Config;
use serde_json::{json, Value};
use std::net::IpAddr;

/// The feature tokens this build reports in every heartbeat (`meta.response_actions.tokens`).
/// The backend acts on an agent only when the token for the command is in this list.
pub const SUPPORTED_TOKENS: &[&str] = &["block_ip_ttl"];
pub const BLOCK_TTL_MIN: i64 = 3_600;
pub const BLOCK_TTL_MAX: i64 = 604_800;
pub const BLOCK_TTL_DEFAULT: i64 = 86_400;

const SUPPORT_REPORT_VERSION: u32 = 1;

/// True for the commands this module answers.
pub fn handles(action: &str) -> bool {
    matches!(action, "block_ip" | "unblock_ip")
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
    handle_at(action, item, cfg, Os::current(), &Store::default(), now_epoch())
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
    json!({"status": "error", "error": err.to_string()})
}

fn param<'a>(item: &'a Value, key: &str) -> Option<&'a Value> {
    item.get("parameters").and_then(|p| p.get(key)).filter(|v| !v.is_null())
}

/// An instruction id the agent will accept as a claim key.
fn valid_id(id: &str) -> bool {
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

fn parse_ip(item: &Value) -> Result<IpAddr, String> {
    let raw = param(item, "ip_address")
        .and_then(Value::as_str)
        .ok_or_else(|| "ip_address is required.".to_string())?;
    raw.parse::<IpAddr>()
        .map(firewall::canonical)
        .map_err(|_| "ip_address is not a valid IP address.".to_string())
}

/// An address that must never be blocked from here: it would cut the host off from itself, from
/// its neighbours, or from the platform.
fn unblockable(ip: IpAddr, cfg: &Config) -> Option<&'static str> {
    let bad = match ip {
        IpAddr::V4(v4) => v4.is_unspecified() || v4.is_loopback() || v4.is_multicast() || v4.is_broadcast() || v4.is_link_local(),
        IpAddr::V6(v6) => {
            v6.is_unspecified() || v6.is_loopback() || v6.is_multicast() || (v6.segments()[0] & 0xffc0) == 0xfe80
        }
    };
    if bad {
        return Some("That address is local, unspecified or multicast and is never blocked.");
    }
    if platform_ip(cfg) == Some(ip) {
        return Some("That is the platform's own address and is never blocked.");
    }
    None
}

/// The platform address when `api_base_url` names it as an IP literal.
fn platform_ip(cfg: &Config) -> Option<IpAddr> {
    let url = reqwest::Url::parse(&cfg.api_base_url).ok()?;
    let host = url.host_str()?.trim_start_matches('[').trim_end_matches(']');
    host.parse::<IpAddr>().ok().map(firewall::canonical)
}

fn block(item: &Value, cfg: &Config, os: Os, store: &Store, now: i64) -> Value {
    let ip = match parse_ip(item) {
        Ok(ip) => ip,
        Err(why) => return refused(&why),
    };
    if let Some(why) = unblockable(ip, cfg) {
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
    let target = ip.to_string();

    // 1. The claim goes to disk before the firewall changes.
    let added = match store.update(|s| s.add_claim(&target, block_id, now + ttl, now)) {
        Ok(added) => added,
        Err(e) => return failed(e),
    };
    let (outcome, expires_at) = match added {
        ClaimAdded::New => ("applied", now + ttl),
        ClaimAdded::Existing { expires_at } => ("already_applied", expires_at),
    };

    // 2. Add what is missing. Nothing is added twice.
    if let Err(e) = firewall::apply_block(os, ip) {
        if added == ClaimAdded::New {
            undo_failed_block(store, os, ip, &target, block_id, now);
        }
        return failed(e);
    }

    // 3. Check it is there, and say so.
    let present = firewall::rule_present(os, ip).unwrap_or(false);
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
fn undo_failed_block(store: &Store, os: Os, ip: IpAddr, target: &str, block_id: &str, now: i64) {
    let _ = store.update(|s| {
        s.remove_claims(target, Some(block_id));
        if s.live_for(target, now) == 0 {
            let _ = firewall::remove_block(os, ip);
        }
    });
}

fn unblock(item: &Value, os: Os, store: &Store, now: i64) -> Value {
    let ip = match parse_ip(item) {
        Ok(ip) => ip,
        Err(why) => return refused(&why),
    };
    let block_id = match param(item, "block_id") {
        None => None,
        Some(Value::String(id)) if valid_id(id) => Some(id.as_str()),
        Some(_) => return refused("block_id is not valid."),
    };
    let target = ip.to_string();

    // The claim is removed, and the rule with it only when no live claim is left. The change is
    // kept only if the rule removal worked, so a failed removal leaves the claims in place.
    let done = store.update(|state| -> Result<(usize, bool, bool), RemediationError> {
        let mut next = state.clone();
        let claims_removed = next.remove_claims(&target, block_id);
        let still_held = next.live_for(&target, now) > 0;
        let mut rule_removed = false;
        if !still_held {
            rule_removed = firewall::remove_block(os, ip)?;
            next.drop_expired(&target, now);
        }
        *state = next;
        Ok((claims_removed, still_held, rule_removed))
    });
    let (claims_removed, still_held, rule_removed) = match done {
        Ok(Ok(parts)) => parts,
        Ok(Err(e)) | Err(e) => return failed(e),
    };

    let outcome = if claims_removed > 0 || rule_removed { "removed" } else { "not_found" };
    let present = firewall::rule_present(os, ip).unwrap_or(false);
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
