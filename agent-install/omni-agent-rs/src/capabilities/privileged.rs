//! The one place the agent starts a privileged OS command (firewall rule, service control).
//!
//! Every caller passes the program and one argv element per parameter. Nothing here joins
//! arguments into a command line and nothing starts a shell, so a value that came from an
//! instruction can never be read as a second argument or as shell syntax.
//!
//! Under `#[cfg(test)]` the real spawn is replaced by a per-thread recorder: it keeps every call
//! (program first, then each argument) and answers from a queue of scripted results, or with
//! success and no output when the queue is empty. Unit tests therefore never touch a real
//! firewall or service manager. Integration tests in `tests/*.rs` compile the library without
//! `cfg(test)`, so none of them may reach a code path that ends here.

use crate::capabilities::remediation_actions::RemediationError;

/// Runs `program` with `args` and maps a non-zero exit to `OperationFailed`.
pub(crate) fn run(program: &str, args: &[&str]) -> Result<(), RemediationError> {
    run_output(program, args).map(|_| ())
}

/// Raw Windows error codes that mean a security product or policy stopped a program: access
/// denied (5), the file contains a virus (225) and blocked by policy (4551).
const SECURITY_OS_CODES: [i32; 3] = [5, 225, 4551];

/// Phrases a blocked command prints (lower case).
const SECURITY_PHRASES: [&str; 4] =
    ["contains a virus", "potentially unwanted software", "blocked by group policy", "application control policy"];

/// True when a spawn failure (`raw_os` code, only meaningful on Windows) or a command's complaint
/// says a local security product stopped it.
pub(crate) fn blocked_by_security(raw_os: Option<i32>, windows: bool, text: &str) -> bool {
    if windows && raw_os.is_some_and(|code| SECURITY_OS_CODES.contains(&code)) {
        return true;
    }
    let lower = text.to_lowercase();
    SECURITY_PHRASES.iter().any(|phrase| lower.contains(phrase))
}

/// The error for a command that could not be started.
pub(crate) fn spawn_failure(program: &str, raw_os: Option<i32>, windows: bool, text: &str) -> RemediationError {
    if blocked_by_security(raw_os, windows, text) {
        RemediationError::BlockedByLocalSecurity(format!("{program} could not be started: {text}"))
    } else {
        RemediationError::OperationFailed(format!("{program} failed to spawn: {text}"))
    }
}

/// The error for a command that ran and exited with a failure.
pub(crate) fn exit_failure(program: &str, code: Option<i32>, stderr: &str) -> RemediationError {
    if blocked_by_security(None, false, stderr) {
        RemediationError::BlockedByLocalSecurity(format!("{program} was stopped: {stderr}"))
    } else {
        RemediationError::OperationFailed(format!("{program} exited with {code:?}: {stderr}"))
    }
}

/// Like [`run`], and returns what the command wrote to standard output.
#[cfg(not(test))]
pub(crate) fn run_output(program: &str, args: &[&str]) -> Result<String, RemediationError> {
    let output = std::process::Command::new(program)
        .args(args)
        .output()
        .map_err(|e| spawn_failure(program, e.raw_os_error(), cfg!(windows), &e.to_string()))?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).into_owned())
    } else {
        Err(exit_failure(program, output.status.code(), String::from_utf8_lossy(&output.stderr).trim()))
    }
}

#[cfg(test)]
pub(crate) fn run_output(program: &str, args: &[&str]) -> Result<String, RemediationError> {
    with_recorder(|rec| {
        let mut call = vec![program.to_string()];
        call.extend(args.iter().map(|a| a.to_string()));
        rec.calls.push(call);
        match rec.script.pop_front() {
            Some(Ok(out)) => Ok(out),
            Some(Err(msg)) => match msg.strip_prefix(SPAWN_MARK).and_then(|c| c.parse::<i32>().ok()) {
                Some(code) => Err(spawn_failure(program, Some(code), true, "scripted spawn failure")),
                None => Err(exit_failure(program, Some(1), &msg)),
            },
            None => Ok(String::new()),
        }
    })
}

/// Marks a scripted failure as "the program could not be started, with this raw OS code".
#[cfg(test)]
const SPAWN_MARK: &str = "\u{1}spawn:";

/// What the test seam saw and what it will answer next.
#[cfg(test)]
#[derive(Default)]
pub(crate) struct Recorder {
    /// Every call in order: element 0 is the program, the rest are its argv elements.
    pub calls: Vec<Vec<String>>,
    /// Answers handed out one per call; an empty queue means success with no output.
    pub script: std::collections::VecDeque<Result<String, String>>,
}

#[cfg(test)]
impl Recorder {
    /// Queue `n` failed calls.
    pub fn fail_next(&mut self, n: usize) {
        for _ in 0..n {
            self.script.push_back(Err("scripted failure".to_string()));
        }
    }

    /// Queue one call that cannot start the program, with this raw OS error code.
    pub fn fail_spawn(&mut self, code: i32) {
        self.script.push_back(Err(format!("{SPAWN_MARK}{code}")));
    }

    /// Queue one successful call that prints `out`.
    pub fn answer_next(&mut self, out: &str) {
        self.script.push_back(Ok(out.to_string()));
    }

    /// The calls as one display line each, for assertions only.
    pub fn lines(&self) -> Vec<String> {
        self.calls.iter().map(|c| c.join(" ")).collect()
    }

    /// Forget the calls but keep the script.
    pub fn clear_calls(&mut self) {
        self.calls.clear();
    }
}

#[cfg(test)]
thread_local! {
    static RECORDER: std::cell::RefCell<Recorder> = std::cell::RefCell::new(Recorder::default());
}

/// Gives a test the recorder of its own thread.
#[cfg(test)]
pub(crate) fn with_recorder<R>(f: impl FnOnce(&mut Recorder) -> R) -> R {
    RECORDER.with(|r| f(&mut r.borrow_mut()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_recorder_keeps_one_argv_element_per_parameter() {
        run("iptables", &["-w", "-C", "OMNI_BLOCK", "-s", "45.33.32.156"]).unwrap();
        let calls = with_recorder(|r| r.calls.clone());
        assert_eq!(calls, vec![vec!["iptables", "-w", "-C", "OMNI_BLOCK", "-s", "45.33.32.156"]]);
    }

    #[test]
    fn scripted_results_are_used_in_order_then_success() {
        with_recorder(|r| {
            r.fail_next(1);
            r.answer_next("hello");
        });
        assert!(run("x", &[]).is_err());
        assert_eq!(run_output("x", &[]).unwrap(), "hello");
        assert_eq!(run_output("x", &[]).unwrap(), "");
    }

    #[test]
    fn the_windows_codes_for_a_security_block_are_recognised_only_on_windows() {
        for code in [5, 225, 4551] {
            assert!(blocked_by_security(Some(code), true, "x"), "{code}");
            assert!(!blocked_by_security(Some(code), false, "x"), "{code} on another system");
            assert!(matches!(spawn_failure("netsh", Some(code), true, "x"), RemediationError::BlockedByLocalSecurity(_)));
        }
        for code in [2, 3, 6, 226, 4550] {
            assert!(!blocked_by_security(Some(code), true, "x"), "{code}");
        }
        assert!(!blocked_by_security(None, true, "x"));
        assert!(matches!(spawn_failure("netsh", Some(2), true, "x"), RemediationError::OperationFailed(_)));
    }

    #[test]
    fn a_complaint_that_names_a_virus_or_a_policy_block_is_a_security_block() {
        for text in [
            "Operation did not complete successfully because the file contains a virus or potentially unwanted software.",
            "This program is blocked by group policy. For more information, contact your system administrator.",
            "BLOCKED BY GROUP POLICY",
            "Your application control policy blocked this file",
        ] {
            assert!(blocked_by_security(None, false, text), "{text}");
            assert!(matches!(exit_failure("netsh", Some(1), text), RemediationError::BlockedByLocalSecurity(_)), "{text}");
        }
        for text in ["", "iptables: Bad rule (does a matching rule exist in that chain?).", "Permission denied", "No chain/target/match by that name."] {
            assert!(!blocked_by_security(None, false, text), "{text}");
            assert!(matches!(exit_failure("iptables", Some(1), text), RemediationError::OperationFailed(_)), "{text}");
        }
    }

    #[test]
    fn the_test_seam_can_script_a_spawn_failure() {
        with_recorder(|r| r.fail_spawn(225));
        assert!(matches!(run("netsh", &["x"]), Err(RemediationError::BlockedByLocalSecurity(_))));
        with_recorder(|r| r.fail_spawn(2));
        assert!(matches!(run("netsh", &["x"]), Err(RemediationError::OperationFailed(_))));
    }
}
