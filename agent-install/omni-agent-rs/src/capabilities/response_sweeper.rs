//! The independent task that ends blocks on time.

use crate::capabilities::firewall::Os;
use crate::capabilities::response_state::Store;
use std::sync::atomic::AtomicBool;
use std::time::Duration;

/// How often the sweeper looks at the claims.
pub const PERIOD: Duration = Duration::from_secs(15);

/// One pass.
pub(crate) fn sweep(_store: &Store, _os: Os, _now: i64, _first: bool, _pending: &AtomicBool) {}

pub(crate) async fn run<F>(_stop: Option<tokio::sync::watch::Receiver<bool>>, _period: Duration, _pass: std::sync::Arc<F>)
where
    F: Fn(bool) + Send + Sync + 'static,
{
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
