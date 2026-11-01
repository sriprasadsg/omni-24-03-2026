//! A network is one rule per direction, planned exactly like an address.

use super::*;
use crate::capabilities::privileged::with_recorder;

fn net(text: &str) -> Target {
    let (addr, prefix) = text.split_once('/').unwrap();
    Target::network(addr.parse().unwrap(), prefix.parse().unwrap())
}

fn lines() -> Vec<String> {
    with_recorder(|r| r.lines())
}

fn empty_linux_firewall() {
    with_recorder(|r| {
        for _ in 0..5 {
            r.fail_next(1);
            r.answer_next("");
        }
    });
}

#[test]
fn a_target_prints_as_its_claim_key() {
    assert_eq!(Target::host("45.33.32.156".parse().unwrap()).to_string(), "45.33.32.156");
    assert_eq!(net("45.33.32.0/24").to_string(), "45.33.32.0/24");
    assert_eq!(net("2600:1f18::/32").to_string(), "2600:1f18::/32");
    assert_eq!(Target::host("::ffff:45.33.32.156".parse().unwrap()).to_string(), "45.33.32.156");
}

#[test]
fn linux_blocks_a_network_with_one_source_and_one_destination_rule() {
    empty_linux_firewall();
    apply_block(Os::Linux, net("45.33.32.0/24")).unwrap();
    let got = lines();
    assert_eq!(got.len(), 10);
    assert!(got.contains(&"iptables -w -A OMNI_BLOCK -s 45.33.32.0/24 -j DROP".to_string()), "{got:?}");
    assert!(got.contains(&"iptables -w -A OMNI_BLOCK -d 45.33.32.0/24 -j DROP".to_string()), "{got:?}");
}

#[test]
fn an_ipv6_network_uses_ip6tables() {
    empty_linux_firewall();
    apply_block(Os::Linux, net("2600:1f18::/32")).unwrap();
    let got = lines();
    assert!(got.iter().all(|l| l.starts_with("ip6tables ")));
    assert!(got.contains(&"ip6tables -w -A OMNI_BLOCK -s 2600:1f18::/32 -j DROP".to_string()));
}

#[test]
fn windows_names_a_network_rule_with_an_underscore_and_gives_the_cidr_to_remoteip() {
    with_recorder(|r| {
        r.fail_next(1);
        r.answer_next("");
        r.fail_next(1);
        r.answer_next("");
    });
    apply_block(Os::Windows, net("45.33.32.0/24")).unwrap();
    assert_eq!(
        lines(),
        vec![
            "netsh advfirewall firewall show rule name=OmniAgent_Block_45.33.32.0_24_in",
            "netsh advfirewall firewall add rule name=OmniAgent_Block_45.33.32.0_24_in dir=in action=block remoteip=45.33.32.0/24",
            "netsh advfirewall firewall show rule name=OmniAgent_Block_45.33.32.0_24_out",
            "netsh advfirewall firewall add rule name=OmniAgent_Block_45.33.32.0_24_out dir=out action=block remoteip=45.33.32.0/24",
        ]
    );
}

#[test]
fn windows_removes_a_network_by_the_same_names() {
    assert!(remove_block(Os::Windows, net("45.33.32.0/24")).unwrap());
    let got = lines();
    assert!(got.contains(&"netsh advfirewall firewall delete rule name=OmniAgent_Block_45.33.32.0_24_in".to_string()));
    assert!(got.contains(&"netsh advfirewall firewall delete rule name=OmniAgent_Block_45.33.32.0_24_out".to_string()));
}

#[test]
fn linux_removes_a_network_with_the_same_text_it_added() {
    assert!(remove_block(Os::Linux, net("45.33.32.0/24")).unwrap());
    let got = lines();
    assert!(got.contains(&"iptables -w -D OMNI_BLOCK -s 45.33.32.0/24 -j DROP".to_string()));
    assert!(got.contains(&"iptables -w -D OMNI_BLOCK -d 45.33.32.0/24 -j DROP".to_string()));
}

#[test]
fn a_network_is_always_its_own_argv_element() {
    for os in [Os::Linux, Os::Windows] {
        for step in block_plan(os, net("45.33.32.0/24")) {
            for cmd in [&step.check, &step.add] {
                assert!(cmd.args.iter().all(|a| !a.contains(' ')), "{cmd:?}");
            }
        }
    }
}

#[test]
fn the_rule_names_of_a_plain_address_are_unchanged() {
    let (i, o) = windows_rule_names("45.33.32.156".parse::<IpAddr>().unwrap());
    assert_eq!((i.as_str(), o.as_str()), ("OmniAgent_Block_45.33.32.156_in", "OmniAgent_Block_45.33.32.156_out"));
}
