//! The agent against the shared contract (`shared/agent-response-contract.json`).
//!
//! The backend tests replay the contract's example bodies through the result route; these tests
//! make the real agent dispatch produce them, key for key. If either side changes a token, a
//! limit, an outcome or a body, one of the two suites fails. The file is read at run time; when
//! the agent is built outside the platform repository the tests return early, as the capability
//! catalogue test does.

use crate::capabilities::firewall::Os;
use crate::capabilities::privileged::with_recorder;
use crate::capabilities::response_actions::{
    handle_at, support_report, support_report_for, BLOCK_TTL_DEFAULT, BLOCK_TTL_MAX, BLOCK_TTL_MIN,
    SUPPORTED_TOKENS,
};
use crate::capabilities::quarantine_paths::use_temp_paths;
use crate::capabilities::response_state::{use_temp_store, Store};
use crate::config::Config;
use serde_json::{json, Value};

const T0: i64 = 1_761_900_000;

pub(crate) fn test_cfg() -> Config {
    serde_norway::from_str(
        "api_base_url: http://127.0.0.1:1\n\
         tenant_id: tenant_test\n\
         agent_id: agent_test\n\
         agent_token: tok_test\n\
         registration_key: reg_test\n",
    )
    .expect("parse test config")
}

fn contract() -> Option<Value> {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../shared/agent-response-contract.json");
    let text = std::fs::read_to_string(path).ok()?;
    Some(serde_json::from_str(&text).expect("the contract file is valid JSON"))
}

fn block(id: &str, ip: &str) -> Value {
    json!({"task_id": id, "parameters": {"ip_address": ip, "ttl_seconds": 86400}})
}

fn store() -> (tempfile::TempDir, Store) {
    let dir = tempfile::tempdir().unwrap();
    let store = Store::at(dir.path().join("response_state.json"));
    (dir, store)
}

fn run(action: &str, item: &Value, store: &Store, now: i64) -> Value {
    handle_at(action, item, &test_cfg(), Some(Os::Linux), store, now)
}

#[test]
fn the_shared_limits_and_tokens_match_the_agent() {
    let Some(c) = contract() else { return };
    assert_eq!(c["blockTtlSeconds"]["min"], BLOCK_TTL_MIN);
    assert_eq!(c["blockTtlSeconds"]["max"], BLOCK_TTL_MAX);
    assert_eq!(c["blockTtlSeconds"]["default"], BLOCK_TTL_DEFAULT);
    let tokens: Vec<&str> = c["tokens"].as_array().unwrap().iter().filter_map(Value::as_str).collect();
    for token in SUPPORTED_TOKENS {
        assert!(tokens.contains(token), "{token} is not in the contract's token list");
    }
    // The commands this build answers need the token the contract names for them.
    assert_eq!(c["commandToken"]["block_ip"], "block_ip_ttl");
    assert_eq!(c["commandToken"]["unblock_ip"], "block_ip_ttl");
    assert!(SUPPORTED_TOKENS.contains(&"block_ip_ttl"));
}

#[tokio::test]
async fn the_real_dispatch_answers_a_block_with_the_contract_example() {
    let Some(c) = contract() else { return };
    let _dir = use_temp_store();
    let client = reqwest::Client::new();
    let item = block("task-1", "45.33.32.156");
    let body = crate::instructions::compute_instruction_result("block_ip", "block_ip", &item, &test_cfg(), &client)
        .await
        .expect("block_ip answers");
    assert_eq!(body, c["examples"]["block_applied"]);
}

#[test]
fn block_applied_and_already_applied_equal_the_examples() {
    let Some(c) = contract() else { return };
    let (_d, store) = store();
    let item = block("task-1", "45.33.32.156");
    assert_eq!(run("block_ip", &item, &store, T0), c["examples"]["block_applied"]);
    assert_eq!(run("block_ip", &item, &store, T0), c["examples"]["block_already_applied"]);
}

#[test]
fn a_failed_check_equals_the_verify_failed_example() {
    let Some(c) = contract() else { return };
    let (_d, store) = store();
    with_recorder(|r| {
        for _ in 0..5 {
            r.answer_next(""); // the apply finds every rule already there
        }
        r.fail_next(1); // the check afterwards cannot find the rule
    });
    assert_eq!(run("block_ip", &block("task-1", "45.33.32.156"), &store, T0), c["examples"]["block_verify_failed"]);
}

#[test]
fn unblock_equals_the_removed_example() {
    let Some(c) = contract() else { return };
    let (_d, store) = store();
    run("block_ip", &block("task-1", "45.33.32.156"), &store, T0);
    with_recorder(|r| {
        for _ in 0..6 {
            r.answer_next(""); // three rule checks, each followed by its delete
        }
        r.fail_next(1); // afterwards the rule is gone
    });
    let undo = json!({"parameters": {"ip_address": "45.33.32.156", "block_id": "task-1"}});
    assert_eq!(run("unblock_ip", &undo, &store, T0 + 5), c["examples"]["unblock_removed"]);
}

#[test]
fn every_outcome_and_check_the_agent_produces_is_in_the_contract() {
    let Some(c) = contract() else { return };
    let outcomes: Vec<&str> = c["outcomes"].as_array().unwrap().iter().filter_map(Value::as_str).collect();
    let checks: Vec<&str> = c["checks"].as_array().unwrap().iter().filter_map(Value::as_str).collect();
    let (_d, store) = store();
    let bodies = vec![
        run("block_ip", &block("task-1", "45.33.32.156"), &store, T0),
        run("block_ip", &block("task-1", "45.33.32.156"), &store, T0),
        run("block_ip", &block("task-2", "not-an-ip"), &store, T0),
        run("unblock_ip", &json!({"parameters": {"ip_address": "45.33.32.156", "block_id": "task-1"}}), &store, T0),
        run("unblock_ip", &json!({"parameters": {"ip_address": "45.33.32.156"}}), &store, T0),
    ];
    for body in bodies {
        if let Some(outcome) = body.get("outcome").and_then(Value::as_str) {
            assert!(outcomes.contains(&outcome), "{outcome} is not in the contract");
        }
        if let Some(check) = body.get("verify").and_then(|v| v.get("check")).and_then(Value::as_str) {
            assert!(checks.contains(&check), "{check} is not in the contract");
        }
    }
}

#[test]
fn a_changed_example_body_is_noticed() {
    // The comparison is key for key: a body with one key missing is not equal.
    let Some(c) = contract() else { return };
    let mut broken = c["examples"]["block_applied"].clone();
    broken.as_object_mut().unwrap().remove("expires_in");
    let (_d, store) = store();
    assert_ne!(run("block_ip", &block("task-1", "45.33.32.156"), &store, T0), broken);
}

#[test]
fn support_names_the_platform_and_holds_the_ttl_token() {
    let report = support_report_for(Some(Os::Windows));
    assert_eq!(report["platform"], "windows");
    assert_eq!(report["tokens"], json!(["block_ip_ttl", "block_ip_range", "quarantine_file", "unquarantine_file", "kill_process_exe"]));
    assert_eq!(report["v"], 1);
    assert_eq!(support_report_for(Some(Os::Linux))["tokens"], json!(["block_ip_ttl", "block_ip_range", "quarantine_file", "unquarantine_file", "kill_process_exe"]));
}

#[test]
fn any_other_platform_reports_no_tokens() {
    let report = support_report_for(None);
    assert_eq!(report["tokens"], json!([]));
    assert!(report["platform"].is_string());
}

#[test]
fn the_running_platform_report_matches_the_build() {
    let report = support_report();
    #[cfg(target_os = "linux")]
    assert_eq!(report["platform"], "linux");
    assert!(report["tokens"].is_array());
}

#[test]
fn every_heartbeat_carries_the_support_report() {
    let mut cfg = test_cfg();
    cfg.enabled_capabilities = Some(Vec::new()); // no collector runs in this test
    let sys = sysinfo::System::new();
    let payload = crate::heartbeat::build_payload(&cfg, &sys, &crate::capabilities::CapabilityManager::new());
    assert_eq!(payload["meta"]["response_actions"], support_report());
    assert!(payload["meta"]["response_actions"]["tokens"].is_array());
}

#[tokio::test]
async fn the_real_dispatch_answers_a_quarantine_with_the_contract_example() {
    let Some(c) = contract() else { return };
    let _dir = use_temp_paths();
    let work = tempfile::tempdir().unwrap();
    let file = work.path().join("evil.bin");
    std::fs::write(&file, b"bytes").unwrap();
    let sha = hex::encode(<sha2::Sha256 as sha2::Digest>::digest(b"bytes"));
    let item = json!({"task_id": "task-1", "parameters": {"path": file.to_string_lossy(), "sha256": sha}});
    let client = reqwest::Client::new();
    let body = crate::instructions::compute_instruction_result("quarantine_file", "quarantine_file", &item, &test_cfg(), &client)
        .await
        .expect("quarantine_file answers");
    assert_eq!(body, c["examples"]["quarantine_moved"]);
    let undo = json!({"parameters": {"quarantine_id": "task-1"}});
    let restored = crate::instructions::compute_instruction_result("unquarantine_file", "unquarantine_file", &undo, &test_cfg(), &client)
        .await
        .expect("unquarantine_file answers");
    assert_eq!(restored["outcome"], "restored");
    assert_eq!(restored["verify"]["check"], "restored_to_path");
}

#[test]
fn the_kill_and_quarantine_outcomes_and_checks_are_all_in_the_contract() {
    use crate::capabilities::process_kill::{kill_body, KillPlan};
    use crate::capabilities::quarantine::RunningProcess;
    let Some(c) = contract() else { return };
    let outcomes: Vec<&str> = c["outcomes"].as_array().unwrap().iter().filter_map(Value::as_str).collect();
    let checks: Vec<&str> = c["checks"].as_array().unwrap().iter().filter_map(Value::as_str).collect();
    let p = RunningProcess { pid: 4242, name: "evil.exe".into(), start_time: 1_761_900_000, exe: None };
    let bodies = [
        kill_body(&KillPlan::default(), &[]),
        kill_body(&KillPlan { kill: vec![p.clone()], unconfirmed: vec![] }, &[]),
        kill_body(&KillPlan { kill: vec![p.clone()], unconfirmed: vec![] }, &[p.clone()]),
        kill_body(&KillPlan { kill: vec![], unconfirmed: vec![p] }, &[]),
    ];
    for body in bodies {
        assert!(outcomes.contains(&body["outcome"].as_str().unwrap()));
        assert!(checks.contains(&body["verify"]["check"].as_str().unwrap()));
    }
    for token in ["quarantine_file", "unquarantine_file", "kill_process_exe"] {
        assert!(SUPPORTED_TOKENS.contains(&token));
    }
    assert_eq!(c["commandToken"]["kill_process"], "kill_process_exe");
    assert_eq!(c["commandToken"]["quarantine_file"], "quarantine_file");
    assert_eq!(c["commandToken"]["unquarantine_file"], "unquarantine_file");
}
