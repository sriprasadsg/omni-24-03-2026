//! What each install job changed on this host, so a revert puts back exactly that (PTCH-04, C3).
//!
//! Linux: the version of each package before the job upgraded it. Windows: the KBs the job
//! installed. A revert by job reads the record of that job only, so a package upgraded by jobs N-1
//! and N and reverted with `revert_of` N goes back to the version before N, not before N-1. The
//! older per-package "oldest version" map stays as `legacy` for manual reverts without `revert_of`.

use super::patch_installer::coded_result;
use super::patch_reversible::{NOT_APPLICABLE, NOT_CHANGED_BY_JOB};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// What a Windows job records for an installed KB (a KB is removed by id, not by version).
pub const KB_MARK: &str = "kb";
const KEEP_SECONDS: i64 = 90 * 24 * 3600;

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct JobEntry {
    // A field a hand-edited or older file lacks must not discard every other job (WR-14).
    #[serde(default)]
    pub at: i64,
    #[serde(default)]
    pub os: String,
    /// patch id -> the version before this job (Linux), or `KB_MARK` (Windows)
    #[serde(default)]
    pub changes: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct JobsState {
    /// package -> the oldest version this agent recorded before upgrading it (2.1.16 behaviour)
    #[serde(default)]
    pub legacy: BTreeMap<String, String>,
    #[serde(default)]
    pub jobs: BTreeMap<String, JobEntry>,
}

/// Where a revert by job puts one id.
#[derive(Debug, Clone, PartialEq)]
pub enum Target {
    Version(String),
    Kb,
    NotChanged,
}

/// The ids a revert acts on and the results already known without touching the host.
#[derive(Debug, Default)]
pub struct RevertPlan {
    pub immediate: Vec<Value>,
    /// (patch id, target version or `KB_MARK`)
    pub todo: Vec<(String, String)>,
}

pub fn state_path() -> PathBuf {
    crate::config::config_path().with_file_name("patch_state.json")
}

impl JobsState {
    /// Reads either format: the current one, or the 2.1.16 flat package -> version map (loaded as `legacy`).
    pub fn from_bytes(bytes: &[u8]) -> JobsState {
        Self::try_from_bytes(bytes).unwrap_or_default()
    }

    /// Like `from_bytes`, but None when the bytes are not a state file at all.
    fn try_from_bytes(bytes: &[u8]) -> Option<JobsState> {
        let Ok(Value::Object(map)) = serde_json::from_slice::<Value>(bytes) else { return None };
        if matches!(map.get("legacy"), Some(Value::Object(_))) || matches!(map.get("jobs"), Some(Value::Object(_))) {
            return serde_json::from_value(Value::Object(map)).ok();
        }
        Some(JobsState { legacy: map.into_iter().filter_map(|(k, v)| v.as_str().map(|v| (k, v.to_string()))).collect(), jobs: BTreeMap::new() })
    }

    /// Records that `job_id` changed `id`, which was at `before` (or `KB_MARK`). The first record of
    /// an id within one job wins.
    pub fn record_install(&mut self, job_id: &str, os: &str, now: i64, id: &str, before: &str) {
        let entry = self.jobs.entry(job_id.to_string()).or_insert_with(|| JobEntry { at: now, os: os.to_string(), changes: BTreeMap::new() });
        entry.changes.entry(id.to_string()).or_insert_with(|| before.to_string());
    }

    /// Records every KB a Windows install job reported as installed.
    pub fn record_kb_successes(&mut self, job_id: &str, now: i64, results: &[Value]) {
        for r in results.iter().filter(|r| r["status"] == "success") {
            if let Some(kb) = r["patch_id"].as_str() {
                self.record_install(job_id, "windows", now, kb, KB_MARK);
            }
        }
    }

    /// Drops job records older than 90 days.
    pub fn prune(&mut self, now: i64) {
        self.jobs.retain(|_, j| j.at >= now - KEEP_SECONDS);
    }

    /// For each id: what `job_id` did to it. None when this host has no record of that job.
    pub fn revert_targets(&self, job_id: &str, ids: &[String]) -> Option<Vec<(String, Target)>> {
        let job = self.jobs.get(job_id)?;
        Some(ids.iter().map(|id| (id.clone(), match job.changes.get(id) {
            None => Target::NotChanged,
            Some(m) if m == KB_MARK => Target::Kb,
            Some(version) => Target::Version(version.clone()),
        })).collect())
    }

    /// Splits a revert of `job_id` into answers that need no host work and the ids to act on.
    pub fn plan_revert(&self, job_id: &str, ids: &[String]) -> RevertPlan {
        let mut plan = RevertPlan::default();
        let Some(targets) = self.revert_targets(job_id, ids) else {
            plan.immediate = ids.iter().map(|id| coded_result(id, "failed", NOT_APPLICABLE,
                "This computer has no record of that install job, so nothing was reverted", false)).collect();
            return plan;
        };
        for (id, target) in targets {
            match target {
                Target::NotChanged => plan.immediate.push(coded_result(&id, "skipped", NOT_CHANGED_BY_JOB, &format!("This job did not change {id}"), false)),
                Target::Kb => plan.todo.push((id, KB_MARK.to_string())),
                Target::Version(v) => plan.todo.push((id, v)),
            }
        }
        plan
    }
}

/// A non-empty file that does not parse is copied to `<path>.bad` (replacing an older copy) before the
/// default is returned, so the next save cannot wipe the only record of what jobs changed (WR-14).
pub fn load_from(path: &Path) -> JobsState {
    let Ok(bytes) = std::fs::read(path) else { return JobsState::default() };
    if bytes.iter().all(u8::is_ascii_whitespace) {
        return JobsState::default();
    }
    JobsState::try_from_bytes(&bytes).unwrap_or_else(|| {
        let mut bad = path.as_os_str().to_owned();
        bad.push(".bad");
        match std::fs::write(&bad, &bytes) {
            Ok(()) => log::warn!("{} could not be read; kept as {}", path.display(), Path::new(&bad).display()),
            Err(e) => log::warn!("{} could not be read and could not be copied aside: {e}", path.display()),
        }
        JobsState::default()
    })
}

/// Writes through a temporary file, flushed to disk before the rename, so a crash or power loss never
/// leaves half a state file.
pub fn save_to(path: &Path, state: &JobsState) -> bool {
    use std::io::Write;
    let tmp = path.with_extension("json.tmp");
    let Ok(bytes) = serde_json::to_vec_pretty(state) else { return false };
    let written = std::fs::File::create(&tmp).and_then(|mut f| f.write_all(&bytes).and_then(|_| f.sync_all()));
    written.and_then(|_| std::fs::rename(&tmp, path)).is_ok()
}

pub fn load() -> JobsState {
    load_from(&state_path())
}

pub fn save(state: &mut JobsState) {
    state.prune(chrono::Utc::now().timestamp());
    if !save_to(&state_path(), state) {
        log::warn!("Could not record what this patch job changed in {}", state_path().display());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn ids(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn patch_state_round_trips_with_the_legacy_map_untouched() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("patch_state.json");
        let mut s = JobsState::default();
        s.legacy.insert("openssl".into(), "1.0".into());
        s.record_install("job-1", "linux", 1_000, "openssl", "1.0");
        assert!(save_to(&path, &s));
        assert_eq!(load_from(&path), s);
        assert_eq!(load_from(&path).legacy["openssl"], "1.0");
    }

    #[test]
    fn patch_state_loads_the_2_1_16_flat_map_as_legacy() {
        let flat = serde_json::to_vec(&json!({"openssl": "1.0", "curl": "7.1"})).unwrap();
        let s = JobsState::from_bytes(&flat);
        assert_eq!((s.legacy["openssl"].as_str(), s.legacy["curl"].as_str(), s.jobs.len()), ("1.0", "7.1", 0));
        // a package that happens to be called "jobs" is still a flat map entry, not the new format
        assert_eq!(JobsState::from_bytes(br#"{"jobs": "2.0"}"#).legacy["jobs"], "2.0");
        assert_eq!(JobsState::from_bytes(b"not json"), JobsState::default());
    }

    #[test]
    fn patch_state_revert_of_restores_version_before_that_job() {
        let mut s = JobsState::default();
        s.record_install("job-n-1", "linux", 1_000, "openssl", "1.0"); // 1.0 -> 1.1
        s.record_install("job-n", "linux", 2_000, "openssl", "1.1"); // 1.1 -> 1.2
        let t = s.revert_targets("job-n", &ids(&["openssl"])).unwrap();
        assert_eq!(t, vec![("openssl".to_string(), Target::Version("1.1".to_string()))]);
        let t = s.revert_targets("job-n-1", &ids(&["openssl"])).unwrap();
        assert_eq!(t, vec![("openssl".to_string(), Target::Version("1.0".to_string()))]);
    }

    #[test]
    fn patch_state_an_id_the_job_did_not_change_is_skipped_with_its_code() {
        let mut s = JobsState::default();
        s.record_install("job-1", "linux", 1_000, "openssl", "1.0");
        let plan = s.plan_revert("job-1", &ids(&["curl", "openssl"]));
        assert_eq!(plan.todo, vec![("openssl".to_string(), "1.0".to_string())]);
        assert_eq!((plan.immediate[0]["status"].as_str(), plan.immediate[0]["code"].as_str(), plan.immediate[0]["patch_id"].as_str()),
                   (Some("skipped"), Some("not_changed_by_job"), Some("curl")));
    }

    #[test]
    fn patch_state_a_job_the_host_has_no_record_of_reverts_nothing() {
        let s = JobsState::default();
        assert!(s.revert_targets("job-9", &ids(&["openssl"])).is_none());
        let plan = s.plan_revert("job-9", &ids(&["openssl", "KB5034441"]));
        assert!(plan.todo.is_empty());
        assert!(plan.immediate.iter().all(|r| r["status"] == "failed" && r["code"] == "not_applicable"));
        assert_eq!(plan.immediate.len(), 2);
    }

    #[test]
    fn patch_state_a_windows_job_records_the_kbs_it_installed() {
        let mut s = JobsState::default();
        s.record_install("job-2", "windows", 1_000, "KB5034441", KB_MARK);
        let plan = s.plan_revert("job-2", &ids(&["KB5034441", "KB5000001"]));
        assert_eq!(plan.todo, vec![("KB5034441".to_string(), "kb".to_string())]);
        assert_eq!(plan.immediate[0]["code"], "not_changed_by_job");
    }

    #[test]
    fn patch_state_only_installed_kbs_are_recorded_for_a_windows_job() {
        let mut s = JobsState::default();
        s.record_kb_successes("job-2", 1_000, &[
            json!({"patch_id": "KB5034441", "status": "success"}),
            json!({"patch_id": "KB5000001", "status": "failed"}),
            json!({"patch_id": "KB5000002", "status": "deferred", "code": "not_reversible"}),
            json!({"patch_id": "KB5000003", "status": "skipped"}),
        ]);
        assert_eq!(s.jobs["job-2"].changes.keys().cloned().collect::<Vec<_>>(), vec!["KB5034441".to_string()]);
        s.record_kb_successes("job-3", 1_000, &[json!({"patch_id": "KB5000001", "status": "failed"})]);
        assert!(!s.jobs.contains_key("job-3"));
    }

    #[test]
    fn patch_state_a_job_reads_revert_of_with_the_job_id_shape_rule() {
        use super::super::patch_installer::parse_job;
        let rollback = |item: Value| parse_job(&item, true);
        let ok = rollback(json!({"payload": {"patch_ids": ["openssl"], "revert_of": "job_2-A"}})).unwrap();
        assert_eq!(ok.revert_of.as_deref(), Some("job_2-A"));
        assert_eq!(rollback(json!({"parameters": {"patch_ids": ["openssl"], "revert_of": "job-1"}})).unwrap().revert_of.as_deref(), Some("job-1"));
        assert_eq!(rollback(json!({"payload": {"patch_ids": ["openssl"]}})).unwrap().revert_of, None);
        assert_eq!(rollback(json!({"payload": {"patch_ids": ["openssl"], "revert_of": null}})).unwrap().revert_of, None);
        // a malformed id is an error: it must never fall back to the oldest-version rollback
        for bad in [json!("../x"), json!(""), json!(7), json!("a b"), json!("x".repeat(81))] {
            assert!(rollback(json!({"payload": {"patch_ids": ["openssl"], "revert_of": bad}})).is_err(), "{bad}");
        }
        // an install never carries revert_of
        assert!(parse_job(&json!({"payload": {"patch_ids": ["openssl"], "revert_of": "job-1"}}), false).is_err());
    }

    #[test]
    fn patch_state_prune_drops_jobs_older_than_90_days_only() {
        let mut s = JobsState::default();
        let now = 200 * 24 * 3600;
        s.record_install("old", "linux", now - 91 * 24 * 3600, "a", "1");
        s.record_install("recent", "linux", now - 89 * 24 * 3600, "b", "1");
        s.prune(now);
        assert_eq!(s.jobs.keys().cloned().collect::<Vec<_>>(), vec!["recent".to_string()]);
    }

    #[test]
    fn patch_state_an_entry_missing_a_field_keeps_itself_and_every_other_job() {
        let raw = json!({"legacy": {"curl": "7.1"}, "jobs": {
            "job-a": {"at": 5, "changes": {"openssl": "1.0"}},
            "job-b": {"at": 6, "os": "linux", "changes": {"curl": "7.0"}},
            "job-c": {"os": "windows"}}});
        let s = JobsState::from_bytes(&serde_json::to_vec(&raw).unwrap());
        assert_eq!(s.legacy["curl"], "7.1");
        assert_eq!(s.jobs.len(), 3);
        assert_eq!((s.jobs["job-a"].os.as_str(), s.jobs["job-a"].changes["openssl"].as_str()), ("", "1.0"));
        assert_eq!(s.jobs["job-b"].changes["curl"], "7.0");
        assert!(s.jobs["job-c"].changes.is_empty());
    }

    #[test]
    fn patch_state_an_unreadable_file_is_kept_as_bad_before_the_default_is_returned() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("patch_state.json");
        let bad = dir.path().join("patch_state.json.bad");
        std::fs::write(&path, b"{ half a file").unwrap();
        std::fs::write(&bad, b"an older copy").unwrap();
        assert_eq!(load_from(&path), JobsState::default());
        assert_eq!(std::fs::read(&bad).unwrap(), b"{ half a file", "the older .bad copy is overwritten");
        assert_eq!(std::fs::read(&path).unwrap(), b"{ half a file", "the original is left in place");
    }

    #[test]
    fn patch_state_a_missing_empty_or_good_file_leaves_no_bad_copy() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("patch_state.json");
        let bad = dir.path().join("patch_state.json.bad");
        assert_eq!(load_from(&path), JobsState::default());
        std::fs::write(&path, b"").unwrap();
        assert_eq!(load_from(&path), JobsState::default());
        let mut s = JobsState::default();
        s.record_install("job-1", "linux", 1_000, "openssl", "1.0");
        assert!(save_to(&path, &s));
        assert_eq!(load_from(&path), s);
        // the 2.1.16 flat map is a valid file too
        std::fs::write(&path, br#"{"openssl": "1.0"}"#).unwrap();
        assert_eq!(load_from(&path).legacy["openssl"], "1.0");
        assert!(!bad.exists());
    }

    #[test]
    fn patch_state_save_replaces_the_file_whole_and_leaves_no_temporary_behind() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("patch_state.json");
        let mut s = JobsState::default();
        s.record_install("job-1", "linux", 1_000, "openssl", "1.0");
        assert!(save_to(&path, &s));
        s.record_install("job-2", "linux", 2_000, "curl", "7.0");
        assert!(save_to(&path, &s));
        assert_eq!(load_from(&path), s);
        let names: Vec<String> = std::fs::read_dir(dir.path()).unwrap().map(|e| e.unwrap().file_name().to_string_lossy().into_owned()).collect();
        assert_eq!(names, vec!["patch_state.json".to_string()]);
    }

    #[test]
    fn patch_state_the_first_record_of_an_id_within_a_job_wins() {
        let mut s = JobsState::default();
        s.record_install("job-1", "linux", 1_000, "openssl", "1.0");
        s.record_install("job-1", "linux", 1_001, "openssl", "1.1");
        assert_eq!(s.jobs["job-1"].changes["openssl"], "1.0");
        assert_eq!(s.jobs["job-1"].at, 1_000);
    }
}
