//! Expiry and start-up passes against the recorder. Time is a parameter, so nothing sleeps and no
//! test makes a real firewall call.

use super::*;
use crate::capabilities::firewall::Os;
use crate::capabilities::privileged::with_recorder;

const T0: i64 = 1_761_900_000;
const A: &str = "45.33.32.156";
const B: &str = "45.33.32.157";

fn store_with(claims: &[(&str, &str, i64)]) -> (tempfile::TempDir, Store) {
    let dir = tempfile::tempdir().unwrap();
    let store = Store::at(dir.path().join("response_state.json"));
    store
        .update(|s| {
            for (target, id, expires_at) in claims {
                s.add_claim(target, id, *expires_at, 0);
            }
        })
        .unwrap();
    (dir, store)
}

fn lines() -> Vec<String> {
    with_recorder(|r| r.lines())
}

/// Scripts a Linux firewall with nothing in it: five checks fail, each add succeeds.
fn empty_linux_firewall() {
    with_recorder(|r| {
        for _ in 0..5 {
            r.fail_next(1);
            r.answer_next("");
        }
    });
}

#[test]
fn a_claim_that_expires_exactly_now_is_removed_with_its_rule() {
    let (_d, store) = store_with(&[(A, "a", T0 + 100)]);
    let report = expire_due(&store, Os::Linux, T0 + 100);
    assert!(store.load().unwrap().claims.is_empty());
    assert_eq!(report.removed, vec![A.to_string()]);
    assert_eq!(report.dropped, 1);
    let got = lines();
    assert!(got.contains(&format!("iptables -w -D OMNI_BLOCK -s {A} -j DROP")), "{got:?}");
    assert!(got.contains(&format!("iptables -w -D OMNI_BLOCK -d {A} -j DROP")), "{got:?}");
}

#[test]
fn a_claim_one_second_before_its_time_is_left_alone() {
    let (_d, store) = store_with(&[(A, "a", T0 + 100)]);
    let report = expire_due(&store, Os::Linux, T0 + 99);
    assert_eq!(store.load().unwrap().claims.len(), 1);
    assert_eq!(report, PassReport::default());
    assert!(lines().is_empty());
}

#[test]
fn two_claims_on_one_address_one_expired_gives_up_the_claim_but_not_the_rule() {
    let (_d, store) = store_with(&[(A, "a", T0 + 10), (A, "b", T0 + 1000)]);
    let report = expire_due(&store, Os::Linux, T0 + 20);
    let left = store.load().unwrap().claims;
    assert_eq!(left.len(), 1);
    assert_eq!(left[0].block_id, "b");
    assert_eq!(report.dropped, 1);
    assert!(report.removed.is_empty());
    assert!(lines().is_empty(), "no command may run while a live claim holds the rule: {:?}", lines());
}

#[test]
fn the_rule_goes_only_when_the_last_claim_has_expired() {
    let (_d, store) = store_with(&[(A, "a", T0 + 10), (A, "b", T0 + 50)]);
    expire_due(&store, Os::Linux, T0 + 20);
    assert!(lines().is_empty());
    expire_due(&store, Os::Linux, T0 + 50);
    assert!(store.load().unwrap().claims.is_empty());
    assert!(lines().iter().any(|l| l.contains(" -D OMNI_BLOCK -s ")));
}

#[test]
fn a_failed_removal_keeps_the_claim_and_the_next_pass_clears_it() {
    let (_d, store) = store_with(&[(A, "a", T0 + 10)]);
    with_recorder(|r| {
        r.answer_next(""); // the -s rule is there
        r.fail_next(1); // and cannot be deleted
    });
    let report = expire_due(&store, Os::Linux, T0 + 11);
    assert_eq!(report.failed, vec![A.to_string()]);
    assert_eq!(store.load().unwrap().claims.len(), 1, "the claim must stay while the rule may still be there");

    with_recorder(|r| r.clear_calls());
    let report = expire_due(&store, Os::Linux, T0 + 26);
    assert!(report.failed.is_empty());
    assert_eq!(report.removed, vec![A.to_string()]);
    assert!(store.load().unwrap().claims.is_empty());
}

#[test]
fn one_failing_address_does_not_hold_back_another() {
    let (_d, store) = store_with(&[(A, "a", T0 + 10), (B, "b", T0 + 10)]);
    with_recorder(|r| {
        r.answer_next(""); // A: -s rule there
        r.fail_next(1); // A: delete fails
    });
    let report = expire_due(&store, Os::Linux, T0 + 11);
    assert_eq!(report.failed, vec![A.to_string()]);
    assert_eq!(report.removed, vec![B.to_string()]);
    let left = store.load().unwrap().claims;
    assert_eq!(left.len(), 1);
    assert_eq!(left[0].target, A);
}

#[test]
fn a_corrupt_state_file_is_reported_and_left_exactly_as_it_was() {
    let (_d, store) = store_with(&[]);
    std::fs::write(store.path(), "{ not json").unwrap();
    let report = expire_due(&store, Os::Linux, T0);
    assert!(report.error.is_some());
    assert_eq!(std::fs::read_to_string(store.path()).unwrap(), "{ not json");
    let report = start_up(&store, Os::Linux, T0);
    assert!(report.error.is_some());
    assert_eq!(std::fs::read_to_string(store.path()).unwrap(), "{ not json");
    assert!(lines().is_empty());
}

#[test]
fn an_empty_claim_list_and_a_missing_file_are_a_no_op() {
    let (_d, store) = store_with(&[]);
    assert_eq!(expire_due(&store, Os::Linux, T0), PassReport::default());
    assert_eq!(start_up(&store, Os::Windows, T0), PassReport::default());
    assert!(lines().is_empty());
    assert!(!store.path().exists(), "a pass over nothing must not create the file");
}

#[test]
fn claims_with_equal_expiry_give_the_same_result_in_either_order() {
    let mut seen = Vec::new();
    for order in [[("a", A), ("b", A), ("c", B)], [("c", B), ("b", A), ("a", A)]] {
        let claims: Vec<(&str, &str, i64)> = order.iter().map(|(id, t)| (*t, *id, T0 + 5)).collect();
        let (_d, store) = store_with(&claims);
        with_recorder(|r| r.clear_calls());
        expire_due(&store, Os::Linux, T0 + 5);
        let mut deletes: Vec<String> = lines().into_iter().filter(|l| l.contains(" -D ")).collect();
        deletes.sort();
        assert!(store.load().unwrap().claims.is_empty());
        seen.push(deletes);
    }
    assert_eq!(seen[0], seen[1]);
    assert_eq!(seen[0].len(), 6, "one -s and one -d delete plus the legacy one for each of two addresses");
}

#[test]
fn a_claim_with_a_target_that_is_not_an_address_is_dropped_without_a_command() {
    let (_d, store) = store_with(&[("not-an-address", "a", T0)]);
    let report = expire_due(&store, Os::Linux, T0 + 1);
    assert_eq!(report.dropped, 1);
    assert!(store.load().unwrap().claims.is_empty());
    assert!(lines().is_empty());
}

#[test]
fn start_up_on_linux_puts_a_live_rule_back_and_drops_an_expired_one() {
    let (_d, store) = store_with(&[(A, "a", T0 + 1000), (B, "b", T0 - 5)]);
    // B (expired): the three rule checks find nothing, as after a reboot. Then A is re-applied
    // onto an empty firewall.
    with_recorder(|r| r.fail_next(3));
    empty_linux_firewall();
    let report = start_up(&store, Os::Linux, T0);
    let got = lines();
    assert!(got.iter().any(|l| l == "iptables -w -N OMNI_BLOCK"), "{got:?}");
    assert!(got.contains(&format!("iptables -w -A OMNI_BLOCK -s {A} -j DROP")), "{got:?}");
    assert!(got.contains(&format!("iptables -w -A OMNI_BLOCK -d {A} -j DROP")), "{got:?}");
    assert!(got.iter().all(|l| !l.contains(" -D ")), "nothing to delete after a reboot: {got:?}");
    assert_eq!(report.reapplied, vec![A.to_string()]);
    let left = store.load().unwrap().claims;
    assert_eq!(left.len(), 1);
    assert_eq!(left[0].target, A);
}

#[test]
fn start_up_on_windows_adds_nothing_and_removes_only_the_expired_rules() {
    let (_d, store) = store_with(&[(A, "a", T0 + 1000), (B, "b", T0 - 5)]);
    let report = start_up(&store, Os::Windows, T0);
    let got = lines();
    assert!(got.iter().all(|l| !l.contains(" add rule ")), "{got:?}");
    assert!(got.contains(&format!("netsh advfirewall firewall delete rule name=OmniAgent_Block_{B}_in")), "{got:?}");
    assert!(got.iter().all(|l| !l.contains(A)), "the live address is not touched: {got:?}");
    assert!(report.reapplied.is_empty());
    assert_eq!(store.load().unwrap().claims.len(), 1);
}

#[test]
fn a_reapply_that_fails_is_reported_and_can_be_tried_again() {
    let (_d, store) = store_with(&[(A, "a", T0 + 1000)]);
    with_recorder(|r| {
        r.fail_next(1); // chain missing
        r.fail_next(1); // and cannot be created
    });
    let report = start_up(&store, Os::Linux, T0);
    assert_eq!(report.failed, vec![A.to_string()]);
    assert_eq!(store.load().unwrap().claims.len(), 1, "a failed re-apply keeps the claim");

    with_recorder(|r| r.clear_calls());
    empty_linux_firewall();
    let again = reapply_live(&store, Os::Linux, T0 + 15);
    assert!(again.failed.is_empty());
    assert_eq!(again.reapplied, vec![A.to_string()]);
    assert!(lines().contains(&format!("iptables -w -A OMNI_BLOCK -s {A} -j DROP")));
}

#[test]
fn a_reapply_on_windows_is_a_no_op() {
    let (_d, store) = store_with(&[(A, "a", T0 + 1000)]);
    assert_eq!(reapply_live(&store, Os::Windows, T0), PassReport::default());
    assert!(lines().is_empty());
}
