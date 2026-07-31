/*!
 * Offline store-and-forward spool.
 *
 * When the backend is unreachable, POST payloads (heartbeats, instruction results)
 * are appended to a JSONL file next to the agent binary and retried on the next
 * successful heartbeat — so telemetry and command outcomes survive network outages
 * instead of being silently dropped.
 *
 * The spool is capped at [`MAX_ENTRIES`]; when full, the oldest entries drop first so
 * disk use stays bounded on a host that is offline for a long time.
 */
use std::{fs, io::{BufRead, BufReader}, path::PathBuf, sync::Mutex};

use reqwest::Client;
use serde_json::{json, Value};

use crate::olog;

const MAX_ENTRIES: usize = 5000;

pub struct Spool {
    path: PathBuf,
    lock: Mutex<()>,
}

impl Spool {
    pub fn new() -> Self {
        let path = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.join("omni_spool.jsonl")))
            .unwrap_or_else(|| PathBuf::from("omni_spool.jsonl"));
        Spool { path, lock: Mutex::new(()) }
    }

    fn read_lines(&self) -> Vec<String> {
        match fs::File::open(&self.path) {
            Ok(f) => BufReader::new(f)
                .lines()
                .map_while(Result::ok)
                .filter(|l| !l.trim().is_empty())
                .collect(),
            Err(_) => Vec::new(),
        }
    }

    /// Queue a failed POST for later retry. Oldest entries are trimmed past the cap.
    pub fn enqueue(&self, url: &str, body: &Value) {
        let _g = self.lock.lock().unwrap_or_else(|e| e.into_inner());
        let mut lines = self.read_lines();
        lines.push(json!({ "url": url, "body": body }).to_string());
        if lines.len() > MAX_ENTRIES {
            let drop = lines.len() - MAX_ENTRIES;
            lines.drain(0..drop);
        }
        let _ = fs::write(&self.path, lines.join("\n") + "\n");
    }

    /// Retry all queued POSTs with the current token. Successes are removed; failures
    /// are re-queued for the next flush.
    ///
    /// The queued lines are taken (file removed) under the lock *before* any network I/O,
    /// so an `enqueue` racing during a flush appends to a fresh file and is never lost by
    /// the post-flush rewrite.
    pub async fn flush(&self, client: &Client, token: &str) {
        let taken = {
            let _g = self.lock.lock().unwrap_or_else(|e| e.into_inner());
            let lines = self.read_lines();
            if !lines.is_empty() {
                let _ = fs::remove_file(&self.path);
            }
            lines
        };
        if taken.is_empty() {
            return;
        }

        let mut remaining = Vec::new();
        let mut sent = 0usize;
        for line in taken {
            let entry: Value = match serde_json::from_str(&line) {
                Ok(v) => v,
                Err(_) => continue, // drop unparseable lines
            };
            let url = entry.get("url").and_then(|v| v.as_str()).unwrap_or("");
            if url.is_empty() {
                continue;
            }
            let body = entry.get("body").cloned().unwrap_or(Value::Null);
            let ok = matches!(
                client.post(url).bearer_auth(token).json(&body).send().await,
                Ok(r) if r.status().is_success()
            );
            if ok { sent += 1; } else { remaining.push(line); }
        }

        if !remaining.is_empty() {
            let _g = self.lock.lock().unwrap_or_else(|e| e.into_inner());
            // Re-queue failures ahead of anything enqueued during the flush window.
            let mut all = remaining;
            all.extend(self.read_lines());
            if all.len() > MAX_ENTRIES {
                let drop = all.len() - MAX_ENTRIES;
                all.drain(0..drop);
            }
            let _ = fs::write(&self.path, all.join("\n") + "\n");
        }

        if sent > 0 {
            olog!("[spool] flushed {} queued item(s)", sent);
        }
    }
}
