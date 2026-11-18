//! FIM on macOS: FSEvents (through `notify`) over the configured paths, into the same fim_queue the
//! Linux watcher fills. FSEvents names no process, so an event carries the path, the change and the
//! file's hashes.

use super::ChangeType;
use notify::event::{EventKind, ModifyKind};
#[cfg(target_os = "macos")]
use super::{current_user, enqueue_event, hash_file, FimEvent, ProcessInfo, FIM_STATUS};
#[cfg(target_os = "macos")]
use std::collections::HashMap;

/// The change an FSEvents event stands for; reads and unknown events are not changes.
pub(super) fn change_type(kind: &EventKind) -> Option<ChangeType> {
    match kind {
        EventKind::Create(_) => Some(ChangeType::Create),
        EventKind::Remove(_) => Some(ChangeType::Delete),
        EventKind::Modify(ModifyKind::Name(_)) => Some(ChangeType::Rename),
        EventKind::Modify(ModifyKind::Metadata(_)) => Some(ChangeType::Permission),
        EventKind::Modify(_) => Some(ChangeType::Modify),
        _ => None,
    }
}

/// Watches `paths` recursively until `stop_rx` says stop. Paths that do not exist are skipped;
/// an error only when none can be watched.
#[cfg(target_os = "macos")]
pub fn start_watcher(
    paths: Vec<String>,
    mut stop_rx: tokio::sync::watch::Receiver<bool>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use notify::{RecursiveMode, Watcher};

    if FIM_STATUS.lock().unwrap().watching {
        return Err("watcher already running".into());
    }
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<notify::Event>();
    let mut watcher = notify::recommended_watcher(move |res: notify::Result<notify::Event>| {
        if let Ok(event) = res {
            let _ = tx.send(event);
        }
    })?;
    let mut watched = Vec::new();
    for p in paths.iter().filter(|p| std::path::Path::new(p).exists()) {
        match watcher.watch(std::path::Path::new(p), RecursiveMode::Recursive) {
            Ok(()) => watched.push(p.clone()),
            Err(e) => log::warn!("FIM: cannot watch {p}: {e}"),
        }
    }
    if watched.is_empty() {
        return Err("none of the FIM paths can be watched".into());
    }
    {
        let mut status = FIM_STATUS.lock().unwrap();
        status.watching = true;
        status.watched_paths = watched.clone();
        status.queued = 0;
        status.last_event_ts = None;
        status.last_error = None;
    }
    log::info!("FIM: FSEvents watching {}", watched.join(", "));
    tokio::spawn(async move {
        let _watcher = watcher; // dropping it ends the FSEvents stream
        let mut hashes: HashMap<String, String> = HashMap::new();
        loop {
            tokio::select! {
                Some(event) = rx.recv() => record(&event, &mut hashes),
                changed = stop_rx.changed() => if changed.is_err() || *stop_rx.borrow() { break },
                else => break,
            }
        }
        FIM_STATUS.lock().unwrap().watching = false;
    });
    Ok(())
}

#[cfg(target_os = "macos")]
fn record(event: &notify::Event, hashes: &mut HashMap<String, String>) {
    let Some(change) = change_type(&event.kind) else { return };
    for path in event.paths.iter().filter(|p| !p.is_dir()) {
        let key = path.to_string_lossy().into_owned();
        let after = if matches!(change, ChangeType::Delete | ChangeType::Permission) { None }
                    else { hash_file(path).ok().map(|(h, _, _)| h) };
        let before = match &after {
            Some(h) => hashes.insert(key.clone(), h.clone()),
            None if matches!(change, ChangeType::Delete) => hashes.remove(&key),
            None => hashes.get(&key).cloned(),
        };
        // A write that left the content as it was (touch, an editor's save of the same bytes) is no change.
        if matches!(change, ChangeType::Modify) && before.is_some() && before == after {
            continue;
        }
        let fim_event = FimEvent {
            path: key.clone(),
            change_type: change.clone(),
            hash_before: before,
            hash_after: after,
            process: ProcessInfo::default(),
            user: current_user(),
            ts: chrono::Utc::now().to_rfc3339(),
            source: "fim",
        };
        let mut status = FIM_STATUS.lock().unwrap();
        match enqueue_event(&fim_event) {
            Ok(()) => {
                status.queued += 1;
                status.last_event_ts = Some(fim_event.ts.clone());
            }
            Err(e) => {
                log::error!("Failed to enqueue FIM event for {key}: {e}");
                status.last_error = Some(format!("enqueue failed: {e}"));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use notify::event::{AccessKind, CreateKind, DataChange, MetadataKind, RemoveKind, RenameMode};

    #[test]
    fn fsevents_kinds_map_to_fim_changes_and_reads_are_ignored() {
        let kind = |k: EventKind| change_type(&k).map(|c| serde_json::to_string(&c).unwrap());
        assert_eq!(kind(EventKind::Create(CreateKind::File)).as_deref(), Some("\"create\""));
        assert_eq!(kind(EventKind::Remove(RemoveKind::File)).as_deref(), Some("\"delete\""));
        assert_eq!(kind(EventKind::Modify(ModifyKind::Data(DataChange::Content))).as_deref(), Some("\"modify\""));
        assert_eq!(kind(EventKind::Modify(ModifyKind::Name(RenameMode::Any))).as_deref(), Some("\"rename\""));
        assert_eq!(kind(EventKind::Modify(ModifyKind::Metadata(MetadataKind::Permissions))).as_deref(), Some("\"permission\""));
        assert_eq!(kind(EventKind::Access(AccessKind::Read)), None);
        assert_eq!(kind(EventKind::Any), None);
    }
}
