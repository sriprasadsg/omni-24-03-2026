use std::{fs, io};
use std::path::Path;

#[derive(Debug, Clone)]
pub struct ProcessInfo {
    pub pid: u32,
    pub name: String,
    pub ppid: Option<u32>,
}

/// Reads /proc/<pid>/comm or /proc/<pid>/cmdline to get the process name.
pub fn get_process_name(pid: u32) -> Option<String> {
    let comm_path = Path::new("/proc").join(pid.to_string()).join("comm");
    let cmdline_path = Path::new("/proc").join(pid.to_string()).join("cmdline");

    if comm_path.exists() {
        if let Ok(name) = fs::read_to_string(&comm_path) {
            let name = name.trim();
            if !name.is_empty() {
                return Some(name.to_string());
            }
        }
    }

    if cmdline_path.exists() {
        if let Ok(cmdline) = fs::read_to_string(&cmdline_path) {
            let cmdline_parts: Vec<&str> = cmdline.split('\0').filter(|s| !s.is_empty()).collect();
            if let Some(name) = cmdline_parts.first() {
                let name = name.trim();
                if !name.is_empty() {
                    return Some(name.to_string());
                }
            }
        }
    }
    None
}

/// Reads /proc/<pid>/status for PPid or /proc/<pid>/stat (field 4) to find the parent PID.
pub fn get_parent_pid(pid: u32) -> Option<u32> {
    let stat_path = Path::new("/proc").join(pid.to_string()).join("stat");
    if stat_path.exists() {
        if let Ok(stat_content) = fs::read_to_string(&stat_path) {
            let parts: Vec<&str> = stat_content.split_whitespace().collect();
            // PPID is the 4th field (index 3) in /proc/[pid]/stat
            if parts.len() > 3 {
                if let Ok(ppid) = parts[3].parse::<u32>() {
                    return Some(ppid);
                }
            }
        }
    }
    None
}

/// Recursively builds the full process hierarchy from the given PID up to the root (init process).
pub fn resolve_process_tree(pid: u32) -> Vec<ProcessInfo> {
    let mut tree = Vec::new();
    let mut current_pid = Some(pid);

    while let Some(pid) = current_pid {
        if pid == 0 { // Stop at PID 0 (kernel process) or if no parent is found for init
            break;
        }

        let name = get_process_name(pid).unwrap_or_else(|| format!("<unknown-process-{}>", pid));
        let ppid = get_parent_pid(pid);

        tree.push(ProcessInfo { pid, name, ppid });

        current_pid = ppid;
        if tree.len() > 100 { // Prevent infinite loops in case of /proc anomalies
            break;
        }
    }

    tree.reverse(); // Order from root to child
    tree
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_process_name_self() {
        let pid = std::process::id();
        let name = get_process_name(pid);
        assert!(name.is_some());
        // Exact process name might vary (e.g., "cargo", "main"), so check for substring
        let name_str = name.unwrap();
        println!("Self PID: {}, Name: {}", pid, name_str);
        assert!(!name_str.is_empty());
    }

    #[test]
    fn test_get_parent_pid_self() {
        let pid = std::process::id();
        let ppid = get_parent_pid(pid);
        assert!(ppid.is_some());
        println!("Self PID: {}, Parent PID: {:?}", pid, ppid.unwrap());
    }

    #[test]
    fn test_resolve_process_tree_self() {
        let pid = std::process::id();
        let tree = resolve_process_tree(pid);
        println!("Process tree for PID {}: {:?}", pid, tree);
        assert!(!tree.is_empty());
        assert_eq!(tree.last().unwrap().pid, pid); // Last element should be self
        assert!(tree.first().unwrap().pid <= 1); // First element should be init (pid 1) or systemd (pid 1)
    }

    #[test]
    fn test_resolve_process_tree_init() {
        let tree = resolve_process_tree(1); // PID 1 is typically init/systemd
        println!("Process tree for PID 1: {:?}", tree);
        assert!(!tree.is_empty());
        assert_eq!(tree.len(), 1); // Init process should be its own tree of 1
        assert_eq!(tree[0].pid, 1);
        assert!(tree[0].name == "systemd" || tree[0].name == "init");
    }

    #[test]
    fn test_non_existent_pid() {
        let non_existent_pid = 999999; // Hopefully this PID doesn't exist
        let name = get_process_name(non_existent_pid);
        assert!(name.is_none());

        let ppid = get_parent_pid(non_existent_pid);
        assert!(ppid.is_none());

        let tree = resolve_process_tree(non_existent_pid);
        assert!(tree.is_empty());
    }
}
