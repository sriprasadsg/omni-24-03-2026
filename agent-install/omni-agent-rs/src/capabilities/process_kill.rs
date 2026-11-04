//! Ending a process that a person approved, and only that process (Autonomous Ops, RESP-06).
//!
//! An approval can be a day old, so a pid or a path may mean something else by the time it is
//! used. The instruction therefore names the program (`expected_exe`) and the processes that were
//! running it when the card was made (`processes`: pid and start time). `plan_kill` is a pure
//! function that sorts a process list into three groups:
//!
//! - `kill`: a listed process (same pid and start time) that is running the approved image, or any
//!   process running the quarantined image from its stored path;
//! - `unconfirmed`: a process the plan cannot bind to the approval, which is never signalled and
//!   never reported gone. With nothing moved, an unlisted process on the approved image is one:
//!   it may be another user's run of a shared program the person never saw on the card;
//! - everything else, which is left alone (a pid that now belongs to an unrelated program).
//!
//! After a quarantine the file has moved, so the image shows up under its stored path on Linux
//! when the rename stayed on one volume, and under its original path on Windows or after a copy
//! across volumes. Both are handled. A process that only reports the original path and was not
//! listed is left alone, because a new file may stand there now.
//!
//! `kill_body` says the process is gone (verify ok) only when no named process and no process
//! running the stored image is left after a bounded wait.

use crate::capabilities::quarantine::{running_now, same_exe, RunningProcess, STILL_RUNNING_CAP};
use serde_json::{json, Value};
use std::time::Duration;

/// Two readings of one process's start time may differ this much. Linux adds a boot time read
/// from `/proc/stat`, which moves when the clock is corrected.
pub const START_TIME_TOLERANCE_SECONDS: u64 = 2;

const WAIT_READS: usize = 10;
const WAIT_STEP: Duration = Duration::from_millis(500);

/// A process the card named: where it ran and since when.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ListedProcess {
    pub pid: u32,
    pub start_time: u64,
}

#[derive(Debug, Clone)]
pub struct KillRequest {
    /// The program the person approved ending.
    pub expected_exe: String,
    /// Where the quarantine put that program, when it was moved.
    pub moved_exe: Option<String>,
    pub listed: Vec<ListedProcess>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct KillPlan {
    pub kill: Vec<RunningProcess>,
    pub unconfirmed: Vec<RunningProcess>,
}

/// The same process: equal pid and start times within the tolerance.
pub fn same_process(pid_a: u32, start_a: u64, pid_b: u32, start_b: u64) -> bool {
    pid_a == pid_b && start_a.abs_diff(start_b) <= START_TIME_TOLERANCE_SECONDS
}

fn is_critical(p: &RunningProcess, self_pid: u32) -> bool {
    p.pid <= 1
        || p.pid == self_pid
        || crate::capabilities::remediation_actions::CRITICAL_PROCESS_NAMES
            .iter()
            .any(|n| *n == p.name.to_ascii_lowercase())
}

/// Sort `list` for `req`. See the module comment for the rules.
pub fn plan_kill(list: &[RunningProcess], req: &KillRequest, windows_style: bool, self_pid: u32) -> KillPlan {
    let mut plan = KillPlan::default();
    for p in list {
        let exe = p.exe.as_deref();
        let on_stored = req.moved_exe.as_deref().is_some_and(|m| same_exe(exe, m, windows_style));
        let on_original = same_exe(exe, &req.expected_exe, windows_style);
        let listed = req.listed.iter().find(|l| l.pid == p.pid);
        let bound = if on_stored {
            Some(true) // only the quarantined image can run from its stored path
        } else {
            match (listed, req.moved_exe.is_some()) {
                (None, true) => None, // a new file may stand at the original path now
                (None, false) => on_original.then_some(false), // another instance the card never named (WR-15)
                (Some(l), moved) => {
                    let same_start = same_process(p.pid, p.start_time, l.pid, l.start_time);
                    match (same_start, on_original, exe.is_some()) {
                        (true, true, _) => Some(true),
                        (_, true, _) if !moved => Some(true), // nothing moved: the image alone decides
                        (_, true, _) => Some(false),          // replaced file or clock step: unknown
                        (true, false, _) => Some(false),      // alive, but no longer shows the image
                        (false, false, false) => Some(false), // reused pid, nothing to tell
                        (false, false, true) => None,         // reused pid, unrelated program
                    }
                }
            }
        };
        match bound {
            Some(true) if is_critical(p, self_pid) => plan.unconfirmed.push(p.clone()),
            Some(true) => plan.kill.push(p.clone()),
            Some(false) => plan.unconfirmed.push(p.clone()),
            None => {}
        }
    }
    plan
}

/// The planned processes (killed or not) that `later` still shows, matched by pid and start time,
/// so a pid reused during the wait is not a survivor and a process that left is not one.
pub fn survivors(plan: &KillPlan, later: &[RunningProcess]) -> Vec<RunningProcess> {
    let mut out: Vec<RunningProcess> = Vec::new();
    for p in plan.kill.iter().chain(plan.unconfirmed.iter()) {
        if later.iter().any(|a| same_process(a.pid, a.start_time, p.pid, p.start_time))
            && !out.iter().any(|o| o.pid == p.pid)
        {
            out.push(p.clone());
        }
    }
    out
}

fn entries(list: &[RunningProcess]) -> Value {
    Value::Array(
        list.iter()
            .take(STILL_RUNNING_CAP)
            .map(|p| json!({"pid": p.pid, "name": p.name, "start_time": p.start_time}))
            .collect(),
    )
}

fn merged(a: &[RunningProcess], b: &[RunningProcess]) -> Vec<RunningProcess> {
    let mut out = a.to_vec();
    for p in b {
        if !out.iter().any(|o| o.pid == p.pid) {
            out.push(p.clone());
        }
    }
    out
}

/// The result body. Checked in this order: nothing planned is gone; nothing signalled and
/// something unconfirmed is a refusal; something signalled with no survivor and nothing
/// unconfirmed is done; anything else is a survival with every survivor and unconfirmed entry.
pub fn kill_body(plan: &KillPlan, survivors: &[RunningProcess]) -> Value {
    let check = json!({"ok": false, "check": "process_gone"});
    if plan.kill.is_empty() && plan.unconfirmed.is_empty() {
        return json!({"status": "success", "outcome": "process_gone", "verify": {"ok": true, "check": "process_gone"}});
    }
    if plan.kill.is_empty() {
        return json!({
            "status": "error", "outcome": "refused", "verify": check,
            "still_running": entries(&plan.unconfirmed),
            "error": "The process does not match the expected program.",
        });
    }
    if survivors.is_empty() && plan.unconfirmed.is_empty() {
        return json!({"status": "success", "outcome": "killed", "verify": {"ok": true, "check": "process_gone"}});
    }
    json!({
        "status": "success", "outcome": "killed", "verify": check,
        "still_running": entries(&merged(survivors, &plan.unconfirmed)),
    })
}

/// A refusal that signalled nothing, before any process list was read.
pub fn refused_body(why: &str) -> Value {
    json!({
        "status": "error", "outcome": "refused", "verify": {"ok": false, "check": "process_gone"},
        "still_running": [], "error": why,
    })
}

/// Processes in `later` that run the approved image and were not in the plan: another instance of
/// the program, or a restarted one. They count against "gone".
fn extra_instances(plan: &KillPlan, later: &[RunningProcess], req: &KillRequest, windows_style: bool) -> Vec<RunningProcess> {
    let image = req.moved_exe.as_deref().unwrap_or(&req.expected_exe);
    later
        .iter()
        .filter(|p| same_exe(p.exe.as_deref(), image, windows_style))
        .filter(|p| !plan.kill.iter().chain(plan.unconfirmed.iter()).any(|k| k.pid == p.pid))
        .cloned()
        .collect()
}

async fn list_now() -> Vec<RunningProcess> {
    tokio::task::spawn_blocking(running_now).await.unwrap_or_default()
}

/// Ask the operating system to end `p`, if it is still the process the plan saw.
fn signal(p: &RunningProcess) -> bool {
    use sysinfo::{Pid, ProcessRefreshKind, ProcessesToUpdate, System};
    let pid = Pid::from_u32(p.pid);
    let mut sys = System::new();
    sys.refresh_processes_specifics(ProcessesToUpdate::Some(&[pid]), true, ProcessRefreshKind::nothing());
    match sys.process(pid) {
        Some(now) if same_process(p.pid, now.start_time(), p.pid, p.start_time) => now.kill(),
        _ => false,
    }
}

/// Plan, signal, wait up to 10 x 500 ms for the named processes to leave, and answer. The wait is
/// there because a signal is asynchronous: an immediate read would report a false survivor.
pub async fn kill_by_exe(req: KillRequest) -> Value {
    let windows_style = cfg!(windows);
    let plan = plan_kill(&list_now().await, &req, windows_style, std::process::id());
    for p in &plan.kill {
        signal(p);
    }
    let mut later = list_now().await;
    let left = |later: &[RunningProcess]| {
        merged(&survivors(&plan, later), &extra_instances(&plan, later, &req, windows_style))
    };
    for _ in 0..WAIT_READS {
        let waiting = !plan.kill.is_empty()
            && left(&later).iter().any(|p| !plan.unconfirmed.iter().any(|u| u.pid == p.pid));
        if !waiting {
            break;
        }
        tokio::time::sleep(WAIT_STEP).await;
        later = list_now().await;
    }
    kill_body(&plan, &left(&later))
}

/// Read `expected_exe` and `processes` from an instruction's parameters. Nothing is signalled for
/// any of the refusals: an empty program, no list, a list over the cap, pid 0 or 1, start time 0.
pub fn parse_request(params: &Value) -> Result<(String, Vec<ListedProcess>), String> {
    let exe = params.get("expected_exe").and_then(Value::as_str).unwrap_or("");
    if exe.is_empty() {
        return Err("expected_exe is required.".to_string());
    }
    let list = params.get("processes").and_then(Value::as_array).filter(|l| !l.is_empty());
    let Some(list) = list else { return Err("processes must name at least one process.".to_string()) };
    if list.len() > STILL_RUNNING_CAP {
        return Err(format!("processes holds more than {STILL_RUNNING_CAP} entries."));
    }
    let mut out = Vec::with_capacity(list.len());
    for item in list {
        let pid = item.get("pid").and_then(Value::as_u64).and_then(|v| u32::try_from(v).ok());
        let start = item.get("start_time").and_then(Value::as_u64);
        match (pid, start) {
            (Some(pid), Some(start_time)) if pid > 1 && start_time > 0 => out.push(ListedProcess { pid, start_time }),
            _ => return Err("Each process needs a pid above 1 and a start_time above 0.".to_string()),
        }
    }
    Ok((exe.to_string(), out))
}

#[cfg(test)]
#[path = "process_kill_tests.rs"]
mod tests;
