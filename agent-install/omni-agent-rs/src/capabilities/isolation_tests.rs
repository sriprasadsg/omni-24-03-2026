//! Isolation against the recorder: no test starts a firewall command or touches a network.
//!
//! The recorder answers from a queue and with success when the queue is empty. The scripts below
//! count the commands of each phase (allow, check, block, effective) so a test can make exactly
//! one of them fail.

use super::*;
use crate::capabilities::privileged::with_recorder;
use crate::capabilities::response_state::Isolation;

pub(super) const T0: i64 = 1_761_900_000;
pub(super) const PLATFORM: &str = "https://57.154.210.55";
/// Linux, platform as an address: 3 chains and 6 accept rules per family and the two families.
pub(super) const LINUX_ALLOW: usize = 18;
/// Per family: 3 DROP rules and 3 hooks.
pub(super) const LINUX_BLOCK: usize = 12;
/// The checks after the block: one per hook.
pub(super) const LINUX_EFFECTIVE: usize = 6;

pub(super) const POLICY: &str = "Domain Profile Settings:\n------\nFirewall Policy                       BlockInbound,AllowOutbound\n\n\
Private Profile Settings:\n------\nFirewall Policy                       BlockInbound,AllowOutbound\n\n\
Public Profile Settings:\n------\nFirewall Policy                       AllowInbound,AllowOutbound\n";
pub(super) const BLOCKED: &str = "Domain Profile Settings:\n------\nFirewall Policy                       BlockInbound,BlockOutbound\n\n\
Private Profile Settings:\n------\nFirewall Policy                       BlockInbound,BlockOutbound\n\n\
Public Profile Settings:\n------\nFirewall Policy                       BlockInbound,BlockOutbound\n";

pub(super) fn cfg(url: &str) -> Config {
    serde_norway::from_str(&format!(
        "api_base_url: \"{url}\"\ntenant_id: tenant_test\nagent_id: agent_test\nagent_token: tok_test\nregistration_key: reg_test\n"
    ))
    .expect("parse test config")
}

pub(super) fn fresh() -> (tempfile::TempDir, Store) {
    let dir = tempfile::tempdir().unwrap();
    let store = Store::at(dir.path().join("response_state.json"));
    (dir, store)
}

pub(super) fn lines() -> Vec<String> {
    with_recorder(|r| r.lines())
}

pub(super) fn no_lookup(_: &str) -> Vec<IpAddr> {
    Vec::new()
}

pub(super) fn no_resolvers() -> Vec<IpAddr> {
    Vec::new()
}

pub(super) fn isolate(store: &Store, os: Os, id: &str, now: i64, connect_ok: bool) -> Value {
    apply_with(store, os, &cfg(PLATFORM), id, now, &no_lookup, &no_resolvers, &|_| connect_ok)
}

/// `n` checks that fail, each followed by the add that succeeds (an empty firewall).
pub(super) fn empty_pairs(n: usize) {
    with_recorder(|r| {
        for _ in 0..n {
            r.fail_next(1);
            r.answer_next("");
        }
    });
}

pub(super) fn oks(n: usize) {
    with_recorder(|r| (0..n).for_each(|_| r.answer_next("")));
}

/// A Linux host with nothing isolated that accepts every step.
pub(super) fn script_linux_apply() {
    script_linux_apply_with(LINUX_ALLOW);
}

pub(super) fn script_linux_apply_with(allow: usize) {
    empty_pairs(allow);
    oks(allow);
    empty_pairs(LINUX_BLOCK);
    oks(LINUX_EFFECTIVE);
}

/// A Windows host: policy read, 4 allow rules added and shown, the policy set, the policy read again.
pub(super) fn script_windows_apply(effective: &str) {
    with_recorder(|r| r.answer_next(POLICY));
    empty_pairs(4);
    oks(4);
    oks(1);
    with_recorder(|r| r.answer_next(effective));
}

pub(super) fn is_allow(line: &str) -> bool {
    (line.contains(" -A ") && line.ends_with("ACCEPT")) || (line.contains("add rule") && line.contains("action=allow"))
}

pub(super) fn is_block(line: &str) -> bool {
    (line.contains(" -A ") && line.ends_with("DROP")) || line.contains(" -I ") || line.contains("set allprofiles")
}

pub(super) fn state_isolation(store: &Store) -> Option<Isolation> {
    store.load().unwrap().isolation
}

pub(super) fn record(id: &str, revert_at: i64, confirmed: bool) -> Isolation {
    Isolation { id: id.into(), started_at: T0, revert_at, confirmed, saved_policy: Value::Null }
}

pub(super) fn seed(store: &Store, iso: Isolation) {
    store.update(|s| s.isolation = Some(iso)).unwrap();
}

pub(super) fn contract() -> Option<Value> {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../shared/agent-response-contract.json");
    Some(serde_json::from_str(&std::fs::read_to_string(path).ok()?).expect("valid JSON"))
}

#[test]
fn ordering_every_allow_command_comes_before_the_first_block_command_on_both_systems() {
    for os in [Os::Linux, Os::Windows] {
        let (_d, store) = fresh();
        with_recorder(|r| r.clear_calls());
        match os {
            Os::Linux => script_linux_apply(),
            Os::Windows => script_windows_apply(BLOCKED),
        }
        let body = isolate(&store, os, "iso-1", T0, true);
        assert_eq!(body["outcome"], "isolated", "{os:?}: {body}");
        let got = lines();
        let last_allow = got.iter().rposition(|l| is_allow(l)).expect("an allow command");
        let first_block = got.iter().position(|l| is_block(l)).expect("a block command");
        assert!(last_allow < first_block, "{os:?}: allow at {last_allow}, block at {first_block}\n{got:#?}");
        // The checks that the rules exist sit between the last allow and the first block.
        let between = &got[last_allow + 1..first_block];
        let expected = if os == Os::Linux { LINUX_ALLOW } else { 4 };
        let is_check = |l: &&String| (l.contains(" -C ") || l.contains(" -n -L ") || l.contains("show rule")) && !l.ends_with("DROP");
        let checks = between.iter().filter(is_check).count();
        assert_eq!(checks, expected, "{os:?}: {between:#?}");
    }
}

#[test]
fn the_record_with_revert_at_is_on_disk_before_the_first_firewall_command() {
    let (_d, store) = fresh();
    // An unwritable record stops everything: not one command ran.
    let missing = Store::at(_d.path().join("no/such/dir/response_state.json"));
    let body = isolate(&missing, Os::Linux, "iso-1", T0, true);
    assert_eq!(body["status"], "error");
    assert!(lines().is_empty(), "{:?}", lines());
    // And on success the record held the revert time the whole way: the self-test reads it.
    script_linux_apply();
    let seen = std::cell::RefCell::new(None);
    let body = apply_with(&store, Os::Linux, &cfg(PLATFORM), "iso-1", T0, &no_lookup, &no_resolvers, &|_| {
        *seen.borrow_mut() = state_isolation(&store);
        true
    });
    assert_eq!(body["outcome"], "isolated");
    let iso = seen.into_inner().expect("the record existed when the self-test ran");
    assert_eq!((iso.id.as_str(), iso.started_at, iso.revert_at, iso.confirmed), ("iso-1", T0, T0 + 14_400, false));
}

#[test]
fn the_linux_commands_are_the_planned_ones() {
    let (_d, store) = fresh();
    script_linux_apply();
    isolate(&store, Os::Linux, "iso-1", T0, true);
    let got = lines();
    assert_eq!(got[0], "iptables -w -n -L OMNI_ISOLATE_IN");
    assert_eq!(got[1], "iptables -w -N OMNI_ISOLATE_IN");
    for expected in [
        "iptables -w -A OMNI_ISOLATE_IN -i lo -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_OUT -o lo -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_IN -s 57.154.210.55 -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_OUT -d 57.154.210.55 -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_IN -p udp --sport 67 --dport 68 -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_OUT -p udp --sport 68 --dport 67 -j ACCEPT",
        "ip6tables -w -A OMNI_ISOLATE_IN -i lo -j ACCEPT",
        "ip6tables -w -A OMNI_ISOLATE_OUT -p ipv6-icmp -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_FWD -j DROP",
        "ip6tables -w -A OMNI_ISOLATE_FWD -j DROP",
        "iptables -w -I INPUT 1 -j OMNI_ISOLATE_IN",
        "iptables -w -I OUTPUT 1 -j OMNI_ISOLATE_OUT",
        "iptables -w -I FORWARD 1 -j OMNI_ISOLATE_FWD",
        "ip6tables -w -I INPUT 1 -j OMNI_ISOLATE_IN",
        "ip6tables -w -I OUTPUT 1 -j OMNI_ISOLATE_OUT",
        "ip6tables -w -I FORWARD 1 -j OMNI_ISOLATE_FWD",
    ] {
        assert!(got.contains(&expected.to_string()), "missing {expected}");
    }
    // The platform is accepted before the chain's DROP, in the same chain.
    let accept = got.iter().position(|l| l == "iptables -w -A OMNI_ISOLATE_IN -s 57.154.210.55 -j ACCEPT").unwrap();
    let drop = got.iter().position(|l| l == "iptables -w -A OMNI_ISOLATE_IN -j DROP").unwrap();
    assert!(accept < drop);
}

#[test]
fn the_windows_commands_are_the_planned_ones() {
    let (_d, store) = fresh();
    script_windows_apply(BLOCKED);
    let body = isolate(&store, Os::Windows, "iso-1", T0, true);
    assert_eq!(body["outcome"], "isolated");
    let got = lines();
    assert_eq!(got[0], "netsh advfirewall show allprofiles firewallpolicy");
    assert_eq!(got[1], "netsh advfirewall firewall show rule name=OmniAgent_Isolate_Allow_Out");
    assert_eq!(
        got[2],
        "netsh advfirewall firewall add rule name=OmniAgent_Isolate_Allow_Out dir=out action=allow remoteip=57.154.210.55"
    );
    assert!(got.contains(&"netsh advfirewall firewall add rule name=OmniAgent_Isolate_Allow_In dir=in action=allow remoteip=57.154.210.55".to_string()));
    assert!(got.contains(&"netsh advfirewall firewall add rule name=OmniAgent_Isolate_Allow_DHCP_Out dir=out action=allow protocol=udp localport=68 remoteport=67".to_string()));
    let set = got.iter().position(|l| l == "netsh advfirewall set allprofiles firewallpolicy blockinbound,blockoutbound").unwrap();
    assert_eq!(set, got.len() - 2, "the policy is set, then read again to check it took");
    assert_eq!(got.last().unwrap(), "netsh advfirewall show allprofiles firewallpolicy");
    // The policy each profile had is saved for the way back.
    let saved = state_isolation(&store).unwrap().saved_policy;
    assert_eq!(saved, json!({"domain": "blockinbound,allowoutbound", "private": "blockinbound,allowoutbound", "public": "allowinbound,allowoutbound"}));
}

#[test]
fn a_failed_allow_rule_stops_before_any_block_and_reverts() {
    let (_d, store) = fresh();
    with_recorder(|r| r.fail_next(2)); // the first chain is missing and cannot be created
    let body = isolate(&store, Os::Linux, "iso-1", T0, true);
    assert_eq!(body["status"], "error");
    assert!(body.get("outcome").is_none());
    let got = lines();
    assert!(got.iter().all(|l| !is_block(l)), "{got:#?}");
    assert!(got.contains(&"iptables -w -X OMNI_ISOLATE_IN".to_string()), "the revert ran");
    assert!(state_isolation(&store).is_none());
}

#[test]
fn rules_that_cannot_be_confirmed_stop_before_the_block() {
    let (_d, store) = fresh();
    empty_pairs(LINUX_ALLOW);
    with_recorder(|r| r.fail_next(1)); // the first rule is not there when checked
    let body = isolate(&store, Os::Linux, "iso-1", T0, true);
    assert_eq!(body["status"], "error");
    assert!(body["error"].as_str().unwrap().contains("could not be confirmed"));
    assert!(lines().iter().all(|l| !is_block(l)));
    assert!(state_isolation(&store).is_none());
}

#[test]
fn a_failed_block_step_reverts() {
    let (_d, store) = fresh();
    empty_pairs(LINUX_ALLOW);
    oks(LINUX_ALLOW);
    with_recorder(|r| r.fail_next(2)); // the first DROP cannot be added
    let body = isolate(&store, Os::Linux, "iso-1", T0, true);
    assert_eq!(body["status"], "error");
    assert!(lines().iter().all(|l| !l.contains(" -I ")), "no hook was put in");
    assert!(lines().contains(&"iptables -w -X OMNI_ISOLATE_OUT".to_string()));
    assert!(state_isolation(&store).is_none());
}

#[test]
fn a_hook_that_is_not_in_place_answers_not_effective_and_reverts() {
    let (_d, store) = fresh();
    empty_pairs(LINUX_ALLOW);
    oks(LINUX_ALLOW);
    empty_pairs(LINUX_BLOCK);
    with_recorder(|r| r.fail_next(1)); // the first hook is not there when checked
    let body = isolate(&store, Os::Linux, "iso-1", T0, true);
    assert_eq!(body["outcome"], "not_effective");
    assert_eq!(body["verify"], json!({"ok": false, "check": "management_connection_open"}));
    assert!(lines().contains(&"iptables -w -D INPUT -j OMNI_ISOLATE_IN".to_string()));
    assert!(state_isolation(&store).is_none());
}

#[test]
fn a_group_policy_that_overrides_the_local_policy_answers_not_effective_and_restores_each_profile() {
    let (_d, store) = fresh();
    script_windows_apply(POLICY); // the policy still reads as before
    let body = isolate(&store, Os::Windows, "iso-1", T0, true);
    assert_eq!(body["outcome"], "not_effective");
    let got = lines();
    let public = got.iter().position(|l| l == "netsh advfirewall set publicprofile firewallpolicy allowinbound,allowoutbound").expect("public restored");
    assert!(got.contains(&"netsh advfirewall set domainprofile firewallpolicy blockinbound,allowoutbound".to_string()));
    let first_delete = got.iter().position(|l| l.contains("delete rule")).expect("rules removed");
    assert!(public < first_delete, "the block policy is lifted before the allow rules go");
    assert!(state_isolation(&store).is_none());
}

#[test]
fn a_failed_self_test_reverts_at_once_and_equals_the_contract_example() {
    let (_d, store) = fresh();
    script_linux_apply();
    let body = isolate(&store, Os::Linux, "iso-1", T0, false);
    if let Some(c) = contract() {
        assert_eq!(body, c["examples"]["isolate_self_test_failed"]);
    }
    assert_eq!(body["outcome"], "self_test_failed");
    assert!(state_isolation(&store).is_none());
    // Reverting lifts the block (unhook) before the allow rules and chains go (flush, delete).
    let got = lines();
    let last_unhook = got.iter().rposition(|l| l.contains(" -D ")).unwrap();
    let first_flush = got.iter().position(|l| l.contains(" -F ")).unwrap();
    assert!(last_unhook < first_flush);
}

#[test]
fn on_windows_a_revert_restores_the_policy_before_it_removes_the_allow_rules() {
    let (_d, store) = fresh();
    script_windows_apply(BLOCKED);
    isolate(&store, Os::Windows, "iso-1", T0, false);
    let got = lines();
    let last_set = got.iter().rposition(|l| l.contains("firewallpolicy") && l.contains("profile ")).unwrap();
    let first_delete = got.iter().position(|l| l.contains("delete rule")).unwrap();
    assert!(last_set < first_delete);
    assert!(got.iter().filter(|l| l.contains("delete rule")).all(|l| l.contains("OmniAgent_Isolate_Allow_")), "only the agent's own rules are removed");
}

#[test]
fn a_success_equals_the_contract_example_and_leaves_the_record() {
    let (_d, store) = fresh();
    script_linux_apply();
    let body = isolate(&store, Os::Linux, "iso-1", T0, true);
    if let Some(c) = contract() {
        assert_eq!(body, c["examples"]["isolate_done"]);
    }
    let iso = state_isolation(&store).unwrap();
    assert_eq!((iso.id.as_str(), iso.revert_at, iso.confirmed), ("iso-1", T0 + 14_400, false));
}

#[test]
fn the_record_uses_the_names_later_releases_read() {
    let (_d, store) = fresh();
    script_linux_apply();
    isolate(&store, Os::Linux, "iso-1", T0, true);
    let text = std::fs::read_to_string(store.path()).unwrap();
    for key in ["\"isolation\"", "\"id\"", "\"startedAt\"", "\"revertAt\"", "\"confirmed\"", "\"savedPolicy\""] {
        assert!(text.contains(key), "{key} missing from {text}");
    }
}

#[test]
fn a_repeat_with_the_same_id_or_another_id_changes_nothing() {
    let (_d, store) = fresh();
    script_linux_apply();
    isolate(&store, Os::Linux, "iso-1", T0, true);
    let after_first = lines().len();
    let same = isolate(&store, Os::Linux, "iso-1", T0 + 60, true);
    let other = isolate(&store, Os::Linux, "iso-2", T0 + 120, true);
    assert_eq!(same["outcome"], "already_applied");
    assert_eq!(other["outcome"], "already_applied");
    assert_eq!(lines().len(), after_first, "no firewall command for a repeat");
    let iso = state_isolation(&store).unwrap();
    assert_eq!((iso.id.as_str(), iso.revert_at), ("iso-1", T0 + 14_400), "the first revert time is kept");
}

#[test]
fn a_platform_url_with_no_host_or_an_unresolvable_name_refuses_and_changes_nothing() {
    for url in ["not a url", "file:///etc/hosts", "https://platform.example"] {
        let (_d, store) = fresh();
        let body = apply_with(&store, Os::Linux, &cfg(url), "iso-1", T0, &no_lookup, &no_resolvers, &|_| true);
        assert_eq!((body["status"].as_str(), body["outcome"].as_str()), (Some("error"), Some("refused")), "{url}");
        assert!(lines().is_empty());
        assert!(!store.path().exists());
    }
    assert!(!platform_has_host(&cfg("not a url")));
    assert!(platform_has_host(&cfg(PLATFORM)));
}

#[test]
fn a_bad_instruction_id_is_refused_before_anything_happens() {
    let (_d, store) = fresh();
    let long = "a".repeat(65);
    for id in ["", "a b", "x;y", long.as_str()] {
        assert_eq!(isolate(&store, Os::Linux, id, T0, true)["outcome"], "refused", "{id:?}");
    }
    assert!(lines().is_empty());
}

#[test]
fn a_platform_given_by_name_keeps_every_address_and_the_resolvers_open() {
    let lookup = |_: &str| -> Vec<IpAddr> {
        ["203.0.113.9", "198.51.100.4", "203.0.113.9"].iter().map(|a| a.parse().unwrap()).collect()
    };
    let resolvers = || -> Vec<IpAddr> { vec!["192.0.2.53".parse().unwrap()] };
    let carve = carve_out(&cfg("https://platform.example:8443"), &lookup, &resolvers).unwrap();
    assert_eq!(carve.addresses.len(), 2, "duplicates are dropped");
    assert_eq!((carve.dns.len(), carve.port), (1, 8443));
    // A literal needs no resolver.
    let literal = carve_out(&cfg(PLATFORM), &lookup, &resolvers).unwrap();
    assert_eq!((literal.addresses.len(), literal.dns.len(), literal.port), (1, 0, 443));

    let (_d, store) = fresh();
    // Two platform addresses and one resolver: 15 allow steps for IPv4, 9 for IPv6.
    script_linux_apply_with(24);
    let body = apply_with(&store, Os::Linux, &cfg("https://platform.example"), "iso-1", T0, &lookup, &resolvers, &|_| true);
    assert_eq!(body["outcome"], "isolated");
    let got = lines();
    for expected in [
        "iptables -w -A OMNI_ISOLATE_OUT -d 203.0.113.9 -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_OUT -d 198.51.100.4 -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_OUT -d 192.0.2.53 -p udp --dport 53 -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_IN -s 192.0.2.53 -p udp --sport 53 -j ACCEPT",
    ] {
        assert!(got.contains(&expected.to_string()), "missing {expected}");
    }
}

#[test]
fn a_revert_that_fails_keeps_the_record_and_makes_it_due_now_until_it_works() {
    let (_d, store) = fresh();
    script_linux_apply();
    with_recorder(|r| {
        r.answer_next(""); // the first hook is there ...
        r.fail_next(1); // ... and cannot be removed
    });
    let body = isolate(&store, Os::Linux, "iso-1", T0, false);
    assert!(body["error"].as_str().unwrap().contains("keeps trying"));
    let iso = state_isolation(&store).expect("the record stays");
    assert_eq!(iso.revert_at, T0, "due now");
    assert!(lines().iter().all(|l| !l.contains(" -F ") && !l.contains(" -X ")), "the allow rules stay while the block is not lifted");
    // The next pass tries again and, now that it works, the host is released.
    with_recorder(|r| r.clear_calls());
    let pass = revert_due(&store, Os::Linux, T0 + 15);
    assert!(pass.reverted);
    assert!(state_isolation(&store).is_none());
}
