/// Integration tests for the omni-agent Windows agent.
/// Run with: cargo test -- --test-output immediate
use omni_agent::capabilities::CapabilityManager;
use omni_agent::config::Config;
use sysinfo::System;

// ─── helpers ───────────────────────────────────────────────────────────────

fn base_config_yaml() -> &'static str {
    "api_base_url: http://192.168.1.1:5000\n\
     tenant_id: tenant_test\n\
     agent_id: ''\n\
     agent_token: ''\n\
     registration_key: reg_test123\n\
     interval_seconds: 30\n\
     max_cpu_percent: 20\n\
     agentic_mode_enabled: false\n"
}

fn parse_cfg(yaml: &str) -> Config {
    serde_yaml::from_str(yaml).expect("parse config")
}

// ─── config tests ──────────────────────────────────────────────────────────

#[test]
fn test_config_loads_null_fields_as_empty_string() {
    let yaml = "api_base_url: http://localhost:5000\n\
                agent_id: null\n\
                agent_token: null\n\
                registration_key: reg_abc\n";
    let cfg = parse_cfg(yaml);
    assert!(cfg.agent_id.is_empty(), "null agent_id should be empty string");
    assert!(cfg.agent_token.is_empty(), "null agent_token should be empty string");
    assert_eq!(cfg.registration_key, "reg_abc");
}

#[test]
fn test_config_defaults_applied_when_keys_missing() {
    let yaml = "api_base_url: http://localhost:5000\n";
    let cfg = parse_cfg(yaml);
    assert_eq!(cfg.interval_seconds, 30);
    assert_eq!(cfg.max_cpu_percent, 20.0);
    assert!(!cfg.agentic_mode_enabled);
    assert!(cfg.agent_id.is_empty());
    assert!(cfg.agent_token.is_empty());
}

#[test]
fn test_config_save_roundtrip() {
    let mut cfg = parse_cfg(base_config_yaml());
    cfg.agent_id = "agent-test-123".to_string();
    cfg.agent_token = "tok_abc".to_string();

    let path = std::env::temp_dir().join("omni_agent_test_config.yaml");
    let serialized = serde_yaml::to_string(&cfg).unwrap();
    std::fs::write(&path, &serialized).unwrap();

    let loaded: Config =
        serde_yaml::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    let _ = std::fs::remove_file(&path);

    assert_eq!(loaded.agent_id, "agent-test-123");
    assert_eq!(loaded.agent_token, "tok_abc");
    assert_eq!(loaded.registration_key, "reg_test123");
    assert_eq!(loaded.api_base_url, "http://192.168.1.1:5000");
}

#[test]
fn test_config_registered_means_token_nonempty() {
    let cfg = parse_cfg(base_config_yaml());
    assert!(cfg.agent_token.is_empty());
    assert!(!cfg.registration_key.is_empty());
}

// ─── capability manager tests ─────────────────────────────────────────────

#[test]
fn test_capability_manager_has_15_capabilities() {
    let mgr = CapabilityManager::new();
    assert_eq!(mgr.ids().len(), 15, "expected 15 capabilities");
}

#[test]
fn test_capability_ids_match_expected_set() {
    let mgr = CapabilityManager::new();
    let ids = mgr.ids();
    let expected = [
        "metrics_collection", "log_collection", "fim",
        "vulnerability_scanning", "compliance_enforcement",
        "runtime_security", "predictive_health", "ueba",
        "sbom_analysis", "ebpf_tracing", "system_patching",
        "software_management", "remote_access", "network_discovery",
        "agent_update",
    ];
    for id in &expected {
        assert!(ids.contains(id), "missing capability: {}", id);
    }
}

#[test]
fn test_collect_all_no_panics() {
    let mgr = CapabilityManager::new();
    let results = mgr.collect_all();
    assert_eq!(results.len(), 15);
    for (id, val) in &results {
        assert!(val.is_object(), "capability '{}' returned non-object: {}", id, val);
    }
}

#[test]
fn test_capability_statuses_structure() {
    let mgr = CapabilityManager::new();
    let results = mgr.collect_all();
    let statuses = mgr.statuses(&results);
    assert_eq!(statuses.len(), 15);
    for s in &statuses {
        assert!(s.get("id").is_some());
        assert!(s.get("name").is_some());
        assert!(s.get("enabled").is_some());
        let status = s["status"].as_str().unwrap();
        assert!(
            status == "success" || status == "error",
            "unexpected status: {}",
            status
        );
    }
}

// ─── individual capability schema tests ───────────────────────────────────

#[test]
fn test_metrics_capability_schema() {
    use omni_agent::capabilities::metrics::MetricsCapability;
    use omni_agent::capabilities::Capability;
    let v = MetricsCapability.collect();
    // metrics uses nested structure: cpu.percent, memory.percent, etc.
    assert!(v.get("cpu").is_some(),           "missing cpu object");
    assert!(v["cpu"].get("percent").is_some(), "missing cpu.percent");
    assert!(v.get("memory").is_some(),         "missing memory object");
    assert!(v["memory"].get("percent").is_some(), "missing memory.percent");
    assert!(v.get("disks").is_some(),          "missing disks");
    assert!(v.get("process_count").is_some(),  "missing process_count");
}

#[test]
fn test_agent_update_collect_is_passive() {
    use omni_agent::capabilities::agent_update::AgentUpdateCapability;
    use omni_agent::capabilities::Capability;
    let v = AgentUpdateCapability.collect();
    assert_eq!(v["status"], "ready", "agent_update collect must be passive, not make HTTP calls");
    assert!(v.get("current_version").is_some());
    assert!(v.get("error").is_none(), "agent_update collect panicked or made a network call");
}

#[test]
fn test_sbom_collect_schema() {
    use omni_agent::capabilities::sbom::SbomCapability;
    use omni_agent::capabilities::Capability;
    let v = SbomCapability.collect();
    assert_eq!(v["sbom_version"], "1.0");
    assert_eq!(v["format"], "CycloneDX-Simplified");
    assert!(v.get("total_components").is_some());
    assert!(v.get("sbom_hash").is_some());
    assert!(v.get("component_types").is_some());
    let hash = v["sbom_hash"].as_str().unwrap_or("");
    assert_eq!(hash.len(), 16, "sbom_hash must be 16 hex chars, got: {}", hash);
}

#[test]
fn test_sbom_hash_is_deterministic() {
    use omni_agent::capabilities::sbom::SbomCapability;
    use omni_agent::capabilities::Capability;
    let v1 = SbomCapability.collect();
    let v2 = SbomCapability.collect();
    assert_eq!(v1["sbom_hash"], v2["sbom_hash"], "SBOM hash must be deterministic");
    assert_eq!(v1["total_components"], v2["total_components"]);
}

#[test]
fn test_compliance_collect_schema() {
    use omni_agent::capabilities::compliance::ComplianceCapability;
    use omni_agent::capabilities::Capability;
    let v = ComplianceCapability.collect();
    assert!(v.get("compliance_checks").is_some());
    assert!(v.get("total_checks").is_some());
    assert!(v.get("passed").is_some());
    assert!(v.get("failed").is_some());
    assert!(v.get("compliance_score").is_some());
    let checks = v["compliance_checks"].as_array().unwrap();
    assert!(!checks.is_empty(), "compliance_checks should not be empty");
    for c in checks {
        assert!(c.get("check").is_some());
        let s = c["status"].as_str().unwrap();
        assert!(s == "Pass" || s == "Fail", "status must be Pass or Fail, got: {}", s);
    }
}

#[test]
fn test_predictive_health_schema() {
    use omni_agent::capabilities::predictive_health::PredictiveHealthCapability;
    use omni_agent::capabilities::Capability;
    let v = PredictiveHealthCapability::new().collect();
    for key in &["cpu_trend", "memory_trend", "disk_trend",
                 "current_cpu_percent", "current_memory_percent", "current_disk_percent",
                 "predictions"] {
        assert!(v.get(key).is_some(), "missing field: {}", key);
    }
    let preds = &v["predictions"];
    assert!(preds.get("cpu_exhaustion_hours").is_some());
    assert!(preds.get("memory_exhaustion_hours").is_some());
    assert!(preds.get("disk_exhaustion_hours").is_some());
}

#[test]
fn test_fim_collect_schema() {
    use omni_agent::capabilities::fim::FimCapability;
    use omni_agent::capabilities::Capability;
    let v = FimCapability.collect();
    assert!(v.get("monitored_files").is_some(), "missing monitored_files");
    assert!(v.get("changed_files").is_some(),   "missing changed_files");
    assert!(v.get("files").is_some(),           "missing files array");
    assert!(v.get("timestamp").is_some(),       "missing timestamp");
    assert!(v["files"].is_array(),              "files should be an array");
}

// ─── heartbeat payload tests ──────────────────────────────────────────────

fn make_payload() -> serde_json::Value {
    let cfg = parse_cfg(base_config_yaml());
    let mgr = CapabilityManager::new();
    let mut sys = System::new_all();
    sys.refresh_all();
    omni_agent::heartbeat::build_payload(&cfg, &sys, &mgr)
}

#[test]
fn test_heartbeat_payload_has_flat_metric_keys() {
    let payload = make_payload();
    let meta = &payload["meta"];
    for key in &["current_cpu", "current_memory", "disk_usage",
                 "total_memory_gb", "available_memory_gb",
                 "disk_total_gb", "disk_used_gb", "disk_free_gb"] {
        assert!(meta.get(key).is_some(), "missing meta.{}", key);
    }
}

#[test]
fn test_heartbeat_payload_top_level_fields() {
    let payload = make_payload();
    assert!(payload.get("hostname").is_some());
    assert_eq!(payload["tenantId"], "tenant_test");
    assert_eq!(payload["status"], "Online");
    assert_eq!(payload["platform"], "Windows");
    assert_eq!(payload["version"], "2.0.0");
    assert!(payload.get("ipAddress").is_some());
    assert!(payload.get("meta").is_some());
}

#[test]
fn test_heartbeat_payload_capabilities_present() {
    let payload = make_payload();
    let meta = &payload["meta"];
    let caps = meta["capabilities"].as_array().expect("capabilities should be array");
    assert_eq!(caps.len(), 15, "heartbeat must include all 15 capability IDs");
    assert!(meta.get("capabilities_status").is_some());
}

#[test]
fn test_heartbeat_metric_values_in_range() {
    let payload = make_payload();
    let meta = &payload["meta"];
    let cpu  = meta["current_cpu"].as_f64().unwrap_or(-1.0);
    let mem  = meta["current_memory"].as_f64().unwrap_or(-1.0);
    let disk = meta["disk_usage"].as_f64().unwrap_or(-1.0);
    assert!((0.0..=100.0).contains(&cpu),  "cpu out of range: {}", cpu);
    assert!((0.0..=100.0).contains(&mem),  "memory out of range: {}", mem);
    assert!((0.0..=100.0).contains(&disk), "disk out of range: {}", disk);
    assert!(meta["total_memory_gb"].as_f64().unwrap_or(0.0) > 0.0);
}

// ─── registration guard tests ─────────────────────────────────────────────

#[test]
fn test_registration_skipped_when_token_present() {
    let yaml = "api_base_url: http://localhost:5000\n\
                agent_id: agent-existing\n\
                agent_token: tok_already_set\n\
                registration_key: reg_abc\n";
    let cfg = parse_cfg(yaml);
    assert!(!cfg.agent_token.is_empty(), "token present — no re-registration expected");
}

#[test]
fn test_registration_required_when_no_token() {
    let cfg = parse_cfg(base_config_yaml());
    assert!(cfg.agent_token.is_empty());
    assert!(!cfg.registration_key.is_empty());
}
