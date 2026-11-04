//! Host isolation that cannot lose the host (RESP-05, D-15).
//!
//! `apply` runs in this order and stops at the first failure, backing out at once:
//!
//! 1. write the isolation record (id, `revertAt` = now + 4 hours) to `response_state.json`;
//! 2. add the management allow rules (loopback, the platform, DHCP);
//! 3. check that every one of those rules exists;
//! 4. only then block everything else;
//! 5. check that the block took effect (`not_effective` when a Group Policy firewall or a firewall
//!    manager overrode it, or when a gateway outside the carve-out still answers, see `probe`);
//! 6. connect to the platform from this very process (`self_test_failed` when it cannot).
//!
//! A second `isolate_host` while isolated (WR-16) adopts the new id, so the platform's confirmation
//! finds it, and a new id or a revert already due starts a new 4-hour window. It answers
//! `already_applied` only when every allow rule and the block are really there; otherwise the
//! steps above run again under the record, which keeps the policy saved by the first apply.
//!
//! The agent holds its own revert. `revert_due` (called by the sweeper every 15 seconds and once
//! at start-up) ends an isolation whose `revertAt` has come unless a person confirmed it, with no
//! help from the network. A state file that cannot be read leads to a revert of whatever
//! isolation rules are found, because losing the host is the worse failure. Reverting lifts the
//! block before it removes the allow rules, and a lift that failed keeps the allow rules.
//!
//! One process-wide lock serialises apply, restore and the revert passes. A confirmation arrives
//! through the state file's own lock, so it is either processed before a revert pass (and cancels
//! it) or finds the isolation gone (and changes nothing).

use crate::capabilities::firewall::{Cmd, Ensure, Os};
use crate::capabilities::isolation_plan::{self as plan, ApplyPlan, CarveOut, Do, Undo, REVERT_SECONDS};
use crate::capabilities::net_safety;
use crate::capabilities::privileged;
use crate::capabilities::remediation_actions::RemediationError;
use crate::capabilities::response_actions::{failed, refused, valid_id};
use crate::capabilities::response_state::{Isolation, Store};
use crate::config::Config;
use serde_json::{json, Value};
use std::net::IpAddr;
use std::sync::{Mutex, MutexGuard};

#[path = "isolation_probe.rs"]
mod probe;
pub use probe::{reach, tcp_self_test, Reach};

static LOCK: Mutex<()> = Mutex::new(());

fn lock() -> MutexGuard<'static, ()> {
    LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

const NO_HOST: &str = "api_base_url has no host, so no way to the platform can be kept open and the host is not isolated.";
const UNRESOLVED: &str = "The platform's address could not be worked out, so the host is not isolated.";

fn check(ok: bool) -> Value {
    json!({"ok": ok, "check": "management_connection_open"})
}

/// What a default-block policy cannot close on Windows (WR-20); the result route keeps `message`.
pub const WINDOWS_LIMIT: &str = "Firewall allow rules that were already turned on, for example for Remote Desktop, still apply while this computer is isolated.";

fn isolated_body(os: Os) -> Value {
    let mut body = json!({"status": "success", "outcome": "isolated", "verify": check(true)});
    if os == Os::Windows {
        body["message"] = json!(WINDOWS_LIMIT);
    }
    body
}

fn already_applied_body() -> Value {
    json!({"status": "success", "outcome": "already_applied", "verify": check(true)})
}

fn self_test_failed_body() -> Value {
    json!({
        "status": "error",
        "outcome": "self_test_failed",
        "verify": check(false),
        "error": "The management connection did not stay open, so the change was undone.",
    })
}

fn not_effective_body() -> Value {
    json!({
        "status": "error",
        "outcome": "not_effective",
        "verify": check(false),
        "error": "The firewall rules were added but this computer's firewall settings did not apply them, so the change was undone.",
    })
}

fn step_failed(why: &str) -> Value {
    json!({"status": "error", "error": why})
}

fn restored_body(ok: bool) -> Value {
    json!({"status": "success", "outcome": "restored", "verify": {"ok": ok, "check": "network_restored"}})
}

/// Every address the platform has, and the resolvers to keep open when it is given by name.
pub fn carve_out(
    cfg: &Config,
    lookup: &dyn Fn(&str) -> Vec<IpAddr>,
    resolvers: &dyn Fn() -> Vec<IpAddr>,
) -> Result<CarveOut, &'static str> {
    let url = reqwest::Url::parse(&cfg.api_base_url).map_err(|_| NO_HOST)?;
    let host = url.host_str().ok_or(NO_HOST)?.trim_start_matches('[').trim_end_matches(']').to_string();
    let port = url.port_or_known_default().unwrap_or(443);
    if let Ok(ip) = host.parse::<IpAddr>() {
        return Ok(CarveOut { addresses: vec![ip.to_canonical()], dns: Vec::new(), port });
    }
    let unique = |list: Vec<IpAddr>| {
        let mut out: Vec<IpAddr> = Vec::new();
        for ip in list.into_iter().map(|ip| ip.to_canonical()) {
            if !out.contains(&ip) {
                out.push(ip);
            }
        }
        out
    };
    let addresses = unique(lookup(&host));
    if addresses.is_empty() {
        return Err(UNRESOLVED);
    }
    Ok(CarveOut { addresses, dns: unique(resolvers()), port })
}

/// True when `api_base_url` names a host at all (the cheap refusal before the work is accepted).
pub fn platform_has_host(cfg: &Config) -> bool {
    reqwest::Url::parse(&cfg.api_base_url).ok().is_some_and(|u| u.host_str().is_some())
}

fn output(cmd: &Cmd) -> Result<String, RemediationError> {
    let args: Vec<&str> = cmd.args.iter().map(String::as_str).collect();
    privileged::run_output(cmd.program, &args)
}

/// Add the rule unless the check says it is there; a check that cannot be made fails the step.
fn ensure(e: &Ensure) -> Result<(), RemediationError> {
    if e.check.probe()? { Ok(()) } else { e.add.run() }
}

fn run_do(step: &Do) -> Result<(), RemediationError> {
    match step {
        Do::Ensure(e) => ensure(e),
        Do::Run(cmd) => cmd.run(),
    }
}

fn run_undo(step: &Undo) -> Result<(), RemediationError> {
    match step {
        // Only a definite "not there" skips the delete; a check that could not be made tries it.
        Undo::Remove(r) if matches!(r.check.probe(), Ok(false)) => Ok(()),
        Undo::Remove(r) => r.delete.run(),
        Undo::Run(cmd) => cmd.run(),
    }
}

/// Put the firewall back. Every step is tried, but the allow rules and chains go only when the
/// block was lifted completely: removing them with the block still in place would cut the host off.
fn revert_rules(os: Os, saved: &Value, default_when_unknown: bool) -> Result<(), String> {
    let steps = plan::revert_plan(os, saved, default_when_unknown);
    let lift: Vec<String> = steps.lift.iter().filter_map(|s| run_undo(s).err()).map(|e| e.to_string()).collect();
    if !lift.is_empty() {
        return Err(lift.join("; "));
    }
    let clear: Vec<String> = steps.clear.iter().filter_map(|s| run_undo(s).err()).map(|e| e.to_string()).collect();
    if clear.is_empty() { Ok(()) } else { Err(clear.join("; ")) }
}

/// Any isolation rule is in place, or a check could not tell (WR-19), so callers try the revert or
/// keep the record rather than trust a guess. A firewall tool that is not installed holds no rules.
fn rules_present(os: Os) -> bool {
    plan::present_checks(os).iter().any(|c| match c.probe() {
        Ok(found) => found,
        Err(RemediationError::FileNotFound(_)) => false,
        Err(_) => true,
    })
}

/// The state is lost: remove whatever isolation rules are there. Ok(true) when rules were found
/// and removed, Ok(false) when there were none.
fn force_revert(os: Os) -> Result<bool, String> {
    if !rules_present(os) {
        return Ok(false);
    }
    log::warn!("The isolation record cannot be read; taking out the isolation rules so the host keeps its network");
    revert_rules(os, &Value::Null, true).map(|()| true)
}

/// Undo a failed apply. The record goes only when the firewall is clean; otherwise the revert is
/// made due now, so the sweeper keeps trying every 15 seconds. Ok(true) when the host is clean.
fn back_out(store: &Store, os: Os, now: i64) -> bool {
    let done = store.update(|s| {
        let saved = s.isolation.as_ref().map_or(Value::Null, |i| i.saved_policy.clone());
        match revert_rules(os, &saved, false) {
            Ok(()) => {
                s.isolation = None;
                true
            }
            Err(e) => {
                log::error!("Could not undo a failed isolation, will keep trying: {e}");
                if let Some(i) = s.isolation.as_mut() {
                    i.revert_at = now;
                    i.confirmed = false;
                }
                false
            }
        }
    });
    match done {
        Ok(clean) => clean,
        Err(_) => force_revert(os).unwrap_or(false),
    }
}

/// Back out and answer with `body`; a back-out that could not finish says so.
fn abort(store: &Store, os: Os, now: i64, mut body: Value) -> Value {
    if !back_out(store, os, now) {
        let why = body["error"].as_str().unwrap_or("The change failed.").to_string();
        body["error"] = json!(format!("{why} The change could not be fully undone; the agent keeps trying every 15 seconds."));
    }
    body
}

/// The block is in place (the hooks on Linux, the policy read back on Windows); an error when a
/// check could not be made.
fn effective(os: Os, steps: &ApplyPlan) -> Result<bool, RemediationError> {
    match (os, steps.effective.first()) {
        (Os::Linux, _) => Ok(steps.effective.iter().map(Cmd::probe).collect::<Result<Vec<_>, _>>()?.into_iter().all(|ok| ok)),
        (Os::Windows, Some(read)) => Ok(plan::all_blocked(&output(read)?)),
        (Os::Windows, None) => Ok(false),
    }
}

/// Every allow rule and the block are in place right now.
fn in_place(os: Os, steps: &ApplyPlan) -> Result<bool, RemediationError> {
    for check in steps.verify() {
        if !check.probe()? {
            return Ok(false);
        }
    }
    effective(os, steps)
}

/// Isolate the host with the real name lookup, resolvers, self-test and outside probe.
pub fn apply(store: &Store, os: Os, cfg: &Config, id: &str, now: i64) -> Value {
    apply_with(store, os, cfg, id, now, &net_safety::system_lookup, &|| net_safety::host_addrs(os).dns, &|c| reach(os, c))
}

/// `apply` with the name lookup, the resolver list and the reach checks supplied.
#[allow(clippy::too_many_arguments)]
pub fn apply_with(
    store: &Store,
    os: Os,
    cfg: &Config,
    id: &str,
    now: i64,
    lookup: &dyn Fn(&str) -> Vec<IpAddr>,
    resolvers: &dyn Fn() -> Vec<IpAddr>,
    probe: &dyn Fn(&CarveOut) -> Reach,
) -> Value {
    if !valid_id(id) {
        return refused("The instruction id is missing or not valid.");
    }
    let carve = match carve_out(cfg, lookup, resolvers) {
        Ok(carve) => carve,
        Err(why) => return refused(why),
    };
    let _guard = lock();
    let steps = plan::apply_plan(os, &carve);

    // 1. The record goes to disk before the firewall changes. A repeat adopts the new id; a new id
    //    or a revert already due starts a new window (WR-16).
    let record = Isolation { id: id.to_string(), started_at: now, revert_at: now + REVERT_SECONDS, confirmed: false, saved_policy: Value::Null };
    let held = store.update(|s| match s.isolation.as_mut() {
        None => {
            s.isolation = Some(record);
            None
        }
        Some(i) => {
            if !i.confirmed && (i.id != id || i.revert_at <= now) {
                i.revert_at = now + REVERT_SECONDS;
            }
            i.id = id.to_string();
            Some(i.saved_policy.clone())
        }
    });
    let saved = match held {
        Ok(None) => Value::Null,
        // Rules removed by hand, by a policy refresh or left by a failed back-out are put back.
        Ok(Some(saved)) => match in_place(os, &steps) {
            Ok(true) => return already_applied_body(),
            Ok(false) => saved,
            Err(e) => return failed(e),
        },
        Err(e) => return failed(e),
    };
    // Windows: keep the policy each profile has now, to put it back (a repeat keeps the first one).
    if os == Os::Windows && saved.is_null() {
        let saved = output(&plan::read_policy_cmd()).map(|out| plan::saved_policy(&out));
        let kept = saved.map_err(failed).and_then(|saved| {
            store.update(|s| s.isolation.iter_mut().for_each(|i| i.saved_policy = saved.clone())).map_err(failed)
        });
        if let Err(body) = kept {
            return abort(store, os, now, body);
        }
    }
    // 2. The management path opens. 3. Every rule is checked before anything closes.
    for rule in &steps.allow {
        if let Err(e) = ensure(rule) {
            return abort(store, os, now, failed(e));
        }
    }
    if !steps.verify().iter().all(Cmd::passes) {
        return abort(store, os, now, step_failed("The rules that keep the platform reachable could not be confirmed, so nothing was blocked and the change was undone."));
    }
    // 4. Only now is everything else blocked.
    for step in &steps.block {
        if let Err(e) = run_do(step) {
            return abort(store, os, now, failed(e));
        }
    }
    if !effective(os, &steps).unwrap_or(false) {
        return abort(store, os, now, not_effective_body());
    }
    // 5. Nothing outside the carve-out answers any more, and the platform still does.
    let seen = probe(&carve);
    if seen.outside {
        return abort(store, os, now, not_effective_body());
    }
    if !seen.platform {
        return abort(store, os, now, self_test_failed_body());
    }
    isolated_body(os)
}

/// End the isolation. Any isolation on this host is ended whatever id it carries: failing open
/// for the network is the safe side. A repeat answers `not_found` with no firewall command.
pub fn restore(store: &Store, os: Os, id: &str, now: i64) -> Value {
    if !valid_id(id) {
        return refused("isolation_id is not valid.");
    }
    let _guard = lock();
    let done = store.update(|s| -> Result<bool, String> {
        let Some(saved) = s.isolation.as_ref().map(|i| i.saved_policy.clone()) else { return Ok(false) };
        match revert_rules(os, &saved, false) {
            Ok(()) => {
                s.isolation = None;
                Ok(true)
            }
            Err(e) => {
                if let Some(i) = s.isolation.as_mut() {
                    i.revert_at = now;
                    i.confirmed = false;
                }
                Err(e)
            }
        }
    });
    let found = match done {
        Ok(Ok(found)) => found,
        Ok(Err(e)) => return step_failed(&format!("The host could not be taken out of isolation yet; the agent keeps trying. {e}")),
        Err(e) => match force_revert(os) {
            Ok(found) => found,
            Err(_) => return failed(e),
        },
    };
    if found {
        restored_body(!rules_present(os))
    } else if rules_present(os) {
        // No record but the rules are there: the state file was lost (WR-17), so they come out now.
        match force_revert(os) {
            Ok(_) => restored_body(!rules_present(os)),
            Err(e) => step_failed(&format!("The host could not be taken out of isolation yet. {e}")),
        }
    } else {
        json!({"status": "success", "outcome": "not_found", "verify": {"ok": true, "check": "network_restored"}})
    }
}

/// What one pass did.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct PassOutcome {
    pub reverted: bool,
    pub error: Option<String>,
}

fn due_pass(store: &Store, os: Os, now: i64) -> PassOutcome {
    let done = store.update(|s| -> Option<Result<(), String>> {
        let iso = s.isolation.as_ref()?;
        if iso.confirmed || iso.revert_at > now {
            return None;
        }
        let result = revert_rules(os, &iso.saved_policy.clone(), false);
        if result.is_ok() {
            s.isolation = None;
        }
        Some(result)
    });
    match done {
        Ok(None) => PassOutcome::default(),
        Ok(Some(Ok(()))) => PassOutcome { reverted: true, error: None },
        Ok(Some(Err(e))) => {
            log::error!("The isolation is due to end but could not be lifted, will retry: {e}");
            PassOutcome { reverted: false, error: Some(e) }
        }
        Err(unreadable) => match force_revert(os) {
            Ok(removed) => PassOutcome { reverted: removed, error: Some(unreadable.to_string()) },
            Err(e) => PassOutcome { reverted: false, error: Some(e) },
        },
    }
}

/// One revert pass: an unconfirmed isolation whose `revertAt` has come (`revertAt <= now`) is
/// ended. With no isolation recorded this issues no command.
pub fn revert_due(store: &Store, os: Os, now: i64) -> PassOutcome {
    let _guard = lock();
    due_pass(store, os, now)
}

/// The pass at start-up: `revert_due`; on Linux an isolation whose rules a reboot dropped is
/// forgotten, because the host is no longer isolated and the report must not say it is; and
/// isolation rules with no record (the state file was lost, WR-17) are taken out.
pub fn start_up(store: &Store, os: Os, now: i64) -> PassOutcome {
    let _guard = lock();
    let mut outcome = due_pass(store, os, now);
    let recorded = store.load().is_ok_and(|s| s.isolation.is_some());
    if !outcome.reverted && store.load().is_ok_and(|s| s.isolation.is_none()) {
        match force_revert(os) {
            Ok(removed) => outcome.reverted |= removed,
            Err(e) => outcome.error = Some(e),
        }
    }
    if os == Os::Linux && !outcome.reverted && recorded && !rules_present(os) {
        let dropped = store.update(|s| s.isolation.take().is_some()).unwrap_or(false);
        if dropped {
            log::warn!("The isolation rules are gone (the host restarted), so the isolation record was dropped");
            outcome.reverted = true;
        }
    }
    outcome
}

/// The ids in a heartbeat reply's `isolationConfirmed` (a list, or one id).
pub fn confirmed_ids(body: &Value) -> Vec<String> {
    match body.get("isolationConfirmed") {
        Some(Value::Array(list)) => list.iter().filter_map(Value::as_str).map(str::to_string).collect(),
        Some(Value::String(id)) => vec![id.clone()],
        _ => Vec::new(),
    }
}

/// A person confirmed the isolation with this id: it is kept until someone restores the host.
/// An unknown id, no isolation, or an isolation already ended changes nothing. True when it changed.
pub fn apply_confirmations(store: &Store, ids: &[String]) -> Result<bool, RemediationError> {
    store.update(|s| match s.isolation.as_mut() {
        Some(i) if !i.confirmed && ids.iter().any(|id| *id == i.id) => {
            i.confirmed = true;
            true
        }
        _ => false,
    })
}

/// Called with every heartbeat reply.
pub fn apply_body(body: &Value) {
    let ids = confirmed_ids(body);
    if ids.is_empty() {
        return;
    }
    match apply_confirmations(&Store::default(), &ids) {
        Ok(true) => log::info!("An operator confirmed the isolation; it stays until the host is restored"),
        Ok(false) => {}
        Err(e) => log::warn!("Could not record the isolation confirmation: {e}"),
    }
}

/// `meta.response_state` of every heartbeat: the isolation (so the platform notices an automatic
/// revert), when the host last booted, and how many block claims are live.
pub fn response_state_report(store: &Store, now: i64) -> Value {
    let boot_time = sysinfo::System::boot_time();
    match store.load() {
        Ok(state) => {
            let isolation = state.isolation.as_ref().map(|i| {
                let left = if i.confirmed { Value::Null } else { json!((i.revert_at - now).max(0)) };
                json!({"id": i.id, "active": true, "confirmed": i.confirmed, "revert_in_seconds": left})
            });
            let live = state.claims.iter().filter(|c| c.expires_at > now).count();
            json!({"v": 1, "isolation": isolation, "boot_time": boot_time, "active_blocks": live})
        }
        Err(_) => json!({"v": 1, "isolation": null, "boot_time": boot_time, "active_blocks": 0, "state_unreadable": true}),
    }
}

#[cfg(test)]
#[path = "isolation_tests.rs"]
mod tests;
#[cfg(test)]
#[path = "isolation_pass_tests.rs"]
mod pass_tests;
