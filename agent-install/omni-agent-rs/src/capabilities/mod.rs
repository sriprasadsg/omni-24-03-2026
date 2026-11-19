pub mod feed_bundle;
pub mod security_scan;
pub mod agent_update;
pub mod compliance;
pub mod ebpf_tracing;
pub mod fim;
pub mod fim_baseline;
pub mod logs;
pub mod metrics;
pub mod network_discovery;
pub mod persistence_detection;
pub mod pii_scanner;
pub mod predictive_health;
pub mod process_monitor;
pub mod remote_access;
pub mod control_input;
pub mod screen_capture;
pub mod runtime_security;
pub mod sbom;
pub mod software_management;
pub mod system_patching;
pub mod ueba;
pub mod vulnerability_scan;
pub mod remediation_actions;
pub mod privileged;
pub mod response_state;
pub mod firewall;
pub mod net_safety;
pub mod response_actions;
pub mod response_sweeper;
pub mod isolation;
pub mod isolation_plan;
pub mod service_watch;
pub mod host_power;
pub mod quarantine;
pub mod quarantine_paths;
pub mod process_kill;
#[cfg(test)]
mod response_contract_tests;
pub mod ssh_key_checks;
pub mod ssh_key_rotation;
pub mod patch_installer;
pub mod patch_reversible;
pub mod patch_state;
#[cfg(target_os = "linux")]
pub mod fanotify_watcher;
#[cfg(any(target_os = "macos", test))]
pub mod macos;

#[cfg(target_os = "linux")]
pub mod process_mapper;

use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use sysinfo::System;

/// How often each periodic collector runs (seconds) until the platform sends its own intervals.
/// Mirrors `defaultIntervalSeconds` in shared/agent-capabilities.json (a test keeps them equal);
/// a collector not listed runs with every heartbeat.
pub const DEFAULT_INTERVALS: &[(&str, u64)] = &[
    ("metrics_collection", 60),
    ("log_collection", 300),
    ("process_monitor", 300),
    ("vulnerability_scanning", 3600),
    ("fim", 600),
    ("compliance_enforcement", 3600),
    ("runtime_security", 180),
    ("persistence_detection", 3600),
    ("network_discovery", 7200),
    ("pii_scanner", 3600),
    ("sbom_analysis", 3600),
    ("predictive_health", 600),
    ("ueba", 300),
    ("ebpf_tracing", 60),
    ("system_patching", 3600),
    ("software_management", 3600),
];

/// Heartbeats are not exactly `interval_seconds` apart; a collector this close to due runs now
/// rather than one beat late.
const DUE_SLACK: Duration = Duration::from_secs(5);

/// The interval for collector `id`: the platform's when it sent one, else the built-in default,
/// else zero (every heartbeat).
pub fn interval_for(intervals: Option<&BTreeMap<String, u64>>, id: &str) -> Duration {
    let seconds = intervals
        .and_then(|m| m.get(id).copied())
        .or_else(|| DEFAULT_INTERVALS.iter().find(|(cap, _)| *cap == id).map(|(_, s)| *s))
        .unwrap_or(0);
    Duration::from_secs(seconds)
}

pub trait Capability: Send + Sync {
    fn id(&self) -> &'static str;
    fn name(&self) -> &'static str;
    fn collect(&self, sys: &System) -> Value;
}

pub struct CapabilityManager {
    caps: Vec<Box<dyn Capability>>,
    /// When each collector last ran and whether that run reported an error.
    last_run: Mutex<HashMap<&'static str, (Instant, bool)>>,
}

impl CapabilityManager {
    pub fn new() -> Self {
        CapabilityManager {
            caps: vec![
                Box::new(metrics::MetricsCapability),
                Box::new(process_monitor::ProcessMonitorCapability),
                Box::new(persistence_detection::PersistenceDetectionCapability),
                Box::new(pii_scanner::PiiScannerCapability),
                Box::new(logs::LogsCapability),
                Box::new(fim::FimCapability),
                Box::new(vulnerability_scan::VulnScanCapability),
                Box::new(compliance::ComplianceCapability),
                Box::new(runtime_security::RuntimeSecurityCapability::new()),
                Box::new(predictive_health::PredictiveHealthCapability::new()),
                Box::new(ueba::UebaCapability),
                Box::new(sbom::SbomCapability),
                Box::new(ebpf_tracing::EbpfTracingCapability),
                Box::new(system_patching::SystemPatchingCapability),
                Box::new(software_management::SoftwareManagementCapability),
                Box::new(remote_access::RemoteAccessCapability),
                Box::new(network_discovery::NetworkDiscoveryCapability),
                Box::new(agent_update::AgentUpdateCapability),
            ],
            last_run: Mutex::new(HashMap::new()),
        }
    }

    pub fn ids(&self) -> Vec<&'static str> {
        let mut ids: Vec<&'static str> = self.caps.iter().map(|c| c.id()).collect();
        // Instruction-only capabilities (handled in instructions.rs, no heartbeat
        // collector) — advertised so the portal enables agent chat and ticketing.
        ids.push("chat_window");
        ids.push("ticket_reporter");
        ids
    }

    /// Runs every collector the platform allows (`enabled`, see [`is_enabled`]); a collector it
    /// does not allow does not run at all.
    pub fn collect_all(&self, sys: &System, enabled: Option<&[String]>) -> HashMap<String, Value> {
        let mut results = HashMap::new();
        for cap in self.caps.iter().filter(|cap| is_enabled(enabled, cap.id())) {
            let data = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| cap.collect(sys)))
                .unwrap_or_else(|_| json!({"error": "capability panicked"}));
            results.insert(cap.id().to_string(), data);
        }
        results
    }

    /// Runs the collectors the platform allows (`enabled`) whose interval has passed since they
    /// last ran; one that never ran is due. A collector skipped this beat sends nothing, and the
    /// platform keeps its last data.
    pub fn collect_due(
        &self,
        sys: &System,
        enabled: Option<&[String]>,
        intervals: Option<&BTreeMap<String, u64>>,
    ) -> HashMap<String, Value> {
        self.collect_due_at(sys, enabled, intervals, Instant::now())
    }

    fn collect_due_at(
        &self,
        sys: &System,
        enabled: Option<&[String]>,
        intervals: Option<&BTreeMap<String, u64>>,
        now: Instant,
    ) -> HashMap<String, Value> {
        let mut last = self.last_run.lock().unwrap_or_else(|e| e.into_inner());
        let mut results = HashMap::new();
        for cap in self.caps.iter().filter(|cap| is_enabled(enabled, cap.id())) {
            let every = interval_for(intervals, cap.id());
            if let Some((at, _)) = last.get(cap.id()) {
                if now.saturating_duration_since(*at) + DUE_SLACK < every {
                    continue;
                }
            }
            let data = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| cap.collect(sys)))
                .unwrap_or_else(|_| json!({"error": "capability panicked"}));
            last.insert(cap.id(), (now, data.get("error").is_some()));
            results.insert(cap.id().to_string(), data);
        }
        results
    }

    pub fn statuses(&self, results: &HashMap<String, Value>, enabled: Option<&[String]>) -> Vec<Value> {
        let last = self.last_run.lock().unwrap_or_else(|e| e.into_inner());
        self.caps
            .iter()
            .map(|cap| {
                if !is_enabled(enabled, cap.id()) {
                    return json!({"id": cap.id(), "name": cap.name(), "enabled": false, "status": "disabled"});
                }
                // A collector not due this beat reports how its last run went.
                let has_error = match results.get(cap.id()) {
                    Some(data) => data.get("error").is_some(),
                    None => last.get(cap.id()).is_some_and(|(_, failed)| *failed),
                };
                json!({
                    "id": cap.id(),
                    "name": cap.name(),
                    "enabled": true,
                    "status": if has_error { "error" } else { "success" },
                })
            })
            .collect()
    }
}

/// Whether the platform lets this agent use capability `id`. `enabled` is the tenant's selection
/// from the last heartbeat reply (`Config::enabled_capabilities`); `None` (an older platform, or
/// none received yet) allows everything.
pub fn is_enabled(enabled: Option<&[String]>, id: &str) -> bool {
    enabled.map_or(true, |list| list.iter().any(|c| c == id))
}

/// Stores the capability selection a heartbeat reply carries (`enabledCapabilities`) and persists
/// it, so the agent keeps honouring it across restarts. A reply without the list changes nothing.
pub fn update_enabled_from_heartbeat(cfg: &mut crate::config::Config, body: &Value) {
    if let Some(list) = changed_selection(cfg.enabled_capabilities.as_deref(), body) {
        log::info!("Platform capability selection updated: {}", list.join(", "));
        cfg.enabled_capabilities = Some(list);
        if let Err(e) = crate::config::save(cfg) {
            log::warn!("Could not persist the capability selection to config.yaml: {e}");
        }
    }
}

/// Adopts the collection intervals a heartbeat reply carries, persisting them when they change.
pub fn update_intervals_from_heartbeat(cfg: &mut crate::config::Config, body: &Value) {
    if let Some(intervals) = changed_intervals(cfg.collection_intervals.as_ref(), body) {
        log::info!("Platform collection intervals updated ({} collectors)", intervals.len());
        cfg.collection_intervals = Some(intervals);
        if let Err(e) = crate::config::save(cfg) {
            log::warn!("Could not persist the collection intervals to config.yaml: {e}");
        }
    }
}

/// The intervals a heartbeat reply carries when they differ from `current`; `None` when the reply
/// has no (well-formed) map or it is unchanged.
pub fn changed_intervals(current: Option<&BTreeMap<String, u64>>, body: &Value) -> Option<BTreeMap<String, u64>> {
    let intervals = serde_json::from_value::<BTreeMap<String, u64>>(body.get("collectionIntervals")?.clone()).ok()?;
    (current != Some(&intervals)).then_some(intervals)
}

/// The selection a heartbeat reply carries when it differs from `current`; `None` when the reply
/// has no (well-formed) list or the list is unchanged.
pub fn changed_selection(current: Option<&[String]>, body: &Value) -> Option<Vec<String>> {
    let list = serde_json::from_value::<Vec<String>>(body.get("enabledCapabilities")?.clone()).ok()?;
    (current != Some(list.as_slice())).then_some(list)
}

#[cfg(test)]
mod selection_tests {
    use super::*;

    fn ids(list: &[&str]) -> Vec<String> {
        list.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn a_collector_the_platform_switched_off_does_not_run() {
        let mgr = CapabilityManager::new();
        let enabled = ids(&["metrics_collection", "agent_update"]);
        let results = mgr.collect_all(&System::new(), Some(&enabled));
        let mut ran: Vec<&str> = results.keys().map(|k| k.as_str()).collect();
        ran.sort();
        assert_eq!(ran, vec!["agent_update", "metrics_collection"]);
        let statuses = mgr.statuses(&results, Some(&enabled));
        let pii = statuses.iter().find(|s| s["id"] == "pii_scanner").unwrap();
        assert_eq!((pii["enabled"].as_bool(), pii["status"].as_str()), (Some(false), Some("disabled")));
    }

    #[test]
    fn no_selection_yet_allows_everything() {
        assert!(is_enabled(None, "pii_scanner"));
        assert!(!is_enabled(Some(&ids(&["fim"])), "pii_scanner"));
    }

    #[test]
    fn only_a_new_well_formed_selection_is_taken() {
        let current = ids(&["fim"]);
        assert_eq!(changed_selection(Some(&current), &json!({"enabledCapabilities": ["fim", "ueba"]})),
                   Some(ids(&["fim", "ueba"])));
        assert_eq!(changed_selection(Some(&current), &json!({"enabledCapabilities": ["fim"]})), None);
        assert_eq!(changed_selection(Some(&current), &json!({"success": true})), None);
        assert_eq!(changed_selection(None, &json!({"enabledCapabilities": "fim"})), None);
        assert_eq!(changed_selection(None, &json!({"enabledCapabilities": []})), Some(vec![]));
    }
}

#[cfg(test)]
mod interval_tests {
    use super::*;

    fn metrics_only() -> Vec<String> {
        vec!["metrics_collection".to_string()]
    }

    #[test]
    fn a_collector_runs_again_only_once_its_interval_has_passed() {
        let mgr = CapabilityManager::new();
        let enabled = metrics_only();
        let intervals = BTreeMap::from([("metrics_collection".to_string(), 60)]);
        let sys = System::new();
        let t0 = Instant::now();
        assert!(mgr.collect_due_at(&sys, Some(&enabled), Some(&intervals), t0).contains_key("metrics_collection"));
        let early = mgr.collect_due_at(&sys, Some(&enabled), Some(&intervals), t0 + Duration::from_secs(30));
        assert!(early.is_empty());
        // Not yet 60 s, but within DUE_SLACK of it: runs now instead of a beat late.
        let due = mgr.collect_due_at(&sys, Some(&enabled), Some(&intervals), t0 + Duration::from_secs(57));
        assert!(due.contains_key("metrics_collection"));
    }

    #[test]
    fn a_skipped_collector_reports_its_last_status() {
        let mgr = CapabilityManager::new();
        let enabled = metrics_only();
        let sys = System::new();
        let t0 = Instant::now();
        mgr.collect_due_at(&sys, Some(&enabled), None, t0);
        let skipped = mgr.collect_due_at(&sys, Some(&enabled), None, t0 + Duration::from_secs(1));
        assert!(skipped.is_empty());
        let statuses = mgr.statuses(&skipped, Some(&enabled));
        let metrics = statuses.iter().find(|s| s["id"] == "metrics_collection").unwrap();
        assert_eq!(metrics["status"], "success");
    }

    #[test]
    fn platform_intervals_win_then_defaults_then_every_beat() {
        let platform = BTreeMap::from([("process_monitor".to_string(), 120)]);
        assert_eq!(interval_for(Some(&platform), "process_monitor"), Duration::from_secs(120));
        assert_eq!(interval_for(Some(&platform), "persistence_detection"), Duration::from_secs(3600));
        assert_eq!(interval_for(None, "process_monitor"), Duration::from_secs(300));
        assert_eq!(interval_for(None, "agent_update"), Duration::ZERO);
    }

    #[test]
    fn only_new_well_formed_intervals_are_taken() {
        let current = BTreeMap::from([("fim".to_string(), 600)]);
        assert_eq!(changed_intervals(Some(&current), &json!({"collectionIntervals": {"fim": 900}})),
                   Some(BTreeMap::from([("fim".to_string(), 900)])));
        assert_eq!(changed_intervals(Some(&current), &json!({"collectionIntervals": {"fim": 600}})), None);
        assert_eq!(changed_intervals(None, &json!({"collectionIntervals": {"fim": "soon"}})), None);
        assert_eq!(changed_intervals(None, &json!({"success": true})), None);
    }

    #[test]
    fn defaults_match_the_shared_catalogue() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../shared/agent-capabilities.json");
        let Ok(text) = std::fs::read_to_string(&path) else {
            return; // building outside the platform repository
        };
        let catalogue: Value = serde_json::from_str(&text).unwrap();
        let mut shared = BTreeMap::new();
        for group in catalogue["groups"].as_array().unwrap() {
            for cap in group["capabilities"].as_array().unwrap() {
                if let Some(secs) = cap["defaultIntervalSeconds"].as_u64() {
                    shared.insert(cap["id"].as_str().unwrap().to_string(), secs);
                }
            }
        }
        for (id, secs) in DEFAULT_INTERVALS {
            assert_eq!(shared.get(*id), Some(secs), "{id} differs from shared/agent-capabilities.json");
        }
        let collectors: Vec<&str> = CapabilityManager::new().caps.iter().map(|c| c.id()).collect();
        for id in shared.keys().filter(|id| collectors.contains(&id.as_str())) {
            assert!(DEFAULT_INTERVALS.iter().any(|(cap, _)| cap == id), "{id} has no default in the agent");
        }
    }
}
