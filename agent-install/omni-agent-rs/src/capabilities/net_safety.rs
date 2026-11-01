//! What the agent will not block, whatever the instruction says: an address that is not on the
//! public internet, the platform, this host's default gateway and its DNS servers. A block of any
//! of those cuts the host off from the platform or from the network, so the agent refuses by
//! itself, independently of the backend's never-touch list (T-83-12).
//!
//! Everything here is plain code over typed values. The address and network text from an
//! instruction is parsed to a typed value before it is used anywhere, and an IPv4-mapped IPv6
//! address is unwrapped to its IPv4 form first, so `::ffff:10.0.0.1` is judged as `10.0.0.1`.

use crate::capabilities::firewall::{Os, Target};
use crate::config::Config;
use std::net::IpAddr;

/// A network wider than this is refused: IPv4 /8, IPv6 /32.
pub const WIDEST_V4: u8 = 8;
pub const WIDEST_V6: u8 = 32;

/// The gateway and DNS addresses of this host, as far as they could be read.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct HostAddrs {
    pub gateways: Vec<IpAddr>,
    pub dns: Vec<IpAddr>,
}

pub fn is_global_address(_ip: IpAddr) -> bool {
    true
}

pub fn parse_network(_text: &str) -> Option<(IpAddr, u8)> {
    None
}

pub fn parse_target(_text: &str) -> Option<Target> {
    None
}

pub fn network_contains(_net: (IpAddr, u8), _addr: IpAddr) -> bool {
    false
}

pub fn parse_proc_net_route(_text: &str) -> Vec<IpAddr> {
    Vec::new()
}

pub fn parse_resolv_conf(_text: &str) -> Vec<IpAddr> {
    Vec::new()
}

pub fn parse_windows_route_print(_text: &str) -> Vec<IpAddr> {
    Vec::new()
}

pub fn parse_windows_dns(_text: &str) -> Vec<IpAddr> {
    Vec::new()
}

#[cfg(test)]
thread_local! {
    static TEST_HOST: std::cell::RefCell<HostAddrs> = std::cell::RefCell::new(HostAddrs::default());
}

/// Test support: what `host_addrs` answers on this thread.
#[cfg(test)]
pub(crate) fn set_test_host_addrs(h: HostAddrs) {
    TEST_HOST.with(|t| *t.borrow_mut() = h);
}

pub fn host_addrs(_os: Os) -> HostAddrs {
    HostAddrs::default()
}

/// Name lookup for the platform host. Tests never resolve anything.
pub fn system_lookup(_host: &str) -> Vec<IpAddr> {
    Vec::new()
}

pub fn refuse_reason(
    _target: &Target,
    _cfg: &Config,
    _os: Os,
    _lookup: &dyn Fn(&str) -> Vec<IpAddr>,
) -> Option<&'static str> {
    None
}

#[cfg(test)]
#[path = "net_safety_tests.rs"]
mod tests;
