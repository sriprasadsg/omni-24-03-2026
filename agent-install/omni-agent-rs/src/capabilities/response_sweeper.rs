//! The independent task that ends blocks on time.
//!
//! It reads only `response_state.json` and the local firewall, so a host with no token, no route
//! or an unreachable platform still removes its blocks when they run out. It runs one start-up
//! pass (on Linux that also puts back the rules a reboot lost) and then an expiry pass every 15
//! seconds; each pass also ends an isolation whose revert time has come (`isolation::revert_due`).
//! A pass that panics is logged and the loop carries on. Nothing here talks to the
//! backend: an expiry changes nothing there (D-14).

use crate::capabilities::firewall::Os;
use crate::capabilities::isolation;
use crate::capabilities::response_state::{expire_due, reapply_live, start_up, Store};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::watch::Receiver;

/// How often the sweeper looks at the claims.
pub const PERIOD: Duration = Duration::from_secs(15);

/// Start the sweeper. Call it once, before registration or any network call. A platform with no
/// firewall plan starts nothing.
pub fn spawn(stop_rx: Option<Receiver<bool>>) {
    let Some(os) = Os::current() else { return };
    let store = Store::default();
    let pending = AtomicBool::new(false);
    let pass = Arc::new(move |first: bool| {
        sweep(&store, os, crate::capabilities::response_actions::now_epoch(), first, &pending)
    });
    tokio::spawn(run(stop_rx, PERIOD, pass));
}

/// One pass. `first` is the start-up pass. When a start-up re-apply failed (the firewall may not
/// be ready early in boot) it is tried again on each later pass until it works, so a block that a
/// reboot lost is not forgotten.
pub(crate) fn sweep(store: &Store, os: Os, now: i64, first: bool, pending: &AtomicBool) {
    if first {
        let report = start_up(store, os, now);
        log_report("start-up", &report);
        pending.store(os == Os::Linux && !report.failed.is_empty(), Ordering::SeqCst);
        log_isolation(&isolation::start_up(store, os, now));
        return;
    }
    let report = expire_due(store, os, now);
    log_report("expiry", &report);
    if report.recovered.is_some() {
        // The isolation record went with the set-aside file: as at start-up, isolation rules with
        // no record come out, so the host keeps its network (WR-18).
        log_isolation(&isolation::start_up(store, os, now));
        return;
    }
    log_isolation(&isolation::revert_due(store, os, now));
    if pending.load(Ordering::SeqCst) {
        let again = reapply_live(store, os, now);
        log_report("re-apply", &again);
        pending.store(!again.failed.is_empty() || again.error.is_some(), Ordering::SeqCst);
    }
}

fn log_isolation(pass: &isolation::PassOutcome) {
    if pass.reverted {
        log::info!("Response isolation pass: the host was taken out of isolation");
    }
}

fn log_report(what: &str, r: &crate::capabilities::response_state::PassReport) {
    if r.removed.is_empty() && r.reapplied.is_empty() && r.dropped == 0 {
        return;
    }
    log::info!(
        "Response {what} pass: {} block(s) ended, {} rule(s) put back, {} claim(s) forgotten",
        r.removed.len(),
        r.reapplied.len(),
        r.dropped
    );
}

pub(crate) async fn run<F>(mut stop: Option<Receiver<bool>>, period: Duration, pass: Arc<F>)
where
    F: Fn(bool) + Send + Sync + 'static,
{
    let mut tick = tokio::time::interval(period);
    tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    let mut first = true;
    loop {
        tokio::select! {
            _ = tick.tick() => {}
            _ = stopped(&mut stop) => return,
        }
        let (p, is_first) = (pass.clone(), first);
        // spawn_blocking: the file and firewall work must not hold up the async runtime, and a
        // panic comes back as an error here instead of ending the loop.
        match tokio::task::spawn_blocking(move || p(is_first)).await {
            Ok(()) => first = false,
            Err(e) => log::error!("A response sweeper pass failed and will be tried again: {e}"),
        }
    }
}

async fn stopped(stop: &mut Option<Receiver<bool>>) {
    match stop {
        None => std::future::pending::<()>().await,
        Some(rx) => loop {
            if *rx.borrow() {
                return;
            }
            if rx.changed().await.is_err() {
                std::future::pending::<()>().await;
            }
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::{Arc, Mutex};

    #[tokio::test]
    async fn the_loop_runs_a_first_pass_then_repeats_survives_a_panic_and_stops_on_request() {
        let calls = Arc::new(AtomicUsize::new(0));
        let firsts = Arc::new(Mutex::new(Vec::new()));
        let (tx, rx) = tokio::sync::watch::channel(false);
        let pass = {
            let calls = calls.clone();
            let firsts = firsts.clone();
            Arc::new(move |first: bool| {
                let n = calls.fetch_add(1, Ordering::SeqCst);
                firsts.lock().unwrap().push(first);
                if n == 1 {
                    panic!("a pass blew up");
                }
            })
        };
        let task = tokio::spawn(run(Some(rx), Duration::from_millis(10), pass));
        for _ in 0..200 {
            if calls.load(Ordering::SeqCst) >= 4 {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
        assert!(calls.load(Ordering::SeqCst) >= 4, "the loop must keep going after a panic");
        tx.send(true).unwrap();
        tokio::time::timeout(Duration::from_secs(5), task).await.expect("the loop stops").unwrap();
        let seen = firsts.lock().unwrap().clone();
        assert!(seen[0], "the first pass is the start-up pass");
        assert!(seen[1..].iter().all(|f| !f));
    }

    #[tokio::test]
    async fn a_loop_without_a_stop_channel_still_runs() {
        let calls = Arc::new(AtomicUsize::new(0));
        let c = calls.clone();
        let task = tokio::spawn(run(None, Duration::from_millis(5), Arc::new(move |_| {
            c.fetch_add(1, Ordering::SeqCst);
        })));
        for _ in 0..200 {
            if calls.load(Ordering::SeqCst) >= 2 {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
        task.abort();
        assert!(calls.load(Ordering::SeqCst) >= 2);
    }

    #[test]
    fn after_a_damaged_state_file_is_set_aside_isolation_rules_with_no_record_come_out() {
        // WR-18: the isolation record went with the file; as at start-up, the host keeps its network.
        use crate::capabilities::privileged::with_recorder;
        let dir = tempfile::tempdir().unwrap();
        let store = Store::at(dir.path().join("response_state.json"));
        std::fs::write(store.path(), "{ not json").unwrap();
        sweep(&store, Os::Linux, 100, false, &AtomicBool::new(false));
        assert!(store.load().is_ok(), "the state is usable again");
        assert!(with_recorder(|r| r.lines()).contains(&"iptables -w -D INPUT -j OMNI_ISOLATE_IN".to_string()));
    }

    #[test]
    fn a_failed_start_up_reapply_is_tried_again_on_the_next_pass() {
        use crate::capabilities::privileged::with_recorder;
        let dir = tempfile::tempdir().unwrap();
        let store = Store::at(dir.path().join("response_state.json"));
        store.update(|s| s.add_claim("45.33.32.156", "a", 5000, 0)).unwrap();
        let pending = AtomicBool::new(false);
        with_recorder(|r| r.fail_next(2)); // chain missing and cannot be created
        sweep(&store, Os::Linux, 100, true, &pending);
        assert!(pending.load(Ordering::SeqCst));
        with_recorder(|r| {
            r.clear_calls();
            for _ in 0..5 {
                r.fail_next(1);
                r.answer_next("");
            }
        });
        sweep(&store, Os::Linux, 115, false, &pending);
        assert!(!pending.load(Ordering::SeqCst));
        assert!(with_recorder(|r| r.lines()).contains(&"iptables -w -A OMNI_BLOCK -s 45.33.32.156 -j DROP".to_string()));
    }
}
