//! Revert passes, confirmation, restore and the heartbeat report, against the recorder.

use super::tests::*;
use super::*;
use crate::capabilities::privileged::with_recorder;

#[test]
fn revert_due_acts_at_revert_at_and_not_one_second_earlier() {
    let (_d, store) = fresh();
    seed(&store, record("iso-1", T0 + 100, false));
    assert!(!revert_due(&store, Os::Linux, T0 + 99).reverted);
    assert!(lines().is_empty());
    assert!(state_isolation(&store).is_some());
    let pass = revert_due(&store, Os::Linux, T0 + 100);
    assert!(pass.reverted);
    assert!(lines().contains(&"iptables -w -D INPUT -j OMNI_ISOLATE_IN".to_string()));
    assert!(state_isolation(&store).is_none());
}

#[test]
fn a_confirmed_isolation_never_reverts() {
    let (_d, store) = fresh();
    seed(&store, record("iso-1", T0 + 100, true));
    assert!(!revert_due(&store, Os::Linux, T0 + 10_000_000).reverted);
    assert!(lines().is_empty());
    assert!(state_isolation(&store).is_some());
}

#[test]
fn with_no_isolation_recorded_a_pass_issues_no_command() {
    let (_d, store) = fresh();
    assert_eq!(revert_due(&store, Os::Linux, T0), PassOutcome::default());
    assert_eq!(start_up(&store, Os::Linux, T0), PassOutcome::default());
    assert!(lines().is_empty());
}

#[test]
fn a_confirm_before_the_pass_cancels_it_and_a_confirm_after_it_changes_nothing() {
    let (_d, store) = fresh();
    seed(&store, record("iso-1", T0 + 100, false));
    assert!(apply_confirmations(&store, &["iso-1".to_string()]).unwrap());
    assert!(!revert_due(&store, Os::Linux, T0 + 100).reverted, "the confirm came first");

    let (_d2, store2) = fresh();
    seed(&store2, record("iso-1", T0 + 100, false));
    assert!(revert_due(&store2, Os::Linux, T0 + 100).reverted);
    assert!(!apply_confirmations(&store2, &["iso-1".to_string()]).unwrap(), "the confirm came after the revert");
    assert!(state_isolation(&store2).is_none());
}

#[test]
fn a_confirmation_is_persisted_and_only_its_own_id_counts() {
    let (_d, store) = fresh();
    assert!(!apply_confirmations(&store, &["iso-1".to_string()]).unwrap(), "no isolation");
    assert!(!store.path().exists());
    seed(&store, record("iso-1", T0 + 100, false));
    assert!(!apply_confirmations(&store, &["other".to_string()]).unwrap());
    assert!(!state_isolation(&store).unwrap().confirmed);
    assert!(apply_confirmations(&store, &["other".to_string(), "iso-1".to_string()]).unwrap());
    assert!(Store::at(store.path()).load().unwrap().isolation.unwrap().confirmed);
    assert!(!apply_confirmations(&store, &["iso-1".to_string()]).unwrap(), "already confirmed");
}

#[test]
fn the_reply_key_may_hold_a_list_or_one_id() {
    assert_eq!(confirmed_ids(&json!({"isolationConfirmed": ["a", "b", 3]})), vec!["a", "b"]);
    assert_eq!(confirmed_ids(&json!({"isolationConfirmed": "a"})), vec!["a"]);
    assert!(confirmed_ids(&json!({"isolationConfirmed": 5})).is_empty());
    assert!(confirmed_ids(&json!({})).is_empty());
    assert!(confirmed_ids(&Value::Null).is_empty());
}

#[test]
fn a_state_file_that_cannot_be_read_removes_the_isolation_rules_found() {
    let (_d, store) = fresh();
    std::fs::write(store.path(), "{ not json").unwrap();
    let pass = start_up(&store, Os::Linux, T0);
    assert!(pass.reverted && pass.error.is_some());
    let got = lines();
    assert!(got.contains(&"iptables -w -D INPUT -j OMNI_ISOLATE_IN".to_string()));
    assert!(got.contains(&"ip6tables -w -X OMNI_ISOLATE_FWD".to_string()));
    assert_eq!(std::fs::read_to_string(store.path()).unwrap(), "{ not json", "the file is left as it was");
}

#[test]
fn an_unreadable_state_file_with_no_rules_in_place_removes_nothing() {
    let (_d, store) = fresh();
    std::fs::write(store.path(), "{ not json").unwrap();
    with_recorder(|r| r.fail_next(2)); // neither family has the hook
    let pass = start_up(&store, Os::Linux, T0);
    assert!(!pass.reverted);
    assert!(lines().iter().all(|l| l.contains(" -C ")), "{:?}", lines());
}

#[test]
fn on_windows_a_lost_record_puts_the_default_policy_back_and_removes_the_rules() {
    let (_d, store) = fresh();
    std::fs::write(store.path(), "{ not json").unwrap();
    let pass = revert_due(&store, Os::Windows, T0);
    assert!(pass.reverted);
    let got = lines();
    for profile in ["domain", "private", "public"] {
        assert!(got.contains(&format!("netsh advfirewall set {profile}profile firewallpolicy blockinbound,allowoutbound")));
    }
    assert!(got.contains(&"netsh advfirewall firewall delete rule name=OmniAgent_Isolate_Allow_Out".to_string()));
}

#[test]
fn start_up_reverts_an_isolation_that_ran_out_while_the_agent_was_away() {
    let (_d, store) = fresh();
    seed(&store, record("iso-1", T0 - 5, false));
    assert!(start_up(&store, Os::Linux, T0).reverted);
    assert!(state_isolation(&store).is_none());
}

#[test]
fn start_up_keeps_an_isolation_whose_rules_are_in_place_and_drops_one_a_reboot_lost() {
    let (_d, store) = fresh();
    seed(&store, record("iso-1", T0 + 1_000, false));
    assert!(!start_up(&store, Os::Linux, T0).reverted, "the hook is there");
    assert!(state_isolation(&store).is_some());
    with_recorder(|r| r.fail_next(2)); // a reboot dropped the rules
    assert!(start_up(&store, Os::Linux, T0).reverted);
    assert!(state_isolation(&store).is_none(), "the report must not say isolated");
}

#[test]
fn restore_ends_the_isolation_and_equals_the_contract_example() {
    let (_d, store) = fresh();
    script_linux_apply();
    isolate(&store, Os::Linux, "iso-1", T0, true);
    with_recorder(|r| r.clear_calls());
    oks(36); // 6 unhooks and 12 chain steps, each a check and a command
    with_recorder(|r| r.fail_next(2)); // afterwards neither hook is there
    let body = restore(&store, Os::Linux, "iso-1", T0 + 60);
    if let Some(c) = contract() {
        assert_eq!(body, c["examples"]["restore_done"]);
    }
    assert_eq!(body["outcome"], "restored");
    assert!(state_isolation(&store).is_none());
}

#[test]
fn a_repeat_restore_answers_not_found_with_no_command() {
    let (_d, store) = fresh();
    let body = restore(&store, Os::Linux, "iso-1", T0);
    assert_eq!(body, json!({"status": "success", "outcome": "not_found", "verify": {"ok": true, "check": "network_restored"}}));
    assert!(lines().is_empty());
}

#[test]
fn restore_ends_a_confirmed_isolation_and_a_failed_restore_stays_due() {
    let (_d, store) = fresh();
    seed(&store, record("iso-1", T0 + 100, true));
    with_recorder(|r| {
        r.answer_next("");
        r.fail_next(1); // the first hook cannot be removed
    });
    let body = restore(&store, Os::Linux, "iso-1", T0 + 5);
    assert_eq!(body["status"], "error");
    let iso = state_isolation(&store).expect("still recorded");
    assert_eq!((iso.confirmed, iso.revert_at), (false, T0 + 5), "the sweeper keeps trying");
    assert!(revert_due(&store, Os::Linux, T0 + 20).reverted);
    assert_eq!(restore(&store, Os::Linux, "bad id!", T0)["outcome"], "refused");
}

#[test]
fn the_heartbeat_report_shows_the_isolation_and_its_countdown() {
    let (_d, store) = fresh();
    let none = response_state_report(&store, T0);
    assert_eq!(none["v"], 1);
    assert!(none["isolation"].is_null());
    assert!(none["boot_time"].is_u64());
    assert_eq!(none["active_blocks"], 0);

    store.update(|s| {
        s.add_claim("45.33.32.156", "a", T0 + 500, T0);
        s.add_claim("45.33.32.157", "b", T0 - 1, T0 - 100);
    }).unwrap();
    seed(&store, record("iso-1", T0 + 14_400, false));
    let report = response_state_report(&store, T0 + 400);
    assert_eq!(report["isolation"], json!({"id": "iso-1", "active": true, "confirmed": false, "revert_in_seconds": 14_000}));
    assert_eq!(report["active_blocks"], 1, "only the unexpired claim counts");

    apply_confirmations(&store, &["iso-1".to_string()]).unwrap();
    assert_eq!(response_state_report(&store, T0)["isolation"]["revert_in_seconds"], Value::Null);
    assert_eq!(response_state_report(&store, T0)["isolation"]["confirmed"], true);

    std::fs::write(store.path(), "{ not json").unwrap();
    assert_eq!(response_state_report(&store, T0)["state_unreadable"], true);
}

#[test]
fn the_self_test_reaches_a_listener_and_fails_when_nothing_listens() {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let up = CarveOut { addresses: vec!["127.0.0.1".parse().unwrap()], dns: vec![], port };
    assert!(tcp_self_test(&up));
    drop(listener);
    assert!(!tcp_self_test(&up));
}
