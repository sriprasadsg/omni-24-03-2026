//! What the agent has promised to undo, kept on disk so it survives a restart and works offline.
//!
//! `response_state.json` sits beside `config.yaml`. It holds the block claims (one per block
//! instruction, so an undo removes only its own claim and the firewall rule goes only when the
//! last live claim is gone), and reserves room for the isolation record and the quarantine index
//! that later plans fill in. The file carries a version number so a later release can migrate it;
//! fields this release does not know are kept, not dropped, when it rewrites the file.
//!
//! Writes are atomic: a temp file in the same directory, flushed, then renamed over the old one.
//! A file that cannot be read or parsed is an error, never silently an empty state: an empty
//! state would forget live blocks.

use crate::capabilities::remediation_actions::RemediationError;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

pub const STATE_VERSION: u32 = 1;
const FILE_NAME: &str = "response_state.json";

/// One block instruction's claim on an address. `expires_at` is epoch seconds.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Claim {
    pub target: String,
    pub block_id: String,
    pub expires_at: i64,
}

/// A host isolation in progress (written by a later plan; declared now so the file format does
/// not change).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Isolation {
    pub id: String,
    pub started_at: i64,
    pub revert_at: i64,
    #[serde(default)]
    pub confirmed: bool,
    #[serde(default)]
    pub saved_policy: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ResponseState {
    #[serde(default = "current_version")]
    pub v: u32,
    #[serde(default)]
    pub claims: Vec<Claim>,
    #[serde(default)]
    pub isolation: Option<Isolation>,
    #[serde(default)]
    pub quarantine_index: Vec<Value>,
    /// Fields written by a newer release; carried through unchanged.
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

fn current_version() -> u32 {
    STATE_VERSION
}

impl Default for ResponseState {
    fn default() -> Self {
        ResponseState {
            v: STATE_VERSION,
            claims: Vec::new(),
            isolation: None,
            quarantine_index: Vec::new(),
            extra: Map::new(),
        }
    }
}

/// What `add_claim` did.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ClaimAdded {
    /// A new claim was recorded.
    New,
    /// The same instruction already holds an unexpired claim on this address; nothing changed.
    Existing { expires_at: i64 },
}

impl ResponseState {
    /// The unexpired claims on `target`.
    pub fn live_for(&self, target: &str, now: i64) -> usize {
        self.claims.iter().filter(|c| c.target == target && c.expires_at > now).count()
    }

    /// The claim `block_id` holds on `target`, expired or not.
    pub fn find(&self, target: &str, block_id: &str) -> Option<&Claim> {
        self.claims.iter().find(|c| c.target == target && c.block_id == block_id)
    }

    /// Record a claim. The same `(target, block_id)` while still live is left alone; once it has
    /// expired it is renewed.
    pub fn add_claim(&mut self, target: &str, block_id: &str, expires_at: i64, now: i64) -> ClaimAdded {
        if let Some(existing) = self.claims.iter_mut().find(|c| c.target == target && c.block_id == block_id) {
            if existing.expires_at > now {
                return ClaimAdded::Existing { expires_at: existing.expires_at };
            }
            existing.expires_at = expires_at;
            return ClaimAdded::New;
        }
        self.claims.push(Claim { target: target.to_string(), block_id: block_id.to_string(), expires_at });
        ClaimAdded::New
    }

    /// Remove `block_id`'s claim on `target`, or every claim on `target` when `block_id` is None.
    /// Returns how many were removed.
    pub fn remove_claims(&mut self, target: &str, block_id: Option<&str>) -> usize {
        let before = self.claims.len();
        self.claims.retain(|c| !(c.target == target && block_id.map_or(true, |id| c.block_id == id)));
        before - self.claims.len()
    }

    /// Forget the expired claims on `target`.
    pub fn drop_expired(&mut self, target: &str, now: i64) -> usize {
        let before = self.claims.len();
        self.claims.retain(|c| !(c.target == target && c.expires_at <= now));
        before - self.claims.len()
    }
}

/// Serialises every read-change-write in this process.
static WRITE_LOCK: Mutex<()> = Mutex::new(());

#[cfg(test)]
thread_local! {
    static TEST_PATH: std::cell::RefCell<Option<PathBuf>> = std::cell::RefCell::new(None);
}

/// The state file and the only code that reads or writes it.
#[derive(Debug, Clone)]
pub struct Store {
    path: PathBuf,
}

impl Default for Store {
    fn default() -> Self {
        #[cfg(test)]
        if let Some(path) = TEST_PATH.with(|p| p.borrow().clone()) {
            return Store { path };
        }
        Store { path: crate::config::config_path().with_file_name(FILE_NAME) }
    }
}

impl Store {
    pub fn at(path: impl Into<PathBuf>) -> Store {
        Store { path: path.into() }
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    /// The state on disk. A missing file is an empty state; an unreadable, unparseable or newer
    /// file is an error.
    pub fn load(&self) -> Result<ResponseState, RemediationError> {
        let text = match std::fs::read_to_string(&self.path) {
            Ok(text) => text,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(ResponseState::default()),
            Err(e) => return Err(state_error(&self.path, &e.to_string())),
        };
        let state: ResponseState =
            serde_json::from_str(&text).map_err(|e| state_error(&self.path, &e.to_string()))?;
        if state.v > STATE_VERSION {
            return Err(state_error(
                &self.path,
                &format!("it was written by a newer agent (version {})", state.v),
            ));
        }
        Ok(state)
    }

    /// Read the state, let `change` edit it, and write it back when it changed. The process-wide
    /// lock is held for the whole call, including `change`, so `change` must not call back into
    /// a store. A failed read means `change` does not run.
    pub fn update<T>(&self, change: impl FnOnce(&mut ResponseState) -> T) -> Result<T, RemediationError> {
        let _guard = WRITE_LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut state = self.load()?;
        let before = state.clone();
        let out = change(&mut state);
        if state != before {
            state.v = STATE_VERSION;
            self.write(&state)?;
        }
        Ok(out)
    }

    fn write(&self, state: &ResponseState) -> Result<(), RemediationError> {
        use std::io::Write;
        let text = serde_json::to_string_pretty(state)
            .map_err(|e| state_error(&self.path, &e.to_string()))?;
        let dir = self.path.parent().unwrap_or_else(|| Path::new("."));
        let tmp = dir.join(format!(".{FILE_NAME}.{}.tmp", std::process::id()));
        let result = (|| -> std::io::Result<()> {
            let mut options = std::fs::OpenOptions::new();
            options.write(true).create(true).truncate(true);
            #[cfg(unix)]
            {
                use std::os::unix::fs::OpenOptionsExt;
                options.mode(0o600);
            }
            let mut file = options.open(&tmp)?;
            file.write_all(text.as_bytes())?;
            file.flush()?;
            file.sync_all()?;
            drop(file);
            std::fs::rename(&tmp, &self.path)
        })();
        if let Err(e) = result {
            let _ = std::fs::remove_file(&tmp);
            return Err(state_error(&self.path, &e.to_string()));
        }
        Ok(())
    }
}

fn state_error(path: &Path, why: &str) -> RemediationError {
    RemediationError::OperationFailed(format!("{} cannot be used: {why}", path.display()))
}

/// Test support: points `Store::default()` of this thread at a fresh temporary directory.
#[cfg(test)]
pub(crate) fn use_temp_store() -> tempfile::TempDir {
    let dir = tempfile::tempdir().expect("tempdir");
    let path = dir.path().join(FILE_NAME);
    TEST_PATH.with(|p| *p.borrow_mut() = Some(path));
    dir
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store() -> (tempfile::TempDir, Store) {
        let dir = tempfile::tempdir().unwrap();
        let store = Store::at(dir.path().join(FILE_NAME));
        (dir, store)
    }

    #[test]
    fn a_missing_file_is_an_empty_state_with_the_current_version() {
        let (_dir, store) = store();
        let state = store.load().unwrap();
        assert_eq!(state.v, STATE_VERSION);
        assert!(state.claims.is_empty());
        assert!(state.isolation.is_none());
        assert!(state.quarantine_index.is_empty());
    }

    #[test]
    fn a_claim_survives_a_reload() {
        let (_dir, store) = store();
        store.update(|s| s.add_claim("45.33.32.156", "abc-1", 5000, 1000)).unwrap();
        let again = store.load().unwrap();
        assert_eq!(again.claims, vec![Claim { target: "45.33.32.156".into(), block_id: "abc-1".into(), expires_at: 5000 }]);
    }

    #[test]
    fn a_write_leaves_no_temp_file_behind() {
        let (dir, store) = store();
        store.update(|s| s.add_claim("45.33.32.156", "a", 5000, 1000)).unwrap();
        let names: Vec<String> = std::fs::read_dir(dir.path())
            .unwrap()
            .map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
            .collect();
        assert_eq!(names, vec![FILE_NAME.to_string()]);
    }

    #[test]
    fn a_corrupt_file_is_an_error_and_is_left_untouched() {
        let (_dir, store) = store();
        std::fs::write(store.path(), "{ not json").unwrap();
        assert!(store.load().is_err());
        assert!(store.update(|s| s.add_claim("45.33.32.156", "a", 5000, 1000)).is_err());
        assert_eq!(std::fs::read_to_string(store.path()).unwrap(), "{ not json");
    }

    #[test]
    fn a_file_from_a_newer_agent_is_refused() {
        let (_dir, store) = store();
        std::fs::write(store.path(), r#"{"v": 99, "claims": []}"#).unwrap();
        assert!(store.load().is_err());
    }

    #[test]
    fn fields_this_release_does_not_know_are_kept_when_it_rewrites_the_file() {
        let (_dir, store) = store();
        std::fs::write(store.path(), r#"{"v": 1, "claims": [], "future_field": {"a": 1}}"#).unwrap();
        store.update(|s| s.add_claim("45.33.32.156", "a", 5000, 1000)).unwrap();
        let text = std::fs::read_to_string(store.path()).unwrap();
        assert!(text.contains("future_field"));
    }

    #[test]
    fn isolation_and_quarantine_fields_round_trip_with_defaults() {
        let (_dir, store) = store();
        std::fs::write(
            store.path(),
            r#"{"v":1,"isolation":{"id":"i1","startedAt":10,"revertAt":20},"quarantine_index":[{"id":"q1"}]}"#,
        )
        .unwrap();
        let state = store.load().unwrap();
        let iso = state.isolation.clone().unwrap();
        assert_eq!((iso.id.as_str(), iso.started_at, iso.revert_at, iso.confirmed), ("i1", 10, 20, false));
        assert_eq!(state.quarantine_index.len(), 1);
    }

    #[test]
    fn an_unchanged_state_is_not_rewritten() {
        let (_dir, store) = store();
        store.update(|_| ()).unwrap();
        assert!(!store.path().exists());
    }

    #[test]
    fn the_same_instruction_twice_is_one_claim_and_a_different_one_adds_a_claim() {
        let mut s = ResponseState::default();
        assert_eq!(s.add_claim("1.2.3.4", "a", 5000, 1000), ClaimAdded::New);
        assert_eq!(s.add_claim("1.2.3.4", "a", 9000, 1001), ClaimAdded::Existing { expires_at: 5000 });
        assert_eq!(s.add_claim("1.2.3.4", "b", 6000, 1001), ClaimAdded::New);
        assert_eq!(s.claims.len(), 2);
        assert_eq!(s.live_for("1.2.3.4", 1002), 2);
    }

    #[test]
    fn an_expired_claim_is_renewed_by_the_same_instruction() {
        let mut s = ResponseState::default();
        s.add_claim("1.2.3.4", "a", 2000, 1000);
        assert_eq!(s.add_claim("1.2.3.4", "a", 9000, 3000), ClaimAdded::New);
        assert_eq!(s.find("1.2.3.4", "a").unwrap().expires_at, 9000);
        assert_eq!(s.claims.len(), 1);
    }

    #[test]
    fn removing_one_claim_leaves_the_others_and_none_means_all() {
        let mut s = ResponseState::default();
        s.add_claim("1.2.3.4", "a", 5000, 1000);
        s.add_claim("1.2.3.4", "b", 5000, 1000);
        s.add_claim("5.6.7.8", "c", 5000, 1000);
        assert_eq!(s.remove_claims("1.2.3.4", Some("a")), 1);
        assert_eq!(s.live_for("1.2.3.4", 1000), 1);
        assert_eq!(s.remove_claims("1.2.3.4", None), 1);
        assert_eq!(s.live_for("5.6.7.8", 1000), 1);
    }

    #[test]
    fn expired_claims_are_not_live_and_can_be_dropped() {
        let mut s = ResponseState::default();
        s.add_claim("1.2.3.4", "a", 2000, 1000);
        assert_eq!(s.live_for("1.2.3.4", 2000), 0);
        assert_eq!(s.drop_expired("1.2.3.4", 2000), 1);
        assert!(s.claims.is_empty());
    }
}
