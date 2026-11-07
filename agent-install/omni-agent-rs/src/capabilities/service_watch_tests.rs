//! Service watching and restart against the recorder: no test starts a real `systemctl` or `sc`.
//! Every sample below is the shape of the real command output, kept so the parsers are checked
//! against text and not against words the code makes up.

use super::*;
use crate::capabilities::privileged::with_recorder;
use crate::capabilities::response_contract_tests::test_cfg;
use std::cell::Cell;

/// `systemctl show -p ActiveState,SubState,Result,ExecMainStatus nginx` for a crashed service.
const SYSTEMD_FAILED: &str = "Result=exit-code\nExecMainStatus=1\nActiveState=failed\nSubState=failed\n";
/// The same for a service an admin stopped with `systemctl stop`.
const SYSTEMD_ADMIN_STOP: &str = "Result=success\nExecMainStatus=0\nActiveState=inactive\nSubState=dead\n";
/// A service that crashed and is waiting for systemd's `Restart=` to start it again.
const SYSTEMD_AUTO_RESTART: &str = "Result=exit-code\nExecMainStatus=203\nActiveState=activating\nSubState=auto-restart\n";
const SYSTEMD_ACTIVE: &str = "Result=success\nExecMainStatus=0\nActiveState=active\nSubState=running\n";
/// A unit systemd has never heard of, and a masked one (`LoadState` is asked for first, CR-03).
const SYSTEMD_NOT_FOUND: &str = "LoadState=not-found\nActiveState=inactive\nSubState=dead\nResult=success\nExecMainStatus=0\n";
const SYSTEMD_MASKED: &str = "LoadState=masked\nActiveState=inactive\nSubState=dead\nResult=success\nExecMainStatus=0\n";
const SYSTEMD_LOADED_STOP: &str = "LoadState=loaded\nActiveState=inactive\nSubState=dead\nResult=success\nExecMainStatus=0\n";
const SYSTEMD_LOADED_FAILED: &str = "LoadState=loaded\nActiveState=failed\nSubState=failed\nResult=exit-code\nExecMainStatus=1\n";
/// What `sc query` prints for a service that is not installed (it exits with 1060).
const SC_MISSING: &str = "[SC] EnumQueryServicesStatus:OpenService FAILED 1060:\n\nThe specified service does not exist as an installed service.\n";
const SYSTEMD_STARTING: &str = "Result=success\nExecMainStatus=0\nActiveState=activating\nSubState=start\n";

/// `sc query nginx` for a service that stopped with a service-specific error.
const SC_FAILED: &str = "\nSERVICE_NAME: nginx \n        TYPE               : 10  WIN32_OWN_PROCESS  \n        STATE              : 1  STOPPED \n                                (NOT_STOPPABLE, NOT_PAUSABLE, IGNORES_SHUTDOWN)\n        WIN32_EXIT_CODE    : 1066  (0x42a)\n        SERVICE_EXIT_CODE  : 1  (0x1)\n        CHECKPOINT         : 0x0\n        WAIT_HINT          : 0x0\n";
/// `sc query nginx` after `sc stop nginx` by an administrator.
const SC_ADMIN_STOP: &str = "\nSERVICE_NAME: nginx \n        TYPE               : 10  WIN32_OWN_PROCESS  \n        STATE              : 1  STOPPED \n                                (NOT_STOPPABLE, NOT_PAUSABLE, IGNORES_SHUTDOWN)\n        WIN32_EXIT_CODE    : 0  (0x0)\n        SERVICE_EXIT_CODE  : 0  (0x0)\n        CHECKPOINT         : 0x0\n        WAIT_HINT          : 0x0\n";
const SC_RUNNING: &str = "\nSERVICE_NAME: nginx \n        TYPE               : 10  WIN32_OWN_PROCESS  \n        STATE              : 4  RUNNING \n                                (STOPPABLE, NOT_PAUSABLE, ACCEPTS_SHUTDOWN)\n        WIN32_EXIT_CODE    : 0  (0x0)\n        SERVICE_EXIT_CODE  : 0  (0x0)\n        CHECKPOINT         : 0x0\n        WAIT_HINT          : 0x0\n";
const SC_START_PENDING: &str = "\nSERVICE_NAME: nginx \n        TYPE               : 10  WIN32_OWN_PROCESS  \n        STATE              : 2  START_PENDING \n        WIN32_EXIT_CODE    : 0  (0x0)\n        SERVICE_EXIT_CODE  : 0  (0x0)\n        CHECKPOINT         : 0x0\n        WAIT_HINT          : 0x7d0\n";
/// `sc qc nginx` for an automatic service, and for a disabled one.
const SC_QC_AUTO: &str = "[SC] QueryServiceConfig SUCCESS\n\nSERVICE_NAME: nginx\n        TYPE               : 10  WIN32_OWN_PROCESS\n        START_TYPE         : 2   AUTO_START\n        ERROR_CONTROL      : 1   NORMAL\n        BINARY_PATH_NAME   : C:\\nginx\\nginx.exe\n";
const SC_QC_DISABLED: &str = "[SC] QueryServiceConfig SUCCESS\n\nSERVICE_NAME: nginx\n        TYPE               : 10  WIN32_OWN_PROCESS\n        START_TYPE         : 4   DISABLED\n        ERROR_CONTROL      : 1   NORMAL\n        BINARY_PATH_NAME   : C:\\nginx\\nginx.exe\n";

fn names(list: &[&str]) -> Vec<String> {
    list.iter().map(|s| s.to_string()).collect()
}

fn script(outputs: &[&str]) {
    with_recorder(|r| {
        r.script.clear();
        r.calls.clear();
        for out in outputs {
            r.answer_next(out);
        }
    });
}

fn calls() -> Vec<String> {
    with_recorder(|r| r.lines())
}

fn contract() -> Option<Value> {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../shared/agent-response-contract.json");
    Some(serde_json::from_str(&std::fs::read_to_string(path).ok()?).expect("the contract file is valid JSON"))
}

// ── classification ────────────────────────────────────────────────────────

#[test]
fn systemd_failed_state_is_a_failure() {
    assert_eq!(classify_systemd(SYSTEMD_FAILED), Health::Failed { state: "failed".into(), exit_code: Some(1) });
}

#[test]
fn systemd_inactive_with_result_success_is_an_admin_stop() {
    assert_eq!(classify_systemd(SYSTEMD_ADMIN_STOP), Health::Stopped);
}

#[test]
fn systemd_activating_with_result_exit_code_is_a_failure() {
    assert_eq!(classify_systemd(SYSTEMD_AUTO_RESTART), Health::Failed { state: "activating".into(), exit_code: Some(203) });
    assert_eq!(classify_systemd(SYSTEMD_STARTING), Health::Pending);
}

#[test]
fn systemd_active_is_running_and_an_unreadable_answer_is_unknown() {
    assert_eq!(classify_systemd(SYSTEMD_ACTIVE), Health::Running);
    assert_eq!(classify_systemd(""), Health::Unknown);
    assert_eq!(classify_systemd("Failed to get properties: Unit nginx.service not found.\n"), Health::Unknown);
}

#[test]
fn a_unit_systemd_does_not_know_is_no_failure() {
    // systemd answers a missing unit as inactive with Result=success.
    assert!(!matches!(classify_systemd(SYSTEMD_ADMIN_STOP), Health::Failed { .. }));
}

#[test]
fn a_not_found_or_masked_unit_is_absent_and_a_loaded_one_is_judged_as_before() {
    assert_eq!(classify_systemd(SYSTEMD_NOT_FOUND), Health::Absent);
    assert_eq!(classify_systemd(SYSTEMD_MASKED), Health::Absent);
    assert_eq!(classify_systemd(SYSTEMD_LOADED_STOP), Health::Stopped);
    assert_eq!(classify_systemd(SYSTEMD_LOADED_FAILED), Health::Failed { state: "failed".into(), exit_code: Some(1) });
    assert_eq!(state_from_health(&Health::Absent), "absent");
}

#[test]
fn an_absent_service_is_never_a_failure_and_is_reported_absent_in_the_state() {
    let mut w = Watch::default();
    let watched = names(&["nginx"]);
    script(&[SYSTEMD_NOT_FOUND]);
    assert!(report_with(&mut w, Some(Os::Linux), None, &watched, 1_000).is_empty());
    script(&[SYSTEMD_NOT_FOUND, SYSTEMD_ACTIVE]);
    let state = state_report_with(&names(&["nginx", "sshd"]), 7, &|name| status_of(Os::Linux, name));
    assert_eq!(state["services"], json!([{"name": "nginx", "state": "absent"}, {"name": "sshd", "state": "running"}]));
}

#[test]
fn windows_error_1060_is_absent_and_any_other_sc_failure_is_unknown() {
    with_recorder(|r| { r.script.clear(); r.calls.clear(); r.fail_exit(1060, SC_MISSING); });
    assert_eq!(status_of(Os::Windows, "nginx"), Health::Absent);
    assert_eq!(calls(), vec!["sc query nginx"]);
    with_recorder(|r| { r.script.clear(); r.calls.clear(); r.fail_exit(5, "[SC] OpenService FAILED 5:\n\nAccess is denied.\n"); });
    assert_eq!(status_of(Os::Windows, "nginx"), Health::Unknown);
    with_recorder(|r| { r.script.clear(); r.calls.clear(); r.fail_spawn(2); });
    assert_eq!(status_of(Os::Windows, "nginx"), Health::Unknown);
}

#[test]
fn sc_stopped_with_exit_code_1066_is_a_failure() {
    assert_eq!(classify_sc(SC_FAILED, SC_QC_AUTO), Health::Failed { state: "stopped".into(), exit_code: Some(1066) });
}

#[test]
fn sc_stopped_with_exit_code_zero_is_an_admin_stop() {
    assert_eq!(classify_sc(SC_ADMIN_STOP, SC_QC_AUTO), Health::Stopped);
}

#[test]
fn sc_start_type_disabled_is_an_admin_stop_whatever_the_exit_code() {
    assert_eq!(classify_sc(SC_FAILED, SC_QC_DISABLED), Health::Stopped);
}

#[test]
fn sc_running_and_pending_states_are_not_failures() {
    assert_eq!(classify_sc(SC_RUNNING, ""), Health::Running);
    assert_eq!(classify_sc(SC_START_PENDING, ""), Health::Pending);
    assert_eq!(classify_sc("", ""), Health::Unknown);
    assert_eq!(classify_sc("[SC] EnumQueryServicesStatus:OpenService FAILED 1060:", ""), Health::Unknown);
}

#[test]
fn status_of_asks_with_fixed_argv_on_linux() {
    script(&[SYSTEMD_FAILED]);
    assert_eq!(status_of(Os::Linux, "nginx"), Health::Failed { state: "failed".into(), exit_code: Some(1) });
    assert_eq!(calls(), vec!["systemctl show -p LoadState,ActiveState,SubState,Result,ExecMainStatus nginx"]);
}

#[test]
fn status_of_reads_the_start_type_on_windows_only_for_a_stopped_service() {
    script(&[SC_RUNNING]);
    assert_eq!(status_of(Os::Windows, "nginx"), Health::Running);
    assert_eq!(calls(), vec!["sc query nginx"]);
    script(&[SC_FAILED, SC_QC_AUTO]);
    assert!(matches!(status_of(Os::Windows, "nginx"), Health::Failed { .. }));
    assert_eq!(calls(), vec!["sc query nginx", "sc qc nginx"]);
    script(&[SC_FAILED, SC_QC_DISABLED]);
    assert_eq!(status_of(Os::Windows, "nginx"), Health::Stopped);
}

// ── the watched list ──────────────────────────────────────────────────────

#[test]
fn a_new_well_formed_list_is_taken() {
    let body = json!({"watchedServices": ["nginx", "postgresql"]});
    assert_eq!(changed_watched(None, &body), Some(names(&["nginx", "postgresql"])));
    let before = names(&["nginx"]);
    assert_eq!(changed_watched(Some(&before), &body), Some(names(&["nginx", "postgresql"])));
}

#[test]
fn an_unchanged_malformed_or_absent_list_gives_none() {
    let same = names(&["nginx", "postgresql"]);
    assert_eq!(changed_watched(Some(&same), &json!({"watchedServices": ["nginx", "postgresql"]})), None);
    assert_eq!(changed_watched(None, &json!({"enabledCapabilities": []})), None);
    for bad in [
        json!({"watchedServices": "nginx"}),
        json!({"watchedServices": [1, 2]}),
        json!({"watchedServices": ["ok", "my service"]}),
        json!({"watchedServices": ["--version"]}),
        json!({"watchedServices": [""]}),
        json!({"watchedServices": null}),
    ] {
        assert_eq!(changed_watched(None, &bad), None, "{bad}");
    }
    let too_many: Vec<String> = (0..=MAX_WATCHED).map(|i| format!("svc{i}")).collect();
    assert_eq!(changed_watched(None, &json!({"watchedServices": too_many})), None);
}

#[test]
fn an_emptied_list_is_taken_so_nothing_is_checked() {
    let before = names(&["nginx"]);
    assert_eq!(changed_watched(Some(&before), &json!({"watchedServices": []})), Some(Vec::new()));
    assert_eq!(changed_watched(Some(&[]), &json!({"watchedServices": []})), None);
}

// ── the failure report ────────────────────────────────────────────────────

#[test]
fn a_failure_younger_than_sixty_seconds_is_not_reported_and_an_older_one_is() {
    let mut w = Watch::default();
    let watched = names(&["nginx"]);
    script(&[SYSTEMD_FAILED, SYSTEMD_FAILED]);
    assert!(report_with(&mut w, Some(Os::Linux), None, &watched, 1_000).is_empty());
    // Inside the cache window nothing is asked again.
    assert!(report_with(&mut w, Some(Os::Linux), None, &watched, 1_030).is_empty());
    assert_eq!(calls().len(), 1);
    let out = report_with(&mut w, Some(Os::Linux), None, &watched, 1_060);
    assert_eq!(out.len(), 1);
    let f = &out[0];
    assert_eq!(f["name"], "nginx");
    assert_eq!(f["since"], 1_000);
    assert_eq!(f["state"], "failed");
    assert_eq!(f["exit_code"], 1);
    assert!(f["failure_id"].as_str().is_some_and(|id| !id.is_empty()));
}

#[test]
fn the_same_failure_keeps_one_failure_id_and_recovery_clears_it() {
    let mut w = Watch::default();
    let watched = names(&["nginx"]);
    script(&[SYSTEMD_FAILED, SYSTEMD_FAILED, SYSTEMD_FAILED, SYSTEMD_ACTIVE, SYSTEMD_FAILED, SYSTEMD_FAILED]);
    report_with(&mut w, Some(Os::Linux), None, &watched, 1_000);
    let first = report_with(&mut w, Some(Os::Linux), None, &watched, 1_060);
    let again = report_with(&mut w, Some(Os::Linux), None, &watched, 1_120);
    assert_eq!(first[0]["failure_id"], again[0]["failure_id"]);
    assert_eq!(first[0]["since"], again[0]["since"]);
    // The service came back: nothing is reported, and a later failure is a new one.
    assert!(report_with(&mut w, Some(Os::Linux), None, &watched, 1_180).is_empty());
    assert!(report_with(&mut w, Some(Os::Linux), None, &watched, 1_240).is_empty());
    let next = report_with(&mut w, Some(Os::Linux), None, &watched, 1_300);
    assert_eq!(next[0]["since"], 1_240);
    assert_ne!(next[0]["failure_id"], first[0]["failure_id"]);
}

#[test]
fn a_service_an_admin_stopped_is_never_reported_on_either_system() {
    let mut w = Watch::default();
    let watched = names(&["nginx"]);
    script(&[SYSTEMD_ADMIN_STOP, SYSTEMD_ADMIN_STOP, SYSTEMD_ADMIN_STOP]);
    for now in [1_000, 1_060, 1_120] {
        assert!(report_with(&mut w, Some(Os::Linux), None, &watched, now).is_empty());
    }
    let mut w = Watch::default();
    script(&[SC_ADMIN_STOP, SC_ADMIN_STOP, SC_ADMIN_STOP]);
    for now in [1_000, 1_060, 1_120] {
        assert!(report_with(&mut w, Some(Os::Windows), None, &watched, now).is_empty());
    }
    // A disabled service that carries an error code is also left alone.
    let mut w = Watch::default();
    script(&[SC_FAILED, SC_QC_DISABLED, SC_FAILED, SC_QC_DISABLED]);
    assert!(report_with(&mut w, Some(Os::Windows), None, &watched, 1_000).is_empty());
    assert!(report_with(&mut w, Some(Os::Windows), None, &watched, 1_060).is_empty());
}

#[test]
fn a_windows_failure_is_reported_with_its_exit_code() {
    let mut w = Watch::default();
    let watched = names(&["nginx"]);
    script(&[SC_FAILED, SC_QC_AUTO, SC_FAILED, SC_QC_AUTO]);
    assert!(report_with(&mut w, Some(Os::Windows), None, &watched, 1_000).is_empty());
    let out = report_with(&mut w, Some(Os::Windows), None, &watched, 1_060);
    assert_eq!((out[0]["state"].as_str(), out[0]["exit_code"].as_i64()), (Some("stopped"), Some(1066)));
}

#[test]
fn with_the_capability_off_or_nothing_listed_no_command_runs() {
    let mut w = Watch::default();
    script(&[SYSTEMD_FAILED]);
    let off = names(&["metrics_collection"]);
    assert!(report_with(&mut w, Some(Os::Linux), Some(&off), &names(&["nginx"]), 1_000).is_empty());
    assert!(report_with(&mut w, Some(Os::Linux), Some(&off), &names(&["nginx"]), 1_100).is_empty());
    assert!(report_with(&mut w, Some(Os::Linux), None, &[], 1_200).is_empty());
    assert!(report_with(&mut w, None, None, &names(&["nginx"]), 1_300).is_empty());
    assert!(calls().is_empty(), "{:?}", calls());
}

#[test]
fn a_critical_or_invalid_name_on_the_list_is_never_asked_about() {
    let mut w = Watch::default();
    script(&[SYSTEMD_FAILED]);
    let on = names(&["remediation_executor"]);
    let watched = names(&["sshd", "OmniAgent", "my service", "-x"]);
    assert!(report_with(&mut w, Some(Os::Linux), Some(&on), &watched, 1_000).is_empty());
    assert!(calls().is_empty(), "{:?}", calls());
}

// ── restart ───────────────────────────────────────────────────────────────

#[test]
fn restart_refuses_unsafe_names_and_records_no_command() {
    let long = "a".repeat(129);
    for name in ["my service", "sshd", "SSHD", "sshd.service", "OmniAgent", "OmniAgentRust", "RpcSs", "WinDefend", "-x", "", "a;b", long.as_str()] {
        script(&[]);
        let body = restart(Os::Linux, name, &|| {});
        assert_eq!((body["status"].as_str(), body["outcome"].as_str()), (Some("error"), Some("refused")), "{name}");
        assert!(calls().is_empty(), "{name}: {:?}", calls());
        let body = restart(Os::Windows, name, &|| {});
        assert_eq!(body["outcome"], "refused", "{name}");
        assert!(calls().is_empty(), "{name}: {:?}", calls());
    }
}

#[test]
fn restart_uses_fixed_argv_with_one_element_per_argument() {
    script(&[]);
    restart(Os::Linux, "nginx", &|| {});
    let linux = with_recorder(|r| r.calls.clone());
    assert_eq!(linux[0], vec!["systemctl", "restart", "nginx"]);
    script(&[]);
    restart(Os::Windows, "nginx", &|| {});
    let windows = with_recorder(|r| r.calls.clone());
    assert_eq!(windows[0], vec!["sc", "stop", "nginx"]);
    assert!(windows.contains(&vec!["sc".to_string(), "start".to_string(), "nginx".to_string()]));
    let stop = windows.iter().position(|c| c[1] == "stop").unwrap();
    let start = windows.iter().position(|c| c[1] == "start").unwrap();
    assert!(stop < start);
}

#[test]
fn a_service_running_after_the_poll_answers_restarted_with_healthy_after() {
    script(&["", SYSTEMD_STARTING, SYSTEMD_ACTIVE]);
    let pauses = Cell::new(0u32);
    let body = restart(Os::Linux, "nginx", &|| pauses.set(pauses.get() + 1));
    assert_eq!(body["status"], "success");
    assert_eq!(body["outcome"], "restarted");
    assert_eq!(body["verify"], json!({"ok": true, "check": "service_running"}));
    assert_eq!(body["healthy_after"], 2);
    assert_eq!(pauses.get(), 2);
}

#[test]
fn a_service_that_never_runs_answers_not_running_with_verify_not_ok() {
    script(&["", SYSTEMD_FAILED, SYSTEMD_FAILED, SYSTEMD_FAILED, SYSTEMD_FAILED, SYSTEMD_FAILED, SYSTEMD_FAILED, SYSTEMD_FAILED, SYSTEMD_FAILED, SYSTEMD_FAILED, SYSTEMD_FAILED]);
    let pauses = Cell::new(0u32);
    let body = restart(Os::Linux, "nginx", &|| pauses.set(pauses.get() + 1));
    assert_eq!(body["outcome"], "not_running");
    assert_eq!(body["verify"], json!({"ok": false, "check": "service_running"}));
    assert!(body.get("healthy_after").is_none());
    assert_eq!(pauses.get(), RESTART_POLLS);
}

#[test]
fn a_command_that_fails_is_an_error_body_and_a_security_block_has_its_own_outcome() {
    with_recorder(|r| {
        r.script.clear();
        r.calls.clear();
        r.fail_next(1);
    });
    let body = restart(Os::Linux, "nginx", &|| {});
    assert_eq!(body["status"], "error");
    assert!(body.get("outcome").is_none());
    with_recorder(|r| {
        r.script.clear();
        r.calls.clear();
        r.fail_spawn(225);
    });
    assert_eq!(restart(Os::Windows, "nginx", &|| {})["outcome"], "blocked_by_local_security");
}

#[test]
fn the_restart_done_example_has_a_real_producer() {
    let Some(c) = contract() else { return };
    script(&["", SYSTEMD_ACTIVE]);
    let mut body = restart(Os::Linux, "nginx", &|| {});
    assert_eq!(body["healthy_after"], 1);
    body["healthy_after"] = c["examples"]["restart_done"]["healthy_after"].clone();
    assert_eq!(body, c["examples"]["restart_done"]);
}

#[test]
fn the_critical_service_list_equals_the_contract() {
    let Some(c) = contract() else { return };
    let mut theirs: Vec<&str> = c["criticalServices"].as_array().unwrap().iter().filter_map(Value::as_str).collect();
    let mut ours: Vec<&str> = remediation_actions::CRITICAL_SERVICE_NAMES.to_vec();
    theirs.sort_unstable();
    ours.sort_unstable();
    assert_eq!(ours, theirs);
}

// ── the instruction ───────────────────────────────────────────────────────

#[tokio::test]
async fn the_instruction_refuses_bad_input_at_once_and_otherwise_answers_accepted() {
    let client = reqwest::Client::new();
    let mut cfg = test_cfg();
    cfg.watched_services = Some(names(&["nginx"]));
    for item in [
        json!({"task_id": "t-1", "parameters": {"service_name": "sshd"}}),
        json!({"task_id": "t-1", "parameters": {"service_name": "a b"}}),
        json!({"task_id": "t-1", "parameters": {}}),
        json!({"task_id": "bad id!", "parameters": {"service_name": "nginx"}}),
        json!({"parameters": {"service_name": "nginx"}}),
    ] {
        script(&[]);
        let body = restart_arm(&item, &cfg, &client);
        assert_eq!(body["outcome"], "refused", "{item}");
        assert!(calls().is_empty());
    }
    let ok = restart_arm(&json!({"task_id": "t-1", "parameters": {"service_name": "nginx"}}), &cfg, &client);
    assert_eq!(ok, json!({"status": "accepted"}));
}

#[test]
fn the_failure_id_is_built_from_the_name_and_the_time_it_started() {
    assert_eq!(failure_id("nginx", 1_000), failure_id("nginx", 1_000));
    assert_ne!(failure_id("nginx", 1_000), failure_id("nginx", 1_240));
    assert_ne!(failure_id("nginx", 1_000), failure_id("cron", 1_000));
}

// ── WR-21: only a watched service, and only a service unit ─────────────────

#[test]
fn restart_refuses_a_unit_that_is_not_a_service_and_the_session_and_network_daemons() {
    // `systemctl restart reboot.target` reboots the host; a socket or logind ends every session.
    for name in [
        "reboot.target", "poweroff.target", "halt.target", "rescue.target", "emergency.target", "Reboot.Target",
        "sshd.socket", "ssh.socket", "dbus.socket", "home.mount", "x.timer", "network.target",
        "systemd-logind", "systemd-networkd.service", "network", "networking",
    ] {
        script(&[]);
        assert_eq!(restart(Os::Linux, name, &|| {})["outcome"], "refused", "{name}");
        assert!(calls().is_empty(), "{name}: {:?}", calls());
    }
    for name in ["nginx.service", "php7.4-fpm", "nginx"] {
        assert!(remediation_actions::validate_service_name(name).is_ok(), "{name}");
    }
}

#[tokio::test]
async fn the_instruction_restarts_only_a_service_the_tenant_watches() {
    let client = reqwest::Client::new();
    let mut cfg = test_cfg();
    let item = |name: &str| json!({"task_id": "t-21", "parameters": {"service_name": name}});
    script(&[]);
    assert_eq!(restart_arm(&item("nginx"), &cfg, &client)["outcome"], "refused", "nothing is watched");
    cfg.watched_services = Some(names(&["nginx", "Postgresql"]));
    assert_eq!(restart_arm(&item("cron"), &cfg, &client)["outcome"], "refused");
    for name in ["nginx", "NGINX", "nginx.service", "postgresql"] {
        assert_eq!(restart_arm(&item(name), &cfg, &client), json!({"status": "accepted"}), "{name}");
    }
}

// ── service_state (PTCH-02) ───────────────────────────────────────────────

#[test]
fn state_from_health_maps_every_variant() {
    assert_eq!(state_from_health(&Health::Running), "running");
    assert_eq!(state_from_health(&Health::Stopped), "stopped");
    assert_eq!(state_from_health(&Health::Failed { state: "failed".into(), exit_code: Some(1) }), "failed");
    assert_eq!(state_from_health(&Health::Pending), "unknown");
    assert_eq!(state_from_health(&Health::Unknown), "unknown");
}

#[test]
fn state_report_lists_every_watched_service_in_order_including_a_clean_stop() {
    let status = |name: &str| if name == "nginx" { Health::Stopped } else { Health::Running };
    let report = state_report_with(&names(&["sshd", "nginx"]), 1_767_000_000, &status);
    assert_eq!(report, json!({
        "v": 1, "at": 1_767_000_000,
        "services": [{"name": "sshd", "state": "running"}, {"name": "nginx", "state": "stopped"}],
    }));
}

#[test]
fn state_report_of_an_empty_list_has_no_services() {
    let report = state_report_with(&[], 42, &|_| Health::Running);
    assert_eq!(report, json!({"v": 1, "at": 42, "services": []}));
}

#[test]
fn state_report_lists_a_duplicate_name_once_and_drops_a_name_over_128_characters() {
    let long = "a".repeat(129);
    let ok = "b".repeat(128);
    let report = state_report_with(&names(&["nginx", "NGINX", "nginx", &long, &ok]), 1, &|_| Health::Running);
    let listed: Vec<&str> = report["services"].as_array().unwrap().iter().map(|s| s["name"].as_str().unwrap()).collect();
    assert_eq!(listed, vec!["nginx", ok.as_str()]);
}

#[test]
fn state_report_asks_each_service_once_and_never_for_a_malformed_name() {
    let asked = std::cell::RefCell::new(Vec::new());
    let status = |name: &str| {
        asked.borrow_mut().push(name.to_string());
        Health::Unknown
    };
    let report = state_report_with(&names(&["nginx", "nginx", "--now", "a b", ""]), 1, &status);
    assert_eq!(asked.into_inner(), vec!["nginx".to_string()]);
    assert_eq!(report["services"], json!([{"name": "nginx", "state": "unknown"}]));
}

#[test]
fn state_report_on_another_platform_lists_nothing() {
    let report = state_report(None, &names(&["nginx"]), 7);
    assert_eq!(report, json!({"v": 1, "at": 7, "services": []}));
}
