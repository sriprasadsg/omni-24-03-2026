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
#[allow(unused_imports)]
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

pub fn windows_rule_name(_suffix: &str) -> String { todo!() }
pub fn read_policy_cmd() -> Cmd { todo!() }
pub fn apply_plan(_os: Os, _carve: &CarveOut) -> ApplyPlan { todo!() }
pub fn parse_policies(_out: &str) -> Vec<&'static str> { todo!() }
pub fn saved_policy(_out: &str) -> Value { todo!() }
pub fn all_blocked(_out: &str) -> bool { todo!() }
pub fn revert_plan(_os: Os, _saved: &Value, _default_when_unknown: bool) -> RevertPlan { todo!() }
pub fn present_checks(_os: Os) -> Vec<Cmd> { todo!() }

#[cfg(test)]
#[path = "isolation_plan_tests.rs"]
mod tests;
