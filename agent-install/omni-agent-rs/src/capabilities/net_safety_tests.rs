//! Address classes, network parsing and the refusal rules, against fixed samples. Nothing reads
//! this machine's routes or resolvers.

use super::*;
use crate::capabilities::response_contract_tests::test_cfg;

fn ip(s: &str) -> IpAddr {
    s.parse().unwrap()
}

fn cfg_with_platform(url: &str) -> Config {
    let mut cfg = test_cfg();
    cfg.api_base_url = url.to_string();
    cfg
}

fn no_lookup(_: &str) -> Vec<IpAddr> {
    Vec::new()
}

#[test]
fn every_listed_ipv4_class_is_refused_at_both_edges() {
    for addr in [
        "0.0.0.0", "0.255.255.255", "10.0.0.0", "10.255.255.255", "100.64.0.0", "100.127.255.255", "127.0.0.1",
        "127.255.255.255", "169.254.0.1", "169.254.255.255", "172.16.0.0", "172.31.255.255", "192.0.0.0",
        "192.0.0.255", "192.0.2.0", "192.0.2.255", "192.168.0.0", "192.168.255.255", "198.18.0.0",
        "198.19.255.255", "198.51.100.0", "198.51.100.255", "203.0.113.0", "203.0.113.255", "224.0.0.0",
        "239.255.255.255", "240.0.0.0", "255.255.255.255",
    ] {
        assert!(!is_global_address(ip(addr)), "{addr} must be refused");
    }
}

#[test]
fn the_addresses_just_outside_each_class_are_global() {
    for addr in [
        "1.0.0.0", "9.255.255.255", "11.0.0.0", "100.63.255.255", "100.128.0.0", "126.255.255.255", "128.0.0.0",
        "169.253.255.255", "169.255.0.0", "172.15.255.255", "172.32.0.0", "191.255.255.255", "192.0.1.0",
        "192.0.3.0", "192.167.255.255", "192.169.0.0", "198.17.255.255", "198.20.0.0", "198.51.99.255",
        "198.51.101.0", "203.0.112.255", "203.0.114.0", "223.255.255.255", "45.33.32.156", "8.8.8.8",
    ] {
        assert!(is_global_address(ip(addr)), "{addr} must pass");
    }
}

#[test]
fn every_listed_ipv6_class_is_refused_and_a_public_address_passes() {
    for addr in ["::", "::1", "fc00::1", "fdff:ffff::1", "fe80::1", "febf::1", "ff00::1", "ff02::1", "2001:db8::1", "2001:db8:ffff::1"] {
        assert!(!is_global_address(ip(addr)), "{addr} must be refused");
    }
    for addr in ["2600:1f18::1", "2001:db9::1", "2001:db7::1", "2a00:1450::1", "fbff::1"] {
        assert!(is_global_address(ip(addr)), "{addr} must pass");
    }
}

#[test]
fn a_mapped_address_is_judged_as_its_ipv4_form() {
    assert!(!is_global_address(ip("::ffff:10.0.0.1")));
    assert!(!is_global_address(ip("::ffff:127.0.0.1")));
    assert!(is_global_address(ip("::ffff:45.33.32.156")));
}

#[test]
fn a_network_is_parsed_to_a_typed_value_with_its_address_bits_masked() {
    assert_eq!(parse_network("45.33.32.0/24"), Some((ip("45.33.32.0"), 24)));
    assert_eq!(parse_network("45.33.32.77/24"), Some((ip("45.33.32.0"), 24)));
    assert_eq!(parse_network("45.33.32.156/32"), Some((ip("45.33.32.156"), 32)));
    assert_eq!(parse_network("45.0.0.0/8"), Some((ip("45.0.0.0"), 8)));
    assert_eq!(parse_network("45.33.32.1/0"), Some((ip("0.0.0.0"), 0)));
    assert_eq!(parse_network("2600:1f18:1234::5/32"), Some((ip("2600:1f18::"), 32)));
    assert_eq!(parse_network("2600:1f18::1/128"), Some((ip("2600:1f18::1"), 128)));
    // A mapped network is the IPv4 network.
    assert_eq!(parse_network("::ffff:45.33.32.0/120"), Some((ip("45.33.32.0"), 24)));
}

#[test]
fn malformed_network_text_is_refused() {
    for text in [
        "", "/", "/24", "45.33.32.0", "45.33.32.0/", "45.33.32.0/33", "45.33.32.0/-1", "45.33.32.0/+24",
        "45.33.32.0/ 24", " 45.33.32.0/24", "45.33.32.0/24 ", "45.33.32.0/24/1", "45.33.32.0/024",
        "45.33.32.0/2a", "x/24", "45.33.32/24", "2600::/129", "2600::/", "::ffff:45.33.32.0/64",
        "45.33.32.0/24 -j ACCEPT", "45.33.32.0/24\n", "45.33.32.0/٢٤",
    ] {
        assert_eq!(parse_network(text), None, "{text:?}");
    }
}

#[test]
fn a_target_is_an_address_or_a_network_and_prints_as_its_claim_key() {
    assert_eq!(parse_target("45.33.32.156").map(|t| t.to_string()), Some("45.33.32.156".into()));
    assert_eq!(parse_target("45.33.32.0/24").map(|t| t.to_string()), Some("45.33.32.0/24".into()));
    assert_eq!(parse_target("::ffff:45.33.32.156").map(|t| t.to_string()), Some("45.33.32.156".into()));
    assert_eq!(parse_target("not-an-address"), None);
    assert_eq!(parse_target(""), None);
    assert_eq!(parse_target("45.33.32.0/99"), None);
}

#[test]
fn network_containment_is_exact_at_the_edges_and_never_crosses_families() {
    let net = (ip("45.33.32.0"), 24);
    assert!(network_contains(net, ip("45.33.32.0")));
    assert!(network_contains(net, ip("45.33.32.255")));
    assert!(!network_contains(net, ip("45.33.31.255")));
    assert!(!network_contains(net, ip("45.33.33.0")));
    assert!(network_contains((ip("0.0.0.0"), 0), ip("8.8.8.8")));
    assert!(network_contains((ip("45.33.32.156"), 32), ip("45.33.32.156")));
    assert!(!network_contains((ip("45.33.32.156"), 32), ip("45.33.32.157")));
    assert!(network_contains((ip("2600:1f18::"), 32), ip("2600:1f18:ffff::1")));
    assert!(!network_contains((ip("2600:1f18::"), 32), ip("2600:1f19::1")));
    assert!(!network_contains(net, ip("2600:1f18::1")));
    assert!(network_contains(net, ip("::ffff:45.33.32.9")), "a mapped address is its IPv4 form");
}

// Samples. The first two are this VM's own files; the Windows ones are the layout of
// `route print -4` and `netsh interface ipv4 show dnsservers` on Windows 10 and Server.
const PROC_NET_ROUTE: &str = "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n\
eth0\t00000000\t0100000A\t0003\t0\t0\t100\t00000000\t0\t0\t0\n\
eth0\t0000000A\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0\n\
eth0\t0100000A\t00000000\t0005\t0\t0\t100\tFFFFFFFF\t0\t0\t0\n\
eth1\t00000000\t0201A8C0\t0003\t0\t0\t200\t00000000\t0\t0\t0\n";

const RESOLV_CONF: &str = "# This is /run/systemd/resolve/stub-resolv.conf\nnameserver 127.0.0.53\noptions edns0 trust-ad\nsearch internal.cloudapp.net\n\nnameserver 168.63.129.16\nnameserver   2001:4860:4860::8888  \n#nameserver 9.9.9.9\nnameserver not-an-address\n";

const ROUTE_PRINT: &str = "===========================================================================\n\
Interface List\n  6...00 15 5d 01 02 03 ......Microsoft Hyper-V Network Adapter\n  1...........................Software Loopback Interface 1\n\
===========================================================================\n\nIPv4 Route Table\n\
===========================================================================\nActive Routes:\n\
Network Destination        Netmask          Gateway       Interface  Metric\n\
          0.0.0.0          0.0.0.0       10.1.2.1      10.1.2.55     25\n\
        127.0.0.0        255.0.0.0         On-link         127.0.0.1    331\n\
===========================================================================\nPersistent Routes:\n\
  Network Address          Netmask  Gateway Address  Metric\n\
          0.0.0.0          0.0.0.0       10.1.2.254  Default\n\
          0.0.0.0          0.0.0.0          On-link  Default\n";

const NETSH_DNS: &str = "\nConfiguration for interface \"Ethernet\"\n    DNS servers configured through DHCP:  10.1.2.1\n                                          10.1.2.2\n    Register with which suffix:           Primary only\n\nConfiguration for interface \"Loopback Pseudo-Interface 1\"\n    Statically Configured DNS Servers:    127.0.0.1\n                                          fec0:0:0:ffff::1%1\n    Register with which suffix:           Primary only\n";

#[test]
fn the_linux_default_gateways_come_from_the_default_routes_only() {
    assert_eq!(parse_proc_net_route(PROC_NET_ROUTE), vec![ip("10.0.0.1"), ip("192.168.1.2")]);
    assert!(parse_proc_net_route("").is_empty());
    assert!(parse_proc_net_route("garbage\nmore garbage").is_empty());
}

#[test]
fn the_linux_dns_servers_come_from_nameserver_lines() {
    assert_eq!(parse_resolv_conf(RESOLV_CONF), vec![ip("127.0.0.53"), ip("168.63.129.16"), ip("2001:4860:4860::8888")]);
    assert!(parse_resolv_conf("").is_empty());
}

#[test]
fn the_windows_gateways_come_from_the_default_route_rows() {
    assert_eq!(parse_windows_route_print(ROUTE_PRINT), vec![ip("10.1.2.1"), ip("10.1.2.254")]);
    assert!(parse_windows_route_print("").is_empty());
}

#[test]
fn the_windows_dns_servers_come_from_every_address_in_the_netsh_output() {
    assert_eq!(
        parse_windows_dns(NETSH_DNS),
        vec![ip("10.1.2.1"), ip("10.1.2.2"), ip("127.0.0.1"), ip("fec0:0:0:ffff::1")]
    );
    assert!(parse_windows_dns("").is_empty());
}

#[test]
fn a_public_address_with_nothing_special_passes() {
    let t = Target::host(ip("45.33.32.156"));
    assert_eq!(refuse_reason(&t, &test_cfg(), Os::Linux, &no_lookup), None);
    let t6 = Target::host(ip("2600:1f18::1"));
    assert_eq!(refuse_reason(&t6, &test_cfg(), Os::Linux, &no_lookup), None);
}

#[test]
fn an_address_that_is_not_global_is_refused_and_so_is_a_network_that_starts_in_one() {
    for text in ["10.1.2.3", "192.168.1.1", "100.64.0.1", "172.16.5.5", "::ffff:10.0.0.1", "fd00::1", "2001:db8::5"] {
        let t = parse_target(text).unwrap();
        assert!(refuse_reason(&t, &test_cfg(), Os::Linux, &no_lookup).is_some(), "{text}");
    }
    let net = parse_target("10.0.0.0/16").unwrap();
    assert!(refuse_reason(&net, &test_cfg(), Os::Linux, &no_lookup).is_some());
}

#[test]
fn the_platform_host_is_refused_as_a_literal_mapped_or_resolved_name() {
    let cfg = cfg_with_platform("https://57.154.210.55:8443");
    let t = Target::host(ip("57.154.210.55"));
    assert!(refuse_reason(&t, &cfg, Os::Linux, &no_lookup).is_some());
    assert!(refuse_reason(&parse_target("::ffff:57.154.210.55").unwrap(), &cfg, Os::Linux, &no_lookup).is_some());
    assert_eq!(refuse_reason(&Target::host(ip("57.154.210.56")), &cfg, Os::Linux, &no_lookup), None);

    let named = cfg_with_platform("https://omni.example.com/api");
    let lookup = |host: &str| if host == "omni.example.com" { vec![ip("57.154.210.55"), ip("2600:1f18::99")] } else { Vec::new() };
    assert!(refuse_reason(&t, &named, Os::Linux, &lookup).is_some());
    assert!(refuse_reason(&Target::host(ip("2600:1f18::99")), &named, Os::Linux, &lookup).is_some());
    assert_eq!(refuse_reason(&t, &named, Os::Linux, &no_lookup), None, "a name that does not resolve cannot be matched");
}

#[test]
fn the_gateway_and_the_dns_servers_are_refused_when_they_are_global() {
    set_test_host_addrs(HostAddrs { gateways: vec![ip("45.33.32.1")], dns: vec![ip("8.8.8.8"), ip("2001:4860:4860::8844")] });
    for text in ["45.33.32.1", "8.8.8.8", "2001:4860:4860::8844"] {
        let t = parse_target(text).unwrap();
        assert!(refuse_reason(&t, &test_cfg(), Os::Linux, &no_lookup).is_some(), "{text}");
    }
    assert_eq!(refuse_reason(&Target::host(ip("8.8.4.4")), &test_cfg(), Os::Linux, &no_lookup), None);
}

#[test]
fn a_network_is_refused_when_it_holds_the_platform_the_gateway_or_a_dns_server() {
    set_test_host_addrs(HostAddrs { gateways: vec![ip("45.33.32.1")], dns: vec![ip("8.8.8.8")] });
    let cfg = cfg_with_platform("https://57.154.210.55");
    for text in ["45.33.32.0/24", "8.8.8.0/24", "57.154.0.0/16", "57.154.210.55/32", "8.0.0.0/8"] {
        let t = parse_target(text).unwrap();
        assert!(refuse_reason(&t, &cfg, Os::Linux, &no_lookup).is_some(), "{text}");
    }
    for text in ["45.33.33.0/24", "8.8.9.0/24", "57.155.0.0/16"] {
        let t = parse_target(text).unwrap();
        assert_eq!(refuse_reason(&t, &cfg, Os::Linux, &no_lookup), None, "{text}");
    }
}

#[test]
fn a_network_wider_than_slash_8_or_slash_32_for_ipv6_is_refused() {
    for text in ["64.0.0.0/7", "0.0.0.0/0", "128.0.0.0/1", "2600::/31", "2600::/16"] {
        let t = parse_target(text).unwrap();
        assert!(refuse_reason(&t, &test_cfg(), Os::Linux, &no_lookup).is_some(), "{text}");
    }
    for text in ["45.0.0.0/8", "45.33.0.0/16", "2600:1f18::/32", "2600:1f18::/64"] {
        let t = parse_target(text).unwrap();
        assert_eq!(refuse_reason(&t, &test_cfg(), Os::Linux, &no_lookup), None, "{text}");
    }
}

#[test]
fn the_refusals_are_plain_sentences() {
    let reasons: Vec<&str> = ["10.0.0.1", "64.0.0.0/7"]
        .iter()
        .filter_map(|t| refuse_reason(&parse_target(t).unwrap(), &test_cfg(), Os::Linux, &no_lookup))
        .collect();
    assert_eq!(reasons.len(), 2);
    for r in reasons {
        assert!(r.ends_with('.') && r.len() > 20, "{r}");
    }
}
