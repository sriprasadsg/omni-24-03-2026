//! Host isolation that cannot lose the host (RESP-05, D-15).
//!
//! `apply` runs in this order and stops at the first failure, backing out at once:
//!
//! 1. write the isolation record (id, `revertAt` = now + 4 hours) to `response_state.json`;
//! 2. add the management allow rules (loopback, the platform, DHCP);
//! 3. check that every one of those rules exists;
//! 4. only then block everything else;
//! 5. check that the block took effect (`not_effective` when a Group Policy firewall or a firewall
//!    manager overrode it);
//! 6. connect to the platform from this very process (`self_test_failed` when it cannot).
//!
//! The agent holds its own revert. `revert_due` (called by the sweeper every 15 seconds and once
//! at start-up) ends an isolation whose `revertAt` has come unless a person confirmed it, with no
//! help from the network. A state file that cannot be read leads to a revert of whatever
//! isolation rules are found, because losing the host is the worse failure. Reverting lifts the
//! block before it removes the allow rules, and a lift that failed keeps the allow rules.
//!
//! One process-wide lock serialises apply, restore and the revert passes. A confirmation arrives
//! through the state file's own lock, so it is either processed before a revert pass (and cancels
//! it) or finds the isolation gone (and changes nothing).

use crate::capabilities::firewall::Os;
use crate::capabilities::isolation_plan::CarveOut;
use crate::capabilities::remediation_actions::RemediationError;
use crate::capabilities::response_state::Store;
use crate::config::Config;
#[allow(unused_imports)]
use serde_json::{json, Value};
use std::net::IpAddr;

pub fn carve_out(_cfg: &Config, _lookup: &dyn Fn(&str) -> Vec<IpAddr>, _resolvers: &dyn Fn() -> Vec<IpAddr>) -> Result<CarveOut, &'static str> { todo!() }
pub fn platform_has_host(_cfg: &Config) -> bool { todo!() }
pub fn tcp_self_test(_carve: &CarveOut) -> bool { todo!() }
pub fn apply(_store: &Store, _os: Os, _cfg: &Config, _id: &str, _now: i64, _connect: &dyn Fn(&CarveOut) -> bool) -> Value { todo!() }
#[allow(clippy::too_many_arguments)]
pub fn apply_with(
    _store: &Store, _os: Os, _cfg: &Config, _id: &str, _now: i64,
    _lookup: &dyn Fn(&str) -> Vec<IpAddr>, _resolvers: &dyn Fn() -> Vec<IpAddr>, _connect: &dyn Fn(&CarveOut) -> bool,
) -> Value { todo!() }
pub fn restore(_store: &Store, _os: Os, _id: &str, _now: i64) -> Value { todo!() }

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct PassOutcome {
    pub reverted: bool,
    pub error: Option<String>,
}

pub fn revert_due(_store: &Store, _os: Os, _now: i64) -> PassOutcome { todo!() }
pub fn start_up(_store: &Store, _os: Os, _now: i64) -> PassOutcome { todo!() }
pub fn confirmed_ids(_body: &Value) -> Vec<String> { todo!() }
pub fn apply_confirmations(_store: &Store, _ids: &[String]) -> Result<bool, RemediationError> { todo!() }
pub fn apply_body(_body: &Value) { todo!() }
pub fn response_state_report(_store: &Store, _now: i64) -> Value { todo!() }

#[cfg(test)]
#[path = "isolation_tests.rs"]
mod tests;
#[cfg(test)]
#[path = "isolation_pass_tests.rs"]
mod pass_tests;
