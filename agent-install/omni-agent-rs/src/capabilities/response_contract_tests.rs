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
    HANDLED, SUPPORTED_TOKENS,
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
    assert_eq!(report["tokens"], json!(["block_ip_ttl", "block_ip_range", "quarantine_file", "unquarantine_file", "kill_process_exe", "restart_service", "service_failures", "isolate_host", "restore_host", "reboot_host", "patch_reversible_check", "patch_revert_by_job"]));
    assert_eq!(report["v"], 1);
    assert_eq!(support_report_for(Some(Os::Linux))["tokens"], json!(["block_ip_ttl", "block_ip_range", "quarantine_file", "unquarantine_file", "kill_process_exe", "restart_service", "service_failures", "isolate_host", "restore_host", "reboot_host", "patch_reversible_check", "patch_revert_by_job"]));
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
    let item = json!({"task_id": "task-c1", "parameters": {"path": file.to_string_lossy(), "sha256": sha}});
    let client = reqwest::Client::new();
    let body = crate::instructions::compute_instruction_result("quarantine_file", "quarantine_file", &item, &test_cfg(), &client)
        .await
        .expect("quarantine_file answers");
    assert_eq!(body, json!({"status": "accepted"}), "the work runs off the poll loop");
    let body = crate::instructions::final_body("task-c1").await.expect("a final body");
    assert_eq!(body, c["examples"]["quarantine_moved"]);
    let undo = json!({"task_id": "task-c1u", "parameters": {"quarantine_id": "task-c1"}});
    crate::instructions::compute_instruction_result("unquarantine_file", "unquarantine_file", &undo, &test_cfg(), &client)
        .await
        .expect("unquarantine_file answers");
    let restored = crate::instructions::final_body("task-c1u").await.expect("a final body");
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

#[test]
fn the_isolation_tokens_outcomes_checks_and_revert_time_match_the_contract() {
    use crate::capabilities::isolation_plan::REVERT_SECONDS;
    let Some(c) = contract() else { return };
    let list = |key: &str| -> Vec<String> {
        c[key].as_array().unwrap().iter().filter_map(Value::as_str).map(str::to_string).collect()
    };
    let (tokens, outcomes, checks) = (list("tokens"), list("outcomes"), list("checks"));
    for token in ["isolate_host", "restore_host"] {
        assert!(SUPPORTED_TOKENS.contains(&token) && tokens.iter().any(|t| t == token), "{token}");
        assert_eq!(c["commandToken"][token], token);
    }
    assert_eq!(c["isolationRevertSeconds"], REVERT_SECONDS);
    for outcome in ["isolated", "already_applied", "self_test_failed", "not_effective", "restored", "not_found"] {
        assert!(outcomes.iter().any(|o| o == outcome), "{outcome}");
    }
    for check in ["management_connection_open", "network_restored"] {
        assert!(checks.iter().any(|k| k == check), "{check}");
    }
    assert!(crate::capabilities::response_actions::handles("isolate_host"));
    assert!(crate::capabilities::response_actions::handles("restore_host"));
}

#[test]
fn every_heartbeat_carries_the_response_state_report() {
    let mut cfg = test_cfg();
    cfg.enabled_capabilities = Some(Vec::new());
    let sys = sysinfo::System::new();
    let payload = crate::heartbeat::build_payload(&cfg, &sys, &crate::capabilities::CapabilityManager::new());
    let report = &payload["meta"]["response_state"];
    assert_eq!(report["v"], 1);
    assert!(report.get("isolation").is_some() && report["boot_time"].is_u64() && report["active_blocks"].is_u64());
}

fn strings(c: &Value, key: &str) -> Vec<String> {
    let mut list: Vec<String> = c[key].as_array().unwrap().iter().filter_map(Value::as_str).map(str::to_string).collect();
    list.sort();
    list
}

#[test]
fn the_reported_tokens_equal_the_contract_exactly() {
    let Some(c) = contract() else { return };
    let mut ours: Vec<String> = SUPPORTED_TOKENS.iter().map(|t| t.to_string()).collect();
    ours.sort();
    assert_eq!(ours, strings(&c, "tokens"));
}

#[test]
fn the_command_tokens_cover_every_command_the_agent_answers() {
    let Some(c) = contract() else { return };
    let mut commands: Vec<String> = c["commandToken"].as_object().unwrap().keys().cloned().collect();
    commands.sort();
    let mut handled: Vec<String> = HANDLED.iter().map(|h| h.to_string()).collect();
    handled.sort();
    assert_eq!(handled, commands);
    for (command, token) in c["commandToken"].as_object().unwrap() {
        let token = token.as_str().unwrap();
        assert!(SUPPORTED_TOKENS.contains(&token), "{command} needs {token}, which this build does not report");
        assert!(crate::capabilities::response_actions::handles(command), "{command}");
    }
}

#[test]
fn the_reboot_scheduled_example_has_a_real_producer_on_both_systems() {
    use crate::capabilities::host_power::{DELAY_MAX, DELAY_MIN};
    let Some(c) = contract() else { return };
    assert_eq!(c["rebootDelaySeconds"]["min"], DELAY_MIN);
    assert_eq!(c["rebootDelaySeconds"]["max"], DELAY_MAX);
    let item = json!({"task_id": "task-1", "parameters": {"delay_seconds": 60, "reason": "Patch window"}});
    let (_d, store) = store();
    for os in [Os::Linux, Os::Windows] {
        let body = handle_at("reboot_host", &item, &test_cfg(), Some(os), &store, T0);
        assert_eq!(body, c["examples"]["reboot_scheduled"], "{os:?}");
    }
}

#[test]
fn every_example_in_the_contract_is_one_the_agent_tests_reproduce() {
    // Each of these is compared with a real producer in a test of this crate. A new example in
    // the contract fails here until a producer and a comparison exist for it.
    let Some(c) = contract() else { return };
    let mut known: Vec<String> = [
        "block_applied", "block_already_applied", "block_verify_failed", "unblock_removed", "quarantine_moved",
        "quarantine_moved_still_running", "quarantine_locked", "quarantine_hash_mismatch", "kill_done", "kill_gone",
        "kill_survived", "kill_refused", "restart_done", "isolate_done", "isolate_self_test_failed", "restore_done",
        "reboot_scheduled",
    ]
    .iter()
    .map(|k| k.to_string())
    .collect();
    known.sort();
    let mut theirs: Vec<String> = c["examples"].as_object().unwrap().keys().cloned().collect();
    theirs.sort();
    assert_eq!(theirs, known);
}

/// The result each patch example describes, built by the same helpers the agent's patch jobs use.
fn patch_example_result(name: &str) -> Value {
    use crate::capabilities::patch_installer::{coded_result, deferred_result, patch_result};
    use crate::capabilities::patch_reversible as r;
    match name {
        "install_ok" => patch_result("openssl", "success", "Installed openssl", false),
        "install_ok_reboot" => patch_result("KB5034441", "success", "Installed KB5034441. A restart is needed to finish.", true),
        "install_deferred_not_reversible" => deferred_result("openssl", r::NOT_REVERSIBLE, r::NOT_REVERSIBLE_MESSAGE),
        "install_failed" => patch_result("openssl", "failed", "E: Unable to locate package openssl", false),
        "revert_ok" => coded_result("openssl", "success", r::REVERTED, "Put back the earlier version of openssl", false),
        "revert_not_uninstallable" => coded_result("KB5034441", "failed", r::NOT_UNINSTALLABLE, "Windows does not allow this update to be uninstalled", false),
        "revert_version_not_offered" => coded_result("openssl", "failed", r::VERSION_NOT_OFFERED, "The earlier version is no longer offered by the package source", false),
        "revert_not_changed" => coded_result("curl", "skipped", r::NOT_CHANGED_BY_JOB, "This job did not change curl", false),
        other => panic!("patch example {other} has no producer in this test"),
    }
}

fn keys_of(v: &Value) -> Vec<String> {
    let mut keys: Vec<String> = v.as_object().unwrap().keys().cloned().collect();
    keys.sort();
    keys
}

#[test]
fn every_patch_example_is_produced_by_the_patch_installer_helpers() {
    use crate::capabilities::patch_installer::summarize;
    let Some(c) = contract() else { return };
    let examples = c["patchExamples"].as_object().unwrap();
    let mut names: Vec<&str> = examples.keys().map(String::as_str).collect();
    names.sort();
    assert_eq!(names.len(), 8, "a new patch example needs a producer in patch_example_result");
    for (name, example) in examples {
        let built = patch_example_result(name);
        let theirs = &example["results"][0];
        for field in ["patch_id", "status", "reboot_required"] {
            assert_eq!(built[field], theirs[field], "{name}.{field}");
        }
        assert_eq!(built.get("code"), theirs.get("code"), "{name}.code");
        assert_eq!(keys_of(&built), keys_of(theirs), "{name}: result body keys");
        let summary = summarize(vec![built], Some("job-1"), None);
        for field in ["status", "job_id", "total", "successful", "failed"] {
            assert_eq!(summary[field], example[field], "{name} summary.{field}");
        }
        assert_eq!(keys_of(&summary), keys_of(example), "{name}: summary body keys");
    }
}

#[test]
fn the_patch_statuses_and_codes_the_agent_writes_are_the_contracts() {
    use crate::capabilities::patch_reversible as r;
    let Some(c) = contract() else { return };
    let mut codes = strings(&c, "patchCodes");
    let mut ours: Vec<String> = [r::NOT_REVERSIBLE, r::REVERTED, r::NOT_UNINSTALLABLE, r::VERSION_NOT_OFFERED, r::NOT_CHANGED_BY_JOB, r::NOT_APPLICABLE]
        .iter().map(|s| s.to_string()).collect();
    codes.sort();
    ours.sort();
    assert_eq!(ours, codes);
    let statuses = strings(&c, "patchStatuses");
    for example in c["patchExamples"].as_object().unwrap().values() {
        let status = example["results"][0]["status"].as_str().unwrap();
        assert!(statuses.iter().any(|s| s == status), "{status}");
    }
}

#[test]
fn the_rollout_tokens_the_contract_names_are_reported_by_the_agent() {
    let Some(c) = contract() else { return };
    for key in ["reversibleCheck", "revertByJob"] {
        let token = c["rolloutTokens"][key].as_str().unwrap();
        assert!(SUPPORTED_TOKENS.contains(&token), "{token}");
    }
    assert_eq!(c["rolloutParams"], json!({"requireReversible": "require_reversible", "revertOf": "revert_of"}));
}
