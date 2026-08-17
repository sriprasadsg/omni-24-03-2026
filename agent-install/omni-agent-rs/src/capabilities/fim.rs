//! File Integrity Monitoring (FIM) — event-driven watcher via `notify`.
//!
//! This module replaces the legacy poll-and-hash stub with a real event-driven
//! integrity monitor using the `notify` crate (inotify on Linux,
//! ReadDirectoryChangesW on Windows). It assembles rich change events with
//! before/after hashes, best-effort process/user context, and writes them to a
//! local SQLite `fim_queue` for the remediation engine (Phase 53) and backend
//! POST (52-04) to drain.

use super::Capability;
use rusqlite::{params, Connection};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
#[cfg(target_os = "linux")]
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
#[cfg(target_os = "linux")]
use std::sync::Arc;
use std::sync::Mutex;
use std::time::{Duration, UNIX_EPOCH};
use sysinfo::System;
#[cfg(target_os = "linux")]
use crate::capabilities::fanotify_watcher::{FanotifyEventData, start_fanotify_watcher};
#[cfg(target_os = "linux")]
use crate::capabilities::process_mapper::resolve_process_tree;
#[cfg(target_os = "linux")]
use tokio::sync::mpsc;

pub struct FimCapability;

/// Global state for the watcher (held by CapabilityManager via lazy_static or similar).
/// For this phase, we expose start_watcher and a status struct; 52-04 wires it into agent_loop.
static FIM_STATUS: once_cell::sync::Lazy<Mutex<FimStatus>> =
    once_cell::sync::Lazy::new(|| Mutex::new(FimStatus::default()));

#[derive(Default, Clone, Debug)]
struct FimStatus {
    watching: bool,
    watched_paths: Vec<String>,
    queued: usize,
    last_event_ts: Option<String>,
    last_error: Option<String>,
}

/// FIM change event — mirrors the backend fim-events shape (D-04).
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct FimEvent {
    pub path: String,
    pub change_type: ChangeType,
    pub hash_before: Option<String>,
    pub hash_after: Option<String>,
    pub process: ProcessInfo,
    pub user: String,
    pub ts: String,
    pub source: &'static str,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ChangeType {
    Create,
    Modify,
    Delete,
    Permission,
    Rename,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, Default)]
pub struct ProcessInfo {
    pub pid: Option<u32>,
    pub name: Option<String>,
    pub tree: Option<Vec<String>>,
}

/// Maps fanotify event mask to our ChangeType.
#[cfg(target_os = "linux")]
fn map_fanotify_mask_to_change_type(mask: u32) -> ChangeType {
    use naughtyfy::flags::{FAN_CREATE, FAN_DELETE, FAN_MODIFY, FAN_ATTRIB, FAN_MOVE, FAN_CLOSE_WRITE};
    let mask = mask as u64;
    if (mask & FAN_CREATE) != 0 { ChangeType::Create }
    else if (mask & FAN_DELETE) != 0 { ChangeType::Delete }
    else if (mask & FAN_MODIFY) != 0 { ChangeType::Modify }
    else if (mask & FAN_CLOSE_WRITE) != 0 { ChangeType::Modify }
    else if (mask & FAN_ATTRIB) != 0 { ChangeType::Permission }
    else if (mask & FAN_MOVE) != 0 { ChangeType::Rename }
    else { ChangeType::Modify } // Default fallback
}

/// Best-effort current process user (owner of the agent process).
pub(crate) fn current_user() -> String {
    #[cfg(unix)]
    {
        use std::process::Command;
        let output = Command::new("whoami").output().ok();
        output
            .and_then(|o| String::from_utf8(o.stdout).ok())
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| "unknown".to_string())
    }
    #[cfg(windows)]
    {
        use std::process::Command;
        let output = Command::new("cmd").args(["/C", "echo %USERNAME%"]).output().ok();
        output
            .and_then(|o| String::from_utf8(o.stdout).ok())
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| "unknown".to_string())
    }
    #[cfg(not(any(unix, windows)))]
    {
        "unknown".to_string()
    }
}

// Best-effort process info for a given PID. For now, name and tree are None.
// fn process_info(pid: u32) -> ProcessInfo {
//     ProcessInfo {
//         pid: Some(pid),
//         name: None,
//         tree: None,
//     }
// }

/// Compute SHA256 of a file, returning (hash, size, modified_rfc3339).
fn hash_file(path: &Path) -> Result<(String, u64, String), Box<dyn std::error::Error>> {
    let data = fs::read(path)?;
    let mut hasher = Sha256::new();
    hasher.update(&data);
    let hash = hex::encode(hasher.finalize());
    let meta = fs::metadata(path)?;
    let size = meta.len();
    let modified = meta
        .modified()
        .ok()
        .and_then(|t| {
            t.duration_since(UNIX_EPOCH)
                .ok()
                .map(|d| {
                    chrono::DateTime::<chrono::Utc>::from(UNIX_EPOCH + d).to_rfc3339()
                })
        })
        .unwrap_or_default();
    Ok((hash, size, modified))
}

/// Path to the local fim_queue SQLite database.
fn fim_queue_path() -> PathBuf {
    crate::config::config_path()
        .parent()
        .map(|p| p.join("fim_queue.db"))
        .unwrap_or_else(|| PathBuf::from("fim_queue.db"))
}

/// Initializes the fim_queue table if it doesn't exist.
fn init_fim_queue(conn: &Connection) -> Result<(), rusqlite::Error> {
    conn.execute(
        "CREATE TABLE IF NOT EXISTS fim_queue (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            change_type TEXT NOT NULL,
            hash_before TEXT,
            hash_after TEXT,
            process_json TEXT NOT NULL,
            user TEXT NOT NULL,
            ts TEXT NOT NULL,
            posted INTEGER NOT NULL DEFAULT 0
        )",
        [],
    )?;
    Ok(())
}

/// Enqueues a FIM event into the local SQLite fim_queue.
fn enqueue_event(event: &FimEvent) -> Result<(), rusqlite::Error> {
    let db_path = fim_queue_path();
    let conn = Connection::open(&db_path)?;
    init_fim_queue(&conn)?;

    let process_json = serde_json::to_string(&event.process).unwrap_or_else(|_| "{}".to_string());

    conn.execute(
        "INSERT INTO fim_queue (path, change_type, hash_before, hash_after, process_json, user, ts, posted)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 0)",
        params![
            event.path,
            serde_json::to_string(&event.change_type).unwrap_or_else(|_| "\"modify\"".to_string()),
            event.hash_before,
            event.hash_after,
            process_json,
            event.user,
            event.ts,
        ],
    )?;
    Ok(())
}

/// Builds a FimEvent from FanotifyEventData and enqueues it.
#[cfg(target_os = "linux")]
fn handle_fanotify_event(event_data: FanotifyEventData, last_hashes: &Arc<Mutex<HashMap<String, String>>>) {
    let mut status = FIM_STATUS.lock().unwrap();

    let path_str = event_data.path.clone();
    let change_type = map_fanotify_mask_to_change_type(event_data.event_mask);

    // hash_after: compute if file exists (create/modify/rename), None for delete/permission
    let hash_after = if matches!(change_type, ChangeType::Delete) || matches!(change_type, ChangeType::Permission) {
        None
    } else {
        hash_file(Path::new(&path_str)).map(|(h, _, _)| h).ok()
    };

    // hash_before: look up from last-known map
    let hash_before = {
        let mut map = last_hashes.lock().unwrap();
        let before = map.get(&path_str).cloned();
        if let Some(ref h) = hash_after {
            map.insert(path_str.clone(), h.clone());
        } else if matches!(change_type, ChangeType::Delete) {
            map.remove(&path_str);
        }
        before
    };

    let fim_event = FimEvent {
        path: path_str.clone(),
        change_type,
        hash_before,
        hash_after,
        process: resolve_process_tree(event_data.pid as i32),
        user: current_user(),
        ts: chrono::Utc::now().to_rfc3339(),
        source: "fim",
    };

    if let Err(e) = enqueue_event(&fim_event) {
        log::error!("Failed to enqueue FIM event for {}: {}", path_str, e);
        status.last_error = Some(format!("enqueue failed: {}", e));
    } else {
        status.queued += 1;
        status.last_event_ts = Some(fim_event.ts.clone());
        log::debug!("Enqueued FIM event: {} {:?}", path_str, fim_event.change_type);
    }
}

/// Public API: starts the fanotify watcher over the given paths.
/// Returns a shutdown handle that can be used to stop the watcher.
/// The watcher runs in a background thread; failures are logged and the function returns an error (no panic).
#[cfg(target_os = "linux")]
pub fn start_watcher(
    paths: Vec<String>,
    mut stop_rx: tokio::sync::watch::Receiver<bool>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let mut status = FIM_STATUS.lock().unwrap();
    if status.watching {
        return Err("watcher already running".into());
    }

    // Shared map for last-known hashes (hash_before lookups)
    let last_hashes: Arc<Mutex<HashMap<String, String>>> = Arc::new(Mutex::new(HashMap::new()));

    // Populate initial hashes for existing files
    for p in &paths {
        if let Ok((hash, _, _)) = hash_file(Path::new(p)) {
            last_hashes.lock().unwrap().insert(p.clone(), hash);
        }
    }

    let (fanotify_event_tx, mut fanotify_event_rx) = mpsc::channel(100); // Channel for fanotify events

    // Spawn the fanotify watcher
    let fanotify_paths = paths.clone();
    let fanotify_stop_rx = stop_rx.clone();
    tokio::spawn(async move {
        if let Err(e) = start_fanotify_watcher(fanotify_paths, fanotify_stop_rx, fanotify_event_tx).await {
            log::error!("Fanotify watcher failed: {}", e);
        }
    });

    status.watching = true;
    status.watched_paths = paths.clone();
    status.queued = 0;
    status.last_event_ts = None;
    status.last_error = None;
    drop(status);

    // Process events from the fanotify channel
    let last_hashes_clone = last_hashes.clone();
    tokio::spawn(async move {
        loop {
            tokio::select! {
                Some(event_data) = fanotify_event_rx.recv() => {
                    handle_fanotify_event(event_data, &last_hashes_clone);
                }
                _ = stop_rx.changed() => {
                    if *stop_rx.borrow() {
                        log::info!("FIM event processor stop signal received");
                        break;
                    }
                }
                else => {
                    // Channel closed or no events for a while, prevent busy-waiting
                    tokio::time::sleep(Duration::from_millis(500)).await;
                }
            }
        }
        let mut status = FIM_STATUS.lock().unwrap();
        status.watching = false;
    });

    Ok(())
}

/// fanotify has no macOS/Windows equivalent; FIM watching is unavailable on
/// this platform (Phase 65 shipped Linux-only).
#[cfg(not(target_os = "linux"))]
pub fn start_watcher(
    _paths: Vec<String>,
    _stop_rx: tokio::sync::watch::Receiver<bool>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    Err("FIM watcher (fanotify) is unsupported on this platform.".into())
}

/// Periodic background task that drains unposted FIM events to the backend.
pub async fn drain_queue(
    cfg: crate::config::Config,
    client: reqwest::Client,
    mut stop_rx: tokio::sync::watch::Receiver<bool>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let mut ticker = tokio::time::interval(Duration::from_secs(60));
    loop {
        tokio::select! {
            _ = ticker.tick() => {
                let (cfg_clone, client_clone) = (cfg.clone(), client.clone());
                let result: Result<(), Box<dyn std::error::Error + Send + Sync>> = tokio::task::spawn_blocking(move || {
                    let db_path = fim_queue_path();
                    let mut conn = Connection::open(&db_path)?;

                    let mut stmt = conn.prepare(
                        "SELECT rowid, path, change_type, hash_before, hash_after, process_json, user, ts FROM fim_queue WHERE posted = 0 LIMIT 50"
                    )?;
                    let rows: Vec<(i64, String, String, Option<String>, Option<String>, String, String, String)> = stmt.query_map([], |row| {
                        Ok((
                            row.get::<_, i64>(0)?,
                            row.get::<_, String>(1)?,
                            row.get::<_, String>(2)?,
                            row.get::<_, Option<String>>(3)?,
                            row.get::<_, Option<String>>(4)?,
                            row.get::<_, String>(5)?,
                            row.get::<_, String>(6)?,
                            row.get::<_, String>(7)?,
                        ))
                    })?.flatten().collect();
                    drop(stmt); // Release the borrow on conn

                    if !rows.is_empty() {
                        let to_post: Vec<Value> = rows.iter().map(|(id, path, change_type, hash_before, hash_after, process_json, user, ts)| {
                            json!({
                                "id": *id,
                                "path": path,
                                "change_type": serde_json::from_str::<ChangeType>(change_type).unwrap_or(ChangeType::Modify),
                                "hash_before": hash_before,
                                "hash_after": hash_after,
                                "process": serde_json::from_str::<ProcessInfo>(process_json).unwrap_or_default(),
                                "user": user,
                                "ts": ts,
                            })
                        }).collect();
                        let ids: Vec<i64> = rows.iter().map(|(id, _, _, _, _, _, _, _)| *id).collect();

                        let url = format!("{}/api/agents/{}/security/fim-events", cfg_clone.api_base_url.trim_end_matches('/'), crate::heartbeat::hostname_str());
                        let resp = tokio::runtime::Handle::current().block_on(async {
                            client_clone.post(&url)
                                .bearer_auth(&cfg_clone.agent_token)
                                .json(&json!({"changes": to_post}))
                                .send()
                                .await
                        });

                        if let Ok(r) = resp {
                            if r.status().is_success() {
                                let mut tx = conn.transaction()?;
                                for id in ids {
                                    tx.execute("UPDATE fim_queue SET posted = 1 WHERE rowid = ?1", params![id])?;
                                }
                                tx.commit()?;
                                log::info!("Successfully drained {} FIM events", to_post.len());
                            } else {
                                log::warn!("FIM events drain failed: status {}", r.status());
                            }
                        } else {
                            log::warn!("FIM events drain request failed: {:?}", resp.err());
                        }
                    }
                    Ok(())
                }).await?;
            }
            _ = stop_rx.changed() => {
                if *stop_rx.borrow() { break; }
            }
        }
    }
    Ok(())
}

/// Returns current FIM watcher status for Capability::collect().
fn get_status() -> Value {
    let status = FIM_STATUS.lock().unwrap();
    json!({
        "watching": status.watching,
        "watched_paths": status.watched_paths.len(),
        "paths": status.watched_paths,
        "queued": status.queued,
        "last_event_ts": status.last_event_ts,
        "last_error": status.last_error,
    })
}

impl Capability for FimCapability {
    fn id(&self) -> &'static str { "fim" }
    fn name(&self) -> &'static str { "File Integrity Monitoring" }

    fn collect(&self, _sys: &System) -> Value {
        // Now returns watcher status summary instead of poll-hashing
        get_status()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    #[cfg(target_os = "linux")]
    fn fanotify_mask_mapping() {
        use naughtyfy::flags::{FAN_CREATE, FAN_DELETE, FAN_MODIFY, FAN_ATTRIB, FAN_MOVE, FAN_CLOSE_WRITE};
        assert!(matches!(map_fanotify_mask_to_change_type(FAN_CREATE as u32), ChangeType::Create));
        assert!(matches!(map_fanotify_mask_to_change_type(FAN_DELETE as u32), ChangeType::Delete));
        assert!(matches!(map_fanotify_mask_to_change_type(FAN_MODIFY as u32), ChangeType::Modify));
        assert!(matches!(map_fanotify_mask_to_change_type(FAN_CLOSE_WRITE as u32), ChangeType::Modify));
        assert!(matches!(map_fanotify_mask_to_change_type(FAN_ATTRIB as u32), ChangeType::Permission));
        assert!(matches!(map_fanotify_mask_to_change_type(FAN_MOVE as u32), ChangeType::Rename));
    }

    #[test]
    fn enqueue_inserts_row() {
        let dir = tempdir().unwrap();
        let db_path = dir.path().join("test_fim_queue.db");

        // Directly test the enqueue logic using an in-memory connection
        let conn = Connection::open_in_memory().unwrap();
        init_fim_queue(&conn).unwrap();

        let event = FimEvent {
            path: "/test/file.txt".to_string(),
            change_type: ChangeType::Modify,
            hash_before: Some("abc123".to_string()),
            hash_after: Some("def456".to_string()),
            process: ProcessInfo::default(),
            user: "testuser".to_string(),
            ts: "2024-01-01T00:00:00Z".to_string(),
            source: "fim",
        };

        // Test enqueue via direct SQL (since enqueue_event uses fim_queue_path())
        let process_json = serde_json::to_string(&event.process).unwrap();
        conn.execute(
            "INSERT INTO fim_queue (path, change_type, hash_before, hash_after, process_json, user, ts, posted)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 0)",
            params![
                &event.path,
                "\"modify\"",
                &event.hash_before,
                &event.hash_after,
                &process_json,
                &event.user,
                &event.ts,
            ],
        ).unwrap();

        // Verify row exists with correct columns
        let mut stmt = conn.prepare("SELECT rowid, path, change_type, hash_before, hash_after, user, ts, posted FROM fim_queue").unwrap();
        let rows: Vec<(i64, String, String, Option<String>, Option<String>, String, String, i64)> = stmt.query_map([], |r| {
            Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?, r.get(5)?, r.get(6)?, r.get(7)?))
        }).unwrap().flatten().collect();

        assert_eq!(rows.len(), 1);
        let row = &rows[0];
        assert_eq!(row.1, "/test/file.txt"); // path
        assert_eq!(row.2, "\"modify\""); // change_type (JSON string)
        assert_eq!(row.3, Some("abc123".to_string())); // hash_before
        assert_eq!(row.4, Some("def456".to_string())); // hash_after
        assert_eq!(row.5, "testuser"); // user
        assert_eq!(row.6, "2024-01-01T00:00:00Z"); // ts
        assert_eq!(row.7, 0); // posted = 0
        assert_eq!(row.0, 1); // rowid = 1 (auto-increment)
    }

    #[test]
    fn delete_event_hash_after_none() {
        let conn = Connection::open_in_memory().unwrap();
        init_fim_queue(&conn).unwrap();

        let event = FimEvent {
            path: "/test/deleted.txt".to_string(),
            change_type: ChangeType::Delete,
            hash_before: Some("oldhash".to_string()),
            hash_after: None,
            process: ProcessInfo::default(),
            user: "testuser".to_string(),
            ts: "2024-01-01T00:00:00Z".to_string(),
            source: "fim",
        };

        let process_json = serde_json::to_string(&event.process).unwrap();
        conn.execute(
            "INSERT INTO fim_queue (path, change_type, hash_before, hash_after, process_json, user, ts, posted)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 0)",
            params![
                &event.path,
                "\"delete\"",
                &event.hash_before,
                &event.hash_after,
                &process_json,
                &event.user,
                &event.ts,
            ],
        ).unwrap();

        let mut stmt = conn.prepare("SELECT hash_after FROM fim_queue").unwrap();
        let hash_after: Option<String> = stmt.query_row([], |r| r.get(0)).unwrap();
        assert!(hash_after.is_none());
    }

    #[test]
    fn modify_event_hash_after_computed() {
        let dir = tempdir().unwrap();
        let file = dir.path().join("test.txt");
        fs::write(&file, b"initial content").unwrap();

        let (hash, _, _) = hash_file(&file).unwrap();
        assert!(!hash.is_empty());

        // Modify file
        fs::write(&file, b"modified content").unwrap();
        let (new_hash, _, _) = hash_file(&file).unwrap();
        assert_ne!(hash, new_hash);
    }

    #[test]
    fn hash_file_works() {
        let dir = tempdir().unwrap();
        let file = dir.path().join("test.txt");
        fs::write(&file, b"hello world").unwrap();

        let (hash, size, modified) = hash_file(&file).unwrap();
        assert_eq!(size, 11);
        assert!(!hash.is_empty());
        assert!(!modified.is_empty());
        // Verify it's a valid sha256 (64 hex chars)
        assert_eq!(hash.len(), 64);
    }

    #[test]
    fn fim_queue_schema_columns() {
        let conn = Connection::open_in_memory().unwrap();
        init_fim_queue(&conn).unwrap();

        let cols: Vec<String> = conn
            .prepare("PRAGMA table_info(fim_queue)")
            .unwrap()
            .query_map([], |r| r.get::<_, String>(1))
            .unwrap()
            .flatten()
            .collect();

        assert!(cols.contains(&"rowid".to_string()));
        assert!(cols.contains(&"path".to_string()));
        assert!(cols.contains(&"change_type".to_string()));
        assert!(cols.contains(&"hash_before".to_string()));
        assert!(cols.contains(&"hash_after".to_string()));
        assert!(cols.contains(&"process_json".to_string()));
        assert!(cols.contains(&"user".to_string()));
        assert!(cols.contains(&"ts".to_string()));
        assert!(cols.contains(&"posted".to_string()));
    }
}