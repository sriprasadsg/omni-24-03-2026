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
pub mod ssh_key_checks;
pub mod ssh_key_rotation;
pub mod patch_installer;
#[cfg(target_os = "linux")]
pub mod fanotify_watcher;

#[cfg(target_os = "linux")]
pub mod process_mapper;

use serde_json::{json, Value};
use std::collections::HashMap;
use sysinfo::System;

pub trait Capability: Send + Sync {
    fn id(&self) -> &'static str;
    fn name(&self) -> &'static str;
    fn collect(&self, sys: &System) -> Value;
}

pub struct CapabilityManager {
    caps: Vec<Box<dyn Capability>>,
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

    pub fn statuses(&self, results: &HashMap<String, Value>, enabled: Option<&[String]>) -> Vec<Value> {
        self.caps
            .iter()
            .map(|cap| {
                if !is_enabled(enabled, cap.id()) {
                    return json!({"id": cap.id(), "name": cap.name(), "enabled": false, "status": "disabled"});
                }
                let has_error = results
                    .get(cap.id())
                    .and_then(|v| v.get("error"))
                    .is_some();
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
