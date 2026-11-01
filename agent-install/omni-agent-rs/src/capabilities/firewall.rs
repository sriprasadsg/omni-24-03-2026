//! Host firewall rules for a blocked address, planned as plain data and applied through the
//! privileged seam.
//!
//! The plan functions are ordinary Rust that compiles on every operating system, so the Windows
//! plan is tested on a Linux build machine. `Os::current()` is the single place `cfg` picks the
//! operating system. Nothing here starts a process itself: every command goes through
//! `privileged`, one argv element per parameter.
//!
//! Linux: one chain `OMNI_BLOCK` per address family (iptables or ip6tables, chosen by the
//! address), hooked once at position 1 of INPUT and OUTPUT. The chain holds `-s <addr>` and
//! `-d <addr>` DROP rules, so one rule per direction and nothing is added twice (`-C` before
//! `-A`). Every call carries `-w` so it waits for the firewall lock instead of failing.
//!
//! Windows: two named rules per address, `OmniAgent_Block_<addr>_in` (dir=in) and `_out`
//! (dir=out). The older single rule `OmniAgent_Block_<addr>` is removed on unblock, best effort.
//!
//! A target is an address or a network (`45.33.32.0/24`), one rule per direction either way:
//! `-s`/`-d` and `remoteip` take the CIDR text. In a Windows rule name "/" becomes "_".

use crate::capabilities::privileged;
use crate::capabilities::remediation_actions::RemediationError;
use std::net::IpAddr;

/// The Linux chain that holds this agent's block rules.
pub const LINUX_CHAIN: &str = "OMNI_BLOCK";
/// Windows rule name prefix; the name is `<prefix><address>_in` or `_out`.
pub const WINDOWS_RULE_PREFIX: &str = "OmniAgent_Block_";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Os {
    Linux,
    Windows,
}

impl Os {
    /// The operating system this binary runs on, or None where no firewall plan exists.
    pub fn current() -> Option<Os> {
        #[cfg(target_os = "linux")]
        {
            Some(Os::Linux)
        }
        #[cfg(target_os = "windows")]
        {
            Some(Os::Windows)
        }
        #[cfg(not(any(target_os = "linux", target_os = "windows")))]
        {
            None
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Os::Linux => "linux",
            Os::Windows => "windows",
        }
    }
}

/// One command: a program and one argv element per parameter.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Cmd {
    pub program: &'static str,
    pub args: Vec<String>,
}

impl Cmd {
    fn new(program: &'static str, args: &[&str]) -> Cmd {
        Cmd { program, args: args.iter().map(|a| a.to_string()).collect() }
    }

    fn run(&self) -> Result<(), RemediationError> {
        let args: Vec<&str> = self.args.iter().map(String::as_str).collect();
        privileged::run(self.program, &args)
    }

    /// True when the command exits 0 and, for `netsh show rule`, does not say nothing matched.
    fn passes(&self) -> bool {
        let args: Vec<&str> = self.args.iter().map(String::as_str).collect();
        match privileged::run_output(self.program, &args) {
            Ok(out) => !out.contains("No rules match"),
            Err(_) => false,
        }
    }
}

/// "Make sure this exists": `add` runs only when `check` does not pass.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Ensure {
    pub check: Cmd,
    pub add: Cmd,
}

/// "Make sure this is gone": `delete` runs only when `check` passes. A `legacy` step belongs to
/// an older agent's rule; its failure never fails the removal.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Remove {
    pub check: Cmd,
    pub delete: Cmd,
    pub legacy: bool,
}

/// The same address in the form the firewall tools expect (an IPv4-mapped IPv6 address is the
/// IPv4 address).
pub fn canonical(ip: IpAddr) -> IpAddr {
    ip.to_canonical()
}

/// An address or a network (masked by `net_safety`); its text is the claim key.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Target {
    pub addr: IpAddr,
    pub prefix: Option<u8>,
}

impl Target {
    pub fn host(ip: IpAddr) -> Target { Target { addr: canonical(ip), prefix: None } }

    pub fn network(ip: IpAddr, prefix: u8) -> Target { Target { addr: ip, prefix: Some(prefix) } }

    fn rule_key(&self) -> String {
        self.to_string().replace('/', "_")
    }
}

impl std::fmt::Display for Target {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self.prefix {
            Some(p) => write!(f, "{}/{p}", self.addr),
            None => write!(f, "{}", self.addr),
        }
    }
}

impl From<IpAddr> for Target {
    fn from(ip: IpAddr) -> Target { Target::host(ip) }
}

fn iptables(t: &Target) -> &'static str {
    if t.addr.is_ipv6() { "ip6tables" } else { "iptables" }
}

/// The two Windows rule names for a target: inbound and outbound.
pub fn windows_rule_names(t: impl Into<Target>) -> (String, String) {
    let key = t.into().rule_key();
    (format!("{WINDOWS_RULE_PREFIX}{key}_in"), format!("{WINDOWS_RULE_PREFIX}{key}_out"))
}

fn linux_rule(ipt: &'static str, flag: &'static str, addr: &str, verb: &'static str) -> Cmd {
    Cmd::new(ipt, &["-w", verb, LINUX_CHAIN, flag, addr, "-j", "DROP"])
}

fn linux_hook(ipt: &'static str, chain: &'static str) -> Ensure {
    Ensure {
        check: Cmd::new(ipt, &["-w", "-C", chain, "-j", LINUX_CHAIN]),
        add: Cmd::new(ipt, &["-w", "-I", chain, "1", "-j", LINUX_CHAIN]),
    }
}

fn windows_show(name: &str) -> Cmd {
    Cmd::new("netsh", &["advfirewall", "firewall", "show", "rule", &format!("name={name}")])
}

fn windows_add(name: &str, dir: &str, addr: &str) -> Cmd {
    Cmd::new(
        "netsh",
        &[
            "advfirewall", "firewall", "add", "rule", &format!("name={name}"),
            &format!("dir={dir}"), "action=block", &format!("remoteip={addr}"),
        ],
    )
}

fn windows_delete(name: &str) -> Cmd {
    Cmd::new("netsh", &["advfirewall", "firewall", "delete", "rule", &format!("name={name}")])
}

/// Everything that must exist for `ip` to be blocked in both directions, in order.
pub fn block_plan(os: Os, target: impl Into<Target>) -> Vec<Ensure> {
    let t = target.into();
    let addr = t.to_string();
    match os {
        Os::Linux => {
            let ipt = iptables(&t);
            vec![
                Ensure {
                    check: Cmd::new(ipt, &["-w", "-n", "-L", LINUX_CHAIN]),
                    add: Cmd::new(ipt, &["-w", "-N", LINUX_CHAIN]),
                },
                linux_hook(ipt, "INPUT"),
                linux_hook(ipt, "OUTPUT"),
                Ensure {
                    check: linux_rule(ipt, "-s", &addr, "-C"),
                    add: linux_rule(ipt, "-s", &addr, "-A"),
                },
                Ensure {
                    check: linux_rule(ipt, "-d", &addr, "-C"),
                    add: linux_rule(ipt, "-d", &addr, "-A"),
                },
            ]
        }
        Os::Windows => {
            let (inbound, outbound) = windows_rule_names(t);
            vec![
                Ensure { check: windows_show(&inbound), add: windows_add(&inbound, "in", &addr) },
                Ensure { check: windows_show(&outbound), add: windows_add(&outbound, "out", &addr) },
            ]
        }
    }
}

/// The checks that together say "this address is blocked right now".
pub fn present_plan(os: Os, target: impl Into<Target>) -> Vec<Cmd> {
    let t = target.into();
    let addr = t.to_string();
    match os {
        Os::Linux => {
            let ipt = iptables(&t);
            vec![
                linux_hook(ipt, "INPUT").check,
                linux_hook(ipt, "OUTPUT").check,
                linux_rule(ipt, "-s", &addr, "-C"),
                linux_rule(ipt, "-d", &addr, "-C"),
            ]
        }
        Os::Windows => {
            let (inbound, outbound) = windows_rule_names(t);
            vec![windows_show(&inbound), windows_show(&outbound)]
        }
    }
}

/// Everything that is removed to lift a block. The chain and its hooks stay: other addresses use them.
pub fn unblock_plan(os: Os, target: impl Into<Target>) -> Vec<Remove> {
    let t = target.into();
    let addr = t.to_string();
    match os {
        Os::Linux => {
            let ipt = iptables(&t);
            vec![
                Remove { check: linux_rule(ipt, "-s", &addr, "-C"), delete: linux_rule(ipt, "-s", &addr, "-D"), legacy: false },
                Remove { check: linux_rule(ipt, "-d", &addr, "-C"), delete: linux_rule(ipt, "-d", &addr, "-D"), legacy: false },
                // The rule an earlier agent put straight into INPUT.
                Remove {
                    check: Cmd::new(ipt, &["-w", "-C", "INPUT", "-s", &addr, "-j", "DROP"]),
                    delete: Cmd::new(ipt, &["-w", "-D", "INPUT", "-s", &addr, "-j", "DROP"]),
                    legacy: true,
                },
            ]
        }
        Os::Windows => {
            let (inbound, outbound) = windows_rule_names(t);
            let old = format!("{WINDOWS_RULE_PREFIX}{}", t.rule_key());
            vec![
                Remove { check: windows_show(&inbound), delete: windows_delete(&inbound), legacy: false },
                Remove { check: windows_show(&outbound), delete: windows_delete(&outbound), legacy: false },
                Remove { check: windows_show(&old), delete: windows_delete(&old), legacy: true },
            ]
        }
    }
}

/// Add every missing rule for `ip`. Rules that already exist are left alone, so this is safe to
/// repeat and never creates a second rule.
pub fn apply_block(os: Os, target: impl Into<Target>) -> Result<(), RemediationError> {
    for step in block_plan(os, target) {
        if !step.check.passes() {
            step.add.run()?;
        }
    }
    Ok(())
}

/// Remove every rule for `ip`. Returns true when at least one rule was removed. A rule that is
/// already gone is not an error.
pub fn remove_block(os: Os, target: impl Into<Target>) -> Result<bool, RemediationError> {
    let mut removed = false;
    for step in unblock_plan(os, target) {
        if !step.check.passes() {
            continue;
        }
        match step.delete.run() {
            Ok(()) => removed = true,
            Err(_) if step.legacy => {}
            Err(e) => return Err(e),
        }
    }
    Ok(removed)
}

/// True when the firewall holds every rule that blocks `ip` in both directions.
pub fn rule_present(os: Os, target: impl Into<Target>) -> Result<bool, RemediationError> {
    Ok(present_plan(os, target).iter().all(Cmd::passes))
}

#[cfg(test)]
#[path = "firewall_range_tests.rs"]
mod range_tests;

#[cfg(test)]
mod tests {
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
}
