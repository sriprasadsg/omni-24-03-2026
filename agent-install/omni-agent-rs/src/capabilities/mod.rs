pub mod agent_update;
pub mod compliance;
pub mod ebpf_tracing;
pub mod fim;
pub mod logs;
pub mod metrics;
pub mod network_discovery;
pub mod predictive_health;
pub mod remote_access;
pub mod runtime_security;
pub mod sbom;
pub mod software_management;
pub mod system_patching;
pub mod ueba;
pub mod vulnerability_scan;

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
        self.caps.iter().map(|c| c.id()).collect()
    }

    pub fn collect_all(&self, sys: &System) -> HashMap<String, Value> {
        let mut results = HashMap::new();
        for cap in &self.caps {
            let data = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| cap.collect(sys)))
                .unwrap_or_else(|_| json!({"error": "capability panicked"}));
            results.insert(cap.id().to_string(), data);
        }
        results
    }

    pub fn statuses(&self, results: &HashMap<String, Value>) -> Vec<Value> {
        self.caps
            .iter()
            .map(|cap| {
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
