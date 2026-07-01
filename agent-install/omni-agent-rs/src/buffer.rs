use rusqlite::{Connection, params};
use std::path::PathBuf;

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
