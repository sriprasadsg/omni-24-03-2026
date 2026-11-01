//! The firewall commands that isolate a host and that put it back, planned as plain data.
//!
//! Like `firewall`, nothing here starts a process: the plans are values, `Os::current()` is the
//! only place `cfg` picks a system, and the Windows plan is therefore tested on a Linux build
//! machine. `isolation` runs the plans in the order that keeps the management connection open:
//! every `allow` step first, then the checks that those rules exist, only then the `block` steps.
//! Undoing runs the other way round: `lift` the block first, then `clear` the allow rules.
//!
//! Linux: three chains per address family (`OMNI_ISOLATE_IN`, `_OUT`, `_FWD`), hooked at position
//! 1 of INPUT, OUTPUT and FORWARD for iptables and ip6tables. Each chain accepts loopback, the
//! platform, DHCP (and for IPv6 the neighbour discovery that IPv6 cannot work without) before its
//! final DROP.
//!
//! Windows: rules named `OmniAgent_Isolate_Allow_*` allow the platform, DHCP and, when the
//! platform is given by name, DNS to the host's own resolvers. Then `allprofiles firewallpolicy`
//! becomes `blockinbound,blockoutbound`. The policy each profile had is saved and put back per
//! profile, and only this agent's own rules are removed, so a block added meanwhile survives.

use crate::capabilities::firewall::{Cmd, Ensure, Os, Remove};
use serde_json::{json, Value};
use std::net::IpAddr;

pub const CHAIN_IN: &str = "OMNI_ISOLATE_IN";
pub const CHAIN_OUT: &str = "OMNI_ISOLATE_OUT";
pub const CHAIN_FWD: &str = "OMNI_ISOLATE_FWD";
/// Windows rule name prefix; the rule name is `<prefix>_<suffix>`.
pub const WINDOWS_RULE_PREFIX: &str = "OmniAgent_Isolate_Allow";
const WINDOWS_RULE_SUFFIXES: [&str; 6] = ["Out", "In", "DHCP_Out", "DHCP_In", "DNS_Out", "DNS_TCP_Out"];
/// Windows profiles in the order `show allprofiles` prints them.
pub const WINDOWS_PROFILES: [&str; 3] = ["domain", "private", "public"];
/// What a Windows profile gets back when its saved policy is not known.
pub const DEFAULT_POLICY: &str = "blockinbound,allowoutbound";
pub const ISOLATE_POLICY: &str = "blockinbound,blockoutbound";
/// An unconfirmed isolation ends after this many seconds (D-15).
pub const REVERT_SECONDS: i64 = 14_400;

/// The addresses that must stay reachable while the host is isolated.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CarveOut {
    /// The platform: every address of `api_base_url`.
    pub addresses: Vec<IpAddr>,
    /// The host's own resolvers, opened for DNS only when the platform is given by name.
    pub dns: Vec<IpAddr>,
    pub port: u16,
}

/// One step that closes something.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Do {
    /// Run `add` unless `check` already passes.
    Ensure(Ensure),
    Run(Cmd),
}

/// One step that opens something again.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Undo {
    /// Run `delete` only when `check` passes.
    Remove(Remove),
    Run(Cmd),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ApplyPlan {
    /// The management allow rules, all of them, before anything is blocked.
    pub allow: Vec<Ensure>,
    /// What closes the host.
    pub block: Vec<Do>,
    /// Linux: the hooks that must exist once blocked. Windows: the one command whose output says
    /// every profile now blocks both directions.
    pub effective: Vec<Cmd>,
}

impl ApplyPlan {
    /// The checks that say each allow rule exists.
    pub fn verify(&self) -> Vec<Cmd> {
        self.allow.iter().map(|e| e.check.clone()).collect()
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RevertPlan {
    /// Lifts the block. Nothing below it runs unless every step here worked.
    pub lift: Vec<Undo>,
    /// Takes out the allow rules and chains.
    pub clear: Vec<Undo>,
}

fn tool(v6: bool) -> &'static str {
    if v6 { "ip6tables" } else { "iptables" }
}

fn linux(t: &'static str, parts: &[&str]) -> Cmd {
    let mut args = vec!["-w"];
    args.extend_from_slice(parts);
    Cmd::new(t, &args)
}

fn chain_ensure(t: &'static str, chain: &str) -> Ensure {
    Ensure { check: linux(t, &["-n", "-L", chain]), add: linux(t, &["-N", chain]) }
}

fn rule_ensure(t: &'static str, chain: &str, rule: &[String]) -> Ensure {
    let rule: Vec<&str> = rule.iter().map(String::as_str).collect();
    let with = |verb: &str| {
        let mut parts = vec![verb, chain];
        parts.extend_from_slice(&rule);
        linux(t, &parts)
    };
    Ensure { check: with("-C"), add: with("-A") }
}

fn words(parts: &[&str]) -> Vec<String> {
    parts.iter().map(|p| p.to_string()).collect()
}

/// The ACCEPT rules of one chain, in order: loopback, (IPv6) neighbour discovery, the platform,
/// DHCP, then DNS to the host's resolvers.
fn accept_rules(c: &CarveOut, v6: bool, inbound: bool) -> Vec<Vec<String>> {
    let (lo, peer) = if inbound { ("-i", "-s") } else { ("-o", "-d") };
    let mut rules = vec![words(&[lo, "lo", "-j", "ACCEPT"])];
    if v6 {
        rules.push(words(&["-p", "ipv6-icmp", "-j", "ACCEPT"]));
    }
    for a in c.addresses.iter().filter(|a| a.is_ipv6() == v6) {
        rules.push(vec![peer.to_string(), a.to_string(), "-j".into(), "ACCEPT".into()]);
    }
    let (server, client) = if v6 { ("547", "546") } else { ("67", "68") };
    let (sport, dport) = if inbound { (server, client) } else { (client, server) };
    rules.push(words(&["-p", "udp", "--sport", sport, "--dport", dport, "-j", "ACCEPT"]));
    for r in c.dns.iter().filter(|r| r.is_ipv6() == v6) {
        for proto in ["udp", "tcp"] {
            let port = if inbound { "--sport" } else { "--dport" };
            rules.push(vec![
                peer.into(), r.to_string(), "-p".into(), proto.into(), port.into(), "53".into(), "-j".into(), "ACCEPT".into(),
            ]);
        }
    }
    rules
}

const HOOKS: [(&str, &str); 3] = [(CHAIN_IN, "INPUT"), (CHAIN_OUT, "OUTPUT"), (CHAIN_FWD, "FORWARD")];

fn linux_apply(c: &CarveOut) -> ApplyPlan {
    let (mut allow, mut block, mut effective) = (Vec::new(), Vec::new(), Vec::new());
    for v6 in [false, true] {
        let t = tool(v6);
        for (chain, _) in HOOKS {
            allow.push(chain_ensure(t, chain));
        }
        for rule in accept_rules(c, v6, true) {
            allow.push(rule_ensure(t, CHAIN_IN, &rule));
        }
        for rule in accept_rules(c, v6, false) {
            allow.push(rule_ensure(t, CHAIN_OUT, &rule));
        }
        for (chain, _) in HOOKS {
            block.push(Do::Ensure(rule_ensure(t, chain, &words(&["-j", "DROP"]))));
        }
        for (chain, hook) in HOOKS {
            let check = linux(t, &["-C", hook, "-j", chain]);
            block.push(Do::Ensure(Ensure { check: check.clone(), add: linux(t, &["-I", hook, "1", "-j", chain]) }));
            effective.push(check);
        }
    }
    ApplyPlan { allow, block, effective }
}

pub fn windows_rule_name(suffix: &str) -> String {
    format!("{WINDOWS_RULE_PREFIX}_{suffix}")
}

fn netsh(parts: &[&str]) -> Cmd {
    Cmd::new("netsh", parts)
}

fn windows_allow(suffix: &str, dir: &str, extra: &[String]) -> Ensure {
    let name = format!("name={}", windows_rule_name(suffix));
    let mut add = vec!["advfirewall".to_string(), "firewall".into(), "add".into(), "rule".into(), name.clone()];
    add.extend([format!("dir={dir}"), "action=allow".to_string()]);
    add.extend(extra.iter().cloned());
    let add: Vec<&str> = add.iter().map(String::as_str).collect();
    Ensure { check: netsh(&["advfirewall", "firewall", "show", "rule", &name]), add: netsh(&add) }
}

fn join(list: &[IpAddr]) -> String {
    list.iter().map(IpAddr::to_string).collect::<Vec<_>>().join(",")
}

pub fn read_policy_cmd() -> Cmd {
    netsh(&["advfirewall", "show", "allprofiles", "firewallpolicy"])
}

fn windows_apply(c: &CarveOut) -> ApplyPlan {
    let platform = vec![format!("remoteip={}", join(&c.addresses))];
    let dhcp = words(&["protocol=udp", "localport=68", "remoteport=67"]);
    let mut allow = vec![
        windows_allow("Out", "out", &platform),
        windows_allow("In", "in", &platform),
        windows_allow("DHCP_Out", "out", &dhcp),
        windows_allow("DHCP_In", "in", &dhcp),
    ];
    if !c.dns.is_empty() {
        for (suffix, proto) in [("DNS_Out", "udp"), ("DNS_TCP_Out", "tcp")] {
            allow.push(windows_allow(suffix, "out", &[format!("protocol={proto}"), "remoteport=53".into(), format!("remoteip={}", join(&c.dns))]));
        }
    }
    ApplyPlan {
        allow,
        block: vec![Do::Run(netsh(&["advfirewall", "set", "allprofiles", "firewallpolicy", ISOLATE_POLICY]))],
        effective: vec![read_policy_cmd()],
    }
}

pub fn apply_plan(os: Os, carve: &CarveOut) -> ApplyPlan {
    match os {
        Os::Linux => linux_apply(carve),
        Os::Windows => windows_apply(carve),
    }
}

/// The policy text if it is one of the four values `netsh` accepts, else None. Only these reach a
/// command line, so a damaged state file cannot put anything else there.
fn clean_policy(text: &str) -> Option<&'static str> {
    ["blockinbound,allowoutbound", "blockinbound,blockoutbound", "allowinbound,allowoutbound", "allowinbound,blockoutbound"]
        .into_iter()
        .find(|p| p.eq_ignore_ascii_case(text.trim()))
}

/// The policy of each profile, in the order `show allprofiles firewallpolicy` prints them (domain,
/// private, public). The lines are recognised by their value, so the labels may be in any language.
pub fn parse_policies(out: &str) -> Vec<&'static str> {
    out.lines().filter_map(|line| line.split_whitespace().last()).filter_map(clean_policy).collect()
}

/// What to save before the policy changes: one value per profile, the default for any not read.
pub fn saved_policy(out: &str) -> Value {
    let found = parse_policies(out);
    if found.len() < 3 {
        log::warn!("Read {} of 3 firewall profile policies; the others will go back to {DEFAULT_POLICY}", found.len());
    }
    let mut saved = serde_json::Map::new();
    for (i, profile) in WINDOWS_PROFILES.iter().enumerate() {
        saved.insert(profile.to_string(), json!(found.get(i).copied().unwrap_or(DEFAULT_POLICY)));
    }
    Value::Object(saved)
}

/// True when all three profiles block both directions.
pub fn all_blocked(out: &str) -> bool {
    let found = parse_policies(out);
    found.len() >= 3 && found.iter().take(3).all(|p| *p == ISOLATE_POLICY)
}

fn hook_removals() -> Vec<Undo> {
    let mut lift = Vec::new();
    for v6 in [false, true] {
        let t = tool(v6);
        for (chain, hook) in HOOKS {
            lift.push(Undo::Remove(Remove {
                check: linux(t, &["-C", hook, "-j", chain]),
                delete: linux(t, &["-D", hook, "-j", chain]),
                legacy: false,
            }));
        }
    }
    lift
}

fn chain_removals() -> Vec<Undo> {
    let mut clear = Vec::new();
    for v6 in [false, true] {
        let t = tool(v6);
        for (chain, _) in HOOKS {
            for verb in ["-F", "-X"] {
                clear.push(Undo::Remove(Remove { check: linux(t, &["-n", "-L", chain]), delete: linux(t, &[verb, chain]), legacy: false }));
            }
        }
    }
    clear
}

/// Everything that puts the host back. `saved` is the policy saved by `saved_policy` (Windows).
/// With nothing saved the policy is left alone, because it was not changed yet, unless
/// `default_when_unknown` says the state is lost and the default must be restored.
pub fn revert_plan(os: Os, saved: &Value, default_when_unknown: bool) -> RevertPlan {
    match os {
        Os::Linux => RevertPlan { lift: hook_removals(), clear: chain_removals() },
        Os::Windows => {
            let mut lift = Vec::new();
            for profile in WINDOWS_PROFILES {
                let policy = match saved.get(profile).and_then(Value::as_str).and_then(clean_policy) {
                    Some(p) => Some(p),
                    None if saved.is_object() || default_when_unknown => Some(DEFAULT_POLICY),
                    None => None,
                };
                if let Some(p) = policy {
                    lift.push(Undo::Run(netsh(&["advfirewall", "set", &format!("{profile}profile"), "firewallpolicy", p])));
                }
            }
            let clear = WINDOWS_RULE_SUFFIXES
                .iter()
                .map(|suffix| {
                    let name = format!("name={}", windows_rule_name(suffix));
                    Undo::Remove(Remove {
                        check: netsh(&["advfirewall", "firewall", "show", "rule", &name]),
                        delete: netsh(&["advfirewall", "firewall", "delete", "rule", &name]),
                        legacy: false,
                    })
                })
                .collect();
            RevertPlan { lift, clear }
        }
    }
}

/// The checks that say "the host is isolated right now": the INPUT hooks on Linux, the platform
/// allow rule on Windows. Any one that passes means the rules are in place.
pub fn present_checks(os: Os) -> Vec<Cmd> {
    match os {
        Os::Linux => [false, true].into_iter().map(|v6| linux(tool(v6), &["-C", "INPUT", "-j", CHAIN_IN])).collect(),
        Os::Windows => vec![netsh(&["advfirewall", "firewall", "show", "rule", &format!("name={}", windows_rule_name("Out"))])],
    }
}

#[cfg(test)]
#[path = "isolation_plan_tests.rs"]
mod tests;
