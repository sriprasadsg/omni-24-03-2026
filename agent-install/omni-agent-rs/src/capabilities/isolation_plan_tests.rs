//! The isolation plans as data: what they hold and in which order, with nothing run.

use super::*;

fn carve(addresses: &[&str], dns: &[&str]) -> CarveOut {
    CarveOut {
        addresses: addresses.iter().map(|a| a.parse().unwrap()).collect(),
        dns: dns.iter().map(|a| a.parse().unwrap()).collect(),
        port: 443,
    }
}

fn add_lines(steps: &ApplyPlan) -> Vec<String> {
    steps.allow.iter().map(|e| format!("{} {}", e.add.program, e.add.args.join(" "))).collect()
}

fn do_lines(steps: &ApplyPlan) -> Vec<String> {
    steps
        .block
        .iter()
        .map(|d| match d {
            Do::Ensure(e) => format!("{} {}", e.add.program, e.add.args.join(" ")),
            Do::Run(c) => format!("{} {}", c.program, c.args.join(" ")),
        })
        .collect()
}

#[test]
fn linux_accepts_loopback_the_platform_and_dhcp_in_every_chain_before_it_drops() {
    let plan = apply_plan(Os::Linux, &carve(&["57.154.210.55"], &[]));
    let allow = add_lines(&plan);
    for expected in [
        "iptables -w -A OMNI_ISOLATE_IN -i lo -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_IN -s 57.154.210.55 -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_IN -p udp --sport 67 --dport 68 -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_OUT -o lo -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_OUT -d 57.154.210.55 -j ACCEPT",
        "iptables -w -A OMNI_ISOLATE_OUT -p udp --sport 68 --dport 67 -j ACCEPT",
    ] {
        assert!(allow.contains(&expected.to_string()), "missing {expected}");
    }
    assert!(allow.iter().all(|l| !l.contains("DROP")), "no drop among the allow steps");
    let block = do_lines(&plan);
    assert!(block.iter().take(3).all(|l| l.starts_with("iptables") && l.ends_with("-j DROP")));
    assert!(block.iter().any(|l| l == "iptables -w -I FORWARD 1 -j OMNI_ISOLATE_FWD"));
    assert_eq!(plan.allow.len(), 18);
    assert_eq!(plan.block.len(), 12);
    assert_eq!(plan.effective.len(), 6);
}

#[test]
fn ipv6_gets_neighbour_discovery_and_dhcpv6_and_only_its_own_platform_addresses() {
    let plan = apply_plan(Os::Linux, &carve(&["57.154.210.55", "2600:1f18::1"], &[]));
    let allow = add_lines(&plan);
    assert!(allow.contains(&"ip6tables -w -A OMNI_ISOLATE_IN -p ipv6-icmp -j ACCEPT".to_string()));
    assert!(allow.contains(&"ip6tables -w -A OMNI_ISOLATE_OUT -p udp --sport 546 --dport 547 -j ACCEPT".to_string()));
    assert!(allow.contains(&"ip6tables -w -A OMNI_ISOLATE_IN -s 2600:1f18::1 -j ACCEPT".to_string()));
    assert!(!allow.iter().any(|l| l.starts_with("iptables") && l.contains("2600:1f18")));
    assert!(!allow.iter().any(|l| l.starts_with("ip6tables") && l.contains("57.154.210.55")));
}

#[test]
fn resolvers_are_opened_for_dns_only_when_given() {
    let none = add_lines(&apply_plan(Os::Linux, &carve(&["57.154.210.55"], &[])));
    assert!(none.iter().all(|l| !l.contains("53")));
    let named = add_lines(&apply_plan(Os::Linux, &carve(&["57.154.210.55"], &["192.0.2.53"])));
    assert!(named.contains(&"iptables -w -A OMNI_ISOLATE_OUT -d 192.0.2.53 -p tcp --dport 53 -j ACCEPT".to_string()));
    let windows = apply_plan(Os::Windows, &carve(&["57.154.210.55"], &["192.0.2.53"]));
    assert_eq!(windows.allow.len(), 6);
    assert!(add_lines(&windows).iter().any(|l| l.contains("OmniAgent_Isolate_Allow_DNS_Out") && l.contains("remoteip=192.0.2.53")));
    assert_eq!(apply_plan(Os::Windows, &carve(&["57.154.210.55"], &[])).allow.len(), 4);
}

#[test]
fn windows_sets_the_block_policy_for_every_profile_in_one_command_after_the_allow_rules() {
    let plan = apply_plan(Os::Windows, &carve(&["57.154.210.55", "2600:1f18::1"], &[]));
    assert_eq!(do_lines(&plan), vec!["netsh advfirewall set allprofiles firewallpolicy blockinbound,blockoutbound"]);
    assert!(add_lines(&plan)[0].ends_with("remoteip=57.154.210.55,2600:1f18::1"));
    assert_eq!(plan.effective, vec![read_policy_cmd()]);
}

#[test]
fn every_argument_is_its_own_element_with_no_space_in_it() {
    for os in [Os::Linux, Os::Windows] {
        let plan = apply_plan(os, &carve(&["57.154.210.55", "2600:1f18::1"], &["192.0.2.53"]));
        let revert = revert_plan(os, &saved_policy(""), false);
        let mut cmds: Vec<&Cmd> = plan.allow.iter().flat_map(|e| [&e.check, &e.add]).collect();
        cmds.extend(plan.effective.iter());
        for step in plan.block.iter() {
            match step {
                Do::Ensure(e) => cmds.extend([&e.check, &e.add]),
                Do::Run(c) => cmds.push(c),
            }
        }
        for step in revert.lift.iter().chain(&revert.clear) {
            match step {
                Undo::Remove(r) => cmds.extend([&r.check, &r.delete]),
                Undo::Run(c) => cmds.push(c),
            }
        }
        for cmd in cmds {
            assert!(cmd.args.iter().all(|a| !a.contains(' ')), "{cmd:?}");
        }
    }
}

#[test]
fn the_linux_revert_unhooks_before_it_flushes_and_deletes() {
    let plan = revert_plan(Os::Linux, &Value::Null, false);
    assert_eq!(plan.lift.len(), 6);
    assert_eq!(plan.clear.len(), 12);
    let first = |u: &Undo| match u {
        Undo::Remove(r) => r.delete.args.join(" "),
        Undo::Run(c) => c.args.join(" "),
    };
    assert_eq!(first(&plan.lift[0]), "-w -D INPUT -j OMNI_ISOLATE_IN");
    assert_eq!(first(&plan.clear[0]), "-w -F OMNI_ISOLATE_IN");
    assert_eq!(first(&plan.clear[1]), "-w -X OMNI_ISOLATE_IN");
}

#[test]
fn the_windows_revert_puts_each_profile_back_and_removes_only_its_own_rules() {
    let saved = json!({"domain": "blockinbound,allowoutbound", "private": "allowinbound,allowoutbound", "public": "garbage; calc"});
    let plan = revert_plan(Os::Windows, &saved, false);
    let set: Vec<String> = plan
        .lift
        .iter()
        .map(|u| match u {
            Undo::Run(c) => c.args.join(" "),
            Undo::Remove(_) => unreachable!(),
        })
        .collect();
    assert_eq!(
        set,
        vec![
            "advfirewall set domainprofile firewallpolicy blockinbound,allowoutbound",
            "advfirewall set privateprofile firewallpolicy allowinbound,allowoutbound",
            "advfirewall set publicprofile firewallpolicy blockinbound,allowoutbound",
        ],
        "a value that is not a policy is replaced by the default, never passed on"
    );
    assert_eq!(plan.clear.len(), 6);
    for step in &plan.clear {
        let Undo::Remove(r) = step else { panic!("a removal") };
        assert!(r.delete.args.iter().any(|a| a.starts_with("name=OmniAgent_Isolate_Allow_")), "{:?}", r.delete);
    }
}

#[test]
fn with_nothing_saved_the_policy_is_left_alone_unless_the_state_is_lost() {
    assert!(revert_plan(Os::Windows, &Value::Null, false).lift.is_empty(), "the policy was never changed");
    assert_eq!(revert_plan(Os::Windows, &Value::Null, true).lift.len(), 3);
}

const POLICY: &str = "Domain Profile Settings:\n---\nFirewall Policy                       BlockInbound,AllowOutbound\n\n\
Private Profile Settings:\n---\nFirewall Policy                       BlockInbound,AllowOutbound\n\n\
Public Profile Settings:\n---\nFirewall Policy                       AllowInbound,AllowOutbound\n";

#[test]
fn the_saved_policy_is_read_by_value_per_profile_and_defaults_fill_the_gaps() {
    assert_eq!(
        saved_policy(POLICY),
        json!({"domain": "blockinbound,allowoutbound", "private": "blockinbound,allowoutbound", "public": "allowinbound,allowoutbound"})
    );
    let defaults = json!({"domain": DEFAULT_POLICY, "private": DEFAULT_POLICY, "public": DEFAULT_POLICY});
    assert_eq!(saved_policy("nothing useful here"), defaults);
    assert_eq!(saved_policy(""), defaults);
}

#[test]
fn a_policy_counts_as_blocked_only_when_all_three_profiles_block_both_ways() {
    let blocked = POLICY.replace("BlockInbound,AllowOutbound", "BlockInbound,BlockOutbound").replace("AllowInbound,AllowOutbound", "BlockInbound,BlockOutbound");
    assert!(all_blocked(&blocked));
    assert!(!all_blocked(POLICY));
    assert!(!all_blocked(&blocked.lines().take(6).collect::<Vec<_>>().join("\n")), "fewer than three profiles");
    assert!(!all_blocked(""));
}

#[test]
fn the_present_checks_name_the_input_hooks_or_the_platform_rule() {
    let linux: Vec<String> = present_checks(Os::Linux).iter().map(|c| format!("{} {}", c.program, c.args.join(" "))).collect();
    assert_eq!(linux, vec!["iptables -w -C INPUT -j OMNI_ISOLATE_IN", "ip6tables -w -C INPUT -j OMNI_ISOLATE_IN"]);
    assert_eq!(present_checks(Os::Windows).len(), 1);
}
