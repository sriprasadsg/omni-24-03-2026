use rusqlite::{Connection, params};
use std::path::PathBuf;

/// Heartbeats kept while the platform is unreachable: the newest `MAX_ROWS` (an hour at the
/// default 30 s interval) from the last `MAX_AGE_HOURS`. Older ones are dropped, so an
/// outage never fills the endpoint's disk.
pub const MAX_ROWS: i64 = 120;
pub const MAX_AGE_HOURS: i64 = 24;

pub struct MessageBuffer {
    db_path: PathBuf,
}

impl MessageBuffer {
    pub fn new(db_path: PathBuf) -> Self {
        let buf = MessageBuffer { db_path };
        buf.init_db();
        buf
    }

    fn open(&self) -> Result<Connection, rusqlite::Error> {
        Connection::open(&self.db_path)
    }

    fn init_db(&self) {
        if let Ok(conn) = self.open() {
            let _ = conn.execute_batch(
                "CREATE TABLE IF NOT EXISTS messages (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload   TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );",
            );
            // A buffer left by a build without limits can be large: trim it and give the space back.
            if prune(&conn) > 0 {
                let _ = conn.execute_batch("VACUUM;");
            }
        }
    }

    pub fn push(&self, payload: &serde_json::Value) {
        if let Ok(conn) = self.open() {
            if let Ok(text) = serde_json::to_string(payload) {
                let _ = conn.execute(
                    "INSERT INTO messages (payload) VALUES (?1)",
                    params![text],
                );
                log::info!("Buffered failed heartbeat to SQLite");
                prune(&conn);
            }
        }
    }

    pub fn pending(&self, limit: usize) -> Vec<(i64, serde_json::Value)> {
        let conn = match self.open() {
            Ok(c) => c,
            Err(_) => return vec![],
        };
        let mut stmt = match conn.prepare(
            "SELECT id, payload FROM messages ORDER BY id ASC LIMIT ?1",
        ) {
            Ok(s) => s,
            Err(_) => return vec![],
        };
        let rows = match stmt.query_map(params![limit as i64], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        }) {
            Ok(r) => r,
            Err(_) => return vec![],
        };

        let mut out = vec![];
        for r in rows.flatten() {
            if let Ok(v) = serde_json::from_str(&r.1) {
                out.push((r.0, v));
            }
        }
        out
    }

    pub fn delete(&self, id: i64) {
        if let Ok(conn) = self.open() {
            let _ = conn.execute("DELETE FROM messages WHERE id=?1", params![id]);
        }
    }
}

/// Drops buffered heartbeats past the age and count limits; returns how many went.
fn prune(conn: &Connection) -> usize {
    let aged = conn
        .execute(
            "DELETE FROM messages WHERE timestamp < datetime('now', ?1)",
            params![format!("-{MAX_AGE_HOURS} hours")],
        )
        .unwrap_or(0);
    let excess = conn
        .execute(
            "DELETE FROM messages WHERE id NOT IN (SELECT id FROM messages ORDER BY id DESC LIMIT ?1)",
            params![MAX_ROWS],
        )
        .unwrap_or(0);
    aged + excess
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_buffer(name: &str) -> (MessageBuffer, PathBuf) {
        let path = std::env::temp_dir().join(format!("omni-buffer-{name}-{}.db", std::process::id()));
        let _ = std::fs::remove_file(&path);
        (MessageBuffer::new(path.clone()), path)
    }

    #[test]
    fn keeps_only_the_newest_rows() {
        let (buf, _) = temp_buffer("rows");
        for i in 0..(MAX_ROWS + 15) {
            buf.push(&serde_json::json!({ "beat": i }));
        }
        let pending = buf.pending(1000);
        assert_eq!(pending.len() as i64, MAX_ROWS);
        assert_eq!(pending[0].1["beat"], 15);
    }

    #[test]
    fn drops_rows_older_than_the_age_limit() {
        let (buf, path) = temp_buffer("age");
        let conn = Connection::open(&path).unwrap();
        conn.execute(
            "INSERT INTO messages (payload, timestamp) VALUES ('{\"beat\":\"old\"}', datetime('now', '-25 hours'))",
            [],
        )
        .unwrap();
        buf.push(&serde_json::json!({ "beat": "new" }));
        let pending = buf.pending(10);
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].1["beat"], "new");
    }
}
