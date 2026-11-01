//! RED stub: every function panics until the implementation lands.
use crate::capabilities::firewall::Os;
use crate::capabilities::remediation_actions;
use crate::config::Config;
use serde_json::{json, Value};
use std::collections::HashMap;

pub const GRACE_SECONDS: i64 = 60;
pub const REPORT_CACHE_SECONDS: i64 = 60;
pub const MAX_WATCHED: usize = 50;
pub const RESTART_POLLS: u32 = 10;

#[derive(Debug, Clone, PartialEq)]
pub enum Health {
    Running,
    Pending,
    Stopped,
    Failed { state: String, exit_code: Option<i64> },
    Unknown,
}

pub fn classify_systemd(_output: &str) -> Health { todo!() }
pub fn classify_sc(_query: &str, _qc: &str) -> Health { todo!() }
pub fn status_of(_os: Os, _name: &str) -> Health { todo!() }
pub fn changed_watched(_current: Option<&[String]>, _body: &Value) -> Option<Vec<String>> { todo!() }
pub fn update_watched_from_heartbeat(_cfg: &mut Config, _body: &Value) { todo!() }
pub(crate) fn failure_id(_name: &str, _since: i64) -> String { todo!() }

#[derive(Default)]
pub struct Watch {
    first_seen: HashMap<String, i64>,
}

pub fn report(_enabled: Option<&[String]>, _watched: &[String], _now: i64) -> Vec<Value> { todo!() }
pub(crate) fn report_with(_w: &mut Watch, _os: Option<Os>, _enabled: Option<&[String]>, _watched: &[String], _now: i64) -> Vec<Value> { todo!() }
pub fn restart(_os: Os, _name: &str, _pause: &dyn Fn()) -> Value { todo!() }
pub(crate) fn restart_arm(_item: &Value, _cfg: &Config, _client: &reqwest::Client) -> Value { todo!() }

#[cfg(test)]
#[path = "service_watch_tests.rs"]
mod tests;
