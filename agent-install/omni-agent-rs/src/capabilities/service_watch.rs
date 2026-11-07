//! Failed-service reporting and the safe restart (RESP-04, D-10..D-12).
//!
//! The platform sends a tenant's list of services to watch in the heartbeat reply
//! (`watchedServices`); the agent keeps it in `config.yaml` like the enabled capabilities and
//! checks only those names. A service that is failing is reported in `meta.service_failures`,
//! but only after 60 seconds, so systemd's `Restart=` or the Windows recovery actions get their
//! chance first. A service somebody stopped on purpose is never reported:
//!
//! - Linux (`systemctl show`): only `ActiveState=failed` or a `Result` other than `success` counts;
//!   `inactive` with `Result=success` is a stop.
//! - Windows (`sc query`, `sc qc`): only a stopped service with a non-zero exit code and a start
//!   type that is not disabled counts. A crash that exits 0 is missed, which is the safe
//!   direction. The output is read by its numbers (`STATE : 1`, `WIN32_EXIT_CODE : 1066`,
//!   `START_TYPE : 4`) because the words around them are localised.
//!
//! `restart` validates the name again, refuses the agent's own service, every critical service and
//! any systemd unit that is not a service (`reboot.target`), runs fixed argv through `privileged`,
//! and waits for the running state. The instruction is refused for a name not on the watched list. It has no
//! undo (D-12). Everything that starts a command goes through `privileged`, so tests use its
//! recorder and never touch a real service.

use crate::capabilities::firewall::Os;
use crate::capabilities::privileged;
use crate::capabilities::remediation_actions::{self, RemediationError};
use crate::capabilities::response_actions::{blocking, failed, in_background, refused, valid_id};
use crate::config::Config;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::sync::{Mutex, OnceLock};

/// The capability that carries service-failure reporting (D-21: no new tick).
pub const CAPABILITY: &str = "remediation_executor";
/// A failure must be this old before it is reported.
pub const GRACE_SECONDS: i64 = 60;
/// The services are asked about at most this often.
pub const REPORT_CACHE_SECONDS: i64 = 60;
/// The most services a tenant can list.
pub const MAX_WATCHED: usize = 50;
/// A name longer than this is not put in the state report.
pub const MAX_STATE_NAME: usize = 128;
/// After a restart the service is checked this many times, one second apart.
pub const RESTART_POLLS: u32 = 10;

/// What one service looks like right now.
#[derive(Debug, Clone, PartialEq)]
pub enum Health {
    Running,
    /// Starting or stopping: neither healthy nor failed yet.
    Pending,
    /// Stopped cleanly or on purpose. Never reported, never restarted.
    Stopped,
    Failed { state: String, exit_code: Option<i64> },
    /// The service is not installed on this computer (systemd `LoadState` not-found or masked,
    /// `sc` error 1060). Never a failure; the platform judges it against what the computer had
    /// before the change (CR-03).
    Absent,
    Unknown,
}

fn property<'a>(text: &'a str, key: &str) -> Option<&'a str> {
    text.lines().find_map(|line| line.strip_prefix(key)?.strip_prefix('=')).map(str::trim)
}

/// Reads `systemctl show -p LoadState,ActiveState,SubState,Result,ExecMainStatus <unit>`. A unit
/// systemd does not know answers `ActiveState=inactive`, so `LoadState` is read first.
pub fn classify_systemd(output: &str) -> Health {
    if matches!(property(output, "LoadState"), Some("not-found" | "masked")) {
        return Health::Absent;
    }
    let Some(active) = property(output, "ActiveState") else { return Health::Unknown };
    let exit_code = property(output, "ExecMainStatus").and_then(|v| v.parse().ok());
    let bad_result = property(output, "Result").is_some_and(|r| !r.is_empty() && r != "success");
    let failure = || Health::Failed { state: active.to_string(), exit_code };
    match active {
        "failed" => failure(),
        "active" | "reloading" => Health::Running,
        "activating" | "deactivating" => if bad_result { failure() } else { Health::Pending },
        "inactive" => if bad_result { failure() } else { Health::Stopped },
        _ => Health::Unknown,
    }
}

/// The first number after `key :` in `sc` output (`STATE : 1  STOPPED` gives 1).
fn sc_number(text: &str, key: &str) -> Option<i64> {
    text.lines().find_map(|line| {
        let (label, value) = line.split_once(':')?;
        if label.trim() != key {
            return None;
        }
        value.split_whitespace().next()?.parse().ok()
    })
}

/// Reads `sc query <name>` and `sc qc <name>` (`qc` may be empty when it was not asked for).
pub fn classify_sc(query: &str, qc: &str) -> Health {
    match sc_number(query, "STATE") {
        Some(4) => Health::Running,
        Some(2 | 3 | 5 | 6 | 7) => Health::Pending,
        Some(1) => {
            let exit_code = sc_number(query, "WIN32_EXIT_CODE");
            let disabled = sc_number(qc, "START_TYPE") == Some(4);
            if disabled || exit_code.unwrap_or(0) == 0 {
                Health::Stopped
            } else {
                Health::Failed { state: "stopped".to_string(), exit_code }
            }
        }
        _ => Health::Unknown,
    }
}

/// Ask the operating system. The start type is read only for a stopped service that carries an
/// error code, the one case where it decides.
pub fn status_of(os: Os, name: &str) -> Health {
    match os {
        Os::Linux => privileged::run_output("systemctl", &["show", "-p", "LoadState,ActiveState,SubState,Result,ExecMainStatus", name])
            .map_or(Health::Unknown, |out| classify_systemd(&out)),
        Os::Windows => {
            let Ok(query) = privileged::run_output("sc", &["query", name]) else { return Health::Unknown };
            let first = classify_sc(&query, "");
            if !matches!(first, Health::Failed { .. }) {
                return first;
            }
            let qc = privileged::run_output("sc", &["qc", name]).unwrap_or_default();
            classify_sc(&query, &qc)
        }
    }
}

// ── the watched list ──────────────────────────────────────────────────────

/// The list a heartbeat reply carries when it differs from `current`. `None` when the reply has
/// no list, a malformed one (not a list of well-formed names, or too many) or the same one. An
/// empty list is well formed: it means nothing is watched.
pub fn changed_watched(current: Option<&[String]>, body: &Value) -> Option<Vec<String>> {
    let list: Vec<String> = serde_json::from_value(body.get("watchedServices")?.clone()).ok()?;
    if list.len() > MAX_WATCHED || list.iter().any(|name| !remediation_actions::is_valid_service_name(name)) {
        return None;
    }
    (current != Some(list.as_slice())).then_some(list)
}

/// Adopts the watched list of a heartbeat reply and keeps it across restarts.
pub fn update_watched_from_heartbeat(cfg: &mut Config, body: &Value) {
    if let Some(list) = changed_watched(cfg.watched_services.as_deref(), body) {
        log::info!("Platform watched services updated ({} listed)", list.len());
        cfg.watched_services = Some(list);
        if let Err(e) = crate::config::save(cfg) {
            log::warn!("Could not persist the watched services to config.yaml: {e}");
        }
    }
}

// ── the failure report ────────────────────────────────────────────────────

/// One failure's identity: the same until the service has been seen healthy.
pub(crate) fn failure_id(name: &str, since: i64) -> String {
    format!("{}-{since}", name.to_ascii_lowercase())
}

/// What the report remembers between heartbeats.
#[derive(Default)]
pub struct Watch {
    /// Lower-case name -> when it was first seen failing.
    first_seen: HashMap<String, i64>,
    checked_at: Option<i64>,
    checked_for: Vec<String>,
    cached: Vec<Value>,
}

static WATCH: OnceLock<Mutex<Watch>> = OnceLock::new();

/// `meta.service_failures` for this heartbeat: the watched services that have been failing for
/// at least 60 seconds. Empty when the capability is off, nothing is listed or the platform has
/// no service manager the agent knows.
pub fn report(enabled: Option<&[String]>, watched: &[String], now: i64) -> Vec<Value> {
    let mut watch = WATCH.get_or_init(|| Mutex::new(Watch::default())).lock().unwrap_or_else(|e| e.into_inner());
    report_with(&mut watch, Os::current(), enabled, watched, now)
}

pub(crate) fn report_with(w: &mut Watch, os: Option<Os>, enabled: Option<&[String]>, watched: &[String], now: i64) -> Vec<Value> {
    let Some(os) = os.filter(|_| crate::capabilities::is_enabled(enabled, CAPABILITY) && !watched.is_empty()) else {
        *w = Watch::default();
        return Vec::new();
    };
    // The services are asked about once a minute at most, whatever the heartbeat interval.
    if w.checked_at.is_some_and(|at| (0..REPORT_CACHE_SECONDS).contains(&(now - at))) && w.checked_for == watched {
        return w.cached.clone();
    }
    let (mut asked, mut still_failing, mut out) = (HashSet::new(), HashMap::new(), Vec::new());
    for name in watched {
        let key = name.to_ascii_lowercase();
        // A critical or malformed name is never asked about, so it can never be reported.
        if remediation_actions::validate_service_name(name).is_err() || !asked.insert(key.clone()) {
            continue;
        }
        if let Health::Failed { state, exit_code } = status_of(os, name) {
            let since = w.first_seen.get(&key).copied().unwrap_or(now);
            still_failing.insert(key, since);
            if now - since >= GRACE_SECONDS {
                out.push(json!({
                    "name": name, "failure_id": failure_id(name, since), "since": since,
                    "state": state, "exit_code": exit_code,
                }));
            }
        }
    }
    // A service that is healthy again, or no longer listed, starts a new failure next time.
    w.first_seen = still_failing;
    w.checked_at = Some(now);
    w.checked_for = watched.to_vec();
    w.cached = out.clone();
    out
}

// ── the state report ──────────────────────────────────────────────────────

/// The word the heartbeat carries for one service. Starting or stopping is `unknown`: it is
/// neither running nor stopped yet, and the health gate must not read it as running. A service the
/// computer does not have is `absent`, which is not a failure and not missing data.
pub fn state_from_health(h: &Health) -> &'static str {
    match h {
        Health::Running => "running",
        Health::Stopped => "stopped",
        Health::Failed { .. } => "failed",
        Health::Absent => "absent",
        Health::Pending | Health::Unknown => "unknown",
    }
}

/// `meta.service_state` (PTCH-02): the state of every watched service, so a service that was
/// stopped cleanly is seen too (`service_failures` reports failures only). One entry per name in
/// the watched order, a repeated name (any case) once, a name longer than 128 characters or
/// not a service name left out. Pure: `status` answers for one name.
pub fn state_report_with(watched: &[String], now: i64, status: &dyn Fn(&str) -> Health) -> Value {
    let mut seen = HashSet::new();
    let services: Vec<Value> = watched
        .iter()
        .filter(|name| name.len() <= MAX_STATE_NAME && remediation_actions::is_valid_service_name(name))
        .filter(|name| seen.insert(name.to_ascii_lowercase()))
        .map(|name| json!({"name": name, "state": state_from_health(&status(name))}))
        .collect();
    json!({"v": 1, "at": now, "services": services})
}

/// The report for this host. Windows and Linux ask the service manager (at most once a minute
/// for the same list, like the failure report); another platform lists nothing.
pub fn state_report(os: Option<Os>, watched: &[String], now: i64) -> Value {
    let Some(os) = os else { return state_report_with(&[], now, &|_| Health::Unknown) };
    static CACHE: OnceLock<Mutex<Option<(i64, Vec<String>, Value)>>> = OnceLock::new();
    let mut cache = CACHE.get_or_init(|| Mutex::new(None)).lock().unwrap_or_else(|e| e.into_inner());
    if let Some((at, list, value)) = cache.as_ref() {
        if list == watched && (0..REPORT_CACHE_SECONDS).contains(&(now - at)) {
            return value.clone();
        }
    }
    let value = state_report_with(watched, now, &|name| status_of(os, name));
    *cache = Some((now, watched.to_vec(), value.clone()));
    value
}

// ── restart ───────────────────────────────────────────────────────────────

/// Restart `name` and wait for it to run. `pause` waits one second between checks; production
/// sleeps, tests do nothing. Never panics: every failure is a result body.
pub fn restart(os: Os, name: &str, pause: &dyn Fn()) -> Value {
    if let Err(why) = remediation_actions::validate_service_name(name) {
        return refused(&why.to_string());
    }
    let started = match os {
        Os::Linux => privileged::run("systemctl", &["restart", name]),
        Os::Windows => stop_then_start(name, pause),
    };
    if let Err(e) = started {
        return failed(e);
    }
    for waited in 1..=RESTART_POLLS {
        pause();
        if status_of(os, name) == Health::Running {
            return json!({
                "status": "success", "outcome": "restarted",
                "verify": {"ok": true, "check": "service_running"}, "healthy_after": waited,
            });
        }
    }
    json!({"status": "success", "outcome": "not_running", "verify": {"ok": false, "check": "service_running"}})
}

/// `sc` has no restart. A service that already stopped answers the stop with an error, and what
/// matters is that the start works; only a security product stopping `sc` ends it here.
fn stop_then_start(name: &str, pause: &dyn Fn()) -> Result<(), RemediationError> {
    if let Err(e @ RemediationError::BlockedByLocalSecurity(_)) = privileged::run("sc", &["stop", name]) {
        return Err(e);
    }
    for _ in 0..RESTART_POLLS {
        if status_of(Os::Windows, name) != Health::Pending {
            break;
        }
        pause();
    }
    privileged::run("sc", &["start", name])
}

/// `name` is on the watched list, without regard to case or a `.service` suffix.
pub(crate) fn is_watched(watched: &[String], name: &str) -> bool {
    let bare = |n: &str| {
        let lower = n.to_ascii_lowercase();
        lower.strip_suffix(".service").map(str::to_string).unwrap_or(lower)
    };
    watched.iter().any(|w| bare(w) == bare(name))
}

/// The `restart_service` instruction: check the input, answer `accepted`, and restart off the
/// poll loop (the wait would delay heartbeats). The final body is posted with the same task id.
pub(crate) fn restart_arm(item: &Value, cfg: &Config, client: &reqwest::Client) -> Value {
    let Some(os) = Os::current() else {
        return refused("This platform does not support restarting a service.");
    };
    let Some(task_id) = item.get("task_id").and_then(Value::as_str).filter(|id| valid_id(id)).map(str::to_string) else {
        return refused("The instruction id is missing or not valid.");
    };
    let Some(name) = item.get("parameters").and_then(|p| p.get("service_name")).and_then(Value::as_str).map(str::to_string) else {
        return refused("service_name is required.");
    };
    if let Err(why) = remediation_actions::validate_service_name(&name) {
        return refused(&why.to_string());
    }
    // Only a service the tenant lists is touched, whatever the platform sends (WR-21).
    if !is_watched(cfg.watched_services.as_deref().unwrap_or(&[]), &name) {
        return refused("The service is not on this computer's list of watched services.");
    }
    let work = move || restart(os, &name, &|| std::thread::sleep(std::time::Duration::from_secs(1)));
    in_background(&task_id, "restart_service", cfg, client, blocking("restart", work))
}

#[cfg(test)]
#[path = "service_watch_tests.rs"]
mod tests;
