//! What the host can still reach once it is isolated, tested from this very process (WR-20).
//!
//! The platform must still answer (`tcp_self_test`), and nothing outside the carve-out may: each
//! default gateway of the host is tried on TCP 443. A connection, or a refusal (a reset came back),
//! proves that traffic left the host, so the isolation is `not_effective` and is undone. A timeout
//! or a local block proves nothing either way and counts as isolated, so a gateway that drops
//! every packet never undoes a working isolation.
//!
//! Windows: a default-block policy still lets every enabled allow rule through (Remote Desktop
//! when it was turned on, Core Networking, a rule an installer added for one program). The probe
//! sees only what this process can reach, so that limit is stated in the isolated answer
//! (`isolation::WINDOWS_LIMIT`), not closed.

use crate::capabilities::firewall::Os;
use crate::capabilities::isolation_plan::CarveOut;
use std::net::{IpAddr, SocketAddr, TcpStream};
use std::time::{Duration, Instant};

/// The port an outside address is tried on.
pub const OUTSIDE_PORT: u16 = 443;
const OUTSIDE_TIMEOUT: Duration = Duration::from_millis(1500);

/// What the checks after the block saw.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Reach {
    /// The platform answered from this process.
    pub platform: bool,
    /// Something outside the carve-out answered: the host is not isolated.
    pub outside: bool,
}

/// Both checks against this host's real gateways.
pub fn reach(os: Os, carve: &CarveOut) -> Reach {
    let gateways = crate::capabilities::net_safety::host_addrs(os).gateways;
    let outside = outside_targets(carve, &gateways)
        .iter()
        .any(|target| answered(&TcpStream::connect_timeout(target, OUTSIDE_TIMEOUT)));
    Reach { platform: tcp_self_test(carve), outside }
}

/// Each gateway once, on `OUTSIDE_PORT`, leaving out loopback and every address the carve-out
/// keeps open.
pub fn outside_targets(carve: &CarveOut, gateways: &[IpAddr]) -> Vec<SocketAddr> {
    let mut out: Vec<SocketAddr> = Vec::new();
    for ip in gateways.iter().map(|g| g.to_canonical()) {
        let kept = ip.is_loopback() || ip.is_unspecified() || carve.addresses.contains(&ip);
        if !kept && !out.iter().any(|t| t.ip() == ip) {
            out.push(SocketAddr::new(ip, OUTSIDE_PORT));
        }
    }
    out
}

/// True when the far side answered: a connection, or a refusal or reset that came back from it.
pub fn answered(result: &std::io::Result<TcpStream>) -> bool {
    use std::io::ErrorKind::{ConnectionRefused, ConnectionReset};
    match result {
        Ok(_) => true,
        Err(e) => matches!(e.kind(), ConnectionRefused | ConnectionReset),
    }
}

/// Connect to the platform from this process: three tries over at most 5 seconds.
pub fn tcp_self_test(carve: &CarveOut) -> bool {
    let deadline = Instant::now() + Duration::from_secs(5);
    for attempt in 0..3 {
        for ip in &carve.addresses {
            let left = deadline.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return false;
            }
            let addr = SocketAddr::new(*ip, carve.port);
            if TcpStream::connect_timeout(&addr, left.min(Duration::from_millis(1500))).is_ok() {
                return true;
            }
        }
        if attempt < 2 {
            std::thread::sleep(Duration::from_millis(300));
        }
    }
    false
}
