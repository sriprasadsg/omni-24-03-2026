//! What the agent will not block, whatever the instruction says: an address that is not on the
//! public internet, the platform, this host's default gateway and its DNS servers. A block of any
//! of those cuts the host off from the platform or from the network, so the agent refuses by
//! itself, independently of the backend's never-touch list (T-83-12).
//!
//! Everything here is plain code over typed values. The address and network text from an
//! instruction is parsed to a typed value before it is used anywhere, and an IPv4-mapped IPv6
//! address is unwrapped to its IPv4 form first, so `::ffff:10.0.0.1` is judged as `10.0.0.1`.

use crate::capabilities::firewall::{Os, Target};
use crate::capabilities::privileged;
use crate::config::Config;
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};

/// A network wider than this is refused: IPv4 /8, IPv6 /32.
pub const WIDEST_V4: u8 = 8;
pub const WIDEST_V6: u8 = 32;

/// The gateway and DNS addresses of this host, as far as they could be read.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct HostAddrs {
    pub gateways: Vec<IpAddr>,
    pub dns: Vec<IpAddr>,
}

/// True for an address on the public internet. `IpAddr::is_global` is not stable, so the classes
/// are written out: for IPv4 0/8, 10/8, 100.64/10, 127/8, 169.254/16, 172.16/12, 192.0.0/24,
/// 192.0.2/24, 192.168/16, 198.18/15, 198.51.100/24, 203.0.113/24 and 224/3 (multicast and
/// reserved); for IPv6 `::`, `::1`, fc00::/7, fe80::/10, ff00::/8 and 2001:db8::/32.
pub fn is_global_address(ip: IpAddr) -> bool {
    match ip.to_canonical() {
        IpAddr::V4(a) => {
            let [a0, a1, a2, _] = a.octets();
            !(a0 == 0
                || a0 == 10
                || (a0 == 100 && (a1 & 0xc0) == 64)
                || a0 == 127
                || (a0 == 169 && a1 == 254)
                || (a0 == 172 && (a1 & 0xf0) == 16)
                || (a0 == 192 && a1 == 0 && (a2 == 0 || a2 == 2))
                || (a0 == 192 && a1 == 168)
                || (a0 == 198 && (a1 & 0xfe) == 18)
                || (a0 == 198 && a1 == 51 && a2 == 100)
                || (a0 == 203 && a1 == 0 && a2 == 113)
                || a0 >= 224)
        }
        IpAddr::V6(a) => {
            let s0 = a.segments()[0];
            !(a.is_unspecified()
                || a.is_loopback()
                || (s0 & 0xfe00) == 0xfc00
                || (s0 & 0xffc0) == 0xfe80
                || (s0 & 0xff00) == 0xff00
                || (s0 == 0x2001 && a.segments()[1] == 0x0db8))
        }
    }
}

fn max_prefix(ip: IpAddr) -> u8 {
    if ip.is_ipv4() { 32 } else { 128 }
}

/// The address with every bit beyond `prefix` cleared.
fn mask(ip: IpAddr, prefix: u8) -> IpAddr {
    match ip {
        IpAddr::V4(a) => {
            let m = if prefix == 0 { 0 } else { u32::MAX << (32 - u32::from(prefix)) };
            IpAddr::V4(Ipv4Addr::from(u32::from(a) & m))
        }
        IpAddr::V6(a) => {
            let m = if prefix == 0 { 0 } else { u128::MAX << (128 - u32::from(prefix)) };
            IpAddr::V6(Ipv6Addr::from(u128::from(a) & m))
        }
    }
}

/// Parse `address/prefix` with std only. The prefix is plain digits without a sign, a space or a
/// leading zero. The address bits beyond the prefix are cleared, so `45.33.32.77/24` is
/// `45.33.32.0/24`. A mapped IPv6 network of /96 or more becomes the IPv4 network.
pub fn parse_network(text: &str) -> Option<(IpAddr, u8)> {
    let (addr, prefix) = text.split_once('/')?;
    if prefix.is_empty() || prefix.len() > 3 || !prefix.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    if prefix.len() > 1 && prefix.starts_with('0') {
        return None;
    }
    let prefix: u8 = prefix.parse().ok()?;
    let (ip, prefix) = match addr.parse::<IpAddr>().ok()? {
        IpAddr::V6(v6) => match v6.to_ipv4_mapped() {
            Some(v4) => (IpAddr::V4(v4), prefix.checked_sub(96)?),
            None => (IpAddr::V6(v6), prefix),
        },
        v4 => (v4, prefix),
    };
    (prefix <= max_prefix(ip)).then(|| (mask(ip, prefix), prefix))
}

/// An address or a network from text, as a firewall target.
pub fn parse_target(text: &str) -> Option<Target> {
    if text.contains('/') {
        return parse_network(text).map(|(ip, prefix)| Target::network(ip, prefix));
    }
    text.parse::<IpAddr>().ok().map(Target::host)
}

/// True when `addr` lies inside the network (a mapped address is its IPv4 form).
pub fn network_contains(net: (IpAddr, u8), addr: IpAddr) -> bool {
    let addr = addr.to_canonical();
    addr.is_ipv4() == net.0.is_ipv4() && mask(addr, net.1) == net.0
}

fn dedup(mut list: Vec<IpAddr>) -> Vec<IpAddr> {
    let mut seen = Vec::new();
    list.retain(|ip| {
        let fresh = !seen.contains(ip);
        seen.push(*ip);
        fresh
    });
    list
}

/// Default-route gateways from `/proc/net/route` (hex, little-endian, columns Iface Destination
/// Gateway Flags RefCnt Use Metric Mask ...).
pub fn parse_proc_net_route(text: &str) -> Vec<IpAddr> {
    let found = text
        .lines()
        .filter_map(|line| {
            let c: Vec<&str> = line.split_whitespace().collect();
            if c.len() < 8 || c[1] != "00000000" || c[7] != "00000000" {
                return None;
            }
            let gw = u32::from_str_radix(c[2], 16).ok().filter(|g| *g != 0)?;
            Some(IpAddr::V4(Ipv4Addr::from(gw.to_le_bytes())))
        })
        .collect();
    dedup(found)
}

fn address_token(token: &str) -> Option<IpAddr> {
    token.split('%').next()?.parse::<IpAddr>().ok().map(|ip| ip.to_canonical())
}

/// `nameserver <address>` lines of a resolv.conf.
pub fn parse_resolv_conf(text: &str) -> Vec<IpAddr> {
    let found = text
        .lines()
        .filter_map(|line| {
            let mut words = line.split_whitespace();
            (words.next()? == "nameserver").then_some(())?;
            address_token(words.next()?)
        })
        .collect();
    dedup(found)
}

/// Gateways of the default-route rows (`0.0.0.0  0.0.0.0  <gateway> ...`) of `route print -4`,
/// active and persistent routes alike.
pub fn parse_windows_route_print(text: &str) -> Vec<IpAddr> {
    let found = text
        .lines()
        .filter_map(|line| {
            let c: Vec<&str> = line.split_whitespace().collect();
            if c.len() < 3 || c[0] != "0.0.0.0" || c[1] != "0.0.0.0" {
                return None;
            }
            c[2].parse::<Ipv4Addr>().ok().map(IpAddr::V4)
        })
        .collect();
    dedup(found)
}

/// Every address that appears in `netsh interface ipv4|ipv6 show dnsservers` output. Taking every
/// address errs on the side of refusing, which is the safe side.
pub fn parse_windows_dns(text: &str) -> Vec<IpAddr> {
    dedup(text.split_whitespace().filter_map(address_token).collect())
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

/// The gateway and DNS servers of this host. Best effort: what cannot be read is logged and left
/// out, and the block goes on (assumption A-83-GW; the non-global refusal already covers almost
/// every gateway). Tests get what `set_test_host_addrs` set, never this machine's real files.
pub fn host_addrs(os: Os) -> HostAddrs {
    #[cfg(test)]
    {
        let _ = os;
        TEST_HOST.with(|t| t.borrow().clone())
    }
    #[cfg(not(test))]
    {
        read_host_addrs(os)
    }
}

#[cfg_attr(test, allow(dead_code))]
pub(crate) fn read_host_addrs(os: Os) -> HostAddrs {
    let mut host = HostAddrs::default();
    match os {
        Os::Linux => {
            match std::fs::read_to_string("/proc/net/route") {
                Ok(text) => host.gateways = parse_proc_net_route(&text),
                Err(e) => log::warn!("Could not read the default gateway: {e}"),
            }
            for path in ["/etc/resolv.conf", "/run/systemd/resolve/resolv.conf"] {
                if let Ok(text) = std::fs::read_to_string(path) {
                    host.dns.extend(parse_resolv_conf(&text));
                }
            }
        }
        Os::Windows => {
            match privileged::run_output("route", &["print", "-4"]) {
                Ok(text) => host.gateways = parse_windows_route_print(&text),
                Err(e) => log::warn!("Could not read the default gateway: {e}"),
            }
            for family in ["ipv4", "ipv6"] {
                match privileged::run_output("netsh", &["interface", family, "show", "dnsservers"]) {
                    Ok(text) => host.dns.extend(parse_windows_dns(&text)),
                    Err(e) => log::warn!("Could not read the {family} DNS servers: {e}"),
                }
            }
        }
    }
    host.dns = dedup(host.dns);
    if host.dns.is_empty() {
        log::warn!("No DNS server could be read; blocks go on without that check");
    }
    host
}

/// Name lookup for a platform host that is given as a name. Tests never resolve anything.
pub fn system_lookup(host: &str) -> Vec<IpAddr> {
    #[cfg(test)]
    {
        let _ = host;
        Vec::new()
    }
    #[cfg(not(test))]
    {
        use std::net::ToSocketAddrs;
        match (host, 0u16).to_socket_addrs() {
            Ok(found) => found.map(|a| a.ip().to_canonical()).collect(),
            Err(e) => {
                log::warn!("Could not resolve the platform host {host}: {e}");
                Vec::new()
            }
        }
    }
}

/// The platform's addresses: `api_base_url` as an IP literal, or the lookup of its name.
fn platform_addrs(cfg: &Config, lookup: &dyn Fn(&str) -> Vec<IpAddr>) -> Vec<IpAddr> {
    let Ok(url) = reqwest::Url::parse(&cfg.api_base_url) else { return Vec::new() };
    let Some(host) = url.host_str() else { return Vec::new() };
    let host = host.trim_start_matches('[').trim_end_matches(']');
    match host.parse::<IpAddr>() {
        Ok(ip) => vec![ip.to_canonical()],
        Err(_) => lookup(host).into_iter().map(|a| a.to_canonical()).collect(),
    }
}

fn covers(target: &Target, addr: IpAddr) -> bool {
    match target.prefix {
        Some(prefix) => network_contains((target.addr, prefix), addr),
        None => target.addr == addr.to_canonical(),
    }
}

/// Why this target must not be blocked, or None. Checked by the agent itself before any state
/// write or firewall command, whatever the backend decided: not globally routable, wider than
/// /8 (IPv6 /32), the platform host, the default gateway, a DNS server.
pub fn refuse_reason(
    target: &Target,
    cfg: &Config,
    os: Os,
    lookup: &dyn Fn(&str) -> Vec<IpAddr>,
) -> Option<&'static str> {
    if !is_global_address(target.addr) {
        return Some("That address is not on the public internet and is never blocked.");
    }
    let widest = if target.addr.is_ipv4() { WIDEST_V4 } else { WIDEST_V6 };
    if target.prefix.is_some_and(|p| p < widest) {
        return Some("That network is wider than the agent will block.");
    }
    if platform_addrs(cfg, lookup).into_iter().any(|a| covers(target, a)) {
        return Some("That includes the platform's address and is never blocked.");
    }
    let host = host_addrs(os);
    if host.gateways.iter().chain(&host.dns).any(|a| covers(target, *a)) {
        return Some("That includes this computer's gateway or a DNS server and is never blocked.");
    }
    None
}

#[cfg(test)]
#[path = "net_safety_tests.rs"]
mod tests;
