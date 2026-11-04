//! The block, check and removal plans against the recorder: no test starts a firewall command.

use super::*;
use crate::capabilities::privileged::with_recorder;

fn v4() -> IpAddr {
    "45.33.32.156".parse().unwrap()
}

fn lines() -> Vec<String> {
    with_recorder(|r| r.lines())
}

/// Scripts an empty firewall: every check fails once, every add succeeds.
fn empty_linux_firewall() {
    with_recorder(|r| {
        // chain: -L fails, -N ok; hooks: -C fails, -I ok (twice); rules: -C fails, -A ok (twice)
        for _ in 0..5 {
            r.fail_next(1);
            r.answer_next("");
        }
    });
}

#[test]
fn linux_block_creates_the_chain_hooks_and_both_directions_with_wait_flag() {
    empty_linux_firewall();
    apply_block(Os::Linux, v4()).unwrap();
    let got = lines();
    assert_eq!(
        got,
        vec![
            "iptables -w -n -L OMNI_BLOCK",
            "iptables -w -N OMNI_BLOCK",
            "iptables -w -C INPUT -j OMNI_BLOCK",
            "iptables -w -I INPUT 1 -j OMNI_BLOCK",
            "iptables -w -C OUTPUT -j OMNI_BLOCK",
            "iptables -w -I OUTPUT 1 -j OMNI_BLOCK",
            "iptables -w -C OMNI_BLOCK -s 45.33.32.156 -j DROP",
            "iptables -w -A OMNI_BLOCK -s 45.33.32.156 -j DROP",
            "iptables -w -C OMNI_BLOCK -d 45.33.32.156 -j DROP",
            "iptables -w -A OMNI_BLOCK -d 45.33.32.156 -j DROP",
        ]
    );
    assert!(got.iter().all(|l| l.contains(" -w ")));
}

#[test]
fn a_second_apply_adds_nothing_because_every_check_passes() {
    apply_block(Os::Linux, v4()).unwrap();
    let got = lines();
    assert_eq!(got.len(), 5);
    assert!(got.iter().all(|l| !l.contains(" -A ") && !l.contains(" -I ") && !l.contains(" -N ")));
}

#[test]
fn the_final_check_asks_for_both_hooks_and_both_rules() {
    assert!(rule_present(Os::Linux, v4()).unwrap());
    assert_eq!(
        lines(),
        vec![
            "iptables -w -C INPUT -j OMNI_BLOCK",
            "iptables -w -C OUTPUT -j OMNI_BLOCK",
            "iptables -w -C OMNI_BLOCK -s 45.33.32.156 -j DROP",
            "iptables -w -C OMNI_BLOCK -d 45.33.32.156 -j DROP",
        ]
    );
}

#[test]
fn a_missing_rule_is_reported_as_not_present() {
    with_recorder(|r| {
        r.answer_next("");
        r.answer_next("");
        r.answer_next("");
        r.fail_next(1);
    });
    assert!(!rule_present(Os::Linux, v4()).unwrap());
}

#[test]
fn ipv6_uses_ip6tables_for_every_call() {
    empty_linux_firewall();
    let v6: IpAddr = "2600:1f18::1".parse().unwrap();
    apply_block(Os::Linux, v6).unwrap();
    let got = lines();
    assert_eq!(got.len(), 10);
    assert!(got.iter().all(|l| l.starts_with("ip6tables ")));
    assert!(got.contains(&"ip6tables -w -A OMNI_BLOCK -s 2600:1f18::1 -j DROP".to_string()));
}

#[test]
fn an_ipv4_mapped_address_is_treated_as_the_ipv4_address() {
    let mapped: IpAddr = "::ffff:45.33.32.156".parse().unwrap();
    apply_block(Os::Linux, mapped).unwrap();
    assert!(lines().iter().all(|l| l.starts_with("iptables ")));
    assert!(lines().iter().any(|l| l.contains("45.33.32.156")));
}

#[test]
fn windows_block_adds_one_inbound_and_one_outbound_rule() {
    with_recorder(|r| {
        r.fail_next(1);
        r.answer_next("");
        r.fail_next(1);
        r.answer_next("");
    });
    apply_block(Os::Windows, v4()).unwrap();
    assert_eq!(
        lines(),
        vec![
            "netsh advfirewall firewall show rule name=OmniAgent_Block_45.33.32.156_in",
            "netsh advfirewall firewall add rule name=OmniAgent_Block_45.33.32.156_in dir=in action=block remoteip=45.33.32.156",
            "netsh advfirewall firewall show rule name=OmniAgent_Block_45.33.32.156_out",
            "netsh advfirewall firewall add rule name=OmniAgent_Block_45.33.32.156_out dir=out action=block remoteip=45.33.32.156",
        ]
    );
}

#[test]
fn windows_treats_no_rules_match_as_absent_even_when_netsh_exits_zero() {
    with_recorder(|r| r.answer_next("No rules match the specified criteria.\n"));
    assert!(!rule_present(Os::Windows, v4()).unwrap());
}

#[test]
fn windows_present_check_shows_both_rules() {
    assert!(rule_present(Os::Windows, v4()).unwrap());
    assert_eq!(lines().len(), 2);
}

#[test]
fn windows_removal_deletes_both_names_and_tries_the_legacy_name() {
    let removed = remove_block(Os::Windows, v4()).unwrap();
    assert!(removed);
    let got = lines();
    assert!(got.contains(&"netsh advfirewall firewall delete rule name=OmniAgent_Block_45.33.32.156_in".to_string()));
    assert!(got.contains(&"netsh advfirewall firewall delete rule name=OmniAgent_Block_45.33.32.156_out".to_string()));
    assert!(got.contains(&"netsh advfirewall firewall delete rule name=OmniAgent_Block_45.33.32.156".to_string()));
}

#[test]
fn removal_of_an_address_that_is_not_blocked_deletes_nothing() {
    with_recorder(|r| r.fail_next(3));
    assert!(!remove_block(Os::Linux, v4()).unwrap());
    assert!(lines().iter().all(|l| !l.contains(" -D ")));
}

#[test]
fn a_legacy_rule_that_will_not_delete_does_not_fail_the_removal() {
    with_recorder(|r| {
        r.fail_next(2); // the chain rules are not there
        r.answer_next(""); // legacy check passes
        r.fail_next(1); // legacy delete fails
    });
    assert!(remove_block(Os::Linux, v4()).is_ok());
}

#[test]
fn a_real_delete_failure_is_returned() {
    with_recorder(|r| {
        r.answer_next(""); // -s check passes
        r.fail_next(1); // -s delete fails
    });
    assert!(remove_block(Os::Linux, v4()).is_err());
}

#[test]
fn an_address_is_always_its_own_argv_element() {
    for os in [Os::Linux, Os::Windows] {
        let addr = "45.33.32.156";
        for step in block_plan(os, v4()) {
            for cmd in [&step.check, &step.add] {
                let joined_inside = cmd.args.iter().any(|a| a.contains(addr) && a.contains(' '));
                assert!(!joined_inside, "{:?}", cmd);
                assert!(cmd.args.iter().all(|a| !a.contains(' ')));
            }
        }
    }
}

#[test]
fn the_current_os_is_linux_on_the_test_machine() {
    #[cfg(target_os = "linux")]
    assert_eq!(Os::current(), Some(Os::Linux));
}

#[test]
fn an_apply_error_is_returned() {
    with_recorder(|r| {
        r.fail_next(1); // chain missing
        r.fail_next(1); // and creating it fails
    });
    assert!(apply_block(Os::Linux, v4()).is_err());
}

// ── WR-19: only a definite "not there" is absent ───────────────────────────

#[test]
fn a_check_that_cannot_run_fails_the_block_and_adds_nothing() {
    with_recorder(|r| r.fail_spawn(2)); // iptables is not there to ask
    assert!(apply_block(Os::Linux, v4()).is_err());
    assert_eq!(lines(), vec!["iptables -w -n -L OMNI_BLOCK"], "nothing is added on a guess");
}

#[test]
fn a_check_that_fails_for_another_reason_adds_no_second_rule() {
    // Exit code 4: the xtables lock could not be taken. The rule may well be there already.
    with_recorder(|r| {
        r.answer_next("");
        r.answer_next("");
        r.answer_next("");
        r.fail_exit(4, "Another app is currently holding the xtables lock.");
    });
    assert!(apply_block(Os::Linux, v4()).is_err());
    assert!(lines().iter().all(|l| !l.contains(" -A ")), "{:?}", lines());
}


#[test]
fn iptables_exit_code_one_is_the_only_linux_absent() {
    with_recorder(|r| {
        r.fail_exit(1, "iptables: No chain/target/match by that name.");
        r.answer_next("");
    });
    let step = &block_plan(Os::Linux, v4())[0];
    assert!(!step.check.probe().unwrap());
    assert!(step.check.probe().unwrap());
    for code in [2, 3, 4] {
        with_recorder(|r| r.fail_exit(code, "x"));
        assert!(step.check.probe().is_err(), "{code}");
    }
}

#[test]
fn a_check_that_cannot_run_during_removal_is_an_error_and_deletes_nothing() {
    with_recorder(|r| r.fail_spawn(2));
    assert!(remove_block(Os::Linux, v4()).is_err());
    assert!(lines().iter().all(|l| !l.contains(" -D ")), "{:?}", lines());
}

#[test]
fn a_legacy_check_that_cannot_run_does_not_fail_the_removal() {
    with_recorder(|r| {
        r.fail_next(2); // the chain rules are not there
        r.fail_spawn(2); // the legacy rule cannot be asked about
    });
    assert_eq!(remove_block(Os::Linux, v4()).unwrap(), false);
}

#[test]
fn netsh_exit_code_one_is_absent_in_any_language_and_a_blocked_netsh_is_an_error() {
    // netsh prints "no rules match" in the local language and exits 1.
    with_recorder(|r| r.fail_exit(1, "Es wurden keine Regeln gefunden, die den Kriterien entsprechen."));
    assert!(!rule_present(Os::Windows, v4()).unwrap());
    with_recorder(|r| r.fail_spawn(225)); // a security product stopped netsh
    assert!(matches!(rule_present(Os::Windows, v4()), Err(RemediationError::BlockedByLocalSecurity(_))));
}

#[test]
fn a_present_check_that_cannot_run_is_an_error_not_a_no() {
    with_recorder(|r| r.fail_spawn(2));
    assert!(rule_present(Os::Linux, v4()).is_err());
}
