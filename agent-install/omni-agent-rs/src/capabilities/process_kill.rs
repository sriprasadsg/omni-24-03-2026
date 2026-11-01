//! Ending a process that a person approved, and only that process (Autonomous Ops, RESP-06).
//! The kill itself arrives with the next change; this part holds what the quarantine shares.

/// Two readings of one process's start time may differ this much. Linux adds a boot time read
/// from `/proc/stat`, which moves when the clock is corrected.
pub const START_TIME_TOLERANCE_SECONDS: u64 = 2;

/// The same process: equal pid and start times within the tolerance.
pub fn same_process(pid_a: u32, start_a: u64, pid_b: u32, start_b: u64) -> bool {
    pid_a == pid_b && start_a.abs_diff(start_b) <= START_TIME_TOLERANCE_SECONDS
}
