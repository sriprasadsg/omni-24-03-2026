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
    pub(crate) fn new(program: &'static str, args: &[&str]) -> Cmd {
        Cmd { program, args: args.iter().map(|a| a.to_string()).collect() }
    }

    pub(crate) fn run(&self) -> Result<(), RemediationError> {
        let args: Vec<&str> = self.args.iter().map(String::as_str).collect();
        privileged::run(self.program, &args)
    }

    /// Whether what this check asks about is there (WR-19). Only a definite "no" is `Ok(false)`:
    /// iptables exit code 1, and for netsh "No rules match" or exit code 1 (netsh says it in the
    /// local language). A check that cannot start, runs out of time or fails any other way is an
    /// error, so a caller neither adds a second copy of a rule nor forgets one still in place.
    pub(crate) fn probe(&self) -> Result<bool, RemediationError> {
        let args: Vec<&str> = self.args.iter().map(String::as_str).collect();
        let done = privileged::run_status(self.program, &args)?;
        let netsh = self.program == "netsh";
        if netsh && (done.stdout.contains("No rules match") || done.code == Some(1)) {
            return Ok(false);
        }
        match done.code {
            Some(0) => Ok(true),
            Some(1) if !netsh => Ok(false),
            code => Err(privileged::exit_failure(self.program, code, done.stderr.trim())),
        }
    }

    /// True only when the check says it is there; a check that could not be made is a no.
    pub(crate) fn passes(&self) -> bool {
        matches!(self.probe(), Ok(true))
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
/// repeat and never creates a second rule. A check that cannot be made fails the step.
pub fn apply_block(os: Os, target: impl Into<Target>) -> Result<(), RemediationError> {
    for step in block_plan(os, target) {
        if !step.check.probe()? {
            step.add.run()?;
        }
    }
    Ok(())
}

/// Remove every rule for `ip`. Returns true when at least one rule was removed. A rule that is
/// already gone is not an error; a check that cannot be made is, so the caller keeps its claim
/// and tries again (a legacy step's never fails the removal).
pub fn remove_block(os: Os, target: impl Into<Target>) -> Result<bool, RemediationError> {
    let mut removed = false;
    for step in unblock_plan(os, target) {
        match step.check.probe() {
            Ok(true) => {}
            Ok(false) => continue,
            Err(_) if step.legacy => continue,
            Err(e) => return Err(e),
        }
        match step.delete.run() {
            Ok(()) => removed = true,
            Err(_) if step.legacy => {}
            Err(e) => return Err(e),
        }
    }
    Ok(removed)
}

/// True when the firewall holds every rule that blocks `ip` in both directions; an error when a
/// check could not be made.
pub fn rule_present(os: Os, target: impl Into<Target>) -> Result<bool, RemediationError> {
    for check in present_plan(os, target) {
        if !check.probe()? {
            return Ok(false);
        }
    }
    Ok(true)
}

#[cfg(test)]
#[path = "firewall_range_tests.rs"]
mod range_tests;

#[cfg(test)]
#[path = "firewall_tests.rs"]
mod tests;
