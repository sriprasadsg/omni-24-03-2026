//! The block commands against the recorder: time, platform and state file are all supplied.

use super::*;
use crate::capabilities::privileged::with_recorder;
use crate::capabilities::response_contract_tests::test_cfg;

const T0: i64 = 1_761_900_000;

fn block_item(id: &str, ip: &str, ttl: Option<Value>) -> Value {
    let mut params = json!({"ip_address": ip});
    if let Some(ttl) = ttl {
        params["ttl_seconds"] = ttl;
    }
    json!({"task_id": id, "parameters": params})
}

fn run(action: &str, item: &Value, store: &Store, now: i64) -> Value {
    handle_at(action, item, &test_cfg(), Some(Os::Linux), store, now)
}

fn fresh() -> (tempfile::TempDir, Store) {
    let dir = tempfile::tempdir().unwrap();
    let store = Store::at(dir.path().join("response_state.json"));
    (dir, store)
}

fn recorded() -> Vec<String> {
    with_recorder(|r| r.lines())
}

#[test]
fn only_the_block_commands_are_handled() {
    assert!(handles("block_ip") && handles("unblock_ip"));
    assert!(handles("quarantine_file") && handles("unquarantine_file"));
    assert!(handles("kill_process") && !handles("enable_rdp"));
}

#[test]
fn a_ttl_outside_the_range_is_refused_and_nothing_touches_the_firewall() {
    let (_d, store) = fresh();
    for ttl in [json!(3599), json!(604_801), json!(0), json!(-5), json!("86400"), json!(3600.5)] {
        let body = run("block_ip", &block_item("t-1", "45.33.32.156", Some(ttl)), &store, T0);
        assert_eq!(body["status"], "error");
        assert_eq!(body["outcome"], "refused");
    }
    assert!(recorded().is_empty());
    assert!(store.load().unwrap().claims.is_empty());
}

#[test]
fn the_range_edges_are_accepted() {
    let (_d, store) = fresh();
    assert_eq!(run("block_ip", &block_item("a", "45.33.32.156", Some(json!(3600))), &store, T0)["expires_in"], 3600);
    assert_eq!(run("block_ip", &block_item("b", "45.33.32.157", Some(json!(604_800))), &store, T0)["expires_in"], 604_800);
}

#[test]
fn a_missing_ttl_is_24_hours_so_no_block_is_open_ended() {
    let (_d, store) = fresh();
    let body = run("block_ip", &block_item("t-1", "45.33.32.156", None), &store, T0);
    assert_eq!(body["expires_in"], 86_400);
    assert_eq!(store.load().unwrap().claims[0].expires_at, T0 + 86_400);
    let body = run("block_ip", &block_item("t-2", "45.33.32.157", Some(Value::Null)), &store, T0);
    assert_eq!(body["expires_in"], 86_400);
}

#[test]
fn an_instruction_id_must_be_1_to_64_letters_digits_or_hyphens() {
    let (_d, store) = fresh();
    let long = "a".repeat(65);
    for id in ["", "a b", "a_b", "a/b", "ä", long.as_str()] {
        let body = run("block_ip", &block_item(id, "45.33.32.156", None), &store, T0);
        assert_eq!(body["outcome"], "refused", "{id:?}");
    }
    let no_id = json!({"parameters": {"ip_address": "45.33.32.156"}});
    assert_eq!(run("block_ip", &no_id, &store, T0)["outcome"], "refused");
    assert!(recorded().is_empty());
    let ok = "a".repeat(64);
    assert_eq!(run("block_ip", &block_item(&ok, "45.33.32.156", None), &store, T0)["outcome"], "applied");
}

#[test]
fn addresses_that_cannot_be_blocked_are_refused() {
    let (_d, store) = fresh();
    for ip in ["", "not-an-ip", "0.0.0.0", "127.0.0.1", "::1", "::", "224.0.0.1", "255.255.255.255", "169.254.1.1", "fe80::1", "45.33.32.156/24", "1.2.3.4 -j ACCEPT"] {
        let body = run("block_ip", &block_item("t-1", ip, None), &store, T0);
        assert_eq!(body["outcome"], "refused", "{ip:?}");
    }
    assert!(recorded().is_empty());
}

#[test]
fn the_platform_address_is_never_blocked() {
    let (_d, store) = fresh();
    let cfg: Config = serde_norway::from_str(
        "api_base_url: https://57.154.210.55\ntenant_id: t\nagent_id: a\nagent_token: x\nregistration_key: r\n",
    )
    .unwrap();
    let body = handle_at("block_ip", &block_item("t-1", "57.154.210.55", None), &cfg, Some(Os::Linux), &store, T0);
    assert_eq!(body["outcome"], "refused");
    assert!(recorded().is_empty());
}

#[test]
fn a_platform_without_a_firewall_plan_refuses() {
    let (_d, store) = fresh();
    let body = handle_at("block_ip", &block_item("t-1", "45.33.32.156", None), &test_cfg(), None, &store, T0);
    assert_eq!(body["outcome"], "refused");
    assert!(recorded().is_empty());
}

#[test]
fn the_claim_is_written_before_the_firewall_is_touched() {
    let (_d, store) = fresh();
    // A state file that cannot be used stops the block before any firewall call.
    std::fs::write(store.path(), "{ not json").unwrap();
    let body = run("block_ip", &block_item("t-1", "45.33.32.156", None), &store, T0);
    assert_eq!(body["status"], "error");
    assert!(recorded().is_empty());
}

#[test]
fn a_firewall_error_removes_the_claim_again() {
    let (_d, store) = fresh();
    // The chain is missing and creating it fails, so the apply stops at once.
    with_recorder(|r| r.fail_next(2));
    let body = run("block_ip", &block_item("t-1", "45.33.32.156", None), &store, T0);
    assert_eq!(body["status"], "error");
    assert!(recorded()[0].contains("-L OMNI_BLOCK"));
    assert!(store.load().unwrap().claims.is_empty());
}

#[test]
fn a_rule_the_check_cannot_find_keeps_the_claim() {
    let (_d, store) = fresh();
    with_recorder(|r| {
        for _ in 0..5 {
            r.answer_next("");
        }
        r.fail_next(1);
    });
    let body = run("block_ip", &block_item("t-1", "45.33.32.156", None), &store, T0);
    assert_eq!(body["status"], "success");
    assert_eq!(body["verify"], json!({"ok": false, "check": "firewall_rule_present"}));
    assert!(body.get("expires_in").is_none());
    assert_eq!(store.load().unwrap().claims.len(), 1);
}

#[test]
fn a_repeat_with_the_same_id_adds_no_second_rule_and_a_different_id_adds_a_claim() {
    let (_d, store) = fresh();
    let item = block_item("t-1", "45.33.32.156", None);
    assert_eq!(run("block_ip", &item, &store, T0)["outcome"], "applied");
    with_recorder(|r| r.clear_calls());
    assert_eq!(run("block_ip", &item, &store, T0 + 5)["outcome"], "already_applied");
    assert_eq!(run("block_ip", &block_item("t-2", "45.33.32.156", None), &store, T0 + 6)["outcome"], "applied");
    let adds = recorded().iter().filter(|l| l.contains(" -A ") || l.contains(" -I ") || l.contains(" -N ")).count();
    assert_eq!(adds, 0);
    assert_eq!(store.load().unwrap().claims.len(), 2);
}

#[test]
fn a_repeat_reports_the_time_that_is_left() {
    let (_d, store) = fresh();
    let item = block_item("t-1", "45.33.32.156", Some(json!(3600)));
    run("block_ip", &item, &store, T0);
    assert_eq!(run("block_ip", &item, &store, T0 + 600)["expires_in"], 3000);
}

#[test]
fn undo_removes_one_claim_and_the_rule_only_with_the_last() {
    let (_d, store) = fresh();
    run("block_ip", &block_item("t-1", "45.33.32.156", None), &store, T0);
    run("block_ip", &block_item("t-2", "45.33.32.156", None), &store, T0);
    with_recorder(|r| r.clear_calls());

    let first = run("unblock_ip", &json!({"parameters": {"ip_address": "45.33.32.156", "block_id": "t-1"}}), &store, T0 + 10);
    assert_eq!(first["outcome"], "removed");
    assert_eq!(first["verify"], json!({"ok": true, "check": "firewall_rule_present"}));
    assert!(recorded().iter().all(|l| !l.contains(" -D ")), "the rule must stay: {:?}", recorded());
    assert_eq!(store.load().unwrap().claims.len(), 1);

    // Now the last claim: the checks that follow the delete say the rule is gone.
    with_recorder(|r| {
        r.clear_calls();
        for _ in 0..6 {
            r.answer_next("");
        }
        r.fail_next(1);
    });
    let last = run("unblock_ip", &json!({"parameters": {"ip_address": "45.33.32.156", "block_id": "t-2"}}), &store, T0 + 20);
    assert_eq!(last["outcome"], "removed");
    assert_eq!(last["verify"], json!({"ok": true, "check": "firewall_rule_absent"}));
    assert!(recorded().iter().any(|l| l.contains(" -D OMNI_BLOCK -s 45.33.32.156")));
    assert!(store.load().unwrap().claims.is_empty());
}

#[test]
fn undo_without_a_block_id_removes_every_claim_on_the_address() {
    let (_d, store) = fresh();
    run("block_ip", &block_item("t-1", "45.33.32.156", None), &store, T0);
    run("block_ip", &block_item("t-2", "45.33.32.156", None), &store, T0);
    run("block_ip", &block_item("t-3", "45.33.32.157", None), &store, T0);
    let body = run("unblock_ip", &json!({"parameters": {"ip_address": "45.33.32.156"}}), &store, T0 + 1);
    assert_eq!(body["outcome"], "removed");
    let left = store.load().unwrap().claims;
    assert_eq!(left.len(), 1);
    assert_eq!(left[0].target, "45.33.32.157");
}

#[test]
fn a_failed_rule_removal_leaves_the_claims_in_place() {
    let (_d, store) = fresh();
    run("block_ip", &block_item("t-1", "45.33.32.156", None), &store, T0);
    with_recorder(|r| {
        r.answer_next(""); // -s check passes
        r.fail_next(1); // -s delete fails
    });
    let body = run("unblock_ip", &json!({"parameters": {"ip_address": "45.33.32.156", "block_id": "t-1"}}), &store, T0 + 1);
    assert_eq!(body["status"], "error");
    assert_eq!(store.load().unwrap().claims.len(), 1);
}

#[test]
fn undo_of_something_that_is_not_blocked_says_not_found() {
    let (_d, store) = fresh();
    with_recorder(|r| r.fail_next(3));
    let body = run("unblock_ip", &json!({"parameters": {"ip_address": "45.33.32.156", "block_id": "t-9"}}), &store, T0);
    assert_eq!(body["outcome"], "not_found");
}

#[test]
fn an_invalid_block_id_on_undo_is_refused() {
    let (_d, store) = fresh();
    let body = run("unblock_ip", &json!({"parameters": {"ip_address": "45.33.32.156", "block_id": "a b"}}), &store, T0);
    assert_eq!(body["outcome"], "refused");
    assert!(recorded().is_empty());
}

// ---- Phase 83 plan 04: the agent's own refusals, ranges and the security-product outcome ----

use crate::capabilities::net_safety::{set_test_host_addrs, HostAddrs};

fn ip(s: &str) -> std::net::IpAddr {
    s.parse().unwrap()
}

fn range_item(id: &str, cidr: &str, ttl: Option<Value>) -> Value {
    let mut params = json!({"cidr": cidr});
    if let Some(ttl) = ttl {
        params["ttl_seconds"] = ttl;
    }
    json!({"task_id": id, "parameters": params})
}

fn platform_cfg(url: &str) -> Config {
    let mut cfg = test_cfg();
    cfg.api_base_url = url.to_string();
    cfg
}

#[test]
fn an_address_that_is_not_global_is_refused_with_no_command_and_no_claim() {
    let (_d, store) = fresh();
    for addr in ["10.1.2.3", "192.168.1.1", "100.64.0.1", "172.16.9.9", "::ffff:10.0.0.1", "::ffff:127.0.0.1", "fd00::1", "2001:db8::1"] {
        let body = run("block_ip", &block_item("t-1", addr, None), &store, T0);
        assert_eq!(body["outcome"], "refused", "{addr}");
        assert_eq!(body["status"], "error", "{addr}");
    }
    assert!(recorded().is_empty());
    assert!(!store.path().exists(), "a refusal must come before any state write");
}

#[test]
fn the_platform_given_as_a_mapped_address_is_refused() {
    let (_d, store) = fresh();
    let cfg = platform_cfg("https://57.154.210.55");
    let body = handle_at("block_ip", &block_item("t-1", "::ffff:57.154.210.55", None), &cfg, Some(Os::Linux), &store, T0);
    assert_eq!(body["outcome"], "refused");
    assert!(recorded().is_empty() && !store.path().exists());
}

#[test]
fn the_gateway_and_a_dns_server_are_refused_before_any_command() {
    let (_d, store) = fresh();
    set_test_host_addrs(HostAddrs { gateways: vec![ip("45.33.32.1")], dns: vec![ip("8.8.8.8")] });
    for addr in ["45.33.32.1", "8.8.8.8"] {
        let body = run("block_ip", &block_item("t-1", addr, None), &store, T0);
        assert_eq!(body["outcome"], "refused", "{addr}");
    }
    assert!(recorded().is_empty() && !store.path().exists());
    // The same code path still blocks a different address on that host.
    assert_eq!(run("block_ip", &block_item("t-2", "8.8.4.4", None), &store, T0)["outcome"], "applied");
}

#[test]
fn a_range_is_one_rule_under_the_same_claim_rules() {
    let (_d, store) = fresh();
    let body = run("block_ip", &range_item("t-1", "45.33.32.0/24", Some(json!(3600))), &store, T0);
    assert_eq!(body["status"], "success");
    assert_eq!(body["outcome"], "applied");
    assert_eq!(body["expires_in"], 3600);
    assert_eq!(body["verify"], json!({"ok": true, "check": "firewall_rule_present"}));
    let claims = store.load().unwrap().claims;
    assert_eq!((claims[0].target.as_str(), claims[0].expires_at), ("45.33.32.0/24", T0 + 3600));
    assert!(recorded().iter().any(|l| l == "iptables -w -C OMNI_BLOCK -s 45.33.32.0/24 -j DROP"), "{:?}", recorded());
    assert_eq!(run("block_ip", &range_item("t-1", "45.33.32.0/24", Some(json!(3600))), &store, T0 + 5)["outcome"], "already_applied");
}

#[test]
fn a_range_written_with_host_bits_is_the_same_network() {
    let (_d, store) = fresh();
    run("block_ip", &range_item("t-1", "45.33.32.77/24", None), &store, T0);
    assert_eq!(store.load().unwrap().claims[0].target, "45.33.32.0/24");
}

#[test]
fn a_range_is_undone_by_giving_the_same_cidr() {
    let (_d, store) = fresh();
    run("block_ip", &range_item("t-1", "45.33.32.0/24", None), &store, T0);
    with_recorder(|r| r.clear_calls());
    let body = run("unblock_ip", &json!({"parameters": {"cidr": "45.33.32.0/24", "block_id": "t-1"}}), &store, T0 + 9);
    assert_eq!(body["status"], "success");
    assert_eq!(body["outcome"], "removed");
    assert!(store.load().unwrap().claims.is_empty());
    assert!(recorded().iter().any(|l| l == "iptables -w -D OMNI_BLOCK -s 45.33.32.0/24 -j DROP"), "{:?}", recorded());
}

#[test]
fn a_range_the_agent_must_not_block_is_refused_without_a_command() {
    let (_d, store) = fresh();
    let cfg = platform_cfg("https://57.154.210.55");
    for cidr in ["64.0.0.0/7", "0.0.0.0/0", "2600::/31", "57.154.0.0/16", "57.154.210.55/32", "10.0.0.0/16", "not-a-network", "45.33.32.0/33", ""] {
        let body = handle_at("block_ip", &range_item("t-1", cidr, None), &cfg, Some(Os::Linux), &store, T0);
        assert_eq!(body["outcome"], "refused", "{cidr:?}");
    }
    assert!(recorded().is_empty() && !store.path().exists());
}

#[test]
fn an_address_and_a_cidr_together_are_refused_and_so_is_neither() {
    let (_d, store) = fresh();
    let both = json!({"task_id": "t-1", "parameters": {"ip_address": "45.33.32.156", "cidr": "45.33.32.0/24"}});
    assert_eq!(run("block_ip", &both, &store, T0)["outcome"], "refused");
    let neither = json!({"task_id": "t-1", "parameters": {}});
    assert_eq!(run("block_ip", &neither, &store, T0)["outcome"], "refused");
    assert!(recorded().is_empty());
}

#[test]
fn this_build_reports_the_range_token() {
    assert!(SUPPORTED_TOKENS.contains(&"block_ip_range"));
    assert!(SUPPORTED_TOKENS.contains(&"block_ip_ttl"));
}

#[test]
fn a_command_a_security_product_stops_is_named_and_not_retried() {
    for code in [5, 225, 4551] {
        let (_d, store) = fresh();
        with_recorder(|r| {
            r.fail_next(1); // the chain is not there
            r.fail_spawn(code); // and creating it is stopped
        });
        let body = run("block_ip", &block_item("t-1", "45.33.32.156", None), &store, T0);
        assert_eq!(body["status"], "error", "{code}");
        assert_eq!(body["outcome"], "blocked_by_local_security", "{code}");
        let creates = recorded().iter().filter(|l| l.contains(" -N OMNI_BLOCK")).count();
        assert_eq!(creates, 1, "no automatic retry ({code}): {:?}", recorded());
        assert!(store.load().unwrap().claims.is_empty(), "the claim is given back");
        with_recorder(|r| r.clear_calls());
    }
}

#[test]
fn a_complaint_naming_a_policy_block_gives_the_same_outcome() {
    let (_d, store) = fresh();
    with_recorder(|r| {
        r.fail_next(1);
        r.script.push_back(Err("This program is blocked by group policy.".to_string()));
    });
    let body = run("block_ip", &block_item("t-1", "45.33.32.156", None), &store, T0);
    assert_eq!(body["outcome"], "blocked_by_local_security");
}

#[test]
fn an_ordinary_firewall_failure_has_no_outcome_name() {
    let (_d, store) = fresh();
    with_recorder(|r| r.fail_next(2));
    let body = run("block_ip", &block_item("t-1", "45.33.32.156", None), &store, T0);
    assert_eq!(body["status"], "error");
    assert!(body.get("outcome").is_none());
}
