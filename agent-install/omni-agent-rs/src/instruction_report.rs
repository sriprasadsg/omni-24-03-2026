//! Posting an instruction's result to the platform (WR-22).
//!
//! A final body is posted up to three times, with a pause between tries, when the platform cannot
//! be reached or answers 5xx or 429, and the last failure is logged; a lost final body would leave
//! the card at `accepted`, and a platform that offers the instruction again would repeat it. An
//! `accepted` body is posted once, because the final body follows it and replaces it.
//!
//! A command that finishes off the poll loop waits for its `accepted` answer to have been posted
//! (`after_accepted`, released by the loop through `accepted_posted`) before it posts its final
//! body, so the final body is the last word the platform hears for the task. If no release comes
//! (the `accepted` post was never made) it goes ahead after `ACCEPTED_WAIT`.

use crate::config::Config;
use crate::heartbeat::hostname_str;
use serde_json::Value;
use std::sync::Mutex;
use std::time::Duration;
use tokio::sync::oneshot;

const ATTEMPTS: usize = 3;
#[cfg(not(test))]
const PAUSES: [Duration; 2] = [Duration::from_secs(1), Duration::from_secs(3)];
#[cfg(test)]
const PAUSES: [Duration; 2] = [Duration::from_millis(10), Duration::from_millis(10)];
/// The longest a final body waits for its `accepted` post (that post's own timeout is 30 s).
const ACCEPTED_WAIT: Duration = Duration::from_secs(45);

static WAITING: Mutex<Vec<(String, oneshot::Sender<()>)>> = Mutex::new(Vec::new());

/// Completes once the `accepted` answer for `task_id` has been posted. Call it before the
/// `accepted` body is handed back, so the release cannot come first.
pub(crate) fn after_accepted(task_id: &str) -> impl std::future::Future<Output = ()> + Send + 'static {
    let (tx, rx) = oneshot::channel();
    let mut waiting = WAITING.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    waiting.retain(|(_, sender)| !sender.is_closed());
    waiting.push((task_id.to_string(), tx));
    async move {
        let _ = tokio::time::timeout(ACCEPTED_WAIT, rx).await;
    }
}

/// The poll loop posted the answer for `task_id`: release whatever waits on it.
pub(crate) fn accepted_posted(task_id: &str) {
    let mut waiting = WAITING.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    let (mine, rest): (Vec<_>, Vec<_>) = std::mem::take(&mut *waiting).into_iter().partition(|(id, _)| id == task_id);
    *waiting = rest;
    for (_, sender) in mine {
        let _ = sender.send(());
    }
}

/// Post one instruction's result. A command that finishes later than its poll (isolation, a
/// restart, a quarantine, a kill) calls this a second time with the same `task_id`.
pub(crate) async fn report_result(client: &reqwest::Client, cfg: &Config, task_id: &str, action: &str, result: &Value) {
    let url = format!("{}/api/agents/{}/instructions/result", cfg.api_base_url.trim_end_matches('/'), hostname_str());
    // Backend (agent_tasks_endpoints.report_instruction_result) keys the
    // instruction-status update on task_id and reads status at the top level.
    let status = result.get("status").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
    let attempts = if status == "accepted" { 1 } else { ATTEMPTS };
    let body = serde_json::json!({
        "task_id": task_id,
        "action": action,
        "type": action,
        "status": status,
        "result": result,
        "timestamp": chrono::Utc::now().to_rfc3339(),
    });
    #[cfg(test)]
    {
        // Unit tests never reach a platform: the body is kept for `final_body`.
        let _ = (client, url, attempts, body);
        POSTED.lock().unwrap_or_else(|p| p.into_inner()).push((task_id.to_string(), result.clone()));
    }
    #[cfg(not(test))]
    post_with_retry(client, &url, &cfg.agent_token, &body, attempts, &format!("instruction {task_id} ({action})")).await;
}

/// Post `body`, trying again after a network failure, a 5xx or a 429. True when it was taken.
pub(crate) async fn post_with_retry(client: &reqwest::Client, url: &str, token: &str, body: &Value, attempts: usize, what: &str) -> bool {
    let mut last = String::new();
    for attempt in 0..attempts {
        match client.post(url).bearer_auth(token).json(body).send().await {
            Ok(r) if r.status().is_success() => return true,
            Ok(r) if !(r.status().is_server_error() || r.status().as_u16() == 429) => {
                log::warn!("The result of {what} was refused: {}", r.status());
                return false;
            }
            Ok(r) => last = r.status().to_string(),
            Err(e) => last = e.to_string(),
        }
        if attempt + 1 < attempts {
            tokio::time::sleep(PAUSES[attempt.min(PAUSES.len() - 1)]).await;
        }
    }
    log::error!("The result of {what} could not be posted after {attempts} tries: {last}");
    false
}

#[cfg(test)]
static POSTED: Mutex<Vec<(String, Value)>> = Mutex::new(Vec::new());

/// Test support: act as the poll loop that posted `accepted`, then wait for the final body.
#[cfg(test)]
pub(crate) async fn final_body(task_id: &str) -> Option<Value> {
    accepted_posted(task_id);
    for _ in 0..500 {
        {
            let mut posted = POSTED.lock().unwrap_or_else(|p| p.into_inner());
            if let Some(i) = posted.iter().position(|(id, _)| id == task_id) {
                return Some(posted.remove(i).1);
            }
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;

    /// A local HTTP server that answers each request with the next status code.
    fn server(codes: Vec<u16>) -> (String, Arc<AtomicUsize>) {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}/result", listener.local_addr().unwrap());
        let seen = Arc::new(AtomicUsize::new(0));
        let count = seen.clone();
        std::thread::spawn(move || {
            for code in codes {
                let Ok((mut conn, _)) = listener.accept() else { return };
                let mut got = Vec::new();
                let mut chunk = [0u8; 4096];
                while let Ok(n) = conn.read(&mut chunk) {
                    got.extend_from_slice(&chunk[..n]);
                    let text = String::from_utf8_lossy(&got).to_lowercase();
                    let Some(head) = text.find("\r\n\r\n") else { continue };
                    let len = text.lines().find_map(|l| l.strip_prefix("content-length:")).and_then(|v| v.trim().parse().ok()).unwrap_or(0);
                    if n == 0 || got.len() >= head + 4 + len {
                        break;
                    }
                }
                count.fetch_add(1, Ordering::SeqCst);
                let _ = write!(conn, "HTTP/1.1 {code} X\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
            }
        });
        (url, seen)
    }

    #[tokio::test]
    async fn a_final_body_is_posted_again_after_a_server_error_and_a_refusal_is_not() {
        let client = reqwest::Client::new();
        let body = serde_json::json!({"status": "success"});
        let (url, seen) = server(vec![500, 503, 200]);
        assert!(post_with_retry(&client, &url, "tok", &body, ATTEMPTS, "t").await);
        assert_eq!(seen.load(Ordering::SeqCst), 3);
        let (url, seen) = server(vec![404, 200]);
        assert!(!post_with_retry(&client, &url, "tok", &body, ATTEMPTS, "t").await);
        assert_eq!(seen.load(Ordering::SeqCst), 1, "a refusal is not sent again");
        let (url, seen) = server(vec![500, 500, 500, 200]);
        assert!(!post_with_retry(&client, &url, "tok", &body, ATTEMPTS, "t").await);
        assert_eq!(seen.load(Ordering::SeqCst), 3, "three tries, then the failure is logged");
    }

    #[tokio::test]
    async fn a_final_body_waits_until_its_accepted_answer_was_posted() {
        let waiting = after_accepted("task-order-1");
        let done = Arc::new(AtomicUsize::new(0));
        let flag = done.clone();
        let task = tokio::spawn(async move {
            waiting.await;
            flag.store(1, Ordering::SeqCst);
        });
        tokio::time::sleep(Duration::from_millis(100)).await;
        assert_eq!(done.load(Ordering::SeqCst), 0, "no final body before the accepted one");
        accepted_posted("task-order-other");
        tokio::time::sleep(Duration::from_millis(50)).await;
        assert_eq!(done.load(Ordering::SeqCst), 0, "another task's post releases nothing");
        accepted_posted("task-order-1");
        tokio::time::timeout(Duration::from_secs(2), task).await.unwrap().unwrap();
        assert_eq!(done.load(Ordering::SeqCst), 1);
    }
}
