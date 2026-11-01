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

/// Like [`run`], and returns what the command wrote to standard output.
#[cfg(not(test))]
pub(crate) fn run_output(program: &str, args: &[&str]) -> Result<String, RemediationError> {
    let output = std::process::Command::new(program)
        .args(args)
        .output()
        .map_err(|e| RemediationError::OperationFailed(format!("{program} failed to spawn: {e}")))?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).into_owned())
    } else {
        Err(RemediationError::OperationFailed(format!(
            "{program} exited with {:?}: {}",
            output.status.code(),
            String::from_utf8_lossy(&output.stderr).trim()
        )))
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
            Some(Err(msg)) => Err(RemediationError::OperationFailed(msg)),
            None => Ok(String::new()),
        }
    })
}

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
}
