//! Quarantine and restore (Autonomous Ops, RESP-03): a flagged file is moved out of reach and can
//! be put back with one instruction. Nothing here ever deletes a person's file.
//!
//! A move runs in this order: check the instruction id and the path (full path, no `..`, not the
//! agent's own files, not a protected system path unless allowed), refuse a folder or a link,
//! hash the file and compare it with the hash the backend flagged (`hash_mismatch` leaves it
//! untouched), write the manifest, then rename the file into the quarantine folder. Across two
//! volumes the file is copied, flushed and hashed again, and only then is the original removed;
//! if it cannot be removed the copy is removed instead and the answer is `locked`.
//!
//! The stored file is `<id>` (mode 000) on Linux and `<id>.q` on Windows, with `<id>.json` beside
//! it holding where it came from. A restore reads that manifest and nothing else: the instruction
//! names only the id. It refuses an existing destination, a linked destination folder and a stored
//! file whose hash no longer matches. Whole operations run under the response-state lock.

use crate::capabilities::process_kill::same_process;
pub use crate::capabilities::quarantine_paths::{
    is_absolute, manifest_path, normalize, running_from, running_now, same_exe, stored_path,
    QuarantinePaths, RunningProcess, PROTECTED_LINUX, PROTECTED_WINDOWS, STILL_RUNNING_CAP,
};
use crate::capabilities::quarantine_paths::{has_dotdot, is_own_file, under_protected, unix_mode, unix_owner};
use crate::capabilities::response_actions::valid_id;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::io;
use std::path::Path;

const MANIFEST_VERSION: u32 = 1;
const IN_QUARANTINE: &str = "in_quarantine";
const RESTORED: &str = "restored_to_path";

/// What a quarantine instruction asks for.
#[derive(Debug, Clone)]
pub struct QuarantineRequest {
    pub path: String,
    pub sha256: String,
    pub allow_protected: bool,
    /// The instruction's task id; it names the stored file.
    pub id: String,
}

/// The two file operations that can lose data, as values so a test can make them fail.
pub struct FileOps {
    pub rename: fn(&Path, &Path) -> io::Result<()>,
    /// Removes the ORIGINAL after a verified copy exists. Called from `copy_across` only.
    pub remove_original: fn(&Path) -> io::Result<()>,
}

impl FileOps {
    pub const REAL: FileOps = FileOps { rename: rename_file, remove_original: remove_original_file };
}

fn rename_file(from: &Path, to: &Path) -> io::Result<()> {
    std::fs::rename(from, to)
}

// remove_file: the original, called only after the copy was flushed and its hash matched.
fn remove_original_file(path: &Path) -> io::Result<()> {
    std::fs::remove_file(path)
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Manifest {
    v: u32,
    id: String,
    original_path: String,
    sha256: String,
    size: u64,
    quarantined_at: i64,
    #[serde(default)]
    mode: Option<u32>,
    #[serde(default)]
    uid: Option<u32>,
    #[serde(default)]
    gid: Option<u32>,
}

enum MoveError {
    Locked,
    Mismatch,
    Other(String),
}

fn verify(ok: bool, check: &str) -> Value {
    json!({"ok": ok, "check": check})
}

fn refused(why: &str) -> Value {
    json!({"status": "error", "outcome": "refused", "error": why})
}

fn failed(why: &str) -> Value {
    json!({"status": "error", "error": why})
}

fn still_json(list: &[RunningProcess]) -> Value {
    Value::Array(
        list.iter()
            .take(STILL_RUNNING_CAP)
            .map(|p| json!({"pid": p.pid, "name": p.name, "start_time": p.start_time}))
            .collect(),
    )
}

fn error_body(outcome: &str, why: &str, still: &[RunningProcess]) -> Value {
    let mut body = json!({"status": "error", "outcome": outcome, "verify": verify(false, IN_QUARANTINE), "error": why});
    if !still.is_empty() {
        body["still_running"] = still_json(still);
    }
    body
}

fn locked_body(still: &[RunningProcess]) -> Value {
    error_body("locked", "The file is in use and could not be moved.", still)
}

fn protected_body() -> Value {
    error_body("protected_path", "The file is a protected system file or belongs to this agent.", &[])
}

fn quarantined_body(outcome: &str, ok: bool, still: &[RunningProcess]) -> Value {
    let mut body = json!({"status": "success", "outcome": outcome, "verify": verify(ok, IN_QUARANTINE)});
    if !still.is_empty() {
        body["still_running"] = still_json(still);
    }
    body
}

pub(crate) fn hash_file(path: &Path) -> io::Result<String> {
    use io::Read;
    use sha2::{Digest, Sha256};
    let mut file = std::fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 65536];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            return Ok(hex::encode(hasher.finalize()));
        }
        hasher.update(&buf[..n]);
    }
}

#[cfg(unix)]
fn set_mode(path: &Path, mode: u32) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(mode))
}

/// Run `read` on the stored file with its owner able to read it (it is mode 000 on Linux).
fn with_readable<T>(stored: &Path, read: impl FnOnce(&Path) -> io::Result<T>) -> io::Result<T> {
    #[cfg(unix)]
    set_mode(stored, 0o400)?;
    let out = read(stored);
    #[cfg(unix)]
    let _ = set_mode(stored, 0o000);
    out
}

fn hash_stored(stored: &Path) -> io::Result<String> {
    with_readable(stored, hash_file)
}

/// True for a symlink, and on Windows for any reparse point.
pub(crate) fn is_link_like(meta: &std::fs::Metadata) -> bool {
    if meta.file_type().is_symlink() {
        return true;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        return meta.file_attributes() & 0x400 != 0;
    }
    #[cfg(not(windows))]
    false
}

fn crosses_device(e: &io::Error) -> bool {
    e.kind() == io::ErrorKind::CrossesDevices
        || matches!(e.raw_os_error(), Some(code) if (cfg!(windows) && code == 17) || (cfg!(unix) && code == 18))
}

/// A sharing violation, a lock violation, a busy executable, or no access.
fn locked_error(e: &io::Error) -> bool {
    e.kind() == io::ErrorKind::PermissionDenied
        || matches!(e.raw_os_error(), Some(code) if (cfg!(windows) && (code == 32 || code == 33)) || (cfg!(unix) && code == 26))
}

// remove_file: a file this module wrote itself (a manifest or a copy). Never a person's file.
fn discard_own(path: &Path) {
    let _ = std::fs::remove_file(path);
}

fn write_manifest(path: &Path, manifest: &Manifest) -> io::Result<()> {
    use io::Write;
    let text = serde_json::to_string_pretty(manifest).map_err(io::Error::other)?;
    let tmp = path.with_extension("json.tmp");
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&tmp)?;
    file.write_all(text.as_bytes())?;
    file.sync_all()?;
    drop(file);
    std::fs::rename(&tmp, path).inspect_err(|_| discard_own(&tmp))
}

fn read_manifest(paths: &QuarantinePaths, id: &str) -> Result<Option<Manifest>, String> {
    match std::fs::read_to_string(manifest_path(paths, id)) {
        Ok(text) => serde_json::from_str(&text).map(Some).map_err(|e| format!("The manifest cannot be read: {e}")),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(format!("The manifest cannot be read: {e}")),
    }
}

fn ensure_dir(dir: &Path) -> Result<(), String> {
    if let Ok(meta) = std::fs::symlink_metadata(dir) {
        if is_link_like(&meta) || !meta.is_dir() {
            return Err("The quarantine folder is not a normal folder.".to_string());
        }
    }
    std::fs::create_dir_all(dir).map_err(|e| format!("The quarantine folder cannot be created: {e}"))?;
    #[cfg(unix)]
    set_mode(dir, 0o700).map_err(|e| format!("The quarantine folder cannot be locked down: {e}"))?;
    Ok(())
}

/// The file's own bytes, hashed again after the copy; only then may the original go.
fn copy_across(ops: &FileOps, src: &Path, dst: &Path, sha: &str) -> Result<(), MoveError> {
    // create_new: a name that is already taken is never opened, and so never discarded below.
    let mut out = match std::fs::OpenOptions::new().write(true).create_new(true).open(dst) {
        Ok(out) => out,
        Err(e) => return Err(if locked_error(&e) { MoveError::Locked } else { MoveError::Other(e.to_string()) }),
    };
    let copied = std::fs::File::open(src).and_then(|mut from| io::copy(&mut from, &mut out)).and_then(|_| out.sync_all());
    drop(out);
    if let Err(e) = copied {
        discard_own(dst);
        return Err(if locked_error(&e) { MoveError::Locked } else { MoveError::Other(e.to_string()) });
    }
    #[cfg(unix)]
    let _ = set_mode(dst, 0o400);
    if hash_file(dst).ok().as_deref() != Some(sha) {
        discard_own(dst);
        return Err(MoveError::Mismatch);
    }
    if (ops.remove_original)(src).is_err() {
        discard_own(dst); // our own copy goes; the person's file stays where it was
        return Err(MoveError::Locked);
    }
    Ok(())
}

fn move_file(ops: &FileOps, src: &Path, dst: &Path, sha: &str) -> Result<(), MoveError> {
    match (ops.rename)(src, dst) {
        Ok(()) => Ok(()),
        Err(e) if crosses_device(&e) => copy_across(ops, src, dst, sha),
        Err(e) if locked_error(&e) => Err(MoveError::Locked),
        Err(e) => Err(MoveError::Other(e.to_string())),
    }
}

/// Manifest present, stored hash equal to `sha`, original path gone.
fn verify_in_quarantine(paths: &QuarantinePaths, id: &str, sha: &str, original: &str) -> bool {
    let manifest_ok = matches!(read_manifest(paths, id), Ok(Some(m)) if m.sha256 == sha);
    let stored_ok = hash_stored(&stored_path(paths, id)).ok().as_deref() == Some(sha);
    let gone = matches!(std::fs::symlink_metadata(original), Err(e) if e.kind() == io::ErrorKind::NotFound);
    manifest_ok && stored_ok && gone
}

/// The answer for an instruction id that already holds a quarantined file: the same file is
/// `already_applied` (nothing moves), another file is refused. None when the id is free or only
/// a manifest from a move that never finished is left.
fn already_held(paths: &QuarantinePaths, req: &QuarantineRequest, sha: &str) -> Option<Value> {
    let held = matches!(read_manifest(paths, &req.id), Ok(Some(_))) && std::fs::symlink_metadata(stored_path(paths, &req.id)).is_ok();
    if !held {
        return None;
    }
    let same = matches!(read_manifest(paths, &req.id), Ok(Some(m)) if m.original_path == req.path && m.sha256 == sha);
    Some(if same {
        quarantined_body("already_applied", verify_in_quarantine(paths, &req.id, sha, &req.path), &[])
    } else {
        refused("This instruction id already holds a different file.")
    })
}

/// Move the file named by `req` into quarantine. `running` is a process list read just before.
pub fn quarantine_at(paths: &QuarantinePaths, req: &QuarantineRequest, now: i64, running: &[RunningProcess]) -> Value {
    quarantine_with(paths, req, now, running, &running_now, &FileOps::REAL)
}

/// `quarantine_at` with the later process list and the file operations supplied.
pub(crate) fn quarantine_with(
    paths: &QuarantinePaths,
    req: &QuarantineRequest,
    now: i64,
    running: &[RunningProcess],
    later: &dyn Fn() -> Vec<RunningProcess>,
    ops: &FileOps,
) -> Value {
    let ws = paths.windows_style;
    if !valid_id(&req.id) {
        return refused("The instruction id is missing or not valid.");
    }
    let sha = req.sha256.to_ascii_lowercase();
    if sha.len() != 64 || !sha.chars().all(|c| c.is_ascii_hexdigit()) {
        return refused("sha256 must be 64 hexadecimal characters.");
    }
    let normal = normalize(&req.path, ws);
    if req.path.is_empty() || !is_absolute(&normal, ws) || has_dotdot(&req.path, ws) {
        return refused("The path must be a full path with no '..' part.");
    }
    if is_own_file(paths, &normal) || (!req.allow_protected && under_protected(&normal, &paths.protected, ws)) {
        return protected_body();
    }
    if let Some(answer) = already_held(paths, req, &sha) {
        return answer; // a repeat: the file is already in quarantine and the original path is empty
    }
    let matched = running_from(running, &req.path, ws);
    let src = Path::new(&req.path);
    let meta = match std::fs::symlink_metadata(src) {
        Ok(meta) => meta,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return refused("The file is no longer at that path."),
        Err(e) if locked_error(&e) => return locked_body(&matched),
        Err(e) => return failed(&format!("The file cannot be inspected: {e}")),
    };
    if is_link_like(&meta) || meta.is_dir() || !meta.is_file() {
        return refused("Only a regular file can be quarantined, not a folder or a link.");
    }
    match hash_file(src) {
        Ok(actual) if actual == sha => {}
        Ok(_) => return error_body("hash_mismatch", "The file no longer matches the hash that was flagged.", &[]),
        Err(e) if locked_error(&e) => return locked_body(&matched),
        Err(e) => return failed(&format!("The file cannot be read: {e}")),
    }
    if let Err(why) = ensure_dir(&paths.dir) {
        return failed(&why);
    }
    let result = paths.store.update(|state| {
        let stored = stored_path(paths, &req.id);
        if let Some(answer) = already_held(paths, req, &sha) {
            return answer;
        }
        if std::fs::symlink_metadata(&stored).is_ok() {
            return refused("The quarantine folder already holds a file for this instruction id.");
        }
        let manifest = Manifest {
            v: MANIFEST_VERSION,
            id: req.id.clone(),
            original_path: req.path.clone(),
            sha256: sha.clone(),
            size: meta.len(),
            quarantined_at: now,
            mode: unix_mode(&meta),
            uid: unix_owner(&meta).map(|o| o.0),
            gid: unix_owner(&meta).map(|o| o.1),
        };
        let manifest_file = manifest_path(paths, &req.id);
        if let Err(e) = write_manifest(&manifest_file, &manifest) {
            return failed(&format!("The manifest cannot be written: {e}"));
        }
        if let Err(moved) = move_file(ops, src, &stored, &sha) {
            discard_own(&manifest_file);
            return match moved {
                MoveError::Locked => locked_body(&matched),
                MoveError::Mismatch => {
                    error_body("hash_mismatch", "The file no longer matches the hash that was flagged.", &[])
                }
                MoveError::Other(why) => failed(&format!("The file could not be moved: {why}")),
            };
        }
        #[cfg(unix)]
        let _ = set_mode(&stored, 0o000);
        state.quarantine_index.retain(|e| e.get("id").and_then(Value::as_str) != Some(req.id.as_str()));
        state.quarantine_index.push(json!({
            "id": req.id, "originalPath": req.path, "sha256": sha, "quarantinedAt": now,
        }));
        let after = later();
        let survivors: Vec<RunningProcess> = matched
            .iter()
            .filter(|m| after.iter().any(|a| same_process(a.pid, a.start_time, m.pid, m.start_time)))
            .cloned()
            .collect();
        quarantined_body("quarantined", verify_in_quarantine(paths, &req.id, &sha, &req.path), &survivors)
    });
    result.unwrap_or_else(|e| failed(&e.to_string()))
}

fn restore_error(outcome: &str, why: &str) -> Value {
    json!({"status": "error", "outcome": outcome, "verify": verify(false, RESTORED), "error": why})
}

/// Put the file quarantined for `id` back at the path its manifest names.
pub fn restore_at(paths: &QuarantinePaths, id: &str) -> Value {
    if !valid_id(id) {
        return refused("quarantine_id is missing or not valid.");
    }
    let result = paths.store.update(|state| {
        let m = match read_manifest(paths, id) {
            Ok(Some(m)) => m,
            Ok(None) => return restore_error("not_found", "Nothing is quarantined under that id."),
            Err(why) => return restore_error("refused", &why),
        };
        let stored = stored_path(paths, id);
        if std::fs::symlink_metadata(&stored).is_err() {
            return restore_error("not_found", "The stored file is not in the quarantine folder.");
        }
        let ws = paths.windows_style;
        let normal = normalize(&m.original_path, ws);
        if !is_absolute(&normal, ws) || has_dotdot(&m.original_path, ws) {
            return restore_error("refused", "The manifest does not hold a usable path.");
        }
        let dest = Path::new(&m.original_path);
        if std::fs::symlink_metadata(dest).is_ok() {
            return restore_error("refused", "A file is already at the original path, so nothing was restored.");
        }
        match dest.parent().map(std::fs::symlink_metadata) {
            Some(Ok(dir)) if !is_link_like(&dir) && dir.is_dir() => {}
            Some(Ok(_)) => return restore_error("refused", "The original folder is a link, so nothing was restored."),
            _ => return restore_error("refused", "The original folder is gone, so nothing was restored."),
        }
        if hash_stored(&stored).ok().as_deref() != Some(m.sha256.as_str()) {
            return restore_error("refused", "The stored file has changed since it was quarantined.");
        }
        if let Err(why) = place_back(&stored, dest) {
            return restore_error("refused", &why);
        }
        #[cfg(unix)]
        {
            // A hard link shares the stored file's mode (000), so set it before reading.
            let _ = set_mode(dest, m.mode.unwrap_or(0o600));
            if let (Some(uid), Some(gid)) = (m.uid, m.gid) {
                let _ = std::os::unix::fs::chown(dest, Some(uid), Some(gid)); // fails without root: ignored
            }
        }
        if hash_file(dest).ok().as_deref() != Some(m.sha256.as_str()) {
            discard_own(dest); // the name place_back just created; the stored file stays
            #[cfg(unix)]
            let _ = set_mode(&stored, 0o000);
            return restore_error("refused", "The restored copy did not match, so it was taken out again.");
        }
        // remove_file: the stored name, in the restore branch, after the file is back and hashed.
        let _ = std::fs::remove_file(&stored);
        discard_own(&manifest_path(paths, id));
        state.quarantine_index.retain(|e| e.get("id").and_then(Value::as_str) != Some(id));
        let back = hash_file(dest).ok().as_deref() == Some(m.sha256.as_str()) && std::fs::symlink_metadata(&stored).is_err();
        json!({"status": "success", "outcome": "restored", "verify": verify(back, RESTORED)})
    });
    result.unwrap_or_else(|e| failed(&e.to_string()))
}

/// A hard link never replaces a file that appeared meanwhile; where links are not possible the
/// bytes are copied to a new file and hashed again. The stored file stays until this succeeds.
fn place_back(stored: &Path, dest: &Path) -> Result<(), String> {
    match std::fs::hard_link(stored, dest) {
        Ok(()) => return Ok(()),
        Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {
            return Err("A file is already at the original path, so nothing was restored.".to_string());
        }
        Err(_) => {}
    }
    let mut out = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(dest)
        .map_err(|e| format!("The file could not be put back: {e}"))?;
    let copied = with_readable(stored, |from| {
        io::copy(&mut std::fs::File::open(from)?, &mut out)?;
        out.sync_all()
    });
    drop(out);
    copied.map_err(|e| {
        discard_own(dest); // the file create_new just made
        format!("The file could not be put back: {e}")
    })
}

#[cfg(test)]
#[path = "quarantine_tests.rs"]
mod tests;
