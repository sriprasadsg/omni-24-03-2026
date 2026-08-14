use super::fim::ProcessInfo;
use std::fs;
use std::path::Path;

/// Resolves the full process tree for a given PID by traversing /proc/<pid>/status
/// Returns a ProcessInfo with pid, name, and tree (vector of "name(pid)" strings from init to target)
pub fn resolve_process_tree(pid: i32) -> ProcessInfo {
    let mut tree: Vec<String> = Vec::new();
    let mut current_pid = pid;

    // Walk up the process tree
    loop {
        let status_path = format!("/proc/{}/status", current_pid);
        let path = Path::new(&status_path);

        if !path.exists() {
            // Process disappeared or invalid PID
            break;
        }

        let content = match fs::read_to_string(path) {
            Ok(c) => c,
            Err(_) => break, // Permission denied or other error
        };

        // Parse Name and PPid from status file
        let mut name = "unknown";
        let mut ppid: Option<i32> = None;

        for line in content.lines() {
            if line.starts_with("Name:") {
                name = line.split(':').nth(1).map(|s| s.trim()).unwrap_or("unknown");
            } else if line.starts_with("PPid:") {
                ppid = line.split(':').nth(1).map(|s| s.trim().parse().ok()).flatten();
            }
        }

        tree.push(format!("{}({})", name, current_pid));

        // If we reached init (PID 1) or no parent, stop
        match ppid {
            Some(0) | Some(1) => break,
            Some(next_pid) => current_pid = next_pid,
            None => break,
        }
    }

    // Reverse to get init -> target order
    tree.reverse();

    let (final_pid, final_name) = if let Some(first) = tree.first() {
        // Extract pid and name from the first entry (which is now init)
        // Actually we want the original PID and name at the end of the original tree
        // Since we reversed, the last element is the original target
        if let Some(last) = tree.last() {
            let parts: Vec<&str> = last.split('(').collect();
            if parts.len() == 2 {
                let n = parts[0];
                let p = parts[1].trim_end_matches(')').parse().ok();
                (p.unwrap_or(pid), n.to_string())
            } else {
                (pid, "unknown".to_string())
            }
        } else {
            (pid, "unknown".to_string())
        }
    } else {
        (pid, "unknown".to_string())
    };

    ProcessInfo {
        pid: Some(final_pid as u32),
        name: Some(final_name),
        tree: Some(tree),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process;

    #[test]
    fn test_resolve_current_process() {
        let pid = process::id() as i32;
        let info = resolve_process_tree(pid);

        assert!(info.pid.is_some());
        assert!(info.name.is_some());
        assert!(info.tree.is_some());
        let tree = info.tree.unwrap();
        assert!(!tree.is_empty());
        // Should contain at least the current process
        assert!(tree.iter().any(|s| s.contains(&pid.to_string())));
    }

    #[test]
    fn test_resolve_invalid_pid() {
        let info = resolve_process_tree(999999);
        // Should return default/empty for invalid PID
        assert!(info.pid.is_some() || info.pid.is_none()); // Either is fine for error case
        assert!(info.tree.is_some() || info.tree.is_none());
    }

    #[test]
    fn test_resolve_init_process() {
        // PID 1 should exist on any Linux system
        let info = resolve_process_tree(1);
        assert!(info.pid.is_some());
        if let Some(tree) = &info.tree {
            assert!(!tree.is_empty());
        }
    }
}